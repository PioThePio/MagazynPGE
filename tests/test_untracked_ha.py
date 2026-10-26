"""Untracked consumption has durable HA entities and actual Recorder history."""

import asyncio
from datetime import timedelta
from functools import partial

import pytest
from homeassistant.components.recorder import history
from homeassistant.components.recorder.core import SynchronizeTask
from homeassistant.const import EVENT_STATE_CHANGED
from homeassistant.core import State
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.recorder import get_instance
from homeassistant.util import dt as dt_util

from custom_components.pge_storage.ledger import WARSAW, boundary

pytestmark = pytest.mark.asyncio(loop_scope="module")


async def test_untracked_entities_history_parent_exclusion_and_reload(ha):
    hass, _ = ha
    values = {
        "i": ("100", "kWh"),
        "e": ("100", "kWh"),
        "home_energy": ("1000", "kWh"),
        "ac_energy": ("200", "kWh"),
        "pv": ("2000", "W"),
        "grid": ("500", "W"),
        "charge": ("1000", "W"),
        "ac": ("300", "W"),
        "ac_down": ("100", "W"),
        "ac_up": ("200", "W"),
        "fridge": ("100", "W"),
    }
    ids = {key: f"sensor.untracked_test_{key}" for key in values}
    for key, (value, unit) in values.items():
        hass.states.async_set(ids[key], value, {"unit_of_measurement": unit})
    yesterday = (
        dt_util.utcnow().astimezone(WARSAW).date() - timedelta(days=1)
    ).isoformat()
    moment = boundary(yesterday) - timedelta(minutes=1)
    for key, value in {
        "home_energy": "990",
        "ac_energy": "196",
        "i": "90",
        "e": "90",
    }.items():
        state = State(
            ids[key], value, {"unit_of_measurement": "kWh"}, last_updated=moment
        )
        hass.bus.async_fire_internal(
            EVENT_STATE_CHANGED,
            {
                "entity_id": ids[key],
                "old_state": None,
                "new_state": state,
            },
            time_fired=moment.timestamp(),
        )
    await hass.async_block_till_done()
    recorder = get_instance(hass)
    future = hass.loop.create_future()
    recorder.queue_task(SynchronizeTask(future))
    await asyncio.wait_for(future, 10)
    flow = await hass.config_entries.flow.async_init(
        "pge_storage", context={"source": "user"}
    )
    result = await hass.config_entries.flow.async_configure(
        flow["flow_id"],
        {
            "import_entity_id": ids["i"],
            "export_entity_id": ids["e"],
            "max_age_hours": 24,
        },
    )
    await hass.async_block_till_done()
    entry = result["result"]
    manager = entry.runtime_data
    await manager.async_put_energy(
        {
            "sources": {
                "pv_power": ids["pv"],
                "grid_import_power": ids["grid"],
                "battery_charge_power": ids["charge"],
                "home_energy": ids["home_energy"],
            },
            "consumers": [
                {
                    "id": "ac",
                    "name": "AC",
                    "power": ids["ac"],
                    "energy": ids["ac_energy"],
                },
                {
                    "id": "down",
                    "name": "AC-Dół",
                    "power": ids["ac_down"],
                    "parent_id": "ac",
                },
                {
                    "id": "up",
                    "name": "AC-Góra",
                    "power": ids["ac_up"],
                    "parent_id": "ac",
                },
                {"id": "fridge", "name": "Lodówka", "power": ids["fridge"]},
            ],
        },
        manager.revision,
    )
    await hass.async_block_till_done()
    registry = er.async_get(hass)
    power = registry.async_get_entity_id(
        "sensor", "pge_storage", f"{entry.entry_id}_untracked_power"
    )
    daily = registry.async_get_entity_id(
        "sensor", "pge_storage", f"{entry.entry_id}_untracked_today"
    )
    assert (
        float(hass.states.get(power).state) == 1100
    )  # 2000 + 500 - 1000 - (300 + 100)
    assert (
        float(hass.states.get(daily).state) == 6
    )  # 10 - 4; children do not double count
    assert hass.states.get(power).attributes["state_class"] == "measurement"
    hass.states.async_set(ids["pv"], "2200", {"unit_of_measurement": "W"})
    await hass.async_block_till_done()
    assert float(hass.states.get(power).state) == 1300
    hass.states.async_set(ids["ac"], "400", {"unit_of_measurement": "W"})
    await hass.async_block_till_done()
    assert float(hass.states.get(power).state) == 1200
    future = hass.loop.create_future()
    recorder.queue_task(SynchronizeTask(future))
    await asyncio.wait_for(future, 10)
    rows = await recorder.async_add_executor_job(
        partial(
            history.get_significant_states,
            hass,
            dt_util.utcnow() - timedelta(minutes=1),
            None,
            [power],
            significant_changes_only=False,
            minimal_response=False,
        )
    )
    recorded = {
        float(state.state)
        for state in rows.get(power, [])
        if state.state not in ("unknown", "unavailable")
    }
    assert {1100, 1300, 1200} <= recorded
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert (
        registry.async_get_entity_id(
            "sensor", "pge_storage", f"{entry.entry_id}_untracked_power"
        )
        == power
    )
    assert float(hass.states.get(power).state) == 1200
