"""Load the card through Lovelace after HA initializes its element registry."""

import logging
from urllib.parse import urlsplit

from homeassistant.components.lovelace.const import LOVELACE_DATA
from homeassistant.components.lovelace.resources import ResourceStorageCollection
from homeassistant.core import HomeAssistant

from .const import CARD_URL

_LOGGER = logging.getLogger(__name__)


async def async_register_card(hass: HomeAssistant) -> None:
    """Create or update our module without changing other Lovelace resources."""
    resources = hass.data[LOVELACE_DATA].resources
    if not isinstance(resources, ResourceStorageCollection):
        _LOGGER.warning(
            "Zasoby Lovelace są zarządzane w YAML. Dodaj do lovelace.resources: "
            "url: %s, type: module",
            CARD_URL,
        )
        return

    await resources.async_get_info()
    matches = [
        item
        for item in resources.async_items()
        if not urlsplit(item["url"]).netloc
        and urlsplit(item["url"]).path == urlsplit(CARD_URL).path
    ]
    data = {"url": CARD_URL, "res_type": "module"}
    if not matches:
        await resources.async_create_item(data)
        return
    first, *duplicates = matches
    if first["url"] != CARD_URL or first["type"] != "module":
        await resources.async_update_item(first["id"], data)
    for duplicate in duplicates:
        await resources.async_delete_item(duplicate["id"])
