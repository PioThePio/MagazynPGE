import asyncio
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import aiohttp
import pytest
from homeassistant.components.recorder.tasks import SynchronizeTask
from homeassistant.const import EVENT_STATE_CHANGED
from homeassistant.core import State
from homeassistant.exceptions import Unauthorized
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.recorder import get_instance
from homeassistant.util import dt as dt_util

from custom_components.pge_storage.const import DOMAIN
from custom_components.pge_storage.coordinator import LedgerCoordinator
from custom_components.pge_storage.history import async_read_counters
from custom_components.pge_storage.ledger import LedgerError, boundary
from custom_components.pge_storage.websocket import _get

pytestmark = pytest.mark.asyncio(loop_scope="module")
SOURCE = "sensor.pge_import_total"
EXPORT = "sensor.victron_grid_export_total"
SOURCES = {"import": SOURCE, "export": EXPORT}


async def record(hass, day, imported, exported, *, offset=1):
    moment = boundary(day) - timedelta(seconds=offset)
    for entity_id, value in [(SOURCE, imported), (EXPORT, exported)]:
        if value is None:
            continue
        state = State(
            entity_id, value, {"unit_of_measurement": "kWh"}, last_updated=moment
        )
        hass.bus.async_fire_internal(
            EVENT_STATE_CHANGED,
            {"entity_id": entity_id, "old_state": None, "new_state": state},
            time_fired=moment.timestamp(),
        )
    await hass.async_block_till_done()
    # Always enqueue a barrier: async_block_till_done may see an empty queue
    # while Recorder is already processing the last event in another thread.
    committed = hass.loop.create_future()
    get_instance(hass).queue_task(SynchronizeTask(committed))
    await asyncio.wait_for(committed, timeout=10)


async def test_full_integration_recorder_gui_api_and_restart(ha):
    hass, port = ha
    hass.states.async_set(SOURCE, "7410", {"unit_of_measurement": "kWh"})
    hass.states.async_set(EXPORT, "10000", {"unit_of_measurement": "kWh"})
    await hass.async_block_till_done()
    source_before = hass.states.get(SOURCE)
    initial = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    assert initial["type"] == "form"
    result = await hass.config_entries.flow.async_configure(
        initial["flow_id"],
        {"import_entity_id": SOURCE, "export_entity_id": EXPORT, "max_age_hours": 24},
    )
    assert result["type"] == "create_entry"
    await hass.async_block_till_done()
    entry = result["result"]
    manager = entry.runtime_data
    assert entry.state.value == "loaded"
    entities = er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id)
    from custom_components.pge_storage.sensor import SENSOR_DEFINITIONS

    assert len(entities) == len(SENSOR_DEFINITIONS)

    for day, imported, exported in [
        ("2025-03-15", "1000", "1250"),
        ("2025-09-15", "2000", "3750"),
        ("2026-03-15", "4750", "4750"),
    ]:
        await record(hass, day, imported, exported)
    assert (
        await async_read_counters(hass, SOURCES, "2025-09-15", 24, dt_util.utcnow())
    ).value == "1000"

    # Real HA HTTP and authenticated websocket, not a mocked command dispatcher.
    user = await hass.auth.async_create_user(
        "PGE test admin", group_ids=["system-admin"]
    )
    refresh = await hass.auth.async_create_refresh_token(
        user, client_id="http://pge.test/"
    )
    token = hass.auth.async_create_access_token(refresh)
    async with aiohttp.ClientSession() as session:
        async with session.get(
            f"http://127.0.0.1:{port}/pge_storage/pge-storage-card.js"
        ) as response:
            assert response.status == 200
            assert "customElements.define" in await response.text()
        async with session.ws_connect(f"http://127.0.0.1:{port}/api/websocket") as ws:
            assert (await ws.receive_json())["type"] == "auth_required"
            await ws.send_json({"type": "auth", "access_token": token})
            assert (await ws.receive_json())["type"] == "auth_ok"

            async def call(message_id, action, **data):
                await ws.send_json(
                    {"id": message_id, "type": f"pge_storage/{action}", **data}
                )
                response = await asyncio.wait_for(ws.receive_json(), timeout=10)
                assert response["id"] == message_id, response
                return response

            for index, (day, invoice) in enumerate(
                [("2025-03-15", "0"), ("2025-09-15", "1000"), ("2026-03-15", "0")], 1
            ):
                response = await call(
                    index,
                    "put",
                    revision=index - 1,
                    record={"day": day, "invoice_balance": invoice},
                )
                assert response["success"], response
            assert manager.data["current"]["period_balance"] == "1540"
            assert manager.data["current"]["estimated_balance"] == "1540"
            assert manager.data["records"][2]["invoice_difference"] == "950"

            diagnostic = await call(4, "diagnose", day="2025-09-15")
            assert diagnostic["success"]
            assert diagnostic["result"]["sample"]["value"] == "1000"
            assert not diagnostic["result"]["statistics"]["import"][
                "has_statistics_metadata"
            ]
            missing = await call(5, "put", revision=3, record={"day": "2024-01-01"})
            assert missing["error"]["code"] == "missing_history"
            assert manager.revision == 3
            conflict = await call(
                6, "delete", revision=0, record_id=manager.records[0].id
            )
            assert conflict["error"]["code"] == "conflict"
            exported = (await call(7, "export"))["result"]
            assert len(exported["records"]) == 3

            # An invoice-only edit must not reread a purged historical sample.
            with patch(
                "custom_components.pge_storage.coordinator.async_read_counters",
                side_effect=AssertionError("Unexpected history read"),
            ):
                changed = await call(
                    8,
                    "put",
                    revision=3,
                    record={
                        "id": manager.records[-1].id,
                        "day": "2026-03-15",
                        "invoice_balance": "50",
                    },
                )
                assert changed["success"], changed
            assert manager.data["current"]["estimated_balance"] == "1590"
            restored = await call(9, "import", revision=4, document=exported)
            assert restored["success"], restored
            assert manager.data["current"]["estimated_balance"] == "1540"
            removed = await call(
                10, "delete", revision=5, record_id=manager.records[1].id
            )
            assert removed["success"], removed
            assert manager.data["records"][1]["period_balance"] == "-950"
            await call(11, "import", revision=6, document=exported)

            subscribed = await call(12, "subscribe")
            assert subscribed["success"]
            snapshot = await ws.receive_json()
            assert snapshot["event"]["current"]["estimated_balance"] == "1540"
            assert hass.states.get(SOURCE) is source_before
            hass.states.async_set(EXPORT, "10012.5", {"unit_of_measurement": "kWh"})
            event = await asyncio.wait_for(ws.receive_json(), timeout=10)
            assert event["event"]["current"]["period_balance"] == "1550"
            # An open card must follow the replacement coordinator after reload.
            assert await hass.config_entries.async_reload(entry.entry_id)
            await hass.async_block_till_done()
            while True:
                event = await asyncio.wait_for(ws.receive_json(), timeout=10)
                if event["event"]["loaded"]:
                    break
            hass.states.async_set(EXPORT, "10013.75", {"unit_of_measurement": "kWh"})
            event = await asyncio.wait_for(ws.receive_json(), timeout=10)
            assert event["event"]["current"]["period_balance"] == "1551"
            await ws.send_json(
                {"id": 13, "type": "unsubscribe_events", "subscription": 12}
            )
            assert (await ws.receive_json())["success"]

    # Reload above went through HA's unload/setup paths and durable Store.
    restarted = entry.runtime_data
    assert restarted is not manager
    assert restarted.export() == exported
    assert restarted.data["current"]["estimated_balance"] == "1551"
    assert source_before.state == "7410"
    assert (
        hass.states.get(SOURCE).state == "7410"
    )  # Only the explicit test write changed it.
    assert hass.states.get(SOURCE).attributes == source_before.attributes
    await hass.config_entries.async_remove(entry.entry_id)
    assert hass.states.get(SOURCE).state == "7410"
    assert not (
        restarted.store.path
        and __import__("pathlib").Path(restarted.store.path).exists()
    )


