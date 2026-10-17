from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from homeassistant.core import State

from custom_components.pge_storage.history import select_sample
from custom_components.pge_storage.ledger import (
    LedgerError,
    Sample,
    Settlement,
    boundary,
    calculate,
    check_counter_progression,
    combine_counters,
    energy,
    validate_records,
)


def row(day, value, invoice=None, correction=None, note=""):
    return Settlement(
        str(uuid4()),
        day,
        Sample(str(value), (boundary(day) - timedelta(minutes=1)).isoformat()),
        invoice,
        correction,
        note,
    )


def test_example_periods_and_invoice_differences():
    records = [
        row("2025-03-15", "0", "0"),
        row("2025-09-15", "1000", "1000"),
        row("2026-03-15", "-950", "0"),
    ]
    result = calculate(records, "590")
    assert [r["period_balance"] for r in result["records"]] == [None, "1000", "-1950"]
    assert result["records"][-1]["estimated_before_invoice"] == "-950"
    assert result["records"][-1]["invoice_difference"] == "950"
    assert result["current"]["period_balance"] == "1540"
    assert result["current"]["estimated_balance"] == "1540"


def test_negative_source_and_deficit():
    result = calculate([row("2026-03-15", "-1000", "0")], "-1659.8")
    assert result["current"]["period_balance"] == "-659.8"
    assert result["current"]["estimated_balance"] == "-659.8"
    assert result["current"]["available_energy"] == "0"
    assert result["current"]["deficit"] == "659.8"


def test_unknown_opening_balance_not_assumed_zero():
    result = calculate([row("2025-03-15", "-100"), row("2025-09-15", "200")], "210")
    assert result["records"][1]["period_balance"] == "300"
    assert result["current"]["period_balance"] == "10"
    assert result["current"]["estimated_balance"] is None


def test_later_invoice_establishes_balance():
    result = calculate(
        [row("2025-03-15", "100"), row("2025-09-15", "300", "50")], "290"
    )
    assert result["records"][1]["invoice_difference"] is None
    assert result["current"]["estimated_balance"] == "40"


def test_invoice_shortfall_is_historical_and_not_subtracted_again():
    first = row("2025-01-01", "0", "0")
    settled = Settlement(
        str(uuid4()),
        "2025-07-01",
        Sample("-950", (boundary("2025-07-01") - timedelta(minutes=1)).isoformat()),
        "0",
        invoice_shortfall="950",
    )
    result = calculate([first, settled], "-850")
    assert result["records"][1]["invoice_shortfall"] == "950"
    assert result["current"]["estimated_balance"] == "100"
    assert result["current"]["deficit"] == "0"


def test_unapplied_correction_remains_explicit_when_opening_balance_unknown():
    result = calculate([row("2025-01-01", "0", correction="50")], "100")
    assert result["records"][0]["correction"] == "50"
    assert result["records"][0]["correction_applied"] is False
    assert result["current"]["estimated_balance"] is None


def test_correction_and_invoice_reset_propagate_separately():
    records = [
        row("2025-03-15", "0", "100"),
        row("2025-09-15", "200", correction="-25"),
        row("2026-03-15", "150"),
    ]
    result = calculate(records, "160")
    assert result["records"][1]["estimated_before_invoice"] == "300"
    assert result["records"][1]["carried_balance"] == "275"
    assert result["current"]["estimated_balance"] == "235"
    records[1] = row("2025-09-15", "200", "0")
    assert calculate(records, "160")["current"]["estimated_balance"] == "-40"
    assert (
        calculate([records[0], records[2]], "160")["current"]["estimated_balance"]
        == "260"
    )


def test_precision_no_second_opust_and_no_artificial_limit():
    start = datetime(2020, 1, 1, tzinfo=UTC)
    records = [
        row(
            (start + timedelta(days=i)).date().isoformat(),
            str(i / 10),
            "0" if i == 0 else None,
        )
        for i in range(500)
    ]
    result = calculate(records, "50.1")
    assert len(result["records"]) == 500
    assert result["current"]["estimated_balance"] == "50.1"
    assert energy("0.1") + energy("0.2") == energy("0.3")


@pytest.mark.parametrize(
    "value", ["unavailable", "unknown", "nan", "inf", "-inf", True, None, "1e9999"]
)
def test_nonfinite_or_nonnumeric_values_rejected(value):
    with pytest.raises(LedgerError):
        energy(value)


@pytest.mark.parametrize("value", [None, "unknown", "unavailable", "NaN"])
def test_bad_live_value_does_not_invent_balance(value):
    current = calculate([row("2025-01-01", "10", "15")], value)["current"]
    assert current["period_balance"] is None
    assert current["available_energy"] is None
    assert current["carried_balance"] == "15"


def test_warsaw_midnight_and_dst_lengths():
    assert boundary("2026-01-01").isoformat() == "2026-01-01T23:00:00+00:00"
    assert boundary("2026-07-01").isoformat() == "2026-07-01T22:00:00+00:00"
    assert boundary("2026-03-29") - boundary("2026-03-28") == timedelta(hours=23)
    assert boundary("2026-10-25") - boundary("2026-10-24") == timedelta(hours=25)


