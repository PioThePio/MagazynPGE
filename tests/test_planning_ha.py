import asyncio
import json
import shutil
import time
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import aiohttp
import pytest
from homeassistant.components.http.config import async_get_and_load_store
from homeassistant.components.recorder.models.statistics import StatisticMeanType
from homeassistant.components.recorder.statistics import async_import_statistics
from homeassistant.components.recorder.tasks import SynchronizeTask
from homeassistant.const import EVENT_STATE_CHANGED
from homeassistant.core import State
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.recorder import get_instance
from playwright.async_api import async_playwright, expect

from custom_components.pge_storage.ledger import LedgerError, boundary
from custom_components.pge_storage.planning_history import async_seasonal_profile

pytestmark = pytest.mark.asyncio(loop_scope="module")
SOURCES = {"import": "sensor.planning_import", "export": "sensor.planning_export"}


async def record(hass, day, imported, exported):
    moment = boundary(day) - timedelta(minutes=1)
    for name, value in [("import", imported), ("export", exported)]:
        state = State(
            SOURCES[name],
            str(value),
            {"unit_of_measurement": "kWh"},
            last_updated=moment,
        )
        hass.bus.async_fire_internal(
            EVENT_STATE_CHANGED,
            {"entity_id": SOURCES[name], "old_state": None, "new_state": state},
            time_fired=moment.timestamp(),
        )
    await hass.async_block_till_done()
    future = hass.loop.create_future()
    get_instance(hass).queue_task(SynchronizeTask(future))
    await asyncio.wait_for(future, 10)


