from copy import deepcopy
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from homeassistant.core import State

from custom_components.pge_storage.hourly import HourBook, make_hour, replay
from custom_components.pge_storage.ledger import WARSAW, LedgerError
from custom_components.pge_storage.planning import validate_plan
from custom_components.pge_storage.recovery import (
    empty,
    observe,
    point,
    reconcile,
    validate,
)
from tests.test_hourly import anchor

SOURCES = {"import": "sensor.i", "export": "sensor.e"}


def example(start=None):
    start = start or datetime(2026, 10, 1, 8, tzinfo=UTC)
    end = start + timedelta(hours=7)
    cache = empty(SOURCES)
    before = point(start + timedelta(minutes=30), {"import": "1000", "export": "500"})
    after = point(end - timedelta(minutes=10), {"import": "1010", "export": "505"})
    cache["last"] = after
    cache["gaps"] = [{"before": before, "after": after}]
    boundaries = {
        start.isoformat(): {"import": "1000", "export": "500"},
        end.isoformat(): {"import": "1010", "export": "505"},
    }
    return cache, boundaries, start, end


def test_0830_to_1450_is_one_minus_six_correction_not_hourly_distribution():
    cache, boundaries, start, end = example()
    pending = reconcile(cache, boundaries, {}, end - timedelta(minutes=10))
    assert pending["blocks"][0]["status"] == "pending"
    assert (
        HourBook(recoveries=pending["blocks"]).interval(start, end)["complete"] is False
    )
    restored = reconcile(cache, boundaries, {}, end)
    block = restored["blocks"][0]
    assert block["status"] == "estimated"
    assert block["raw_import_kwh"] == "10" and block["raw_export_kwh"] == "5"
    assert block["net_kwh"] == "-6"
    gaps = [r for r in block["events"] if r["basis"] == "outage_estimate"]
    assert len(gaps) == 1 and gaps[0]["net_kwh"] == "-6"
    book = HourBook(recoveries=restored["blocks"])
    assert book.interval(start, end)["net_kwh"] == "-6"
    assert book.interval(start, end)["estimated"] is True
    assert reconcile(restored, boundaries, {}, end) == restored
    reloaded = validate(restored, SOURCES, end)
    assert (
        HourBook(recoveries=reloaded["blocks"]).interval(start, end)["net_kwh"] == "-6"
    )


def test_known_edge_fragments_and_native_jump_are_never_counted_twice():
    cache, boundaries, start, end = example()
    boundaries[start.isoformat()] = {"import": "999", "export": "497"}
    boundaries[end.isoformat()] = {"import": "1013", "export": "506"}
    native = {
        row["start"]: row
        for row in [make_hour(start, 1, 3), make_hour(end - timedelta(hours=1), 13, 6)]
    }
    result = reconcile(cache, boundaries, native, end)
    block = result["blocks"][0]
    # prefix +1.6, outage -6, suffix -2. These replace overlapping native rows.
    assert block["net_kwh"] == "-6.4"
    assert (
        HourBook(native, recoveries=result["blocks"]).interval(start, end)["net_kwh"]
        == "-6.4"
    )
    assert (
        HourBook(native, recoveries=result["blocks"]).interval(start, end)[
            "raw_import_kwh"
        ]
        == "14"
    )


def test_recovered_real_hour_boundaries_replace_estimate_without_adding_it():
    cache, boundaries, start, end = example()
    estimates = reconcile(cache, boundaries, {}, end)
    rows = [make_hour(start + timedelta(hours=i), 0, 0) for i in range(7)]
    rows[1] = make_hour(start + timedelta(hours=1), 10, 5)
    hours = {r["start"]: r for r in rows}
    assert reconcile(estimates, {}, hours, end)["blocks"][0]["status"] == "estimated"
    repaired = reconcile(estimates, {}, hours, end, set(hours))
    assert repaired["blocks"][0]["status"] == "replaced"
    book = HourBook(hours, recoveries=repaired["blocks"])
    assert book.interval(start, end)["net_kwh"] == "-5"
    assert book.interval(start, end)["estimated"] is False
    assert reconcile(repaired, {}, hours, end)["blocks"][0]["status"] == "replaced"
    reloaded = validate(repaired, SOURCES, end, hours)
    assert reloaded["blocks"][0]["status"] == "replaced"
    assert (
        HourBook(hours, recoveries=reloaded["blocks"]).interval(start, end)["net_kwh"]
        == "-5"
    )


