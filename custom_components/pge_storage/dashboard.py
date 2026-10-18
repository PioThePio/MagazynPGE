"""Create an editable Lovelace dashboard with independent PGE cards."""

import asyncio
from hashlib import sha256

from homeassistant.components import frontend, websocket_api
from homeassistant.components.lovelace.const import (
    LOVELACE_DATA,
    MODE_STORAGE,
    ConfigNotFound,
)
from homeassistant.components.lovelace.dashboard import DashboardsCollection
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .ledger import LedgerError

_LOCK = f"{DOMAIN}_dashboard_lock"


def dashboard_config(entry_id: str) -> dict:
    """Build native sections; every card is movable and editable in HA."""

    def card(kind, columns, **extra):
        return {
            "type": f"custom:pge-{kind}-card",
            "entry_id": entry_id,
            "grid_options": {"columns": columns, "rows": "auto"},
            **extra,
        }

    return {
        "title": "Magazyn PGE",
        # This identifies only a dashboard created here, never an existing one.
        DOMAIN: {"entry_id": entry_id, "schema": 1},
        "views": [
            {
                "title": "Magazyn PGE",
                "path": "magazyn",
                "icon": "mdi:transmission-tower",
                "type": "sections",
                "max_columns": 3,
                "sections": [
                    {
                        "type": "grid",
                        "column_span": 3,
                        "cards": [
                            card("balance", 12, metric=metric)
                            for metric in (
                                "available_energy",
                                "deficit",
                                "period_balance",
                            )
                        ],
                    },
                    {
                        "type": "grid",
                        "column_span": 2,
                        "cards": [card("energy", 24)],
                    },
                    {"type": "grid", "cards": [card("consumers", 12)]},
                    {
                        "type": "grid",
                        "column_span": 2,
                        "cards": [card("projection", 24)],
                    },
                    {"type": "grid", "cards": [card("settings", 12)]},
                    {
                        "type": "grid",
                        "column_span": 3,
                        "cards": [card("history", 36)],
                    },
                ],
            }
        ],
    }


def _collection(hass: HomeAssistant) -> DashboardsCollection:
    """Use HA's active collection, including its native panel listeners.

    Lovelace does not expose this collection on LovelaceData. Its registered list
    command is bound to the native collection adapter. A second collection would
    have stale data and could overwrite dashboards created from the HA UI.
    """
    command = hass.data.get(websocket_api.DOMAIN, {}).get("lovelace/dashboards/list")
    adapter = getattr(command[0], "__self__", None) if command else None
    collection = getattr(adapter, "storage_collection", None)
    if not isinstance(collection, DashboardsCollection):
        raise LedgerError(
            "dashboard_unavailable",
            "Home Assistant nie udostępnił edytowalnych dashboardów Lovelace.",
        )
    return collection


async def async_create_dashboard(hass: HomeAssistant, entry_id: str) -> dict:
    """Create once, preserving all other dashboards and later user edits."""
    lock = hass.data.setdefault(_LOCK, asyncio.Lock())
    async with lock:
        if LOVELACE_DATA not in hass.data or hass.config.recovery_mode:
            raise LedgerError(
                "dashboard_unavailable",
                "Dashboard można utworzyć po pełnym uruchomieniu Home Assistant.",
            )
        collection = _collection(hass)
        dashboards = hass.data[LOVELACE_DATA].dashboards
        base_path = f"pge-energia-{sha256(entry_id.encode()).hexdigest()[:10]}"
        for index in range(1, 101):
            path = base_path if index == 1 else f"{base_path}-{index}"
            existing = dashboards.get(path)
            if existing and existing.mode == MODE_STORAGE:
                try:
                    config = await existing.async_load(False)
                except ConfigNotFound:
                    config = {}
                owner = config.get(DOMAIN)
                if isinstance(owner, dict) and owner.get("entry_id") == entry_id:
                    return {
                        "url_path": path,
                        "url": f"/{path}/magazyn",
                        "created": False,
                    }
            if existing or frontend.async_panel_exists(hass, path):
                continue
            item = await collection.async_create_item(
                {
                    "url_path": path,
                    "title": "Magazyn PGE",
                    "icon": "mdi:transmission-tower",
                    "show_in_sidebar": True,
                    "require_admin": False,
                    "mode": MODE_STORAGE,
                }
            )
            try:
                await dashboards[path].async_save(dashboard_config(entry_id))
            except Exception:
                # Remove only the empty dashboard just created by this action.
                await collection.async_delete_item(item["id"])
                raise
            return {"url_path": path, "url": f"/{path}/magazyn", "created": True}
        raise LedgerError(
            "dashboard_unavailable",
            "Nie znaleziono wolnego adresu nowego dashboardu Magazyn PGE.",
        )
