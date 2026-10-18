"""Optional energy dashboard sources. Read entities without changing them."""

from dataclasses import asdict
from datetime import timedelta

from homeassistant.util import dt as dt_util

from .history import async_read_samples, sample_from_state
from .ledger import WARSAW, LedgerError, Sample, energy, energy_text

ROLES = {
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

        sources = {key: entity(value) for key, value in sources.items() if value}
        items = []
        for item in consumers:
            if not isinstance(item, dict) or set(item) - {"name", "power", "energy"}:
                raise ValueError
            name = item.get("name", "").strip()
            if (
                not name
                or len(name) > 80
                or not (item.get("power") or item.get("energy"))
            ):
                raise ValueError
            items.append(
                {
                    "name": name,
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
        return {"sources": sources, "consumers": items, "directions": directions}
    except (TypeError, ValueError, AttributeError) as err:
        raise LedgerError(
            "invalid_energy", "Wybierz sensory i nazwy odbiorców (maks. 16)."
        ) from err


def energy_sources(config):
    return set(config["sources"].values()) | {
        value
        for item in config["consumers"]
        for key, value in item.items()
        if key != "name"
    }


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
        value
        for key, value in config["sources"].items()
        if ROLES[key][1] == "kWh" and key != "battery_stored"
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


def energy_snapshot(hass, config, core, cache):
    day = (dt_util.utcnow().astimezone(WARSAW).date() - timedelta(days=1)).isoformat()
    values, today = {}, {}

    def delta(entity_id):
        value = reading(hass, entity_id, "kWh")
        baseline = cache.get(entity_id, {}).get(day, {}).get("value")
        if value is None or baseline is None or energy(value) < energy(baseline):
            return None
        return energy_text(energy(value) - energy(baseline))

    for key, (_name, unit) in ROLES.items():
        entity_id = config["sources"].get(key)
        values[key] = reading(
            hass, entity_id, unit, key in ("grid_power", "battery_power")
        )
        if key.endswith("_energy"):
            today[key] = delta(entity_id) if entity_id else None
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
    today["grid_import_energy"] = delta(core["import"])
    today["grid_export_energy"] = delta(core["export"])
    today["credited_energy"] = (
        energy_text(energy(today["grid_export_energy"]) * energy("0.8"))
        if today["grid_export_energy"] is not None
        else None
    )
    consumers = [
        {
            **item,
            "power_w": reading(hass, item.get("power"), "W"),
            "today_kwh": delta(item.get("energy")) if item.get("energy") else None,
        }
        for item in config["consumers"]
    ]
    return {"config": config, "values": values, "today": today, "consumers": consumers}