def test_fresh_pair_after_restart_or_unavailability_and_decreasing_counter():
    now = datetime(2026, 10, 1, 8, 30, tzinfo=UTC)
    states = {}
    hass = SimpleNamespace(states=SimpleNamespace(get=states.get))

    def set_pair(p, e, at):
        for k, v in (("import", p), ("export", e)):
            states[SOURCES[k]] = State(
                SOURCES[k], str(v), {"unit_of_measurement": "kWh"}, last_reported=at
            )

    set_pair(1000, 500, now)
    cache = empty(SOURCES)
    observe(cache, hass, now)
    durable = deepcopy(cache)
    later = now + timedelta(hours=6, minutes=20)
    set_pair(1010, 505, later)
    # One direction is still missing: do not accept a half-recovered pair.
    states[SOURCES["export"]] = State(SOURCES["export"], "unavailable")
    observe(durable, hass, later)
    assert durable["last"] == cache["last"] and not durable["gaps"]
    set_pair(1010, 505, later)
    observe(durable, hass, later)
    assert len(durable["gaps"]) == 1
    observe(durable, hass, later + timedelta(seconds=1))
    assert len(durable["gaps"]) == 1
    set_pair(1, 505, later + timedelta(seconds=2))
    observe(durable, hass, later + timedelta(seconds=2))
    assert durable["error"] and durable["last"]["import"] == "1010"


def test_return_day_attribution_fifo_expiry_and_stock_floor():
    start = datetime(2026, 10, 1, 23, tzinfo=WARSAW).astimezone(UTC)
    cache, boundaries, start, end = example(start)
    result = reconcile(cache, boundaries, {}, end)
    book = HourBook(recoveries=result["blocks"])
    midnight = (start.astimezone(WARSAW) + timedelta(hours=1)).astimezone(UTC)
    assert book.interval(start, midnight)["net_kwh"] == "0"
    assert book.interval(midnight, end)["net_kwh"] == "-6"
    record = anchor("2026-09-30", "3")
    beginning = datetime(2026, 10, 1, tzinfo=WARSAW).astimezone(UTC)
    rows = {
        r["start"]: r
        for r in [make_hour(beginning + timedelta(hours=i), 0, 0) for i in range(23)]
    }
    book = HourBook(rows, recoveries=result["blocks"])
    state = replay(book, [record], validate_plan({}), end)
    assert state["balance"] == -3
    # Insufficient stock becomes a deficit, not a negative available stock.
    from custom_components.pge_storage.hourly import accounting_snapshot

    snapshot = accounting_snapshot(book, [record], validate_plan({}), end)
    assert snapshot["current"]["available_energy"] == "0"
    assert snapshot["current"]["deficit"] == "3"


def test_import_rejects_other_sources_negative_or_overlapping_gaps():
    cache, boundaries, start, end = example()
    cache = reconcile(cache, boundaries, {}, end)
    with pytest.raises(LedgerError):
        validate(cache, {"import": "sensor.other", "export": "sensor.e"}, end)
    damaged = deepcopy(cache)
    damaged["gaps"].append(damaged["gaps"][0])
    with pytest.raises(LedgerError):
        validate(damaged, SOURCES, end)
    damaged = deepcopy(cache)
    damaged["blocks"][0]["net_kwh"] = "999999"
    # Derived totals are recomputed from counter evidence on import.
    assert validate(damaged, SOURCES, end)["blocks"][0]["net_kwh"] == "-6"


def test_same_hour_outage_can_use_exact_hour_totals_without_guessing_minutes():
    cache, boundaries, start, _end = example()
    end = start + timedelta(hours=1)
    cache["gaps"][0]["after"]["at"] = (start + timedelta(minutes=50)).isoformat()
    cache["last"] = cache["gaps"][0]["after"]
    boundaries = {
        start.isoformat(): {"import": "1000", "export": "500"},
        end.isoformat(): {"import": "1010", "export": "505"},
    }
    row = make_hour(start, 10, 5)
    result = reconcile(cache, boundaries, {row["start"]: row}, end)
    assert result["blocks"][0]["status"] == "replaced"
    assert (
        HourBook({row["start"]: row}, recoveries=result["blocks"]).interval(start, end)[
            "net_kwh"
        ]
        == "-5"
    )


