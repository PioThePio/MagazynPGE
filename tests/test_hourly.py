from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from homeassistant.core import State

from custom_components.pge_storage.hourly import (
    FINALIZATION_DELAY,
    HourBook,
    accounting_snapshot,
    hour_floor,
    make_hour,
    replay,
    settlement_flows,
    validate_archive,
)
from custom_components.pge_storage.hourly_history import from_states, from_sums
from custom_components.pge_storage.ledger import (
    WARSAW,
    LedgerError,
    Sample,
    Settlement,
    boundary,
    combine_counters,
)
from custom_components.pge_storage.planning import validate_plan


def anchor(day="2026-09-30", balance="10"):
    stamp = (boundary(day) - timedelta(seconds=1)).isoformat()
    return Settlement(
        str(uuid4()),
        day,
        combine_counters(Sample("1000", stamp), Sample("1000", stamp)),
        balance,
    )


def book_rows(start, pairs):
    rows = [
        make_hour(start + timedelta(hours=i), p, e) for i, (p, e) in enumerate(pairs)
    ]
    return HourBook({row["start"]: row for row in rows})


@pytest.mark.parametrize(
    ("p", "e", "consumed", "surplus", "credit", "delta"),
    [
        (1, 1, "0", "0", "0", "0"),
        (1, 3, "0", "2", "1.6", "1.6"),
        (3, 1, "2", "0", "0", "-2"),
        (0, 1, "0", "1", "0.8", "0.8"),
    ],
)
def test_user_hourly_examples(p, e, consumed, surplus, credit, delta):
    result = settlement_flows(p, e)
    assert [
        result[k] for k in ("import_kwh", "export_kwh", "credited_kwh", "net_kwh")
    ] == [consumed, surplus, credit, delta]


def test_distinct_hours_do_not_cancel_like_a_day_and_expose_uncovered_import():
    row = anchor(balance="0")
    start = boundary(row.day)
    book = book_rows(start, [(0, 1), (1, 0)])
    summary = book.interval(start, start + timedelta(hours=2))
    assert summary["net_kwh"] == "-0.2"
    state = replay(book, [row], validate_plan({}), start + timedelta(hours=2))
    assert state["balance"] == Decimal("-0.2")
    assert state["withdrawn_kwh"] == "0.8" and state["uncovered_kwh"] == "0.2"
    assert (
        book_rows(start, [(1, 1)]).interval(start, start + timedelta(hours=1))[
            "net_kwh"
        ]
        == "0"
    )


def test_missing_hour_is_unknown_and_later_invoice_reanchors_without_guessing():
    first = anchor()
    start = boundary(first.day)
    book = book_rows(start, [(0, 1)])
    summary = book.interval(start, start + timedelta(hours=2))
    assert summary["net_kwh"] is None and summary["missing_count"] == 1
    assert (
        accounting_snapshot(
            book, [first], validate_plan({}), start + timedelta(hours=2)
        )["current"]["available_energy"]
        is None
    )
    later = anchor("2026-10-01", "50")
    state = accounting_snapshot(
        book, [first, later], validate_plan({}), boundary(later.day)
    )
    assert state["current"]["available_energy"] == "50"
    assert state["records"][1]["estimated_before_invoice"] is None


@pytest.mark.parametrize(("day", "count"), [("2026-03-29", 23), ("2026-10-25", 25)])
def test_dst_uses_distinct_utc_hours_and_warsaw_calendar(day, count):
    end = boundary(day)
    start = datetime.combine(
        datetime.fromisoformat(day).date(), datetime.min.time(), WARSAW
    ).astimezone(UTC)
    book = book_rows(start, [(1, 1)] * count)
    assert (end - start).total_seconds() == count * 3600
    assert book.interval(start, end)["known_hours"] == count
    assert book.interval(start, end)["net_kwh"] == "0"
    assert len(book.hours) == count
    if count == 25:
        repeated = [
            datetime.fromisoformat(key).astimezone(WARSAW)
            for key in book.hours
            if datetime.fromisoformat(key).astimezone(WARSAW).hour == 2
        ]
        assert len(repeated) == 2 and repeated[0].utcoffset() != repeated[1].utcoffset()


