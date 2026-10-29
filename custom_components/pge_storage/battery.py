"""Optional battery time estimates, bounded learning, explicit forecast inputs."""

from collections import deque
from math import isfinite

from .ledger import LedgerError


def options(raw):
    raw = raw or {}
    allowed = {
        "enabled",
        "average_minutes",
        "learn",
        "min_soc_entity",
        "charge_limit_entity",
        "bms_current_entity",
        "voltage_entity",
        "discharge_current_entity",
        "pv_forecast_entity",
        "home_forecast_entity",
        "forecast_hours",
    }
    if not isinstance(raw, dict) or set(raw) - allowed:
        raise LedgerError(
            "invalid_energy", "Nieprawidłowe ustawienia prognozy baterii."
        )
    result = {
        "enabled": raw.get("enabled", True),
        "average_minutes": int(raw.get("average_minutes", 5)),
        "learn": raw.get("learn", False),
        "forecast_hours": float(raw.get("forecast_hours", 6)),
    }
    if (
        result["average_minutes"] not in (1, 5, 15)
        or not 1 <= result["forecast_hours"] <= 24
        or not all(isinstance(result[k], bool) for k in ("enabled", "learn"))
    ):
        raise LedgerError("invalid_energy", "Wybierz średnią baterii 1/5/15 minut.")
    for key in allowed - set(result):
        entity = raw.get(key) or None
        if entity and (
            not isinstance(entity, str)
            or not entity.startswith(("sensor.", "number."))
            or len(entity) > 255
            or any(c.isspace() for c in entity)
        ):
            raise LedgerError("invalid_energy", "Wybierz encję prognozy baterii.")
        result[key] = entity
    return result


def value(hass, entity, units):
    state = hass.states.get(entity) if entity else None
    try:
        number = float(state.state)
        unit = state.attributes.get("unit_of_measurement")
        if not isfinite(number) or unit not in units:
            return None
        return number * units[unit]
    except AttributeError, ValueError, TypeError:
        return None


def capacity_reading(hass, config):
    """Full capacity, not remaining charge. Never infer nominal voltage."""
    voltage = config.get("battery_voltage")
    for key, basis in (
        ("battery_capacity_entity", "bms_capacity"),
        ("battery_installed_capacity_entity", "installed_capacity_fallback"),
    ):
        entity = config.get(key)
        if not entity or hass is None:
            continue
        state = hass.states.get(entity)
        unit = state.attributes.get("unit_of_measurement") if state else None
        amount = value(hass, entity, {"Ah": 1, "kWh": 1, "Wh": 0.001})
        if amount is None or amount <= 0:
            continue
        kwh = (
            amount * float(voltage) / 1000
            if unit == "Ah" and voltage
            else amount
            if unit in ("kWh", "Wh")
            else None
        )
        if kwh:
            return {
                "kwh": str(kwh),
                "basis": basis,
                "ah": str(amount) if unit == "Ah" else None,
                "voltage": voltage,
                "entity_id": entity,
            }
    if config.get("battery_capacity_entity") or config.get(
        "battery_installed_capacity_entity"
    ):
        return {
            "kwh": None,
            "basis": "missing_capacity_reading",
            "ah": None,
            "voltage": voltage,
        }
    explicit = config.get("battery_capacity_kwh")
    ah = config.get("battery_capacity_ah")
    from .ledger import energy, energy_text

    return {
        "kwh": explicit
        if explicit
        else energy_text(energy(ah) * energy(voltage) / 1000)
        if ah and voltage
        else None,
        "basis": "kwh"
        if explicit
        else "ah_voltage"
        if ah and voltage
        else "incomplete",
        "ah": ah,
        "voltage": voltage,
    }


def battery_identity(config):
    sources = config["sources"]
    opt = config["battery_forecast"]
    return repr(
        (
            [
                (key, sources[key])
                for key in sorted(sources)
                if key.startswith("battery_")
            ],
            config.get("battery_capacity_kwh"),
            config.get("battery_capacity_ah"),
            config.get("battery_voltage"),
            config.get("battery_capacity_entity"),
            config.get("battery_installed_capacity_entity"),
            opt["bms_current_entity"],
            opt["voltage_entity"],
        )
    )


