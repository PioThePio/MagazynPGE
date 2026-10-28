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


def test_independent_counter_ranges_preserve_all_available_energy():
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
    assert result["value"] == "25"
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


def test_sparse_pv_never_discards_night_grid_consumption_and_missing_is_unknown():
    begin = datetime(2026, 10, 28, tzinfo=UTC)
    at = int(begin.timestamp())
    end = begin + timedelta(days=1)
    grid = {at + h * 3600: str(100 + h) for h in range(25)}
    pv = {at - 7 * 3600: "50", at + 8 * 3600: "50.2", at + 16 * 3600: "52.47"}
    result = balanced_total({"pv": pv, "grid": grid}, {"pv": 1, "grid": 1}, begin, end)
    assert result["value"] == "26.47"
    assert result["partial"] is True
    assert result["sources"]["grid"]["value"] == "24"
    stale_baseline = available_total(
        {at - 7 * 3600: "50", at + 24 * 3600: "52.47"}, begin, end
    )
    assert stale_baseline["partial"] is True
    assert stale_baseline["baseline_at"] == (begin - timedelta(hours=7)).isoformat()
    assert (
        balanced_total({"pv": {}, "grid": grid}, {"pv": 1, "grid": 1}, begin, end)
        is None
    )


def test_sources_need_no_identical_report_timestamps():
    begin = datetime(2026, 10, 28, tzinfo=UTC)
    at = int(begin.timestamp())
    result = balanced_total(
        {"grid": {at: "100", at + 3600: "110"}, "pv": {at - 60: "20", at + 3540: "22"}},
        {"grid": 1, "pv": 1},
        begin,
        begin + timedelta(hours=1),
    )
    assert result["value"] == "12"
    assert result["partial"] is True
