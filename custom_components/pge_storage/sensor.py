"""A fixed number of derived sensors, regardless of the number of invoices."""

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.const import UnitOfEnergy
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN

SENSORS = {
    "estimated_balance": "Szacunkowe saldo magazynu",
    "available_energy": "Energia dostępna",
    "deficit": "Niedobór energii",
    "period_balance": "Bilans bieżącego okresu",
    "carried_balance": "Saldo przeniesione",
}


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities(
        PGESensor(entry.runtime_data, key, name) for key, name in SENSORS.items()
    )


class PGESensor(CoordinatorEntity, SensorEntity):
    _attr_has_entity_name = True
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_device_class = SensorDeviceClass.ENERGY
    # This is a signed balance, not a monotonically increasing energy meter.
    # No state_class: do not imply sums/statistics or automatic meter resets.

    def __init__(self, coordinator, key, name):
        super().__init__(coordinator)
        self.key = key
        self._attr_name = name
        self._attr_unique_id = f"{coordinator.entry.entry_id}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.entry.entry_id)},
            name="Magazyn PGE",
            manufacturer="Projekt MagazynPGE",
        )

    @property
    def native_value(self):
        value = self.coordinator.data["current"][self.key]
        return float(value) if value is not None else None

    @property
    def available(self):
        return self.coordinator.data["current"][self.key] is not None

    @property
    def extra_state_attributes(self):
        return {
            "sources": self.coordinator.sources,
            "start_day": self.coordinator.data["current"]["start_day"],
            "revision": self.coordinator.revision,
            "time_zone": self.coordinator.data["time_zone"],
        }
