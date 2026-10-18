"""Exercise native Lovelace storage and the complete HA frontend in Chromium."""

import json
import shutil
import time
from unittest.mock import patch

import pytest
from homeassistant.components.http.config import async_get_and_load_store
from homeassistant.components.lovelace.const import LOVELACE_DATA
from homeassistant.components.lovelace.resources import ResourceYAMLCollection
from playwright.async_api import async_playwright, expect

from custom_components.pge_storage.const import CARD_URL, DOMAIN
from custom_components.pge_storage.resources import async_register_card

pytestmark = pytest.mark.asyncio(loop_scope="module")


async def test_resource_upgrade_is_idempotent_and_preserves_other_cards(ha):
    hass, _ = ha
    resources = hass.data[LOVELACE_DATA].resources
    original = next(item for item in resources.async_items() if item["url"] == CARD_URL)
    other = await resources.async_create_item(
        {"url": "/local/another-card.js?v=1", "res_type": "module"}
    )
    await resources.async_update_item(
        original["id"],
        {"url": "/pge_storage/pge-storage-card.js?v=0.2.0", "res_type": "js"},
    )
    await resources.async_create_item(
        {"url": "/pge_storage/pge-storage-card.js", "res_type": "module"}
    )
    await async_register_card(hass)
    await async_register_card(hass)
    assert resources.async_items() == [
        {**original, "url": CARD_URL, "type": "module"},
        other,
    ]


async def test_yaml_resources_remain_user_managed(ha, caplog):
    hass, _ = ha
    yaml = ResourceYAMLCollection([{"url": "/local/custom.js", "type": "module"}])
    with patch.object(hass.data[LOVELACE_DATA], "resources", yaml):
        await async_register_card(hass)
    assert yaml.async_items() == [{"url": "/local/custom.js", "type": "module"}]
    assert CARD_URL in caplog.text


async def test_card_loads_on_real_lovelace_dashboard(ha):
    hass, port = ha
    # This is an isolated HA with synthetic users and sources, never a live HA.
    hass.data["onboarding"].onboarded = True
    hass.states.async_set(
        "sensor.browser_import", "7410", {"unit_of_measurement": "kWh"}
    )
    hass.states.async_set(
        "sensor.browser_export", "10000", {"unit_of_measurement": "kWh"}
    )
    flow = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    result = await hass.config_entries.flow.async_configure(
        flow["flow_id"],
        {
            "import_entity_id": "sensor.browser_import",
            "export_entity_id": "sensor.browser_export",
            "max_age_hours": 1,
        },
    )
    assert result["type"] == "create_entry"
    await hass.async_block_till_done()
    # Confirm the isolated server's random port so its setup dialog does not
    # cover the dashboard during real mouse and form interactions.
    http_store = await async_get_and_load_store(hass)
    if http_store.pending is not None:
        await http_store.async_promote_pending()
    origin = f"http://127.0.0.1:{port}"
    user = await hass.auth.async_create_user("Browser test", group_ids=["system-admin"])
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
            context = await browser.new_context()
            await context.add_init_script(
                f"localStorage.setItem('hassTokens', {json.dumps(json.dumps(tokens))});"
            )
            page = await context.new_page()
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            response = await page.goto(f"{origin}/dashboard-pge-test/magazyn")
            assert response.status == 200
            # Global extra JS executes before HA installs its element registry.
            # The module must instead be requested by Lovelace after that point.
            assert CARD_URL not in await response.text()
            period = page.locator("pge-energy-card h2")
            await expect(period).to_contain_text("Energia w domu", timeout=30000)
            await expect(page.locator("pge-balance-card").first).to_contain_text(
                "Magazyn PGE"
            )
            assert await page.evaluate(
                "typeof customElements.get('pge-storage-card') === 'function'"
            )
            await page.reload()
            await expect(period).to_contain_text("Energia w domu", timeout=30000)

            async def select_text(locator):
                await locator.scroll_into_view_if_needed()
                await locator.click(trial=True)
                positions = await locator.evaluate(
                    """element => {
                        const range = document.createRange();
                        range.selectNodeContents(element);
                        const rects = [...range.getClientRects()];
                        const first = rects[0], last = rects.at(-1);
                        return {x1: first.left + 1, y1: first.top + first.height / 2,
                                x2: last.right - 1, y2: last.top + last.height / 2};
                    }"""
                )
                await page.mouse.move(positions["x1"], positions["y1"])
                await page.mouse.down()
                await page.mouse.move(positions["x2"], positions["y2"], steps=20)
                await page.mouse.up()
                return await page.evaluate("window.getSelection().toString()")

            assert "Energia w domu" in await select_text(
                page.locator("pge-energy-card h2")
            )
            await page.locator("pge-settings-card #open-invoices").click()
            await expect(page.locator("pge-admin-panel #day")).to_be_visible()
            await page.locator("pge-admin-panel #day").fill("2025-01-01")
            await page.locator("pge-admin-panel #invoice").fill("0")
            await page.locator('pge-admin-panel #editor button[type="submit"]').click()
            error = page.locator("pge-admin-panel #message")
            await expect(error).to_contain_text("Brak próbki Recorder")
            assert "Brak próbki Recorder" in await select_text(error)
            assert not errors, errors
        finally:
            await browser.close()
