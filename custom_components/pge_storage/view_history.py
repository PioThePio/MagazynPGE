"""Bounded, read-only Recorder reconstruction for display power and BMS profile."""

from datetime import UTC, datetime, timedelta
from functools import partial
from types import SimpleNamespace

from homeassistant.components.recorder import history
from homeassistant.helpers.recorder import get_instance

from .battery import BatteryEstimate, battery_identity, value
from .energy import ROLES, energy_snapshot, source_ids


async def read_states(hass, ids, begin, end):
    if not ids:
        return {}
    return await get_instance(hass).async_add_executor_job(
        partial(
            history.get_significant_states,
            hass,
            begin,
            end,
            sorted(ids),
            include_start_time_state=True,
            significant_changes_only=False,
            minimal_response=False,
            no_attributes=False,
        )
    )


def frames_from_states(rows, config, core, begin, end):
    """Five-second reconstruction; recorded unavailable power is explicitly 0 W."""
    series = {
        key: sorted(items, key=lambda row: row.last_updated)
        for key, items in rows.items()
    }
    cursors = dict.fromkeys(series, 0)
    states = {}
    proxy = SimpleNamespace(states=SimpleNamespace(get=states.get))
    ids = power_ids(config)
    frames = []
    stamp = begin
    while stamp <= end:
        for entity, items in series.items():
            index = cursors[entity]
            while index < len(items) and items[index].last_updated <= stamp:
                states[entity] = items[index]
                index += 1
            cursors[entity] = index
        snapshot = energy_snapshot(proxy, config, core, {})
        known = {
            key: all(
                entity in states for entity in source_ids(config["sources"].get(key))
            )
            for key, (_label, unit) in ROLES.items()
            if unit == "W"
        }
        for kind in ("grid", "battery"):
            if config["sources"].get(f"{kind}_power"):
                for direction in (
                    ("import", "export") if kind == "grid" else ("charge", "discharge")
                ):
                    known[f"{kind}_{direction}_power"] = known[f"{kind}_power"]
        if snapshot["calculation"].get("home_power", {}).get("basis") == "balance":
            known["home_power"] = all(
                known.get(k, True)
                for k in (
                    "pv_power",
                    "grid_import_power",
                    "grid_export_power",
                    "battery_charge_power",
                    "battery_discharge_power",
                )
            )
        snapshot["power_history_known"] = known
        snapshot["consumer_history_known"] = {
            row.get("id")
            or row.get("statistic")
            or row.get("energy")
            or row.get("power"): not row.get("power") or row["power"] in states
            for row in snapshot["consumers"]
        }
        snapshot["pv_history_known"] = {
            row["id"]: not row.get("power_entity") or row["power_entity"] in states
            for row in snapshot["pv_arrays"]
        }
        frames.append((stamp.timestamp(), snapshot))
        stamp += timedelta(seconds=5)
    return (
        frames,
        {
            entity: [
                (
                    max(begin, state.last_updated).timestamp(),
                    float(
                        value(
                            SimpleNamespace(
                                states=SimpleNamespace(
                                    get=lambda _id, state=state: state
                                )
                            ),
                            entity,
                            {"W": 1, "kW": 1000},
                        )
                        or 0
                    ),
                )
                for state in items
            ]
            for entity, items in series.items()
            if entity in source_ids(config["sources"].get("pv_power"))
        },
        bool(ids - set(rows)),
    )


def power_ids(config):
    return {
        entity
        for role, selected in config["sources"].items()
        if ROLES[role][1] == "W"
        for entity in source_ids(selected)
    } | {row["power"] for row in config["consumers"] if row.get("power")}


async def restore_power_history(hass, config, core, now):
    begin = now - timedelta(seconds=1830)
    rows = await read_states(hass, power_ids(config), begin, now)
    return await get_instance(hass).async_add_executor_job(
        partial(frames_from_states, rows, config, core, begin, now)
    )