async def test_failed_save_does_not_change_in_memory_ledger(ha):
    hass, _port = ha
    hass.states.async_set(SOURCE, "7410", {"unit_of_measurement": "kWh"})
    hass.states.async_set(EXPORT, "10000", {"unit_of_measurement": "kWh"})
    await record(hass, "2025-03-15", "1000", "1250")
    await record(hass, "2025-09-15", "2000", "3750")
    flow = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    result = await hass.config_entries.flow.async_configure(
        flow["flow_id"],
        {"import_entity_id": SOURCE, "export_entity_id": EXPORT, "max_age_hours": 24},
    )
    await hass.async_block_till_done()
    manager = result["result"].runtime_data
    original = manager.export()
    with patch.object(
        manager.store, "async_save", new=AsyncMock(side_effect=OSError("disk full"))
    ):
        with pytest.raises(OSError, match="disk full"):
            await manager.async_put({"day": "2025-03-15", "invoice_balance": "0"}, 0)
    assert manager.export() == original
    assert manager.revision == 0
    with pytest.raises(LedgerError, match="zakończon"):
        await manager.async_put({"day": "2099-01-01"}, 0)
    # Loading the same stored ledger in another coordinator validates startup.
    copy = LedgerCoordinator(hass, result["result"])
    await copy.async_load()
    assert copy.export() == original

    # Two writers using the same revision cannot silently overwrite one another.
    writes = await asyncio.gather(
        manager.async_put({"day": "2025-03-15", "invoice_balance": "0"}, 0),
        manager.async_put({"day": "2025-09-15", "invoice_balance": "0"}, 0),
        return_exceptions=True,
    )
    assert (
        sum(
            isinstance(outcome, LedgerError) and outcome.code == "conflict"
            for outcome in writes
        )
        == 1
    )
    assert manager.revision == 1
    assert len(manager.records) == 1

    options = await hass.config_entries.options.async_init(result["result"].entry_id)
    updated = await hass.config_entries.options.async_configure(
        options["flow_id"], {"max_age_hours": 48}
    )
    assert updated["type"] == "create_entry"
    await hass.async_block_till_done()
    assert manager.max_age_hours == 48


