from datetime import UTC, datetime, timedelta

import pytest

from custom_components.pge_storage.ledger import LedgerError
from custom_components.pge_storage.period import (
    pending_statistics_hour,
    period_bounds,
    sum_delta,
)


@pytest.mark.parametrize(
    ("kind", "anchor", "start", "end", "hours"),
    [
        ("day", "2026-03-29", "2026-03-29", "2026-03-30", 23),
        ("day", "2026-10-25", "2026-10-25", "2026-10-26", 25),
        ("week", "2026-10-25", "2026-10-19", "2026-10-26", 169),
        ("month", "2026-10-12", "2026-10-01", "2026-11-01", 745),
        ("year", "2024-02-29", "2024-01-01", "2025-01-01", 8784),
    ],
)
def test_calendar_bounds_use_warsaw_and_real_dst_hours(kind, anchor, start, end, hours):
    bounds = period_bounds(kind, anchor, datetime(2027, 1, 1, tzinfo=UTC))
    assert bounds.start.isoformat() == start
    assert bounds.stop.isoformat() == end
    assert (bounds.end - bounds.begin).total_seconds() / 3600 == hours
    assert not bounds.is_current


def test_current_period_uses_five_minute_boundary_and_rejects_future():
    now = datetime(2026, 10, 19, 11, 47, tzinfo=UTC)
    current = period_bounds("month", "2026-10-01", now)
    assert current.as_of == now.replace(minute=45)
    assert current.is_current
    for kind, anchor in [("day", "2026-10-20"), ("month", "2026-11-01"), ("no", "bad")]:
        with pytest.raises(LedgerError):
            period_bounds(kind, anchor, now)


def test_statistic_difference_needs_coverage_and_accepts_meter_resets():
    start = datetime(2026, 10, 1, tzinfo=UTC)
    rows = {
        int((start + timedelta(hours=i)).timestamp()): str(100 + i * 2)
        for i in range(-1, 3)
    }
    assert sum_delta(rows, start, start + timedelta(hours=3)) == "6"
    del rows[int((start + timedelta(hours=1)).timestamp())]
    assert sum_delta(rows, start, start + timedelta(hours=3)) is None


def test_current_statistics_allow_only_the_pending_trailing_hour():
    start = datetime(2026, 10, 19, tzinfo=UTC)
    points = {
        int((start + timedelta(hours=i)).timestamp()): str(100 + i)
        for i in range(-1, 3)
    }
    end = start + timedelta(hours=4)
    assert sum_delta(points, start, end) is None
    assert pending_statistics_hour({"pv": points}, end)
    assert sum_delta(points, start, end - timedelta(hours=1)) == "3"
    del points[int((start + timedelta(hours=1)).timestamp())]
    assert sum_delta(points, start, end - timedelta(hours=1)) is None
