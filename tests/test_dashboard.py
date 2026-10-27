"""Exercise editable dashboards through real HA Lovelace and websocket APIs."""

import asyncio
from copy import deepcopy
from hashlib import sha256
from unittest.mock import patch

import aiohttp
import pytest
from homeassistant.components.lovelace.const import LOVELACE_DATA
from homeassistant.components.lovelace.dashboard import LovelaceStorage

from custom_components.pge_storage.const import DOMAIN
from custom_components.pge_storage.dashboard import async_create_dashboard

pytestmark = pytest.mark.asyncio(loop_scope="module")


async def _entry(hass, suffix):
    imported, exported = (
        f"sensor.dashboard_import_{suffix}",
        f"sensor.dashboard_export_{suffix}",
    )
    for entity_id in (imported, exported):
        hass.states.async_set(entity_id, "1000", {"unit_of_measurement": "kWh"})
    flow = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    result = await hass.config_entries.flow.async_configure(
        flow["flow_id"],
        {
            "import_entity_id": imported,
            "export_entity_id": exported,
            "max_age_hours": 24,
        },
    )
    await hass.async_block_till_done()
    return result["result"]


async def _token(hass, group):
    user = await hass.auth.async_create_user("Dashboard test", group_ids=[group])
    refresh = await hass.auth.async_create_refresh_token(
        user, client_id="http://pge.test/"
    )
    return hass.auth.async_create_access_token(refresh)


async def test_native_dashboard_cards_editing_and_reload(ha):
    hass, port = ha
    entry = await _entry(hass, "first")
    ledger = deepcopy(entry.runtime_data.export())
    token = await _token(hass, "system-admin")
    async with aiohttp.ClientSession() as session:
        async with session.ws_connect(f"http://127.0.0.1:{port}/api/websocket") as ws:
            await ws.receive_json()
            await ws.send_json({"type": "auth", "access_token": token})
            assert (await ws.receive_json())["type"] == "auth_ok"

            async def call(message_id, command, **values):
                await ws.send_json({"id": message_id, "type": command, **values})
                response = await asyncio.wait_for(ws.receive_json(), timeout=10)
                assert response["id"] == message_id, response
                assert response["success"], response
                return response["result"]

            other = await call(
                1,
                "lovelace/dashboards/create",
                url_path="dashboard-unrelated",
                title="Other dashboard",
                mode="storage",
                show_in_sidebar=True,
                require_admin=False,
            )
            dashboards = hass.data[LOVELACE_DATA].dashboards
            other_config = {"views": [{"title": "Original", "cards": []}]}
            await dashboards[other["url_path"]].async_save(deepcopy(other_config))
            result = await call(
                2, "pge_storage/create_dashboard", entry_id=entry.entry_id
            )
            assert result["created"] is True
            assert result["url"] == f"/{result['url_path']}/magazyn"
            native = dashboards[result["url_path"]]
            assert isinstance(native, LovelaceStorage)
            config = await native.async_load(False)
            view = config["views"][0]
            assert view["type"] == "sections"
            cards = [card for section in view["sections"] for card in section["cards"]]
            assert [card["type"] for card in cards] == [
                "custom:pge-balance-card",
                "custom:pge-balance-card",
                "custom:pge-balance-card",
                "custom:pge-energy-card",
                "custom:pge-consumers-card",
                "custom:pge-projection-card",
                "custom:pge-opust-card",
                "custom:pge-settings-card",
                "custom:pge-history-card",
            ]
            assert all(card["entry_id"] == entry.entry_id for card in cards)
            assert all(card["grid_options"]["columns"] >= 12 for card in cards)
            # Saving/reloading uses native HA storage, not a wrapper's private UI.
            changed = deepcopy(config)
            changed["views"][0]["sections"][0]["cards"][0]["title"] = "My stock tile"
            changed["views"][0]["sections"][1]["cards"].append(
                {"type": "markdown", "content": "User-added card"}
            )
            await call(
                3, "lovelace/config/save", url_path=result["url_path"], config=changed
            )
            repeated = await call(
                4, "pge_storage/create_dashboard", entry_id=entry.entry_id
            )
            assert repeated == {**result, "created": False}
            reloaded = LovelaceStorage(hass, native.config)
            assert await reloaded.async_load(False) == changed
            listed = await call(5, "lovelace/dashboards/list")
            assert sum(item["url_path"] == result["url_path"] for item in listed) == 1
            assert await dashboards[other["url_path"]].async_load(False) == other_config
    assert entry.runtime_data.export() == ledger
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert await async_create_dashboard(hass, entry.entry_id) == repeated
    assert await native.async_load(False) == changed


async def test_existing_path_is_preserved_and_failed_creation_cleans_only_own_panel(ha):
    hass, _ = ha
    entry = await _entry(hass, "collision")
    base = f"pge-energia-{sha256(entry.entry_id.encode()).hexdigest()[:10]}"
    from custom_components.pge_storage.dashboard import _collection

    collection = _collection(hass)
    item = await collection.async_create_item(
        {
            "url_path": base,
            "title": "User dashboard",
            "mode": "storage",
            "show_in_sidebar": True,
            "require_admin": False,
        }
    )
    dashboards = hass.data[LOVELACE_DATA].dashboards
    original = {"views": [{"title": "Keep me", "cards": []}], DOMAIN: "user value"}
    await dashboards[base].async_save(deepcopy(original))
    before = deepcopy(collection.async_items())
    with patch.object(LovelaceStorage, "async_save", side_effect=OSError("disk full")):
        with pytest.raises(OSError, match="disk full"):
            await async_create_dashboard(hass, entry.entry_id)
    assert collection.async_items() == before
    assert base + "-2" not in dashboards
    assert await dashboards[base].async_load(False) == original
    result = await async_create_dashboard(hass, entry.entry_id)
    assert result["url_path"] == base + "-2"
    assert item in collection.async_items()
    assert await dashboards[base].async_load(False) == original


async def test_dashboard_creation_requires_admin(ha):
    hass, port = ha
    token = await _token(hass, "system-read-only")
    async with aiohttp.ClientSession() as session:
        async with session.ws_connect(f"http://127.0.0.1:{port}/api/websocket") as ws:
            await ws.receive_json()
            await ws.send_json({"type": "auth", "access_token": token})
            assert (await ws.receive_json())["type"] == "auth_ok"
            await ws.send_json({"id": 1, "type": "pge_storage/create_dashboard"})
            response = await asyncio.wait_for(ws.receive_json(), timeout=10)
            assert response["success"] is False
            assert response["error"]["code"] == "unauthorized"
