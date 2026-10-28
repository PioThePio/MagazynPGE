"""Optional energy dashboard sources. Read entities without changing them."""

from dataclasses import asdict
from datetime import timedelta

from homeassistant.util import dt as dt_util

from .battery import capacity_reading
from .battery import options as battery_options
from .history import async_read_samples, sample_from_state
from .ledger import WARSAW, LedgerError, Sample, energy, energy_text

ROLES = {
    "grid_import_energy": ("Pobór z sieci", "kWh"),
    "grid_export_energy": ("Oddawanie do sieci", "kWh"),
    "grid_power": ("Moc sieci ze znakiem", "W"),
    "battery_power": ("Moc akumulatora ze znakiem", "W"),
    "pv_power": ("Produkcja PV", "W"),
    "home_power": ("Zużycie domu", "W"),
    "grid_import_power": ("Pobór z sieci", "W"),
    "grid_export_power": ("Oddawanie do sieci", "W"),
    "battery_charge_power": ("Ładowanie akumulatora", "W"),
    "battery_discharge_power": ("Rozładowanie akumulatora", "W"),
    "battery_soc": ("Poziom akumulatora", "%"),
    "battery_stored": ("Energia w akumulatorze", "kWh"),
    "pv_energy": ("Produkcja PV", "kWh"),
    "home_energy": ("Zużycie domu", "kWh"),
    "battery_charge_energy": ("Ładowanie akumulatora", "kWh"),
    "battery_discharge_energy": ("Rozładowanie akumulatora", "kWh"),
}


