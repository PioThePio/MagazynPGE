"""A fixed number of derived sensors, regardless of the number of invoices."""

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.const import UnitOfEnergy
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .energy import ROLES

SENSORS = {
    "estimated_balance": "Szacunkowe saldo magazynu",
    "available_energy": "Energia dostępna",
    "deficit": "Niedobór energii",
    "period_balance": "Bilans bieżącego okresu",
    "carried_balance": "Saldo przeniesione",
}


SENSOR_DEFINITIONS = {
    key: (name, "kWh", "current", key) for key, name in SENSORS.items()
}
SENSOR_DEFINITIONS.update(
    {
        "import_since_settlement": (
            "Pobrano z magazynu od faktury",
            "kWh",
            "current",
            "import_since_settlement_kwh",
        ),
        "credited_since_settlement": (
            "Oddano do magazynu od faktury",
            "kWh",
            "current",
            "credited_since_settlement_kwh",
        ),
    }
)
SENSOR_DEFINITIONS.update(
    {
        key: (name, unit, "values", key)
        for key, (name, unit) in ROLES.items()
        if not key.endswith("_energy")
    }
)
SENSOR_DEFINITIONS.update(
    {
        key.replace("_energy", "_today"): (name + " dzisiaj", "kWh", "today", key)
        for key, name in {
            "pv_energy": "Produkcja PV",
            "home_energy": "Zużycie domu",
            "battery_charge_energy": "Ładowanie akumulatora",
            "battery_discharge_energy": "Rozładowanie akumulatora",
            "grid_import_energy": "Pobrano z sieci",
            "grid_export_energy": "Oddano do sieci",
            "credited_energy": "Oddano do magazynu PGE",
        }.items()
    }
)


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities(
        PGESensor(entry.runtime_data, key, definition[0])
        for key, definition in SENSOR_DEFINITIONS.items()
    )


class PGESensor(CoordinatorEntity, SensorEntity):
    _attr_has_entity_name = True
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_suggested_display_precision = 0
    # This is a signed balance, not a monotonically increasing energy meter.
    # No state_class: do not imply sums/statistics or automatic meter resets.

    def __init__(self, coordinator, key, name):
        super().__init__(coordinator)
        self.key = key
        _name, unit, self._value_group, self.field = SENSOR_DEFINITIONS[key]
        self._attr_native_unit_of_measurement = unit
        self._attr_device_class = (
            SensorDeviceClass.POWER
            if unit == "W"
            else SensorDeviceClass.BATTERY
            if unit == "%"
            else SensorDeviceClass.ENERGY
        )
        self._attr_name = name
        self._attr_unique_id = f"{coordinator.entry.entry_id}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.entry.entry_id)},
            name="Magazyn PGE",
            manufacturer="Projekt MagazynPGE",
        )

    @property
    def native_value(self):
        if self._value_group != "current":
            value = (
                self.coordinator.data.get("energy", {})
                .get(self._value_group, {})
                .get(self.field)
            )
            return float(value) if value is not None else None
        value = self.coordinator.data["current"].get(self.field)
        inventory = self.coordinator.data.get("planning", {}).get("inventory")
        if inventory is not None:
            balance = float(inventory["balance_kwh"])
            if self.key == "estimated_balance":
                return balance
            if self.key == "available_energy":
                return max(0, balance)
            if self.key == "deficit":
                return max(0, -balance)
        return float(value) if value is not None else None

    @property
    def available(self):
        return (
            self.coordinator.data.get("loaded", True) and self.native_value is not None
        )

    @property
    def extra_state_attributes(self):
        inventory = self.coordinator.data.get("planning", {}).get("inventory")
        power_attributes = {}
        if self.key == "home_power":
            view = self.coordinator.data.get("energy", {})
            power_attributes = {
                "instantaneous_power_w": view.get("home_power_live"),
                "averaging_seconds": 15,
                "power_average_w": {
                    seconds: row["home_power_w"]
                    for seconds, row in view.get("power_windows", {}).items()
                },
            }
        return {
            **power_attributes,
            "sources": self.coordinator.sources,
            "start_day": self.coordinator.data["current"]["start_day"],
            "revision": self.coordinator.revision,
            "time_zone": self.coordinator.data["time_zone"],
            "balance_basis": "fifo"
            if inventory is not None
            else "measurement_without_expiry",
            "expired_kwh": inventory["expired_kwh"] if inventory else None,
            "next_expiry": inventory["next_expiry"] if inventory else None,
        }
