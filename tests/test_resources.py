"""Exercise native Lovelace storage and the complete HA frontend in Chromium."""

import json
import re
import shutil
import time
from datetime import timedelta
from unittest.mock import patch

import pytest
from homeassistant.components.http.config import async_get_and_load_store
from homeassistant.components.lovelace.const import LOVELACE_DATA
from homeassistant.components.lovelace.resources import ResourceYAMLCollection
from homeassistant.helpers.event import async_track_time_interval
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
    # Populate independent consumers so the layout regression cannot pass merely
    # because an empty device list was omitted from the flow card.
    for entity_id, value in {
        "sensor.browser_pv_power": "2500",
        "sensor.browser_grid_power": "900",
        "sensor.browser_pump_power": "800",
    }.items():
        hass.states.async_set(entity_id, value, {"unit_of_measurement": "W"})
    hass.states.async_set(
        "sensor.browser_battery_soc", "15", {"unit_of_measurement": "%"}
    )
    manager = hass.data[DOMAIN][result["result"].entry_id]
    await manager.async_put_energy(
        {
            "sources": {
                "pv_power": "sensor.browser_pv_power",
                "grid_power": "sensor.browser_grid_power",
            },
            "presence": {"battery": False},
            "consumers": [
                {"name": "Pompa ciepła", "power": "sensor.browser_pump_power"}
            ],
        },
        manager.revision,
    )

    # Real PV devices keep reporting unchanged power. Reproduce that cadence
    # so a slow CI browser does not turn a synthetic healthy source stale.
    async def report_pv(_now):
        for entity in ("sensor.browser_pv_power", "sensor.browser_pv_second_power"):
            state = hass.states.get(entity)
            if state is not None:
                hass.states.async_set(entity, state.state, dict(state.attributes))

    result["result"].async_on_unload(
        async_track_time_interval(hass, report_pv, timedelta(seconds=5))
    )
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
            context = await browser.new_context(
                viewport={"width": 1440, "height": 1000}
            )
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
            await page.locator("pge-settings-card #close-dialog").click()

            async def check_flow_geometry():
                flow = page.locator("pge-energy-card .flow-map")
                geometry = await flow.evaluate(
                    """element => ({
                        bounds: element.getBoundingClientRect().toJSON(),
                        circles: [...element.querySelectorAll('.node')].map(
                            node => node.getBoundingClientRect().toJSON()),
                        nodes: [...element.querySelectorAll('.node')].map(
                            node => node.getBoundingClientRect().toJSON()),
                        cardBottom: element.closest('ha-card').getBoundingClientRect().bottom,
                        card: {
                            width: element.closest('ha-card').clientWidth,
                            scrollWidth: element.closest('ha-card').scrollWidth,
                        },
                    })"""
                )
                assert len(geometry["circles"]) == 5
                assert (
                    geometry["card"]["scrollWidth"] <= geometry["card"]["width"] + 1
                ), geometry
                bounds = geometry["bounds"]
                assert (
                    max(node["bottom"] for node in geometry["nodes"]) + 4
                    <= (geometry["cardBottom"])
                ), geometry
                for index, circle in enumerate(geometry["circles"]):
                    assert circle["width"] > 0
                    assert circle["left"] >= bounds["left"] - 1, geometry
                    assert circle["right"] <= bounds["right"] + 1, geometry
                    for other in geometry["circles"][index + 1 :]:
                        dx = (
                            circle["x"]
                            + circle["width"] / 2
                            - (other["x"] + other["width"] / 2)
                        )
                        dy = (
                            circle["y"]
                            + circle["height"] / 2
                            - (other["y"] + other["height"] / 2)
                        )
                        # Compare circle boundaries, not their rectangular boxes.
                        assert (dx * dx + dy * dy) ** 0.5 + 1 >= (
                            circle["width"] + other["width"]
                        ) / 2, geometry

            async def check_legacy_stack():
                legacy = page.locator("pge-storage-card")
                stacks = await legacy.locator(".layout > .stack").evaluate_all(
                    "elements => elements.map(node => node.getBoundingClientRect().toJSON())"
                )
                assert len(stacks) == 2
                assert stacks[1]["top"] >= stacks[0]["bottom"] - 1, stacks
                dimensions = await legacy.evaluate(
                    "node => ({width: node.clientWidth, scrollWidth: node.scrollWidth})"
                )
                assert dimensions["scrollWidth"] <= dimensions["width"] + 1

            await expect(page.locator("pge-consumers-card")).to_contain_text(
                "Pompa ciepła"
            )
            await expect(page.locator("pge-energy-card .consumer")).to_have_count(0)
            await expect(page.locator("pge-energy-card [data-mode]")).to_have_count(0)
            await expect(page.locator("pge-consumers-card [data-mode]")).to_have_count(
                0
            )
            await expect(page.locator("pge-energy-card .node-pv")).to_contain_text(
                "2500 W"
            )
            await expect(page.locator("pge-energy-card .node-pv")).to_contain_text(
                "kWh"
            )
            await expect(page.locator("pge-energy-card .node-pv")).to_contain_text(
                "kWh"
            )
            await expect(page.locator("pge-energy-card .node-home")).to_contain_text(
                "3400 W"
            )
            await expect(
                page.locator("pge-consumers-card .device:not(.untracked)")
            ).to_contain_text("800 W")
            await expect(
                page.locator("pge-consumers-card .device:not(.untracked)")
            ).to_contain_text("kWh")
            # Missing instantaneous W readings count as zero without hiding
            # the production measured by another PV installation.
            hass.states.async_set(
                "sensor.browser_pv_second_power",
                "500",
                {"unit_of_measurement": "W"},
            )
            single_pv = manager.energy_config
            await manager.async_put_energy(
                {
                    **single_pv,
                    "sources": {
                        **single_pv["sources"],
                        "pv_power": [
                            "sensor.browser_pv_power",
                            "sensor.browser_pv_second_power",
                        ],
                    },
                },
                manager.revision,
            )
            await expect(page.locator("pge-energy-card .node-pv")).to_contain_text(
                "3000 W"
            )
            await expect(page.locator("pge-energy-card .node-home")).to_contain_text(
                "3900 W"
            )
            hass.states.async_set(
                "sensor.browser_pv_power",
                "unavailable",
                {"unit_of_measurement": "W"},
            )
            await hass.async_block_till_done()
            await expect(page.locator("pge-energy-card .node-pv")).to_contain_text(
                "500 W", timeout=35000
            )
            await expect(page.locator("pge-energy-card .node-home")).to_contain_text(
                "1400 W", timeout=35000
            )
            hass.states.async_set(
                "sensor.browser_pv_second_power",
                "unavailable",
                {"unit_of_measurement": "W"},
            )
            await hass.async_block_till_done()
            await expect(page.locator("pge-energy-card .node-pv strong")).to_have_text(
                "0 W", timeout=35000
            )
            await expect(page.locator("pge-energy-card .node-home")).to_contain_text(
                "900 W", timeout=35000
            )
            await page.screenshot(path="/tmp/pge-09-pv-outage.png", full_page=True)
            hass.states.async_set(
                "sensor.browser_pv_power", "2500", {"unit_of_measurement": "W"}
            )
            await manager.async_put_energy(single_pv, manager.revision)
            await expect(page.locator("pge-energy-card .node-home")).to_contain_text(
                "3400 W"
            )
            # Stored kWh is optional: selecting SOC and usable capacity is
            # sufficient, and the dialog previews the result before saving.
            await page.locator("pge-settings-card #open-sources").click()
            await page.locator(
                "pge-settings-card [data-source=battery_soc]"
            ).select_option("sensor.browser_battery_soc")
            await page.locator("pge-settings-card [data-capacity]").fill("10")
            await expect(
                page.locator("pge-settings-card [data-source=battery_stored]")
            ).to_have_value("")
            await expect(
                page.locator("pge-settings-card #battery-estimate")
            ).to_contain_text("1,5 kWh")
            await page.screenshot(
                path="/tmp/pge-09-battery-settings.png", full_page=True
            )
            await page.locator("pge-settings-card #save-sources").click()
            await expect(
                page.locator("pge-settings-card #source-status")
            ).to_contain_text("Źródła zapisane")
            await page.locator("pge-settings-card #close-dialog").click()
            await expect(page.locator("pge-energy-card .node-battery")).to_contain_text(
                "15%"
            )
            await expect(page.locator("pge-energy-card .node-home")).to_contain_text(
                "3400 W"
            )
            await check_flow_geometry()
            await page.screenshot(path="/tmp/pge-09-desktop.png", full_page=True)

            # This reproduces the user's desktop screenshot: a narrow HA card
            # in a wide browser must follow its own width, not the viewport.
            await page.locator("pge-storage-card").evaluate(
                """async node => {
                    node.style.width = '500px';
                    node.style.maxWidth = '100%';
                    node.style.margin = '0 auto';
                    await new Promise(requestAnimationFrame);
                }"""
            )
            await check_legacy_stack()
            await check_flow_geometry()
            await page.screenshot(path="/tmp/pge-09-narrow.png", full_page=True)
            await page.set_viewport_size({"width": 390, "height": 844})
            await check_legacy_stack()
            await check_flow_geometry()
            await page.screenshot(path="/tmp/pge-09-mobile.png", full_page=True)

            await page.set_viewport_size({"width": 1440, "height": 1000})
            await page.locator("pge-settings-card #create-dashboard").click()
            link = page.locator("pge-settings-card #open-dashboard")
            await expect(link).to_be_visible()
            url = await link.get_attribute("href")
            assert url.startswith("/pge-energia-") and url.endswith("/magazyn")
            await link.click()
            await expect(page).to_have_url(f"{origin}{url}")
            await expect(page.locator("pge-storage-card")).to_have_count(0)
            await expect(page.locator("pge-energy-card")).to_have_count(1)
            await expect(page.locator("pge-consumers-card")).to_have_count(1)
            await expect(page.locator("pge-balance-card")).to_have_count(3)
            for tag in (
                "pge-energy-card",
                "pge-consumers-card",
                "pge-projection-card",
                "pge-history-card",
                "pge-settings-card",
            ):
                card = page.locator(tag)
                await expect(card).to_be_visible()
                ancestors = await card.evaluate(
                    """element => {
                        const tags = [];
                        for (let node = element; node; node = node.parentElement || node.getRootNode().host)
                            tags.push(node.localName);
                        return tags;
                    }"""
                )
                # Each component is its own HA editing target, with no nested
                # monolithic compatibility card anywhere in its ancestor chain.
                assert "hui-card" in ancestors, ancestors
                assert "pge-storage-card" not in ancestors, ancestors
            await expect(page.locator("pge-energy-card .node-home")).to_contain_text(
                "3400 W"
            )
            await expect(page.locator("pge-energy-card .node-home")).to_contain_text(
                "kWh"
            )
            await check_flow_geometry()
            await page.locator('pge-energy-card [data-period="month"]').click()
            await expect(
                page.locator('pge-energy-card [data-period="month"]')
            ).to_have_attribute("aria-pressed", "true")
            current_month = await page.locator("pge-energy-card").evaluate(
                "node => node.anchor.slice(0,7)"
            )
            await page.locator('pge-energy-card [data-shift="-1"]').click()
            previous_month = await page.locator("pge-energy-card").evaluate(
                "node => node.anchor.slice(0,7)"
            )
            assert current_month != previous_month
            await expect(
                page.locator("pge-energy-card .node-home strong")
            ).to_have_text("3400 W")
            await page.locator("pge-energy-card [data-current]").click()
            await page.locator('pge-energy-card [data-period="day"]').click()
            for entity_id, value in {
                "sensor.ac": "300.2",
                "sensor.ac_down": "100.1",
                "sensor.ac_up": "200.1",
            }.items():
                hass.states.async_set(entity_id, value, {"unit_of_measurement": "W"})
            await manager.async_put_energy(
                {
                    **manager.energy_config,
                    "consumers": [
                        *manager.energy_config["consumers"],
                        {"id": "ac", "name": "AC", "power": "sensor.ac"},
                        {
                            "id": "ac_down",
                            "name": "AC-Dół",
                            "power": "sensor.ac_down",
                            "parent_id": "ac",
                        },
                        {
                            "id": "ac_up",
                            "name": "AC-Góra",
                            "power": "sensor.ac_up",
                            "parent_id": "ac",
                        },
                    ],
                },
                manager.revision,
            )
            await expect(
                page.locator("pge-consumers-card [data-folder]")
            ).to_have_count(0)
            await expect(
                page.locator('pge-consumers-card [data-consumer-id="ac_down"]')
            ).to_contain_text("100 W")
            await expect(
                page.locator("pge-consumers-card .consumer-summary")
            ).to_contain_text(re.compile(r"1\s?100 W"))
            await expect(page.locator("pge-consumers-card .untracked")).to_contain_text(
                re.compile(r"2\s?300 W")
            )
            untracked = page.locator("pge-consumers-card .untracked")
            await untracked.scroll_into_view_if_needed()
            before = await untracked.evaluate("""row => {
              window.pgeScrollNodes = [];
              for (let n = row; n; n = n.parentElement || n.getRootNode()?.host) {
                if (n.scrollHeight > n.clientHeight + 1)
                  window.pgeScrollNodes.push({node:n, top:n.scrollTop});
              }
              window.pgeMountedCard = row.getRootNode().querySelector('ha-card');
              return window.pgeScrollNodes.map(x => x.top);
            }""")
            hass.states.async_set(
                "sensor.browser_pv_power", "2600", {"unit_of_measurement": "W"}
            )
            await expect(untracked).to_contain_text(re.compile(r"2\s?400 W"))
            after = await untracked.evaluate("""row => {
              if (window.pgeMountedCard !== row.getRootNode().querySelector('ha-card'))
                throw new Error('Live update replaced mounted card');
              return window.pgeScrollNodes.map(x => x.node.scrollTop);
            }""")
            assert after == before
            hass.states.async_set(
                "sensor.browser_pv_power", "2500", {"unit_of_measurement": "W"}
            )
            await page.locator('pge-consumers-card [data-sort="name"]').click()
            await expect(
                page.locator('pge-consumers-card [data-sort="name"]')
            ).to_have_attribute("aria-pressed", "true")
            await page.locator("pge-consumers-card select[data-average]").select_option(
                "10"
            )
            await expect(
                page.locator("pge-consumers-card select[data-average]")
            ).to_have_value("10")
            await expect(
                page.locator("pge-consumers-card .untracked .device-average")
            ).to_contain_text("W")
            await expect(page.locator("pge-energy-card .period-note")).to_have_count(0)
            await expect(
                page.locator("pge-consumers-card .device-header [data-sort]")
            ).to_have_count(4)
            await expect(
                page.locator("pge-consumers-card .sort-options")
            ).to_have_count(0)
            await page.locator('pge-consumers-card [data-sort="name"]').click()
            await expect(
                page.locator(
                    'pge-consumers-card .device-header [aria-sort="descending"]'
                )
            ).to_contain_text("Nazwa")
            await page.locator('pge-consumers-card [data-sort="name"]').click()

            await page.locator("pge-settings-card #open-sources").click()
            await page.locator("pge-settings-card [data-capacity-mode]").select_option(
                "ah"
            )
            await page.locator("pge-settings-card [data-capacity-ah]").fill("99")
            await expect(
                page.locator("pge-settings-card #battery-estimate")
            ).to_contain_text("napięcie nominalne")
            await page.locator("pge-settings-card [data-voltage]").fill("51.2")
            await expect(
                page.locator("pge-settings-card #battery-estimate")
            ).to_contain_text("5,07 kWh")
            await page.locator("pge-settings-card #save-sources").click()
            await expect(
                page.locator("pge-settings-card #source-status")
            ).to_contain_text("Źródła zapisane")
            assert manager.energy_config["consumers"][-1]["parent_id"] == "ac"
            await page.locator("pge-settings-card #close-dialog").click()
            await page.screenshot(path="/tmp/pge-09-native-desktop.png", full_page=True)
            await page.set_viewport_size({"width": 390, "height": 844})
            await check_flow_geometry()
            await page.screenshot(path="/tmp/pge-09-native-mobile.png", full_page=True)
            assert not errors, errors
        finally:
            await browser.close()