def validate_energy_config(raw):
    try:
        if not isinstance(raw, dict) or set(raw) - {
            "sources",
            "consumers",
            "directions",
            "statistics",
            "presence",
            "imported_from_energy",
            "battery_capacity_kwh",
            "battery_capacity_ah",
            "battery_voltage",
            "flow_clock_source",
            "flow_mode",
            "show_hour",
            "pv_order",
            "battery_forecast",
            "battery_capacity_entity",
            "battery_installed_capacity_entity",
            "pv_names",
            "consumer_sync",
        }:
            raise ValueError
        sources, consumers = raw.get("sources", {}), raw.get("consumers", [])
        if (
            not isinstance(sources, dict)
            or set(sources) - ROLES.keys()
            or not isinstance(consumers, list)
            or len(consumers) > 16
        ):
            raise ValueError

        def entity(value):
            if (
                not isinstance(value, str)
                or not value.startswith("sensor.")
                or len(value) > 255
                or any(c.isspace() for c in value)
            ):
                raise ValueError
            return value

        sources = {
            key: (
                [entity(v) for v in value] if isinstance(value, list) else entity(value)
            )
            for key, value in sources.items()
            if value
        }
        for key, value in sources.items():
            if isinstance(value, list) and (
                len(value) > 32
                or len(value) != len(set(value))
                or key in ("battery_soc", "battery_stored")
            ):
                raise ValueError
        stat_roles = {
            key
            for key, (_name, unit) in ROLES.items()
            if unit == "kWh" and key != "battery_stored"
        }
        statistics = raw.get("statistics", {})
        if not isinstance(statistics, dict) or set(statistics) - stat_roles:
            raise ValueError

        def statistic(value):
            if (
                not isinstance(value, str)
                or not value
                or len(value) > 255
                or any(c.isspace() for c in value)
            ):
                raise ValueError
            return value

        for key, ids in statistics.items():
            if (
                not isinstance(ids, list)
                or not ids
                or len(ids) > 32
                or len(ids) != len(set(ids))
            ):
                raise ValueError
            statistics[key] = [statistic(value) for value in ids]
        presence = raw.get("presence", {})
        if (
            not isinstance(presence, dict)
            or set(presence) - {"solar", "battery", "grid_export"}
            or any(type(v) is not bool for v in presence.values())
        ):
            raise ValueError
        imported = raw.get("imported_from_energy", False)
        if type(imported) is not bool:
            raise ValueError
        capacities = {}
        for key in ("battery_capacity_kwh", "battery_capacity_ah", "battery_voltage"):
            value = raw.get(key)
            if value is not None:
                value = energy_text(energy(value))
                if energy(value) <= 0:
                    raise ValueError
            capacities[key] = value
        items = []
        for item in consumers:
            if not isinstance(item, dict) or set(item) - {
                "name",
                "power",
                "energy",
                "statistic",
                "id",
                "parent_id",
            }:
                raise ValueError
            name = item.get("name", "").strip()
            if (
                not name
                or len(name) > 80
                or not (
                    item.get("power") or item.get("energy") or item.get("statistic")
                )
            ):
                raise ValueError
            items.append(
                {
                    "id": statistic(consumer_id(item)),
                    "name": name,
                    **(
                        {
                            "parent_id": statistic(item["parent_id"])
                            if item["parent_id"]
                            else None
                        }
                        if "parent_id" in item
                        else {}
                    ),
                    **(
                        {"statistic": statistic(item["statistic"])}
                        if item.get("statistic")
                        else {}
                    ),
                    **{
                        key: entity(item[key])
                        for key in ("power", "energy")
                        if item.get(key)
                    },
                }
            )
        by_id = {item["id"]: item for item in items}
        if len(by_id) != len(items):
            raise LedgerError(
                "invalid_energy", "Każdy odbiorca musi mieć inny identyfikator."
            )
        for item in items:
            seen = {item["id"]}
            parent = item.get("parent_id")
            while parent:
                if parent not in by_id:
                    raise LedgerError(
                        "invalid_energy", "Wybierz istniejącego odbiorcę nadrzędnego."
                    )
                if parent in seen:
                    raise LedgerError(
                        "invalid_energy", "Powiązania odbiorców nie mogą tworzyć pętli."
                    )
                seen.add(parent)
                parent = by_id[parent].get("parent_id")
        directions = raw.get("directions", {})
        if not isinstance(directions, dict) or set(directions) - {"grid", "battery"}:
            raise ValueError
        directions = {
            "grid": directions.get("grid", "import"),
            "battery": directions.get("battery", "charge"),
        }
        if directions["grid"] not in ("import", "export") or directions[
            "battery"
        ] not in ("charge", "discharge"):
            raise ValueError
        if sources.get("grid_power") and any(
            sources.get(key) for key in ("grid_import_power", "grid_export_power")
        ):
            raise ValueError
        if sources.get("battery_power") and any(
            sources.get(key)
            for key in ("battery_charge_power", "battery_discharge_power")
        ):
            raise ValueError
        flow_clock = raw.get("flow_clock_source") or None
        if flow_clock is not None and (
            entity(flow_clock) not in source_ids(sources.get("pv_power"))
        ):
            raise ValueError
        capacity_entities = {
            k: entity(raw[k]) if raw.get(k) else None
            for k in ("battery_capacity_entity", "battery_installed_capacity_entity")
        }
        names = raw.get("pv_names", {})
        sync = raw.get("consumer_sync", {})
        if (
            not isinstance(names, dict)
            or len(names) > 64
            or not isinstance(sync, dict)
            or set(sync) - {"known", "ignored"}
        ):
            raise ValueError
        names = {str(k): str(v).strip() for k, v in names.items() if str(v).strip()}
        if any(len(k) > 255 or len(v) > 80 for k, v in names.items()):
            raise ValueError
        sync = {key: list(sync.get(key, [])) for key in ("known", "ignored")}
        if any(
            len(ids) > 256 or any(not isinstance(i, str) or len(i) > 255 for i in ids)
            for ids in sync.values()
        ):
            raise ValueError
        flow_mode = raw.get("flow_mode", "aligned")
        order = raw.get("pv_order", [])
        if (
            flow_mode not in ("aligned", "latest")
            or not isinstance(raw.get("show_hour", True), bool)
            or not isinstance(order, list)
            or len(order) > 32
            or len(set(order)) != len(order)
        ):
            raise ValueError
        order = [statistic(v) for v in order]
        return {
            **capacity_entities,
            "pv_names": names,
            "consumer_sync": sync,
            "flow_mode": flow_mode,
            "show_hour": raw.get("show_hour", True),
            "pv_order": order,
            "battery_forecast": battery_options(raw.get("battery_forecast")),
            "flow_clock_source": flow_clock,
            "sources": sources,
            "consumers": items,
            "directions": directions,
            "statistics": statistics,
            "presence": presence,
            "imported_from_energy": imported,
            **capacities,
        }
    except (TypeError, ValueError, AttributeError) as err:
        raise LedgerError(
            "invalid_energy", "Wybierz sensory i nazwy odbiorców (maks. 16)."
        ) from err


