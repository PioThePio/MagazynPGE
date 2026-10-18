"""Optional energy dashboard sources. Read entities without changing them."""

from dataclasses import asdict
from datetime import timedelta

from homeassistant.util import dt as dt_util

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
        capacity = raw.get("battery_capacity_kwh")
        if capacity is not None:
            capacity = energy_text(energy(capacity))
            if energy(capacity) <= 0:
                raise ValueError
        items = []
        for item in consumers:
            if not isinstance(item, dict) or set(item) - {
                "name",
                "power",
                "energy",
                "statistic",
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
                    "name": name,
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
        return {
            "sources": sources,
            "consumers": items,
            "directions": directions,
            "statistics": statistics,
            "presence": presence,
            "imported_from_energy": imported,
            "battery_capacity_kwh": capacity,
        }
    except (TypeError, ValueError, AttributeError) as err:
        raise LedgerError(
            "invalid_energy", "Wybierz sensory i nazwy odbiorców (maks. 16)."
        ) from err


def source_ids(value):
    return value if isinstance(value, list) else [value] if value else []


def energy_sources(config):
    ids = {
        entity_id
        for value in config["sources"].values()
        for entity_id in source_ids(value)
    }
    ids |= {
        value
        for item in config["consumers"]
        for key, value in item.items()
        if key not in ("name", "statistic")
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


def source_reading(hass, ids, unit, signed=False):
    return aggregate([reading(hass, value, unit, signed) for value in source_ids(ids)])


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
    values, today = {}, {}
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
        if key.endswith("_energy"):
            today[key] = (
                aggregate([stat_values.get(stat) for stat in config["statistics"][key]])
                if key in config.get("statistics", {})
                else aggregate([delta(value) for value in source_ids(entity_id)])
            )
    if native:
        # A partial PV power reading is not the whole installation. An explicit
        # manual aggregate power selection may replace the native per-array map.
        native_config = native["config"]
        native_pv = set(source_ids(native_config["sources"].get("pv_power")))
        selected_pv = set(source_ids(config["sources"].get("pv_power")))
        same_energy = set(config.get("statistics", {}).get("pv_energy", [])) == set(
            native_config["statistics"].get("pv_energy", [])
        )
        if (
            same_energy
            and selected_pv == native_pv
            and any(
                item["type"] == "solar" and "pv_power" in item["missing"]
                for item in native.get("report", [])
            )
        ):
            values["pv_power"] = None
    for kind, positive, negative in (
        ("grid", "import", "export"),
        ("battery", "charge", "discharge"),
    ):
        value = values.get(f"{kind}_power")
        if value is not None:
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
    today["credited_energy"] = (
        energy_text(energy(delta(core["export"])) * energy("0.8"))
        if delta(core["export"]) is not None
        else None
    )
    consumers = [
        {
            **item,
            "power_w": reading(hass, item.get("power"), "W"),
            "today_kwh": stat_values.get(item["statistic"])
            if item.get("statistic")
            else delta(item.get("energy"))
            if item.get("energy")
            else None,
        }
        for item in config["consumers"]
    ]
    calculation = {}
    if (
        values.get("battery_stored") is None
        and values.get("battery_soc") is not None
        and config.get("battery_capacity_kwh")
    ):
        values["battery_stored"] = energy_text(
            energy(values["battery_soc"]) * energy(config["battery_capacity_kwh"]) / 100
        )
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
            energy_text(result) if result is not None and result >= 0 else None
        )
        calculation[home] = {
            "basis": "balance",
            "missing": missing,
            "negative": result is not None and result < 0,
        }
    return {
        "config": config,
        "values": values,
        "today": today,
        "consumers": consumers,
        "calculation": calculation,
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