def test_expiry_is_applied_before_next_day_withdrawal_and_fifo_is_oldest_month():
    row = anchor("2026-05-31", "100")
    plan = validate_plan(
        {
            "anchor_id": row.id,
            "lots": [
                {"month": "2025-05", "export_kwh": "125", "expires_on": "2026-05-31"}
            ],
        }
    )
    start = boundary(row.day)
    state = replay(book_rows(start, [(1, 0)]), [row], plan, start + timedelta(hours=1))
    assert state["balance"] == Decimal(-1)
    assert state["inventory"].expired == 100
    summary = accounting_snapshot(
        book_rows(start, [(1, 0)]), [row], plan, start + timedelta(hours=1)
    )
    assert summary["current"]["period_balance"] == "-101"
    assert summary["current"]["net_flow_since_settlement_kwh"] == "-1"
    assert summary["current"]["expired_since_settlement_kwh"] == "100"
    assert state["withdrawn_kwh"] == "0" and state["uncovered_kwh"] == "1"


def test_hour_credit_uses_month_of_start_not_next_midnight_and_twelve_months():
    row = anchor("2026-01-30", "0")
    plan = validate_plan({"anchor_id": row.id, "lots": []})
    start = boundary(row.day)
    state = replay(
        book_rows(start, [(0, 0)] * 23 + [(0, 10)]),
        [row],
        plan,
        start + timedelta(hours=24),
    )
    assert state["inventory"].serialize() == [
        {"month": "2026-01", "expires_on": "2027-01-31", "kwh": "8"}
    ]


def test_archive_validation_rejects_tampering_wrong_pair_future_and_early_finalization():
    start = datetime(2026, 10, 1, tzinfo=UTC)
    row = make_hour(start, 1, 3)
    sources = {"import": "sensor.i", "export": "sensor.e"}
    cache = {
        "model": "clock_hour_net_0.8_v1",
        "sources": sources,
        "hours": {row["start"]: row},
    }
    assert (
        validate_archive(
            cache, sources, start + timedelta(hours=1) + FINALIZATION_DELAY
        )
        == cache
    )
    with pytest.raises(LedgerError):
        validate_archive(cache, sources, start + timedelta(minutes=59))
    with pytest.raises(LedgerError):
        validate_archive(
            cache,
            {"import": "sensor.other", "export": "sensor.e"},
            start + timedelta(days=1),
        )
    row["credited_kwh"] = "999"
    with pytest.raises(LedgerError):
        validate_archive(cache, sources, start + timedelta(days=1))


def test_native_sum_handles_physical_counter_reset_and_rejects_sum_decrease():
    start = datetime(2026, 10, 1, tzinfo=UTC)
    sources = {"import": "sensor.i", "export": "sensor.e"}
    rows = {
        "sensor.i": [
            {"start": (start - timedelta(hours=1)).timestamp(), "sum": 100},
            {"start": start.timestamp(), "sum": 103},
        ],
        "sensor.e": [
            {"start": (start - timedelta(hours=1)).timestamp(), "sum": 20},
            {"start": start.timestamp(), "sum": 21},
        ],
    }
    known, invalid = from_sums(rows, sources, start, start + timedelta(hours=1))
    assert known[start.isoformat()]["import_kwh"] == "2" and not invalid
    rows["sensor.i"][1]["sum"] = 2
    known, invalid = from_sums(rows, sources, start, start + timedelta(hours=1))
    assert not known and start.isoformat() in invalid


def test_raw_hour_boundaries_detect_inside_hour_reset_and_never_erase_ten_minutes():
    start = datetime(2026, 10, 1, tzinfo=UTC)
    sources = {"import": "sensor.i", "export": "sensor.e"}

    def state(entity, value, offset):
        return State(
            entity,
            str(value),
            {"unit_of_measurement": "Wh"},
            last_updated=start + timedelta(minutes=offset),
        )

    rows = {
        "sensor.i": [
            state("sensor.i", 1000, 0),
            state("sensor.i", 1500, 4),
            state("sensor.i", 2000, 56),
            state("sensor.i", 3000, 60),
        ],
        "sensor.e": [state("sensor.e", 1000, 0), state("sensor.e", 2000, 60)],
    }
    result = from_states(rows, sources, start, start + timedelta(hours=1))
    assert result[start.isoformat()]["raw_import_kwh"] == "2"
    assert result[start.isoformat()]["import_kwh"] == "1"
    rows["sensor.i"].insert(2, state("sensor.i", 0, 30))
    assert not from_states(rows, sources, start, start + timedelta(hours=1))
    rows["sensor.i"][2] = state("sensor.i", "unavailable", 30)
    assert not from_states(rows, sources, start, start + timedelta(hours=1))


def test_hour_floor_does_not_use_rolling_sixty_minutes():
    at = datetime(2026, 10, 26, 13, 37, 42, tzinfo=WARSAW)
    assert hour_floor(at).astimezone(WARSAW).hour == 13
    assert hour_floor(at).minute == 0