def source_ids(value):
    return value if isinstance(value, list) else [value] if value else []


def consumer_id(item):
    """Stable across ordering and names; imported IDs match native statistics."""
    return (
        item.get("id")
        or item.get("statistic")
        or item.get("energy")
        or item.get("power")
    )


def energy_sources(config):
    ids = {
        entity_id
        for value in config["sources"].values()
        for entity_id in source_ids(value)
    }
    ids |= {
        config[k]
        for k in ("battery_capacity_entity", "battery_installed_capacity_entity")
        if config.get(k)
    }
    ids |= {
        v
        for k, v in config.get("battery_forecast", {}).items()
        if k.endswith("_entity") and v
    }
    ids |= {
        value
        for item in config["consumers"]
        for key, value in item.items()
        if key in ("power", "energy")
    }
    ids |= {
        stat
        for values in config.get("statistics", {}).values()
        for stat in values
        if stat.startswith("sensor.")
    }
    ids |= {
        item["statistic"]
        for item in config["consumers"]
        if item.get("statistic", "").startswith("sensor.")
    }
    return ids


def aggregate(values):
    return (
        energy_text(sum((energy(v) for v in values), energy(0)))
        if values and all(v is not None for v in values)
        else None
    )


def consumer_summary(consumers, home_power_w, home_kwh, energy_key="today_kwh"):
    """Count a metered ancestor once, falling back to children per metric."""
    by_id = {consumer_id(item): item for item in consumers}
    parents = {item.get("parent_id") for item in consumers if item.get("parent_id")}
    for item in consumers:
        item["id"] = consumer_id(item)
        item["parent_id"] = item.get("parent_id")
        item["has_children"] = item["id"] in parents
        for metric, field in (("power", "power"), ("energy", "energy")):
            configured = bool(
                item.get(field) or (metric == "energy" and item.get("statistic"))
            )
            parent = item.get("parent_id")
            visited = {item["id"]}
            while parent and parent in by_id and parent not in visited:
                visited.add(parent)
                ancestor = by_id[parent]
                if ancestor.get(field) or (
                    metric == "energy" and ancestor.get("statistic")
                ):
                    configured = False
                    break
                parent = ancestor.get("parent_id")
            item[f"counted_{metric}"] = configured

    def tracked(metric, field):
        selected = [item.get(field) for item in consumers if item[f"counted_{metric}"]]
        return aggregate([value for value in selected if value is not None]) or "0"

    power, kwh = tracked("power", "power_w"), tracked("energy", energy_key)

    def remainder(total, measured):
        return (
            energy_text(energy(total) - energy(measured))
            if total is not None and measured is not None
            else None
        )

    untracked_power, untracked_kwh = (
        remainder(home_power_w, power),
        remainder(home_kwh, kwh),
    )
    return {
        "home_power_w": home_power_w,
        "home_kwh": home_kwh,
        "tracked_power_w": power,
        "tracked_kwh": kwh,
        "untracked_power_w": untracked_power,
        "untracked_kwh": untracked_kwh,
        "overcount_power": untracked_power is not None and energy(untracked_power) < 0,
        "overcount_energy": untracked_kwh is not None and energy(untracked_kwh) < 0,
    }


def battery_capacity(config, hass=None):
    return capacity_reading(hass, config)


