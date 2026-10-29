"""Durable counter outage evidence and conservative, non-hourly recovery events."""

from copy import deepcopy
from datetime import UTC, datetime, timedelta

from .history import sample_from_state
from .hourly import hour_floor, settlement_flows
from .ledger import WARSAW, LedgerError, energy, energy_text

FIELDS = (
    "raw_import_kwh",
    "raw_export_kwh",
    "import_kwh",
    "export_kwh",
    "credited_kwh",
    "net_kwh",
)
MAX_SILENCE = timedelta(seconds=90)


def moment(value):
    result = datetime.fromisoformat(value)
    if result.tzinfo is None:
        raise ValueError
    return result.astimezone(UTC)


def point(at, values):
    return {
        "at": at.isoformat(),
        **{k: energy_text(energy(values[k])) for k in ("import", "export")},
    }


def empty(sources):
    return {
        "version": 1,
        "sources": dict(sources),
        "last": None,
        "unavailable": False,
        "gaps": [],
        "boundaries": {},
        "blocks": [],
    }


def observe(cache, hass, now):
    """Only a fresh pair is eligible; counter totals may stay unchanged."""
    if cache.get("error"):
        return
    try:
        states = {k: hass.states.get(v) for k, v in cache["sources"].items()}
        values = {k: energy(sample_from_state(s).value) for k, s in states.items()}
        if any(
            s.attributes.get("restored") or now - s.last_reported > MAX_SILENCE
            for s in states.values()
        ):
            raise ValueError
    except LedgerError, ValueError, AttributeError, TypeError:
        cache["unavailable"] = True
        return
    current = point(now, values)
    previous = cache["last"]
    if previous and now <= moment(previous["at"]):
        return
    if (
        previous
        and now - moment(previous["at"]) < timedelta(seconds=15)
        and all(values[k] == energy(previous[k]) for k in values)
    ):
        cache["unavailable"] = False
        return
    if previous and any(values[k] < energy(previous[k]) for k in values):
        # Never convert a reset into a negative or zero recovery. Native sums
        # may later repair the hours; preserve an explicit audit error.
        cache["unavailable"] = True
        cache["error"] = "Licznik spadł; automatyczne uzupełnienie zatrzymane."
        return
    if previous and (
        cache["unavailable"] or now - moment(previous["at"]) > MAX_SILENCE
    ):
        cache["gaps"].append({"before": deepcopy(previous), "after": current})
    cache["last"] = current
    cache["unavailable"] = False


def _delta(a, b):
    values = {k: energy(b[k]) - energy(a[k]) for k in ("import", "export")}
    if min(values.values()) < 0:
        raise ValueError
    return values


def _event(start, stop, a, b, estimated):
    delta = _delta(a, b)
    if estimated:
        p, e = delta["import"], delta["export"]
        flows = {
            "raw_import_kwh": energy_text(p),
            "raw_export_kwh": energy_text(e),
            "import_kwh": energy_text(p),
            "export_kwh": energy_text(e),
            "credited_kwh": energy_text(e * energy("0.8")),
            "net_kwh": energy_text(e * energy("0.8") - p),
        }
    else:
        flows = settlement_flows(delta["import"], delta["export"])
    # Attribute the unknown interval once, at return. Known edge fragments
    # belong to their own day, including a fragment ending at midnight.
    at = stop - timedelta(microseconds=1)
    return {
        "start": at.isoformat(),
        "end": at.isoformat(),
        "observed_start": start.isoformat(),
        "observed_end": stop.isoformat(),
        "basis": "outage_estimate" if estimated else "observed_hour_fragment",
        **flows,
    }


