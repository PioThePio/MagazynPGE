"""Available cumulative energy, with hourly history and recent five-minute sums."""

from datetime import UTC, datetime, timedelta
from functools import partial

from homeassistant.components.recorder import statistics
from homeassistant.helpers.recorder import get_instance

from .ledger import LedgerError, energy, energy_text


def available_total(points, begin, end):
    """Subtract observed sums; never demand history before the first observation."""
    first, last = int(begin.timestamp()), int(end.timestamp())
    valid = []
    for stamp, value in sorted(points.items()):
        if stamp > last:
            continue
        try:
            valid.append((stamp, energy(value)))
        except LedgerError, TypeError, ValueError:
            continue
    previous = [row for row in valid if row[0] <= first]
    inside = [row for row in valid if first < row[0] <= last]
    sequence = ([previous[-1]] if previous else []) + inside
    if not sequence or sequence[-1][0] < first:
        return None
    # A native statistics sum survives physical meter resets. A decrease in
    # the sum itself is a correction/discontinuity, not energy consumption.
    total = sum(
        (
            max(energy(0), b[1] - a[1])
            for a, b in zip(sequence, sequence[1:], strict=False)
        ),
        energy(0),
    )
    return {
        "value": energy_text(total),
        "start": datetime.fromtimestamp(max(first, sequence[0][0]), UTC).isoformat(),
        "end": datetime.fromtimestamp(sequence[-1][0], UTC).isoformat(),
        "partial": sequence[0][0] > first
        or sequence[-1][0] < last
        or any(b[1] < a[1] for a, b in zip(sequence, sequence[1:], strict=False)),
    }


def balanced_total(series, terms, begin, end):
    """Balance only observed sums sharing exactly the same time boundaries."""
    present = {key: points for key, points in series.items() if points}
    if not present:
        return None
    common = set.intersection(*(set(points) for points in present.values()))
    aligned = {
        key: {stamp: points[stamp] for stamp in common}
        for key, points in present.items()
    }
    totals = {
        key: available_total(points, begin, end) for key, points in aligned.items()
    }
    if any(row is None for row in totals.values()):
        return None
    result = sum(
        (energy(row["value"]) * terms[key] for key, row in totals.items()), energy(0)
    )
    if result < 0:
        return None
    return {
        "value": energy_text(result),
        "partial": len(present) < len(series)
        or any(row["partial"] for row in totals.values()),
    }


async def async_available_statistics(hass, ids, begin, end, hourly=None):
    """Read-only native statistics. Each endpoint represents the end of a bucket."""
    if not ids:
        return {}, {}
    recorder = get_instance(hass)
    if hourly is None:
        hourly = await recorder.async_add_executor_job(
            partial(
                statistics.statistics_during_period,
                hass,
                begin - timedelta(hours=1),
                end,
                ids,
                "hour",
                {"energy": "kWh"},
                {"sum"},
            )
        )
    # Recent data supplies today's counters without waiting for hourly rollup.
    short = await recorder.async_add_executor_job(
        partial(
            statistics.statistics_during_period,
            hass,
            max(begin - timedelta(minutes=5), end - timedelta(days=2)),
            end,
            ids,
            "5minute",
            {"energy": "kWh"},
            {"sum"},
        )
    )
    points = {
        stat: {int(row["start"]) + 3600: row.get("sum") for row in hourly.get(stat, [])}
        for stat in ids
    }
    for stat in ids:
        points[stat].update(
            {
                int(row["start"]) + 300: row["sum"]
                for row in short.get(stat, [])
                if row.get("sum") is not None
            }
        )
    totals = {stat: available_total(points[stat], begin, end) for stat in ids}
    return points, totals
