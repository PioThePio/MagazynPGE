"""Durable hourly evidence from native sums or bounded real counter states."""

from bisect import bisect_right
from datetime import UTC, datetime, timedelta
from functools import partial

from homeassistant.components.recorder import history, statistics
from homeassistant.helpers.recorder import get_instance

from .history import sample_from_state
from .hourly import hour_floor, make_hour
from .ledger import LedgerError, energy


def from_sums(rows, sources, start, end):
    positions = {
        direction: {
            int(row["start"]) + 3600: row.get("sum") for row in rows.get(source, [])
        }
        for direction, source in sources.items()
    }
    result, invalid = {}, set()
    cursor = start
    while cursor < end:
        stop = min(cursor + timedelta(hours=1), end)
        try:
            deltas = {
                direction: energy(points[int(stop.timestamp())])
                - energy(points[int(cursor.timestamp())])
                for direction, points in positions.items()
            }
            if min(deltas.values()) < 0:
                invalid.add(cursor.isoformat())
            else:
                result[cursor.isoformat()] = make_hour(
                    cursor, deltas["import"], deltas["export"]
                )
        except KeyError, LedgerError, TypeError, ValueError:
            pass
        cursor += timedelta(hours=1)
    return result, invalid


def from_states(rows, sources, start, end):
    series = {
        direction: sorted(rows.get(source, []), key=lambda row: row.last_updated)
        for direction, source in sources.items()
    }
    stamps = {
        direction: [row.last_updated.timestamp() for row in values]
        for direction, values in series.items()
    }
    result = {}
    cursor = start
    while cursor < end:
        stop = min(cursor + timedelta(hours=1), end)
        deltas = {}
        try:
            for direction, values in series.items():
                first = bisect_right(stamps[direction], cursor.timestamp()) - 1
                last = bisect_right(stamps[direction], stop.timestamp()) - 1
                if min(first, last) < 0:
                    raise ValueError
                # Exact boundary evidence only. Do not shift a boundary by
                # accepting an arbitrarily old value or discard any minutes.
                if (
                    values[first].last_updated != cursor
                    or values[last].last_updated != stop
                ):
                    raise ValueError
                selected = [
                    energy(sample_from_state(state).value)
                    for state in values[first : last + 1]
                ]
                if not selected or any(
                    b < a for a, b in zip(selected, selected[1:], strict=False)
                ):
                    raise ValueError
                deltas[direction] = selected[-1] - selected[0]
            result[cursor.isoformat()] = make_hour(
                cursor,
                deltas["import"],
                deltas["export"],
                "recorder_boundaries",
                end=stop,
            )
        except ValueError, LedgerError, KeyError, TypeError:
            pass
        cursor += timedelta(hours=1)
    return result