class BatteryEstimate:
    def __init__(self):
        self.samples = deque(maxlen=32768)
        self.identity = None
        self.profile = {}
        self.last_learning = None
        self.history_driven = False
        self.history_seeded = False

    def restore(self, raw):
        if not isinstance(raw, dict) or len(raw) > 20:
            return
        for k, row in raw.items():
            try:
                if (
                    int(k) not in range(0, 100, 5)
                    or set(row) != {"watts", "count"}
                    or not 0 < float(row["watts"]) < 1000000
                    or not isfinite(float(row["watts"]))
                    or not 1 <= row["count"] <= 10000
                ):
                    continue
                self.profile[k] = {
                    "watts": float(row["watts"]),
                    "count": int(row["count"]),
                }
            except ValueError, TypeError, KeyError:
                continue

    def seed(self, frames, config, now):
        """Restore a continuous direction from recorded power, keeping newer live samples."""
        identity = battery_identity(config)
        if self.identity is not None and self.identity != identity:
            self.profile = {}
        live = list(self.samples) if self.identity == identity else []
        self.identity = identity
        self.samples.clear()
        sources = config["sources"]
        roles = (
            ["battery_power"]
            if sources.get("battery_power")
            else [
                k
                for k in ("battery_charge_power", "battery_discharge_power")
                if sources.get(k)
            ]
        )
        if not roles:
            self.samples.extend(live)
            return
        latest = None
        for stamp, frame in frames:
            if stamp > now or stamp < now - 905:
                continue
            known = frame.get("power_history_known", {})
            if any(not known.get(role, False) for role in roles):
                self.samples.clear()
                continue
            values = frame.get("values", {})
            power = float(values.get("battery_charge_power") or 0) - float(
                values.get("battery_discharge_power") or 0
            )
            if not isfinite(power):
                self.samples.clear()
                continue
            direction = 1 if power > 25 else -1 if power < -25 else 0
            if self.samples and self.samples[-1][2] != direction:
                self.samples.clear()
            self.samples.append((stamp, power, direction))
            latest = stamp
        self.history_seeded = bool(self.samples and self.samples[-1][2])
        for row in live:
            if latest is not None and row[0] <= latest:
                continue
            if self.samples and self.samples[-1][2] != row[2]:
                self.samples.clear()
                self.history_seeded = False
            self.samples.append(row)

    def observe(self, soc, charge, bms, stamp):
        if not (0 <= soc <= 100 and charge > 25 and bms > 25 and charge >= 0.85 * bms):
            return False
        if self.last_learning is not None and stamp - self.last_learning < 60:
            return False
        key = str(min(95, int(soc // 5) * 5))
        old = self.profile.get(key, {"watts": charge, "count": 0})
        count = min(old["count"] + 1, 10000)
        self.profile[key] = {
            "watts": old["watts"] + (charge - old["watts"]) / min(count, 60),
            "count": count,
        }
        self.last_learning = stamp
        return True

    def update(self, hass, config, values, now):
        opt = config["battery_forecast"]
        identity = battery_identity(config)
        if identity != self.identity or (self.samples and now < self.samples[-1][0]):
            if self.identity is not None:
                self.profile = {}
            self.samples.clear()
            self.history_seeded = False
            self.identity = identity
            self.last_learning = None
        soc = values.get("battery_soc")
        charge, discharge = (
            float(values.get("battery_charge_power") or 0),
            float(values.get("battery_discharge_power") or 0),
        )
        power = charge - discharge
        direction = 1 if power > 25 else -1 if power < -25 else 0
        if self.samples and self.samples[-1][2] != direction:
            self.samples.clear()
            self.history_seeded = False
        self.samples.append((now, power, direction))
        while len(self.samples) > 1 and self.samples[1][0] < now - 900:
            self.samples.popleft()
        seconds = opt["average_minutes"] * 60
        start = max(now - seconds, self.samples[0][0])
        duration = now - start
        rows = list(self.samples)
        mean = (
            sum(
                row[1]
                * max(
                    0,
                    (rows[i + 1][0] if i + 1 < len(rows) else now) - max(start, row[0]),
                )
                for i, row in enumerate(rows)
            )
            / duration
            if duration
            else power
        )
        capacity_info = capacity_reading(hass, config)
        capacity = float(capacity_info["kwh"] or 0)
        minimum = value(hass, opt["min_soc_entity"], {"%": 1})
        limit = value(hass, opt["charge_limit_entity"], {"W": 1, "kW": 1000})
        current = value(hass, opt["bms_current_entity"], {"A": 1})
        voltage = value(hass, opt["voltage_entity"], {"V": 1})
        bms = current * voltage if current is not None and voltage is not None else None
        result = {
            "average_minutes": opt["average_minutes"],
            "average_power_w": round(mean),
            "covered_seconds": round(duration),
            "averaging_seconds": round(duration),
            "target_averaging_seconds": seconds,
            "history_seeded": self.history_seeded,
            "direction": "charging"
            if direction > 0
            else "discharging"
            if direction < 0
            else "idle",
            "charge_seconds": None,
            "discharge_seconds": None,
            "reserve_discharge_seconds": None,
            "total_discharge_seconds": None,
            "reserve_kwh": capacity * min(float(soc), minimum) / 100
            if capacity
            and soc is not None
            and 0 <= float(soc) <= 100
            and minimum is not None
            and 0 <= minimum <= 100
            else None,
            "model_range_seconds": None,
            "forecast_range_seconds": None,
            "soc": float(soc) if soc is not None and 0 <= float(soc) <= 100 else None,
            "minimum_soc": minimum,
            "capacity_kwh": capacity or None,
            "capacity_basis": capacity_info["basis"],
            "stored_kwh": capacity * float(soc) / 100
            if capacity and soc is not None and 0 <= float(soc) <= 100
            else None,
            "available_to_minimum_kwh": capacity * max(0, float(soc) - minimum) / 100
            if capacity
            and soc is not None
            and 0 <= float(soc) <= 100
            and minimum is not None
            and 0 <= minimum <= 100
            else None,
            "learned_bins": len(self.profile),
            "profile_bins": [
                {
                    "soc_from": i,
                    "soc_to": i + 5,
                    "watts": self.profile.get(str(i), {}).get("watts"),
                    "observations": self.profile.get(str(i), {}).get("count", 0),
                    "usable": self.profile.get(str(i), {}).get("count", 0) >= 3,
                }
                for i in range(0, 100, 5)
            ],
            "quality": "disabled" if not opt["enabled"] else "collecting",
        }
        if (
            not opt["enabled"]
            or soc is None
            or not capacity
            or not 0 <= float(soc) <= 100
        ):
            result["quality"] = (
                "disabled"
                if not opt["enabled"]
                else "missing_soc"
                if soc is None or not 0 <= float(soc) <= 100
                else "missing_capacity"
            )
            return result
        soc = float(soc)
        # Learn only near an independently observed BMS limit; PV shortage is
        # not evidence of battery taper. At most one sample per minute.
        if (
            opt["learn"]
            and not self.history_driven
            and charge > 25
            and bms
            and bms > 25
            and charge >= 0.85 * bms
            and (self.last_learning is None or now - self.last_learning >= 60)
        ):
            self.observe(soc, charge, bms, now)
        if duration < min(seconds, 30) or not direction or abs(mean) <= 25:
            return result
        result["quality"] = "constant_recent_power"
        if direction > 0:
            usable = min([mean] + [x for x in (limit, bms) if x is not None])
            if usable <= 25:
                return result
            result["charge_seconds"] = round(
                capacity * (100 - soc) / 100 * 3600000 / usable
            )
            if opt["learn"]:
                total, known = 0, True
                cursor = soc
                while cursor < 100:
                    stop = min(100, (int(cursor // 5) + 1) * 5)
                    learned = self.profile.get(str(int(cursor // 5) * 5))
                    if not learned or learned["count"] < 3:
                        known = False
                        break
                    watts = min(usable, learned["watts"])
                    total += capacity * (stop - cursor) / 100 * 3600000 / watts
                    cursor = stop
                if known:
                    result["model_range_seconds"] = [
                        round(total * 0.85),
                        round(total * 1.2),
                    ]
        elif minimum is not None and 0 <= minimum <= 100:
            result["discharge_seconds"] = round(
                capacity * max(0, soc - minimum) / 100 * 3600000 / abs(mean)
            )
            result["reserve_discharge_seconds"] = round(
                capacity * min(soc, minimum) / 100 * 3600000 / abs(mean)
            )
            result["total_discharge_seconds"] = (
                result["discharge_seconds"] + result["reserve_discharge_seconds"]
            )
        # Both inputs are explicitly energy remaining in the same chosen
        # horizon. We never guess the schema of third-party forecast attributes.
        pv = value(hass, opt["pv_forecast_entity"], {"kWh": 1, "Wh": 0.001})
        home = value(hass, opt["home_forecast_entity"], {"kWh": 1, "Wh": 0.001})
        if pv is not None and home is not None and pv >= 0 and home >= 0:
            surplus = (pv - home) / opt["forecast_hours"] * 1000
            if surplus > 25:
                watts = min([surplus] + [x for x in (limit, bms) if x is not None])
                if watts > 25:
                    eta = capacity * (100 - soc) / 100 * 3600000 / watts
                    if eta <= opt["forecast_hours"] * 3600:
                        result["forecast_range_seconds"] = [
                            round(eta * 0.8),
                            round(eta * 1.3),
                        ]
        return result