async def test_websocket_rejects_non_admin_writes_and_unauthorized_reads(ha):
    hass, port = ha
    viewer = await hass.auth.async_create_user(
        "PGE viewer", group_ids=["system-read-only"]
    )
    nobody = await hass.auth.async_create_user("PGE no access", group_ids=[])
    async with aiohttp.ClientSession() as session:
        for user, action, extra in [
            (viewer, "put", {"revision": 0, "record": {"day": "2025-03-15"}}),
            (viewer, "export", {}),
            (viewer, "put_plan", {"revision": 0, "planning": {}}),
            (viewer, "refresh_plan", {}),
            (viewer, "put_energy", {"revision": 0, "config": {}}),
            (nobody, "months", {}),
            (nobody, "subscribe", {}),
            (nobody, "daily", {"month": "2026-09"}),
            (nobody, "profile", {}),
        ]:
            refresh = await hass.auth.async_create_refresh_token(
                user, client_id="http://pge.test/"
            )
            token = hass.auth.async_create_access_token(refresh)
            async with session.ws_connect(
                f"http://127.0.0.1:{port}/api/websocket"
            ) as ws:
                await ws.receive_json()
                await ws.send_json({"type": "auth", "access_token": token})
                assert (await ws.receive_json())["type"] == "auth_ok"
                await ws.send_json({"id": 1, "type": f"pge_storage/{action}", **extra})
                response = await asyncio.wait_for(ws.receive_json(), timeout=10)
                assert response["success"] is False, response
                assert response["error"]["code"] == "unauthorized", response


async def test_source_selection_requires_two_distinct_energy_counters(ha):
    hass, _port = ha
    flow = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    result = await hass.config_entries.flow.async_configure(
        flow["flow_id"],
        {"import_entity_id": SOURCE, "export_entity_id": SOURCE, "max_age_hours": 24},
    )
    assert result["errors"]["base"] == "same_source"
    hass.states.async_set(
        "sensor.victron_power_not_energy", "1000", {"unit_of_measurement": "W"}
    )
    result = await hass.config_entries.flow.async_configure(
        flow["flow_id"],
        {
            "import_entity_id": SOURCE,
            "export_entity_id": "sensor.victron_power_not_energy",
            "max_age_hours": 24,
        },
    )
    assert result["errors"]["export_entity_id"] == "invalid_source"


async def test_missing_export_history_is_not_replaced_with_import_or_other_meter(ha):
    hass, _port = ha
    await record(hass, "2024-06-15", "100", None)
    with pytest.raises(LedgerError, match="export"):
        await async_read_counters(hass, SOURCES, "2024-06-15", 24, dt_util.utcnow())


async def test_permission_to_only_one_source_does_not_reveal_the_ledger(ha):
    hass, _port = ha
    connection = SimpleNamespace(
        user=SimpleNamespace(
            permissions=SimpleNamespace(
                check_entity=lambda entity_id, policy: entity_id == SOURCE
            )
        )
    )
    with pytest.raises(Unauthorized):
        _get(hass, connection, {})


async def test_date_edits_and_refresh_recompute_from_both_counters(ha):
    hass, _port = ha
    manager = next(iter(hass.data[DOMAIN].values()))
    empty = {**manager.export(), "records": []}
    await manager.async_import(empty, manager.revision)
    for day, imported, exported in [
        ("2025-03-15", "1000", "1250"),
        ("2025-09-15", "2000", "3750"),
        ("2026-03-15", "4750", "4750"),
        ("2025-10-15", "2100", "4000"),
    ]:
        await record(hass, day, imported, exported)
    await manager.async_put(
        {"day": "2025-03-15", "invoice_balance": "0"}, manager.revision
    )
    await manager.async_put({"day": "2025-09-15"}, manager.revision)
    await manager.async_put(
        {"day": "2026-03-15", "invoice_balance": "0"}, manager.revision
    )
    row = manager.records[1]
    await manager.async_put({"id": row.id, "day": "2025-10-15"}, manager.revision)
    assert manager.data["records"][1]["period_balance"] == "1100"
    assert manager.data["records"][2]["period_balance"] == "-2050"
    await record(hass, "2025-10-15", "2100", "4125", offset=0.5)
    await manager.async_refresh_sample(row.id, manager.revision)
    assert manager.data["records"][1]["period_balance"] == "1200"
    assert manager.data["records"][2]["period_balance"] == "-2150"
    frozen = manager.export()
    await record(hass, "2025-11-15", "1", "5000")
    with pytest.raises(LedgerError, match="zmalał"):
        await manager.async_put({"day": "2025-11-15"}, manager.revision)
    assert manager.export() == frozen
    hass.states.async_set(SOURCE, "10", {"unit_of_measurement": "kWh"})
    await hass.async_block_till_done()
    assert manager.data["current"]["estimated_balance"] is None
    assert "zmalał" in manager.data["source_error"]