def learn_chunk(rows, config, begin, end, profile):
    """Use co-temporal recorded states, one eligible observation per minute."""
    opt = config["battery_forecast"]
    series = {
        key: sorted(items, key=lambda row: row.last_updated)
        for key, items in rows.items()
    }
    cursors = dict.fromkeys(series, 0)
    states = {}
    proxy = SimpleNamespace(states=SimpleNamespace(get=states.get))
    model = BatteryEstimate()
    model.restore(profile)
    stamp = begin.replace(second=0, microsecond=0)
    if stamp < begin:
        stamp += timedelta(minutes=1)
    covered = eligible = missing = 0
    while stamp < end:
        for entity, items in series.items():
            index = cursors[entity]
            while index < len(items) and items[index].last_updated <= stamp:
                states[entity] = items[index]
                index += 1
            cursors[entity] = index
        soc = value(proxy, config["sources"].get("battery_soc"), {"%": 1})
        current = value(proxy, opt["bms_current_entity"], {"A": 1})
        voltage = value(proxy, opt["voltage_entity"], {"V": 1})
        signed = config["sources"].get("battery_power")
        if signed:
            values = [
                value(proxy, entity, {"W": 1, "kW": 1000})
                for entity in source_ids(signed)
            ]
            charge = (
                sum(values) * (1 if config["directions"]["battery"] == "charge" else -1)
                if all(v is not None for v in values)
                else None
            )
        else:
            selected = source_ids(config["sources"].get("battery_charge_power"))
            values = [value(proxy, entity, {"W": 1, "kW": 1000}) for entity in selected]
            charge = (
                sum(values) if selected and all(v is not None for v in values) else None
            )
        if None in (soc, current, voltage, charge):
            missing += 1
        else:
            covered += 1
            eligible += int(
                model.observe(soc, charge, current * voltage, stamp.timestamp())
            )
        stamp += timedelta(minutes=1)
    return model.profile, {
        "covered_minutes": covered,
        "eligible_minutes": eligible,
        "missing_minutes": missing,
    }


async def restore_battery_profile(hass, config, now, profile, metadata, *, force=False):
    opt = config["battery_forecast"]
    required = (
        config["sources"].get("battery_soc"),
        opt["bms_current_entity"],
        opt["voltage_entity"],
    )
    if not opt["learn"] or not all(required):
        return profile, {
            **metadata,
            "status": "disabled" if not opt["learn"] else "missing_sources",
        }
    end = now.replace(second=0, microsecond=0)
    signature = battery_identity(config)
    same = metadata.get("identity") == signature and not force
    first = end - timedelta(days=7)
    resume = metadata.get("as_of") if same else None
    if isinstance(resume, (int, float)):
        first = max(first, datetime.fromtimestamp(resume, UTC))
    elif not force and metadata.get("status") == "complete":
        return profile, metadata
    learned = profile.copy() if same else {}
    totals = {
        k: metadata.get(k, 0) if same else 0
        for k in ("covered_minutes", "eligible_minutes", "missing_minutes")
    }
    ids = set(filter(None, required)) | set(
        source_ids(
            config["sources"].get("battery_power")
            or config["sources"].get("battery_charge_power")
        )
    )
    cursor = first
    while cursor < end:
        stop = min(end, cursor + timedelta(hours=6))
        rows = await read_states(hass, ids, cursor, stop)
        learned, counts = await get_instance(hass).async_add_executor_job(
            partial(learn_chunk, rows, config, cursor, stop, learned)
        )
        for key in totals:
            totals[key] += counts[key]
        cursor = stop
    # Cached observations remain useful after Recorder retention expires.
    if not force and not same:
        learned = {**profile, **learned}
    elif not learned and profile and not force:
        learned = profile.copy()
    return learned, {
        "identity": signature,
        "as_of": end.timestamp(),
        "from": metadata.get("from", first.isoformat()) if same else first.isoformat(),
        "status": "complete",
        **totals,
    }
