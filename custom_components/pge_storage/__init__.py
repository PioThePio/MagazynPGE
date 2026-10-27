"""Virtual PGE energy storage, reading separate import and export counters."""

import logging
from pathlib import Path

from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.storage import Store

from .const import DOMAIN, SIGNAL_LEDGER_UPDATED, STORAGE_VERSION
from .coordinator import LedgerCoordinator
from .ledger import LedgerError
from .resources import async_register_card
from .websocket import async_register

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    if entry.version != 2:
        logging.getLogger(__name__).error(
            "Wpis PGE 0.1 używał sensora bilansu. Zachowano jego dane bez zmian. W wersji 0.2 utwórz nowy wpis z oddzielnymi licznikami energii; starych próbek nie przeliczamy bez surowych odczytów."
        )
        return False
    return True


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    hass.data.setdefault(DOMAIN, {})
    async_register(hass)
    await hass.http.async_register_static_paths(
        [
            StaticPathConfig(
                "/pge_storage",
                str(Path(__file__).parent / "frontend"),
                False,
            )
        ]
    )
    await async_register_card(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    coordinator = LedgerCoordinator(hass, entry)
    try:
        await coordinator.async_load()
    except (LedgerError, KeyError, TypeError) as err:
        raise ConfigEntryError(f"Nie można wczytać rejestru PGE: {err}") from err
    entry.runtime_data = coordinator
    hass.data[DOMAIN][entry.entry_id] = coordinator
    entry.async_on_unload(entry.add_update_listener(_async_options_updated))
    await hass.config_entries.async_forward_entry_setups(entry, [Platform.SENSOR])
    from .dashboard import async_repair_dashboards

    try:
        await async_repair_dashboards(hass, entry.entry_id)
    except Exception:
        logging.getLogger(__name__).exception(
            "Nie udało się uporządkować starego dashboardu PGE; kopia oryginału pozostaje zachowana"
        )
    return True


async def _async_options_updated(hass: HomeAssistant, entry: ConfigEntry) -> None:
    entry.runtime_data.publish()


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    if unloaded := await hass.config_entries.async_unload_platforms(
        entry, [Platform.SENSOR]
    ):
        coordinator = hass.data[DOMAIN].pop(entry.entry_id, None)
        if coordinator is not None:
            snapshot = {
                **coordinator.data,
                "loaded": False,
                "current": {key: None for key in coordinator.data["current"]},
            }
            async_dispatcher_send(hass, SIGNAL_LEDGER_UPDATED, snapshot)
    return unloaded


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    # Only our own ledger. Recorder and the source entity are never changed.
    await Store(hass, STORAGE_VERSION, f"{DOMAIN}.{entry.entry_id}").async_remove()
