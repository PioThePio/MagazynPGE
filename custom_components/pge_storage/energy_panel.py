"""Read the native Energy preferences; never update its configuration or sources."""

from copy import deepcopy
from datetime import UTC, datetime, time, timedelta
from functools import partial

from homeassistant.components.energy.data import async_get_manager
from homeassistant.components.recorder import statistics
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.recorder import get_instance
from homeassistant.util import dt as dt_util

from .ledger import WARSAW, LedgerError, energy, energy_text


def panel_config(hass, prefs):
    """Copy all supported sources, including multiple PV arrays and external sums."""
    from .energy import source_status, validate_energy_config

    config = {
        "sources": {},
        "statistics": {},
        "presence": {},
        "consumers": [],
        "directions": {"grid": "import", "battery": "discharge"},
        "imported_from_energy": True,
    }
    warnings = []
    report = []
    current = None
    registry = er.async_get(hass)

    def usable(value):
        if (
            not isinstance(value, str)
            or not value
            or len(value) > 255
            or any(c.isspace() for c in value)
        ):
            return False
        entry = registry.async_get(value) if value.startswith("sensor.") else None
        return not (entry and entry.platform == "pge_storage")

    def add(role, value, statistic=False, origin=None):
        if not usable(value):
            return
        if statistic:
            ids = config["statistics"].setdefault(role, [])
            if value not in ids:
                ids.append(value)
        if value.startswith("sensor."):
            ids = config["sources"].setdefault(role, [])
            if value not in ids:
                ids.append(value)
        if current is not None:
            key = "soc" if role == "battery_soc" else "energy" if statistic else "power"
            detail = source_status(hass, value, role, statistic)
            if origin:
                detail["origin"] = origin
            current[key].append(detail)

    def power_source(source, kind, path):
        power = source.get("power_config", {})
        if power.get("stat_rate"):
            return power["stat_rate"], {"path": f"{path}.power_config.stat_rate"}
        if power:
            from homeassistant.components.energy.helpers import (
                generate_power_sensor_entity_id,
                generate_power_sensor_unique_id,
            )

            unique_id = generate_power_sensor_unique_id(kind, power)
            registered = registry.async_get_entity_id("sensor", "energy", unique_id)
            return registered or generate_power_sensor_entity_id(kind, power), {
                "path": f"{path}.power_config",
                "transform": "energy_helper",
                "inputs": dict(power),
                "resolved_by": "entity_registry"
                if registered
                else "generated_entity_id",
            }
        return source.get("stat_rate"), {"path": f"{path}.stat_rate"}

    entries = prefs.get("energy_sources", [])
    for kind in ("solar", "battery"):
        config["presence"][kind] = any(source.get("type") == kind for source in entries)
    for index, source in enumerate(entries):
        kind = source.get("type")
        path = f"energy_sources[{index}]"
        current = {
            "type": kind,
            "name": "",
            "energy": [],
            "power": [],
            "soc": [],
            "missing": [],
            "origin": {"path": path},
        }
        if kind == "solar":
            add(
                "pv_energy",
                source.get("stat_energy_from"),
                True,
                {"path": f"{path}.stat_energy_from"},
            )
            add(
                "pv_power",
                source.get("stat_rate"),
                origin={"path": f"{path}.stat_rate"},
            )
            if not current["power"]:
                current["missing"].append("pv_power")
                current["missing_power_origin"] = {"path": f"{path}.stat_rate"}
        elif kind == "battery":
            add(
                "battery_discharge_energy",
                source.get("stat_energy_from"),
                True,
                {"path": f"{path}.stat_energy_from"},
            )
            add(
                "battery_charge_energy",
                source.get("stat_energy_to"),
                True,
                {"path": f"{path}.stat_energy_to"},
            )
            # HA normalizes inverted/two-sensor configurations into stat_rate.
            power, origin = power_source(source, "battery", path)
            add(
                "battery_power",
                power,
                origin=origin,
            )
            if len([item for item in entries if item.get("type") == "battery"]) == 1:
                add(
                    "battery_soc",
                    source.get("stat_soc"),
                    origin={"path": f"{path}.stat_soc"},
                )
                if source.get("capacity") is not None:
                    config["battery_capacity_kwh"] = str(source["capacity"])
            elif source.get("stat_soc"):
                warnings.append(
                    "Przy kilku akumulatorach wybierz ręcznie encję łącznego poziomu naładowania."
                )
        elif kind == "grid":
            add(
                "grid_import_energy",
                source.get("stat_energy_from"),
                True,
                {"path": f"{path}.stat_energy_from"},
            )
            add(
                "grid_export_energy",
                source.get("stat_energy_to"),
                True,
                {"path": f"{path}.stat_energy_to"},
            )
            for item_index, item in enumerate(source.get("flow_from", [])):
                add(
                    "grid_import_energy",
                    item.get("stat_energy_from"),
                    True,
                    {"path": f"{path}.flow_from[{item_index}].stat_energy_from"},
                )
            for item_index, item in enumerate(source.get("flow_to", [])):
                add(
                    "grid_export_energy",
                    item.get("stat_energy_to"),
                    True,
                    {"path": f"{path}.flow_to[{item_index}].stat_energy_to"},
                )
            power, origin = power_source(source, "grid", path)
            add(
                "grid_power",
                power,
                origin=origin,
            )
            for item_index, item in enumerate(source.get("power", [])):
                power, origin = power_source(
                    item, "grid", f"{path}.power[{item_index}]"
                )
                add("grid_power", power, origin=origin)
        else:
            continue
        if kind == "battery" and not current["power"]:
            current["missing"].append("battery_power")
            current["missing_power_origin"] = origin
        if kind == "grid" and not current["power"]:
            current["missing"].append("grid_power")
            current["missing_power_origin"] = origin
        details = current["energy"] or current["power"] or current["soc"]
        current["name"] = source.get("name") or (
            details[0]["name"] if details else kind
        )
        report.append(current)
    current = None
    grid_entries = [source for source in entries if source.get("type") == "grid"]
    if grid_entries:
        config["presence"]["grid_export"] = bool(
            config["statistics"].get("grid_export_energy")
        )
    for item in prefs.get("device_consumption", []):
        stat, power = item.get("stat_consumption"), item.get("stat_rate")
        if not usable(stat) and not usable(power):
            continue
        if len(config["consumers"]) >= 16:
            warnings.append(
                "Panel Energia ma więcej niż 16 odbiorców; wczytano pierwszych 16."
            )
            break
        state = hass.states.get(stat) if stat and stat.startswith("sensor.") else None
        consumer = {
            "name": item.get("name")
            or (state.attributes.get("friendly_name") if state else None)
            or stat
            or power
        }
        if usable(stat):
            consumer["statistic"] = stat
            if stat.startswith("sensor."):
                consumer["energy"] = stat
        if usable(power) and power.startswith("sensor."):
            consumer["power"] = power
        config["consumers"].append(consumer)
    for role, ids in config["sources"].items():
        if len(ids) == 1:
            config["sources"][role] = ids[0]
    for item in report:
        for detail in [*item["energy"], *item["power"], *item["soc"]]:
            if detail["status"] in ("missing", "unknown", "unavailable", "invalid"):
                warnings.append(
                    f"{detail['id']}: brak poprawnego odczytu encji. "
                    + (
                        "Zachowano identyfikator statystyki z panelu Energia; historia może nadal istnieć."
                        if detail["statistic"]
                        else "Poziom naładowania pozostaje nieznany."
                        if detail["role"] == "battery_soc"
                        else "W bieżącym bilansie mocy ta encja wnosi 0 W."
                    )
                )
        if item["missing"]:
            warnings.append(
                f"{item['name']}: panel Energia nie ma pomiaru bieżącej mocy. "
                "Ta instalacja wnosi 0 W; pozostałe pomiary mocy są nadal sumowane."
            )
    if not config["presence"]["battery"]:
        warnings.append(
            "Panel Energia nie ma lokalnego akumulatora. Wybierz jego źródła ręcznie lub dodaj go w panelu Energia i wczytaj ponownie."
        )
    return {
        "config": validate_energy_config(config),
        "warnings": list(dict.fromkeys(warnings)),
        "report": report,
    }