def pv_arrays(hass, config, native=None):
    """Expose per-array live readings without reading outside selected sources."""
    powers = source_ids(config["sources"].get("pv_power"))
    statistics = config.get("statistics", {}).get("pv_energy") or source_ids(
        config["sources"].get("pv_energy")
    )
    rows = []
    native_config = native.get("config", {}) if native else {}
    if (
        native
        and set(powers)
        == set(source_ids(native_config.get("sources", {}).get("pv_power")))
        and set(statistics)
        == set(native_config.get("statistics", {}).get("pv_energy", []))
    ):
        for item in native.get("report", []):
            if item["type"] != "solar":
                continue
            stat = next((source["id"] for source in item["energy"]), None)
            power = next((source["id"] for source in item["power"]), None)
            rows.append(
                {
                    "id": stat or power or item["origin"]["path"],
                    "name": item["name"],
                    "power_w": source_reading(hass, power, "W"),
                    "energy_statistic": stat,
                    "power_entity": power,
                }
            )
        for row in rows:
            row["name"] = (
                config.get("pv_names", {}).get(row.get("power_entity"))
                or config.get("pv_names", {}).get(row["id"])
                or row["name"]
            )
        return rows
    for index in range(len(powers) or len(statistics)):
        power = powers[index] if powers else None
        # Manual power and energy lists are independent. Do not invent which
        # counter belongs to a power sensor merely from their array positions.
        stat = statistics[index] if not powers else None
        entity_id = stat or power
        state = hass.states.get(entity_id) if entity_id else None
        rows.append(
            {
                "id": entity_id,
                "name": state.attributes.get("friendly_name", entity_id)
                if state
                else entity_id,
                "power_w": source_reading(hass, power, "W"),
                "energy_statistic": stat,
                "power_entity": power,
                "energy_statistics": statistics
                if len(powers) == 1
                else [stat]
                if stat
                else [],
            }
        )
    for row in rows:
        row["name"] = (
            config.get("pv_names", {}).get(row.get("power_entity"))
            or config.get("pv_names", {}).get(row["id"])
            or row["name"]
        )
    return rows


def source_reading(hass, ids, unit, signed=False):
    values = [reading(hass, value, unit, signed) for value in source_ids(ids)]
    # Live power is a sum of available readings, with each absent input set to
    # zero. Counter/history readings retain their strict completeness rules.
    if unit == "W":
        return energy_text(sum((energy(value or "0") for value in values), energy(0)))
    return aggregate(values)


def reading(hass, entity_id, unit, signed=False):
    state = hass.states.get(entity_id) if entity_id else None
    if state is None:
        return None
    try:
        if unit == "kWh":
            value = energy(sample_from_state(state).value)
        else:
            source_unit = state.attributes.get("unit_of_measurement")
            scale = (
                {"W": 1, "kW": 1000}.get(source_unit)
                if unit == "W"
                else 1
                if source_unit == "%"
                else None
            )
            if scale is None:
                return None
            value = energy(state.state) * scale
        if (value < 0 and not signed) or (unit == "%" and value > 100):
            return None
        return energy_text(value)
    except LedgerError, ValueError:
        return None


def valid_source(hass, entity_id, unit, signed=False):
    state = hass.states.get(entity_id)
    if state is None:
        return False
    if state.state in ("unknown", "unavailable"):
        allowed = (
            ("W", "kW")
            if unit == "W"
            else ("Wh", "kWh", "MWh")
            if unit == "kWh"
            else ("%",)
        )
        return state.attributes.get("unit_of_measurement") in allowed
    return reading(hass, entity_id, unit, signed) is not None


def source_status(hass, entity_id, role, statistic=False):
    """Keep missing imported identifiers visible, including historical statistics."""
    state = hass.states.get(entity_id)
    unit = ROLES[role][1]
    status = (
        "external"
        if not entity_id.startswith("sensor.")
        else "missing"
        if state is None
        else state.state
        if state.state in ("unknown", "unavailable")
        else "available"
        if valid_source(hass, entity_id, unit, role in ("grid_power", "battery_power"))
        else "invalid"
    )
    return {
        "id": entity_id,
        "role": role,
        "name": state.attributes.get("friendly_name", entity_id)
        if state
        else entity_id,
        "status": status,
        "unit": state.attributes.get("unit_of_measurement") if state else None,
        "statistic": statistic,
    }


def validate_energy_cache(raw):
    try:
        if not isinstance(raw, dict) or len(raw) > 128:
            raise ValueError
        for entity_id, samples in raw.items():
            if (
                not entity_id.startswith("sensor.")
                or not isinstance(samples, dict)
                or len(samples) > 40
            ):
                raise ValueError
            for day, item in samples.items():
                Sample(**item).validate(day)
                if energy(item["value"]) < 0:
                    raise ValueError
        return raw
    except (TypeError, ValueError, AttributeError) as err:
        raise LedgerError(
            "invalid_energy_cache", "Nieprawidłowe archiwum źródeł energii."
        ) from err