async def test_plan_daily_api_and_durable_month_boundaries(ha):
    hass, port = ha
    for name, value in [("import", "1020"), ("export", "1050")]:
        hass.states.async_set(SOURCES[name], value, {"unit_of_measurement": "kWh"})
    flow = await hass.config_entries.flow.async_init(
        "pge_storage", context={"source": "user"}
    )
    result = await hass.config_entries.flow.async_configure(
        flow["flow_id"],
        {
            "import_entity_id": SOURCES["import"],
            "export_entity_id": SOURCES["export"],
            "max_age_hours": 24,
        },
    )
    await hass.async_block_till_done()
    entry = result["result"]
    manager = entry.runtime_data
    for day, imported, exported in [
        ("2026-08-31", 1000, 1000),
        ("2026-09-01", 1005, 1010),
        ("2026-09-30", 1010, 1025),
    ]:
        await record(hass, day, imported, exported)
    await manager.async_put(
        {"day": "2026-08-31", "invoice_balance": "200"}, manager.revision
    )
    planning = {
        "anchor_id": manager.records[0].id,
        "lots": [{"month": "2026-05", "export_kwh": "250", "expires_on": "2027-05-31"}],
        "profile": [
            {"month": month, "import_kwh": "31", "export_kwh": "0"}
            for month in range(1, 13)
        ],
        "target_day": "2027-03-31",
    }
    user = await hass.auth.async_create_user(
        "Planning admin", group_ids=["system-admin"]
    )
    refresh = await hass.auth.async_create_refresh_token(
        user, client_id="http://pge.test/"
    )
    token = hass.auth.async_create_access_token(refresh)
    async with (
        aiohttp.ClientSession() as session,
        session.ws_connect(f"http://127.0.0.1:{port}/api/websocket") as ws,
    ):
        await ws.receive_json()
        await ws.send_json({"type": "auth", "access_token": token})
        assert (await ws.receive_json())["type"] == "auth_ok"
        await ws.send_json(
            {
                "id": 1,
                "type": "pge_storage/put_plan",
                "revision": manager.revision,
                "planning": planning,
            }
        )
        assert (response := await ws.receive_json())["success"], response
        assert manager.data["planning"]["inventory"]["balance_kwh"] == "220"
        assert manager.data["planning"]["forecast"] is not None
        await ws.send_json({"id": 2, "type": "pge_storage/daily", "month": "2026-09"})
        daily = await ws.receive_json()
        assert daily["success"], daily
        assert daily["result"]["rows"][0]["balance_kwh"] == "203"
        assert daily["result"]["rows"][0]["credited_kwh"] == "8"
        assert daily["result"]["rows"][1]["import_kwh"] is None
    backup = manager.export()
    assert backup["format_version"] == 3
    assert "2026-09-30" in backup["checkpoint_cache"]["samples"]
    # A month boundary already frozen in our Store survives Recorder purging it.
    with patch(
        "custom_components.pge_storage.planning_history.async_read_counters",
        side_effect=AssertionError("Frozen month reread"),
    ):
        assert await hass.config_entries.async_reload(entry.entry_id)
        await hass.async_block_till_done()
    manager = entry.runtime_data
    assert manager.export() == backup
    assert manager.data["planning"]["inventory"]["balance_kwh"] == "220"
    with patch(
        "custom_components.pge_storage.planning_history.async_read_counters",
        side_effect=LedgerError("missing_history", "Purged"),
    ):
        archived = await manager.async_daily("2026-09")
    assert archived["rows"][0]["balance_kwh"] == "203"
    assert archived["rows"][0]["credited_kwh"] == "8"
    before, revision = manager.export(), manager.revision
    with patch.object(
        manager.store, "async_save", new=AsyncMock(side_effect=OSError("full"))
    ):
        with pytest.raises(OSError):
            await manager.async_put_plan(
                {**planning, "target_day": "2027-02-28"}, revision
            )
    assert manager.export() == before and manager.revision == revision
    # Old version-2 copies load with their records intact and no invented lots.
    legacy = {
        key: value
        for key, value in backup.items()
        if key not in ("planning", "checkpoint_cache", "daily_cache")
    }
    legacy["format_version"] = 2
    await manager.async_import(legacy, manager.revision)
    assert manager.records[0].invoice_balance == "200"
    assert manager.data["planning"]["inventory"] is None
    await manager.async_put_plan(planning, manager.revision)
    hass.data["onboarding"].onboarded = True
    http_store = await async_get_and_load_store(hass)
    if http_store.pending is not None:
        await http_store.async_promote_pending()
    origin = f"http://127.0.0.1:{port}"
    refresh = await hass.auth.async_create_refresh_token(user, client_id=f"{origin}/")
    tokens = {
        "hassUrl": origin,
        "clientId": f"{origin}/",
        "access_token": hass.auth.async_create_access_token(refresh),
        "refresh_token": refresh.token,
        "token_type": "Bearer",
        "expires_in": 1800,
        "expires": time.time() * 1000 + 1800000,
    }
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(
            executable_path=shutil.which("chromium"), args=["--no-sandbox"]
        )
        try:
            context = await browser.new_context(
                viewport={"width": 1440, "height": 1000}
            )
            await context.add_init_script(
                f"localStorage.setItem('hassTokens', {json.dumps(json.dumps(tokens))});"
            )
            page = await context.new_page()
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            await page.goto(f"{origin}/dashboard-pge-test/magazyn")
            await expect(page.locator("pge-storage-card #metrics")).to_contain_text(
                "220 kWh", timeout=30000
            )
            await expect(page.locator("pge-storage-card #flow")).to_contain_text(
                "dodano 40 kWh"
            )
            await expect(
                page.locator("pge-storage-card #forecast-table")
            ).to_contain_text("31.03.2027")
            await page.locator(
                'pge-storage-card [data-daily-month="2026-09"] > summary'
            ).click()
            await expect(
                page.locator(
                    'pge-storage-card [data-daily-month="2026-09"] [data-daily-rows] tr'
                ).first
            ).to_contain_text("203", timeout=30000)
            await page.locator("pge-storage-card #plan-settings > summary").click()
            await page.locator(
                'pge-storage-card [data-profile="import"][data-month="10"]'
            ).fill("3100")
            await page.locator(
                'pge-storage-card #plan-editor button[type="submit"]'
            ).click()
            await expect(
                page.locator("pge-storage-card #plan-summary")
            ).to_contain_text("Zapas wyczerpie się")
            await page.locator("pge-storage-card #plan-settings > summary").click()
            await page.locator("pge-storage-card h1").scroll_into_view_if_needed()
            await page.screenshot(path="/tmp/pge-planning-ui.png")
            assert not errors, errors
        finally:
            await browser.close()
    expiring = {
        **planning,
        "lots": [{"month": "2025-09", "export_kwh": "250", "expires_on": "2026-09-30"}],
    }
    await manager.async_put_plan(expiring, manager.revision)
    await hass.async_block_till_done()
    available = er.async_get(hass).async_get_entity_id(
        "sensor", "pge_storage", f"{entry.entry_id}_available_energy"
    )
    assert float(hass.states.get(available).state) == 30
    assert hass.states.get(available).attributes["balance_basis"] == "fifo"


async def test_real_ha_statistics_profile_converts_wh_and_uses_period_changes(ha):
    hass, _port = ha
    start = datetime(2026, 8, 31, 21, tzinfo=UTC)
    for direction, multiplier in [("import", 1), ("export", 2)]:
        async_import_statistics(
            hass,
            {
                "statistic_id": SOURCES[direction],
                "source": "recorder",
                "name": None,
                "unit_class": "energy",
                "unit_of_measurement": "Wh",
                "mean_type": StatisticMeanType.NONE,
                "has_sum": True,
            },
            [
                {
                    "start": start + timedelta(hours=index),
                    "sum": 1000000 + index * multiplier * 1000,
                    "state": 9000000 + index * 1000,
                }
                for index in range(721)
            ],
        )
    await hass.async_block_till_done()
    future = hass.loop.create_future()
    get_instance(hass).queue_task(SynchronizeTask(future))
    await asyncio.wait_for(future, 10)
    result = await async_seasonal_profile(hass, SOURCES)
    september = next(item for item in result["profile"] if item["month"] == 9)
    assert float(september["import_kwh"]) == pytest.approx(720)
    assert september["export_kwh"] == "0"
    assert september["source_month"] == "2026-09"