@pytest.mark.parametrize(
    "unit,raw", [("Wh", "1250000"), ("kWh", "1250"), ("MWh", "1.25")]
)
def test_separate_counters_convert_units_and_apply_opust_exactly_once(unit, raw):
    day = "2026-01-01"
    imported = select_sample(
        [
            State(
                "sensor.import",
                "900",
                {"unit_of_measurement": "kWh"},
                last_updated=boundary(day) - timedelta(seconds=2),
            )
        ],
        day,
        24,
    )
    exported = select_sample(
        [
            State(
                "sensor.victron_feed_in",
                raw,
                {"unit_of_measurement": unit},
                last_updated=boundary(day) - timedelta(seconds=1),
            )
        ],
        day,
        24,
    )
    sample = combine_counters(imported, exported)
    sample.validate(day)
    assert energy(sample.value) == energy("100")
    assert (
        sample.components["import"]["recorded_at"]
        != sample.components["export"]["recorded_at"]
    )


def test_counter_decrease_is_not_interpreted_as_energy_production():
    stamp = (boundary("2025-01-01") - timedelta(seconds=1)).isoformat()
    before = combine_counters(Sample("1000", stamp), Sample("2000", stamp))
    after = combine_counters(Sample("10", stamp), Sample("2100", stamp))
    with pytest.raises(LedgerError, match="zmalał"):
        check_counter_progression(before, after)
    with pytest.raises(LedgerError, match="nieujemne"):
        combine_counters(Sample("-1", stamp), Sample("2", stamp))


def test_import_rejects_balance_inconsistent_with_raw_counters():
    day = "2025-01-01"
    stamp = (boundary(day) - timedelta(seconds=1)).isoformat()
    sample = combine_counters(Sample("100", stamp), Sample("200", stamp))
    corrupted = Sample("9999", sample.recorded_at, sample.components)
    with pytest.raises(LedgerError, match="liczników"):
        corrupted.validate(day)


@pytest.mark.parametrize("day", ["2026-02-30", "20260101", "2026-W01-1", "oops", None])
def test_invalid_dates(day):
    with pytest.raises(LedgerError):
        boundary(day)


def test_real_samples_exclusive_boundary_and_no_interpolation():
    day = "2026-03-29"
    end = boundary(day)
    states = [
        State("sensor.source", "999", {"unit_of_measurement": "kWh"}, last_updated=end),
        State(
            "sensor.source",
            "-10.5",
            {"unit_of_measurement": "kWh"},
            last_updated=end - timedelta(seconds=1),
        ),
        State(
            "sensor.source",
            "500",
            {"unit_of_measurement": "kWh"},
            last_updated=end - timedelta(hours=25),
        ),
    ]
    sample = select_sample(states, day, 24)
    assert sample.value == "-10.5"
    assert sample.recorded_at == (end - timedelta(seconds=1)).isoformat()


def test_latest_unavailable_not_replaced_by_earlier_numeric_sample():
    end = boundary("2026-01-01")
    states = [
        State(
            "sensor.source",
            "100",
            {"unit_of_measurement": "kWh"},
            last_updated=end - timedelta(minutes=2),
        ),
        State(
            "sensor.source",
            "unavailable",
            {"unit_of_measurement": "kWh"},
            last_updated=end - timedelta(minutes=1),
        ),
    ]
    with pytest.raises(LedgerError, match="niedostępny"):
        select_sample(states, "2026-01-01", 24)


@pytest.mark.parametrize("unit", [None, "W", "kW", "%"])
def test_historical_unit_is_checked(unit):
    day = "2026-01-01"
    state = State(
        "sensor.source",
        "10",
        {"unit_of_measurement": unit},
        last_updated=boundary(day) - timedelta(minutes=1),
    )
    with pytest.raises(LedgerError, match="kWh"):
        select_sample([state], day, 24)


def test_missing_and_stale_history_rejected():
    day = "2026-01-01"
    old = State(
        "sensor.source",
        "10",
        {"unit_of_measurement": "kWh"},
        last_updated=boundary(day) - timedelta(hours=25),
    )
    with pytest.raises(LedgerError, match="Brak próbki"):
        select_sample([old], day, 24)


def test_import_validates_dates_duplicates_sample_and_conflicts():
    now = datetime(2026, 10, 17, tzinfo=UTC)
    first = row("2025-01-01", "1", "0").to_dict()
    assert validate_records([first], now)[0].to_dict() == first
    with pytest.raises(LedgerError, match="unikalne"):
        validate_records([first, first], now)
    with pytest.raises(LedgerError, match="zakończone"):
        validate_records([row("2027-01-01", "0").to_dict()], now)
    invalid = row("2025-01-01", "0", "0", "1").to_dict()
    with pytest.raises(LedgerError, match="oba naraz"):
        validate_records([invalid], now)
    invalid = {
        **first,
        "sample": {"value": "0", "recorded_at": boundary(first["day"]).isoformat()},
    }
    with pytest.raises(LedgerError, match="Próbka"):
        validate_records([invalid], now)