async def read_hours(hass, sources, start, now):
    recorder = get_instance(hass)
    end = hour_floor(now)
    metadata = await recorder.async_add_executor_job(
        partial(statistics.get_metadata, hass, statistic_ids=set(sources.values()))
    )
    supported = {
        source
        for source in sources.values()
        if source in metadata
        and metadata[source][1].get("has_sum")
        and metadata[source][1].get("unit_class") == "energy"
    }
    rows = (
        await recorder.async_add_executor_job(
            partial(
                statistics.statistics_during_period,
                hass,
                start - timedelta(hours=1),
                end,
                supported,
                "hour",
                {"energy": "kWh"},
                {"sum", "state"},
            )
        )
        if supported
        else {}
    )
    native, invalid = from_sums(rows, sources, start, end)
    # Recent Recorder states are a bounded fallback, never a daily-counter delta.
    raw_start = max(start, hour_floor(now - timedelta(days=recorder.keep_days)))
    fallback = {}
    # Read states only for missing recent hours, in bounded six-hour chunks.
    # Complete native coverage does not scan days of high-frequency states.
    cursor = raw_start
    while cursor < end:
        if cursor.isoformat() in native or cursor.isoformat() in invalid:
            cursor += timedelta(hours=1)
            continue
        first = cursor
        while (
            cursor < min(end, first + timedelta(hours=6))
            and cursor.isoformat() not in native
            and cursor.isoformat() not in invalid
        ):
            cursor += timedelta(hours=1)
        raw = await recorder.async_add_executor_job(
            partial(
                history.get_significant_states,
                hass,
                first - timedelta(microseconds=1),
                min(now, cursor + timedelta(microseconds=1)),
                list(sources.values()),
                include_start_time_state=True,
                significant_changes_only=False,
                minimal_response=False,
                no_attributes=False,
            )
        )
        recovered = await recorder.async_add_executor_job(
            partial(from_states, raw, sources, first, cursor)
        )
        fallback.update(recovered)
    candidates = {**fallback, **native}
    for key in invalid:
        candidates.pop(key, None)
    finalized = {
        key: row
        for key, row in candidates.items()
        if datetime.fromisoformat(row["end"]) <= now
    }
    pending = {
        key: row
        for key, row in candidates.items()
        if datetime.fromisoformat(row["end"]) > now
    }
    # Native five-minute sums give an explicitly provisional current-hour net.
    current_end = now.astimezone(UTC).replace(
        minute=now.minute // 5 * 5, second=0, microsecond=0
    )
    short = (
        await recorder.async_add_executor_job(
            partial(
                statistics.statistics_during_period,
                hass,
                end - timedelta(hours=1),
                now,
                supported,
                "5minute",
                {"energy": "kWh"},
                {"sum", "state"},
            )
        )
        if supported
        else {}
    )
    points = {
        direction: {
            int(row["start"]) + 300: row.get("sum") for row in short.get(source, [])
        }
        for direction, source in sources.items()
    }
    for direction, source in sources.items():
        points[direction].update(
            {
                int(row["start"]) + 3600: row.get("sum")
                for row in rows.get(source, [])
                if int(row["start"]) + 3600 not in points[direction]
            }
        )
    common = set.intersection(*(set(series) for series in points.values()))
    stops = sorted(
        stamp for stamp in common if end.timestamp() < stamp <= current_end.timestamp()
    )
    provisional = None
    if int(end.timestamp()) in common and stops:
        for stop in reversed(stops):
            try:
                deltas = {
                    direction: energy(series[stop])
                    - energy(series[int(end.timestamp())])
                    for direction, series in points.items()
                }
                provisional = make_hour(
                    end,
                    deltas["import"],
                    deltas["export"],
                    "native_five_minute_sum",
                    end=datetime.fromtimestamp(stop, UTC),
                )
                break
            except LedgerError:
                continue
    # Five-minute native sums can close the preceding hour before the hourly
    # rollup is visible. No minute of energy is discarded at either boundary.
    previous = end - timedelta(hours=1)
    if int(previous.timestamp()) in common and int(end.timestamp()) in common:
        try:
            deltas = {
                direction: energy(series[int(end.timestamp())])
                - energy(series[int(previous.timestamp())])
                for direction, series in points.items()
            }
            row = make_hour(
                previous, deltas["import"], deltas["export"], "native_short_term_sum"
            )
            if (
                previous.isoformat() not in invalid
                and previous.isoformat() not in candidates
            ):
                if end <= now:
                    finalized[previous.isoformat()] = row
                else:
                    pending[previous.isoformat()] = row
        except LedgerError:
            pass
    if provisional:
        pending[end.isoformat()] = provisional
    # Never manufacture a zero for an hour whose opening boundary is missing.
    current = {
        "start": end.isoformat(),
        "end": (end + timedelta(hours=1)).isoformat(),
        "provisional": True,
        "known": provisional is not None,
        "quality": "native_five_minute_sum"
        if provisional
        else "missing_hourly_history",
        "as_of": provisional["end"] if provisional else None,
        **{
            key: provisional[key] if provisional else None
            for key in (
                "raw_import_kwh",
                "raw_export_kwh",
                "import_kwh",
                "export_kwh",
                "credited_kwh",
                "net_kwh",
                "balance_kwh",
            )
        },
    }
    if current["balance_kwh"] is not None:
        current["balance_kwh"] = str(-energy(current["balance_kwh"]))
    live_context = None
    latest = max(
        (stamp for stamp in common if end.timestamp() <= stamp <= now.timestamp()),
        default=None,
    )
    if int(end.timestamp()) in common and latest is not None:
        states = {
            direction: {
                int(row["start"]) + 3600: row.get("state")
                for row in rows.get(source, [])
            }
            for direction, source in sources.items()
        }
        for direction, source in sources.items():
            states[direction].update(
                {
                    int(row["start"]) + 300: row.get("state")
                    for row in short.get(source, [])
                }
            )
        live_context = {
            "start": end.isoformat(),
            "positions": {
                direction: {
                    "opening_sum": points[direction].get(int(end.timestamp())),
                    "sum": points[direction].get(latest),
                    "state": states[direction].get(latest),
                    "end": datetime.fromtimestamp(latest, UTC).isoformat(),
                }
                for direction in sources
            },
        }
    details = {
        direction: {
            "entity_id": source,
            "unit": hass.states.get(source).attributes.get("unit_of_measurement")
            if hass.states.get(source)
            else None,
            "state_class": hass.states.get(source).attributes.get("state_class")
            if hass.states.get(source)
            else None,
            "native_sum_available": source in supported,
        }
        for direction, source in sources.items()
    }
    return {
        "live_context": live_context,
        "finalized": finalized,
        "pending": pending,
        "invalid": invalid,
        "current": current,
        "sources": details,
        "as_of": datetime.fromisoformat(provisional["end"]) if provisional else end,
        "finalized_through": hour_floor(now),
    }