def reconcile(cache, boundaries, hours, now, proven=()):
    """Rebuild overlays, not additive corrections. Persistence is caller-owned."""
    cache = deepcopy(cache)
    cache["boundaries"].update(boundaries)
    groups = []
    for gap in cache["gaps"]:
        start, stop = moment(gap["before"]["at"]), moment(gap["after"]["at"])
        first = hour_floor(start)
        last = hour_floor(stop)
        if last < stop:
            last += timedelta(hours=1)
        if groups and first < groups[-1]["end"]:
            groups[-1]["end"] = max(last, groups[-1]["end"])
            groups[-1]["gaps"].append(gap)
        else:
            groups.append({"start": first, "end": last, "gaps": [gap]})
    old_replaced = {
        b["start"] for b in cache["blocks"] if b.get("status") == "replaced"
    }
    blocks = []
    needed = (
        {hour_floor(moment(cache["last"]["at"])).isoformat()}
        if cache["last"]
        else set()
    )
    for group in groups:
        start, end = group["start"], group["end"]
        block = {
            "start": start.isoformat(),
            "end": end.isoformat(),
            "status": "pending",
            "events": [],
            "gap_count": len(group["gaps"]),
            "gap_rows": [
                _event(
                    moment(g["before"]["at"]),
                    moment(g["after"]["at"]),
                    g["before"],
                    g["after"],
                    True,
                )
                for g in group["gaps"]
            ],
            "timing_uncertain": any(
                moment(g["before"]["at"]).astimezone(WARSAW).date()
                != moment(g["after"]["at"]).astimezone(WARSAW).date()
                for g in group["gaps"]
            ),
        }
        needed.update(k for k in cache["boundaries"] if start <= moment(k) <= end)
        needed.update((start.isoformat(), end.isoformat()))
        if end > now:
            blocks.append(block)
            continue
        points = {
            moment(k): v
            for k, v in cache["boundaries"].items()
            if start <= moment(k) <= end
        }
        # Native sums created after a delayed report cannot prove the missing
        # timeline. Do not split the unknown part at their artificial buckets.
        for gap in group["gaps"]:
            a, b = moment(gap["before"]["at"]), moment(gap["after"]["at"])
            points = {t: v for t, v in points.items() if not a < t < b}
            points[a], points[b] = gap["before"], gap["after"]
        if start not in points or end not in points:
            blocks.append(block)
            continue
        try:
            stamps = sorted(points)
            for a, b in zip(stamps, stamps[1:], strict=False):
                is_gap = any(
                    moment(g["before"]["at"]) <= a and b <= moment(g["after"]["at"])
                    for g in group["gaps"]
                )
                if not is_gap and hour_floor(a) != hour_floor(
                    b - timedelta(microseconds=1)
                ):
                    raise ValueError
                block["events"].append(_event(a, b, points[a], points[b], is_gap))
            block.update(
                {
                    key: energy_text(
                        sum((energy(e[key]) for e in block["events"]), energy(0))
                    )
                    for key in FIELDS
                }
            )
            block["status"] = "estimated"
            keys = [
                (start + timedelta(hours=i)).isoformat()
                for i in range(int((end - start).total_seconds() // 3600))
            ]
            exact = all(
                k in hours
                and (k in proven or start.isoformat() in old_replaced or len(keys) == 1)
                for k in keys
            )
            matches = exact and all(
                sum((energy(hours[k][field]) for k in keys), energy(0))
                == energy(block[field])
                for field in ("raw_import_kwh", "raw_export_kwh")
            )
            if matches:
                block["status"] = "replaced"
        except ValueError, LedgerError:
            block["events"] = []
            block["error"] = (
                "Niepełne granice lub reset licznika; uzupełnienie oczekuje na dane."
            )
        blocks.append(block)
    cache["blocks"] = blocks
    cutoff = now - timedelta(days=2)
    cache["boundaries"] = {
        k: v
        for k, v in cache["boundaries"].items()
        if moment(k) >= cutoff or k in needed
    }
    return cache


def validate(raw, sources, now, hours=None):
    if raw is None:
        return empty(sources)
    try:
        if (
            raw["version"] != 1
            or raw["sources"] != sources
            or not isinstance(raw["unavailable"], bool)
        ):
            raise ValueError
        result = empty(sources)

        def check(p):
            at = moment(p["at"])
            if at > now or any(energy(p[k]) < 0 for k in ("import", "export")):
                raise ValueError
            return point(at, p)

        result["last"] = check(raw["last"]) if raw["last"] else None
        result["unavailable"] = raw["unavailable"]
        if isinstance(raw.get("error"), str):
            result["error"] = raw["error"][:255]
        if len(raw["gaps"]) > 20000 or len(raw["boundaries"]) > 100000:
            raise ValueError
        previous = None
        for gap in raw["gaps"]:
            a, b = check(gap["before"]), check(gap["after"])
            if moment(a["at"]) >= moment(b["at"]) or (
                previous and moment(a["at"]) < previous
            ):
                raise ValueError
            _delta(a, b)
            result["gaps"].append({"before": a, "after": b})
            previous = moment(b["at"])
        result["boundaries"] = {
            k: {
                name: value
                for name, value in check({**v, "at": k}).items()
                if name != "at"
            }
            for k, v in raw["boundaries"].items()
            if moment(k) == hour_floor(moment(k))
        }
        if len(result["boundaries"]) != len(raw["boundaries"]):
            raise ValueError
        # Blocks are derived financial data, never trust imported totals/events.
        rebuilt = reconcile(result, {}, {}, now)
        if hours is not None:
            receipts = {
                b["start"]
                for b in raw.get("blocks", [])
                if b.get("status") == "replaced"
            }
            proven = set()
            for block in rebuilt["blocks"]:
                if block["start"] in receipts:
                    a, b = moment(block["start"]), moment(block["end"])
                    proven.update(
                        (a + timedelta(hours=i)).isoformat()
                        for i in range(int((b - a).total_seconds() // 3600))
                    )
            rebuilt = reconcile(rebuilt, {}, hours, now, proven)
        return rebuilt
    except (KeyError, ValueError, TypeError, AttributeError, LedgerError) as err:
        raise LedgerError(
            "invalid_recovery",
            "Nieprawidłowy zapis uzupełnień po przerwach lub inna para liczników.",
        ) from err


async def proven_hours(hass, sources, cache, hours):
    """Require actual boundary states before replacing an outage approximation.

    Merely receiving a jump in a later statistics bucket is not historical proof.
    """
    from functools import partial

    from homeassistant.components.recorder import history
    from homeassistant.helpers.recorder import get_instance

    from .hourly_history import from_states

    proven = set()
    recorder = get_instance(hass)
    for block in cache["blocks"]:
        if block["status"] != "estimated":
            continue
        start, end = moment(block["start"]), moment(block["end"])
        keys = [
            (start + timedelta(hours=i)).isoformat()
            for i in range(int((end - start).total_seconds() // 3600))
        ]
        if not all(k in hours for k in keys):
            continue
        if not all(
            sum((energy(hours[k][f]) for k in keys), energy(0)) == energy(block[f])
            for f in ("raw_import_kwh", "raw_export_kwh")
        ):
            continue
        cursor, found = start, set()
        while cursor < end:
            stop = min(end, cursor + timedelta(hours=6))
            rows = await recorder.async_add_executor_job(
                partial(
                    history.get_significant_states,
                    hass,
                    cursor - timedelta(microseconds=1),
                    stop + timedelta(microseconds=1),
                    list(sources.values()),
                    include_start_time_state=True,
                    significant_changes_only=False,
                    minimal_response=False,
                    no_attributes=False,
                )
            )
            observed = await recorder.async_add_executor_job(
                partial(from_states, rows, sources, cursor, stop)
            )
            if len(observed) != int((stop - cursor).total_seconds() // 3600) or any(
                any(
                    energy(observed[k][f]) != energy(hours[k][f])
                    for f in ("raw_import_kwh", "raw_export_kwh")
                )
                for k in observed
            ):
                break
            found.update(observed)
            cursor = stop
        if cursor == end:
            proven.update(found)
    return proven