def test_month_boundary_fifo_expires_old_energy_and_credits_return_month():
    start = datetime(2026, 10, 31, 23, tzinfo=WARSAW).astimezone(UTC)
    cache, boundaries, start, end = example(start)
    result = reconcile(cache, boundaries, {}, end)
    # Unknown import/export is accounted on return in November. October's
    # expiring stock cannot be silently used for an unobserved earlier hour.
    record = anchor("2026-10-30", "3")
    plan = validate_plan(
        {
            "anchor_id": record.id,
            "lots": [
                {"month": "2025-10", "export_kwh": "3.75", "expires_on": "2026-10-31"}
            ],
        }
    )
    beginning = datetime(2026, 10, 31, tzinfo=WARSAW).astimezone(UTC)
    rows = {
        r["start"]: r
        for r in [make_hour(beginning + timedelta(hours=i), 0, 0) for i in range(23)]
    }
    book = HourBook(rows, recoveries=result["blocks"])
    from custom_components.pge_storage.hourly import accounting_snapshot

    snapshot = accounting_snapshot(book, [record], plan, end)
    assert snapshot["current"]["recovery_estimated"] is True
    assert snapshot["current"]["deficit"] == "6"
    assert result["blocks"][0]["timing_uncertain"] is True


@pytest.mark.parametrize("day", ["2026-03-29", "2026-10-25"])
def test_recovery_has_one_identity_across_daylight_saving_transition(day):
    start = datetime.fromisoformat(day).replace(tzinfo=WARSAW).astimezone(UTC)
    cache, boundaries, start, end = example(start)
    result = reconcile(cache, boundaries, {}, end)
    assert len(result["blocks"]) == 1
    assert HourBook(recoveries=result["blocks"]).interval(start, end)["net_kwh"] == "-6"
    assert validate(result, SOURCES, end)["blocks"] == result["blocks"]


def test_gap_crossing_an_invoice_does_not_recount_already_invoiced_energy():
    start = datetime(2026, 10, 31, 23, tzinfo=WARSAW).astimezone(UTC)
    cache, boundaries, start, end = example(start)
    result = reconcile(cache, boundaries, {}, end)
    record = anchor("2026-10-31", "100")
    with pytest.raises(LedgerError, match="faktury"):
        replay(HourBook(recoveries=result["blocks"]), [record], validate_plan({}), end)
    # A later authoritative invoice clears older uncertainty.
    from custom_components.pge_storage.ledger import boundary

    later = anchor("2026-11-01", "100")
    assert (
        replay(
            HourBook(recoveries=result["blocks"]),
            [record, later],
            validate_plan({}),
            boundary(later.day),
        )["balance"]
        == 100
    )


def test_adjacent_new_outage_does_not_retract_a_closed_recovery():
    cache, boundaries, start, end = example()
    previous = reconcile(cache, boundaries, {}, end)
    before = point(end + timedelta(minutes=15), {"import": "1010", "export": "505"})
    after = point(end + timedelta(minutes=50), {"import": "1012", "export": "505"})
    previous["gaps"].append({"before": before, "after": after})
    previous["last"] = after
    result = reconcile(previous, {}, {}, end + timedelta(minutes=50))
    assert [b["status"] for b in result["blocks"]] == ["estimated", "pending"]
    assert HourBook(recoveries=result["blocks"]).interval(start, end)["net_kwh"] == "-6"


def test_quiet_export_counter_is_valid_and_does_not_create_a_false_outage():
    now = datetime(2026, 10, 1, 8, tzinfo=UTC)
    old_report = now - timedelta(days=1)
    states = {
        entity: State(
            entity, value, {"unit_of_measurement": "kWh"}, last_reported=old_report
        )
        for entity, value in [(SOURCES["import"], "1000"), (SOURCES["export"], "500")]
    }
    hass = SimpleNamespace(states=SimpleNamespace(get=states.get))
    cache = empty(SOURCES)
    observe(cache, hass, now)
    observe(cache, hass, now + timedelta(seconds=30))
    assert cache["last"]["at"] == (now + timedelta(seconds=30)).isoformat()
    assert cache["unavailable"] is False and not cache["gaps"]
    # HA itself was then off for two hours; export may still correctly retain
    # the same valid numeric value while import advances.
    later = now + timedelta(hours=2)
    states[SOURCES["import"]] = State(
        SOURCES["import"], "1010", {"unit_of_measurement": "kWh"}, last_reported=later
    )
    observe(cache, hass, later)
    assert len(cache["gaps"]) == 1
    assert cache["gaps"][0]["after"]["export"] == "500"