async def async_panel_config(hass):
    manager = await async_get_manager(hass)
    if manager.data is None:
        raise LedgerError(
            "energy_not_configured",
            "Panel Energia nie ma zapisanych źródeł. Możesz wybrać je ręcznie.",
        )
    return panel_config(hass, manager.data)


def merge_panel_config(existing, imported):
    """One-time defaults: an existing manual selection wins, including directions."""
    existing, imported = deepcopy(existing), deepcopy(imported)
    result = {
        **imported,
        **existing,
        "imported_from_energy": True,
        "presence": {**imported["presence"], **existing["presence"]},
        "sources": {**imported["sources"], **existing["sources"]},
        "statistics": {**imported["statistics"], **existing["statistics"]},
    }
    for role in existing["sources"]:
        if role not in existing["statistics"]:
            result["statistics"].pop(role, None)
    if existing["sources"].get("grid_import_power") or existing["sources"].get(
        "grid_export_power"
    ):
        result["sources"].pop("grid_power", None)
    if existing["sources"].get("battery_charge_power") or existing["sources"].get(
        "battery_discharge_power"
    ):
        result["sources"].pop("battery_power", None)
    for kind in ("grid", "battery"):
        if not any(
            role.startswith(f"{kind}_") and role.endswith("power")
            for role in existing["sources"]
        ):
            result["directions"][kind] = imported["directions"][kind]
    if not existing["consumers"]:
        result["consumers"] = imported["consumers"]
    if existing.get("battery_capacity_kwh") is None:
        result["battery_capacity_kwh"] = imported.get("battery_capacity_kwh")
    return result


async def async_statistics_today(hass, config):
    """Use sums, not cumulative states: handle resets and external statistics."""
    now = dt_util.utcnow()
    midnight = datetime.combine(
        now.astimezone(WARSAW).date(), time(), WARSAW
    ).astimezone(UTC)
    end = now.replace(minute=0, second=0, microsecond=0)
    ids = {stat for values in config["statistics"].values() for stat in values}
    ids |= {item["statistic"] for item in config["consumers"] if item.get("statistic")}
    if not ids:
        return {
            "day": now.astimezone(WARSAW).date().isoformat(),
            "as_of": None,
            "values": {},
        }
    rows = await get_instance(hass).async_add_executor_job(
        partial(
            statistics.statistics_during_period,
            hass,
            midnight - timedelta(hours=1),
            end,
            ids,
            "hour",
            {"energy": "kWh"},
            {"sum"},
        )
    )
    values = {}
    for stat in ids:
        points = {int(item["start"]): item.get("sum") for item in rows.get(stat, [])}
        try:
            sequence = [
                energy(points[stamp])
                for stamp in range(
                    int(midnight.timestamp()) - 3600, int(end.timestamp()), 3600
                )
            ]
            if any(b < a for a, b in zip(sequence, sequence[1:], strict=False)):
                raise ValueError
            values[stat] = energy_text(sequence[-1] - sequence[0])
        except KeyError, TypeError, ValueError, LedgerError:
            values[stat] = None
    return {
        "day": now.astimezone(WARSAW).date().isoformat(),
        "as_of": end.isoformat(),
        "values": values,
    }