async def refresh_energy_cache(hass, config, core, cache, max_age):
    today = dt_util.utcnow().astimezone(WARSAW).date()
    day = (today - timedelta(days=1)).isoformat()
    ids = {
        entity_id
        for key, value in config["sources"].items()
        for entity_id in source_ids(value)
        if ROLES[key][1] == "kWh"
        and key != "battery_stored"
        and key not in config.get("statistics", {})
    }
    ids |= {item["energy"] for item in config["consumers"] if item.get("energy")}
    ids |= set(core.values())
    result = {
        key: {
            d: value
            for d, value in cache.get(key, {}).items()
            if d >= (today - timedelta(days=32)).isoformat()
        }
        for key in ids
    }
    for entity_id in ids:
        if day not in result[entity_id]:
            try:
                samples = await async_read_samples(
                    hass, {"source": entity_id}, day, max_age, dt_util.utcnow()
                )
                if energy(samples["source"].value) >= 0:
                    result[entity_id][day] = asdict(samples["source"])
            except LedgerError:
                continue
    return result


def energy_snapshot(hass, config, core, cache, stats=None, native=None):
    day = (dt_util.utcnow().astimezone(WARSAW).date() - timedelta(days=1)).isoformat()
    values, today, power_zero_fallback = {}, {}, {}
    stats = stats or {}
    stat_values = (
        stats.get("values", {})
        if stats.get("day") == dt_util.utcnow().astimezone(WARSAW).date().isoformat()
        else {}
    )

    def delta(entity_id):
        value = reading(hass, entity_id, "kWh")
        baseline = cache.get(entity_id, {}).get(day, {}).get("value")
        if value is None or baseline is None or energy(value) < energy(baseline):
            return None
        return energy_text(energy(value) - energy(baseline))

    for key, (_name, unit) in ROLES.items():
        entity_id = config["sources"].get(key)
        values[key] = source_reading(
            hass, entity_id, unit, key in ("grid_power", "battery_power")
        )
        if unit == "W":
            absent = [
                source_status(hass, item, key)
                for item in source_ids(entity_id)
                if reading(hass, item, unit, key in ("grid_power", "battery_power"))
                is None
            ]
            if absent:
                power_zero_fallback[key] = absent
        if key.endswith("_energy"):
            today[key] = (
                aggregate(
                    [
                        stat_values[stat]
                        for stat in config["statistics"][key]
                        if stat_values.get(stat) is not None
                    ]
                )
                if key in config.get("statistics", {})
                else aggregate([delta(value) for value in source_ids(entity_id)])
            )
    if native:
        for item in native.get("report", []):
            for role in item.get("missing", []):
                if set(source_ids(config["sources"].get(role))) != set(
                    source_ids(native.get("config", {}).get("sources", {}).get(role))
                ):
                    continue
                power_zero_fallback.setdefault(role, []).append(
                    {
                        "id": None,
                        "role": role,
                        "name": item["name"],
                        "status": "unconfigured",
                        "origin": item.get("missing_power_origin"),
                    }
                )
    for kind, positive, negative in (
        ("grid", "import", "export"),
        ("battery", "charge", "discharge"),
    ):
        value = values.get(f"{kind}_power")
        if config["sources"].get(f"{kind}_power"):
            signed = energy(value) * (
                1 if config["directions"][kind] == positive else -1
            )
            values[f"{kind}_{positive}_power"] = energy_text(max(energy(0), signed))
            values[f"{kind}_{negative}_power"] = energy_text(max(energy(0), -signed))
    if not config["sources"].get("grid_import_energy") and not config.get(
        "statistics", {}
    ).get("grid_import_energy"):
        today["grid_import_energy"] = delta(core["import"])
    if not config["sources"].get("grid_export_energy") and not config.get(
        "statistics", {}
    ).get("grid_export_energy"):
        today["grid_export_energy"] = (
            "0"
            if config.get("presence", {}).get("grid_export") is False
            else delta(core["export"])
        )
    # Financial PGE credit is supplied exclusively by the hour book.
    today["credited_energy"] = None
    consumers = [
        {
            **item,
            "power_w": source_reading(hass, item.get("power"), "W"),
            "today_kwh": stat_values.get(item["statistic"])
            if item.get("statistic")
            else delta(item.get("energy"))
            if item.get("energy")
            else None,
        }
        for item in config["consumers"]
    ]
    for item in consumers:
        if item.get("power") and reading(hass, item["power"], "W") is None:
            power_zero_fallback.setdefault("consumers", []).append(
                {
                    **source_status(hass, item["power"], "home_power"),
                    "name": item["name"],
                }
            )
    calculation = {}
    capacity = battery_capacity(config, hass)
    battery_stored_basis = (
        "sensor" if config["sources"].get("battery_stored") else "unconfigured"
    )
    if (
        values.get("battery_stored") is None
        and values.get("battery_soc") is not None
        and capacity["kwh"]
    ):
        values["battery_stored"] = energy_text(
            energy(values["battery_soc"]) * energy(capacity["kwh"]) / 100
        )
        battery_stored_basis = "soc_capacity"
    for group, _unit, home, solar, imported, exported, discharged, charged in (
        (
            values,
            "W",
            "home_power",
            "pv_power",
            "grid_import_power",
            "grid_export_power",
            "battery_discharge_power",
            "battery_charge_power",
        ),
        (
            today,
            "kWh",
            "home_energy",
            "pv_energy",
            "grid_import_energy",
            "grid_export_energy",
            "battery_discharge_energy",
            "battery_charge_energy",
        ),
    ):
        if config["sources"].get(home) or config.get("statistics", {}).get(home):
            calculation[home] = {"basis": "sensor"}
            continue
        terms = {solar: 1, imported: 1, discharged: 1, exported: -1, charged: -1}
        inputs = {}
        for role in terms:
            value = group.get(role)
            kind = (
                "solar"
                if role.startswith("pv_")
                else "battery"
                if role.startswith("battery_")
                else "grid_export"
                if role.startswith("grid_export")
                else None
            )
            prefix = (
                "pv_"
                if kind == "solar"
                else "battery_"
                if kind == "battery"
                else "grid_export"
            )
            configured = any(
                key.startswith(prefix) for key in config["sources"]
            ) or any(key.startswith(prefix) for key in config.get("statistics", {}))
            if (
                value is None
                and kind
                and config.get("presence", {}).get(kind) is False
                and not configured
            ):
                value = "0"
            inputs[role] = value
        missing = [role for role, value in inputs.items() if value is None]
        result = (
            sum(
                (energy(inputs[role]) * factor for role, factor in terms.items()),
                energy(0),
            )
            if not missing
            else None
        )
        group[home] = (
            energy_text(max(energy(0), result))
            if result is not None and (_unit == "W" or result >= 0)
            else None
        )
        calculation[home] = {
            "basis": "balance",
            "missing": missing,
            "negative": result is not None and result < 0,
        }
    if (
        stat_values
        and (
            stats.get("home_coverage") is not None
            or stats.get("home_energy") is not None
        )
        and not config["sources"].get("home_energy")
        and not config["statistics"].get("home_energy")
    ):
        today["home_energy"] = stats["home_energy"]
        calculation["home_energy"]["coverage"] = stats.get("home_coverage")
    totals = consumer_summary(
        consumers, values.get("home_power"), today.get("home_energy")
    )
    return {
        "config": config,
        "values": values,
        "today": today,
        "consumers": consumers,
        "consumer_totals": totals,
        "pv_arrays": pv_arrays(hass, config, native),
        "calculation": calculation,
        "power_zero_fallback": power_zero_fallback,
        "battery_stored_basis": battery_stored_basis,
        "battery_capacity": capacity,
        "as_of": stats.get("as_of") if stat_values else None,
        "source_status": {
            role: [
                source_status(hass, entity_id, role, entity_id in statistics)
                for entity_id in dict.fromkeys(
                    [*source_ids(config["sources"].get(role)), *statistics]
                )
            ]
            for role in ROLES
            if (statistics := config.get("statistics", {}).get(role, []))
            or config["sources"].get(role)
        },
    }
