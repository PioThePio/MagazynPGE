from datetime import UTC, datetime, timedelta

from custom_components.pge_storage.energy_statistics import (
    available_total,
    balanced_total,
)


def test_year_counts_available_summer_history_without_january_baseline():
    begin, end = datetime(2026, 1, 1, tzinfo=UTC), datetime(2026, 10, 19, tzinfo=UTC)
    june = datetime(2026, 6, 1, tzinfo=UTC)
    points = {
        int((june + timedelta(hours=i)).timestamp()): str(value)
        for i, value in ((0, 10000), (1, 10010), (3, 10030))
    }
    result = available_total(points, begin, end)
    assert result["value"] == "30"
    assert result["start"] == june.isoformat()
    assert result["partial"] is True


def test_common_boundaries_prevent_charging_from_a_different_span_in_home_total():
    begin = datetime(2026, 10, 19, tzinfo=UTC)
    at = int(begin.timestamp())
    pv = {at: "100", at + 3600: "110", at + 7200: "130"}
    charge = {at + 3600: "20", at + 7200: "25"}
    result = balanced_total(
        {"pv": pv, "charge": charge},
        {"pv": 1, "charge": -1},
        begin,
        begin + timedelta(hours=2),
    )
    assert result["value"] == "15"
    assert result["partial"] is True


def test_counter_resets_use_native_sum_and_absent_history_remains_unknown():
    begin = datetime(2026, 10, 19, tzinfo=UTC)
    at = int(begin.timestamp())
    assert available_total({}, begin, begin + timedelta(hours=2)) is None
    assert (
        available_total(
            {at: "100", at + 300: "100.5", at + 600: "101.25"},
            begin,
            begin + timedelta(minutes=10),
        )["value"]
        == "1.25"
    )
