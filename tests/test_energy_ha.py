import asyncio
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.components.recorder.core import SynchronizeTask
from homeassistant.components.recorder.models.statistics import StatisticMeanType
from homeassistant.components.recorder.statistics import async_import_statistics
from homeassistant.const import EVENT_STATE_CHANGED
from homeassistant.core import State
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.recorder import get_instance
from homeassistant.util import dt as dt_util

from custom_components.pge_storage.ledger import WARSAW, boundary

pytestmark = pytest.mark.asyncio(loop_scope="module")


async def test_energy_sources_aliases_readonly_persistence_and_failed_write(ha):
    hass, _port = ha
    units = {
        "i": "kWh",
        "e": "kWh",
        "pv": "Wh",
        "home": "kWh",
        "pump": "kWh",
        "pv_power": "kW",
        "grid": "kW",
        "battery": "W",
        "soc": "%",
    }
    live = {
        "i": "1008",
        "e": "2010",
        "pv": "1003000",
        "home": "9020",
        "pump": "205",
        "pv_power": "1.5",
        "grid": "-1.5",
        "battery": "500",
        "soc": "72",
    }
    ids = {key: f"sensor.energy_{key}" for key in units}
    for key, value in live.items():
        hass.states.async_set(ids[key], value, {"unit_of_measurement": units[key]})
    day = (dt_util.utcnow().astimezone(WARSAW).date() - timedelta(days=1)).isoformat()
    moment = boundary(day) - timedelta(minutes=1)
    for key, value in {
        "i": "1000",
        "e": "2000",
        "pv": "1000000",
        "home": "9000",
        "pump": "200",
    }.items():
        state = State(
            ids[key], value, {"unit_of_measurement": units[key]}, last_updated=moment
        )
        hass.bus.async_fire_internal(
            EVENT_STATE_CHANGED,
            {"entity_id": ids[key], "old_state": None, "new_state": state},
            time_fired=moment.timestamp(),
        )
    await hass.async_block_till_done()
    future = hass.loop.create_future()
    get_instance(hass).queue_task(SynchronizeTask(future))
    await asyncio.wait_for(future, 10)
    original = {entity_id: hass.states.get(entity_id) for entity_id in ids.values()}
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
    config = {
        "sources": {
            "pv_energy": ids["pv"],
            "home_energy": ids["home"],
            "pv_power": ids["pv_power"],
            "grid_power": ids["grid"],
            "battery_power": ids["battery"],
            "battery_soc": ids["soc"],
        },
        "consumers": [
            {"name": "Pompa", "energy": ids["pump"], "power": ids["battery"]}
        ],
        "directions": {"grid": "import", "battery": "discharge"},
    }
    await manager.async_put_energy(config, manager.revision)
    await hass.async_block_till_done()
    assert manager.data["energy"]["today"]["pv_energy"] == "3"
    assert manager.data["energy"]["today"]["home_energy"] == "20"
    assert manager.data["energy"]["today"]["credited_energy"] is None
    assert manager.data["energy"]["consumers"][0]["today_kwh"] == "5"
    assert manager.data["energy"]["values"]["grid_export_power"] == "1500"
    assert manager.data["energy"]["values"]["grid_import_power"] == "0"
    assert manager.data["energy"]["values"]["battery_discharge_power"] == "500"
    entity_id = er.async_get(hass).async_get_entity_id(
        "sensor", "pge_storage", f"{entry.entry_id}_pv_today"
    )
    assert float(hass.states.get(entity_id).state) == 3
    hass.states.async_set(ids["pv_power"], "2.1", {"unit_of_measurement": "kW"})
    await hass.async_block_till_done()
    assert manager.data["energy"]["values"]["pv_power"] == "2100"
    await manager.async_put({"day": day, "invoice_balance": "200"}, manager.revision)
    before = manager.export()
    with patch.object(
        manager.store, "async_save", new=AsyncMock(side_effect=OSError("full"))
    ):
        with pytest.raises(OSError):
            await manager.async_put_energy({"sources": {}}, manager.revision)
    assert manager.export() == before
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    manager = entry.runtime_data
    assert manager.export() == before
    assert manager.energy_config["consumers"][0]["name"] == "Pompa"
    for entity_id, value in original.items():
        if entity_id != ids["pv_power"]:
            assert hass.states.get(entity_id) is value

    # Real hourly statistics, isolated database, not invented frontend curves.
    now = dt_util.utcnow()
    previous_start = datetime(2025, 9, 30, 21, tzinfo=UTC)
    previous_end = datetime(2026, 3, 31, 22, tzinfo=UTC)
    current_start = datetime(2026, 9, 30, 21, tzinfo=UTC)
    current_end = now.replace(minute=0, second=0, microsecond=0)
    hours = []
    for start, end, rate in (
        (previous_start, previous_end, 1000),
        (current_start, current_end, 500),
    ):
        cursor = start
        index = 0
        while cursor < end:
            hours.append(
                {
                    "start": cursor,
                    "sum": 1000000 + index * rate,
                    "state": 9000000 + index * rate,
                }
            )
            cursor += timedelta(hours=1)
            index += 1
    async_import_statistics(
        hass,
        {
            "statistic_id": ids["i"],
            "source": "recorder",
            "name": None,
            "unit_class": "energy",
            "unit_of_measurement": "Wh",
            "mean_type": StatisticMeanType.NONE,
            "has_sum": True,
        },
        hours,
    )
    async_import_statistics(
        hass,
        {
            "statistic_id": ids["e"],
            "source": "recorder",
            "name": None,
            "unit_class": "energy",
            "unit_of_measurement": "Wh",
            "mean_type": StatisticMeanType.NONE,
            "has_sum": True,
        },
        [{**row, "sum": 1000000, "state": 1000000} for row in hours],
    )
    await hass.async_block_till_done()
    future = hass.loop.create_future()
    get_instance(hass).queue_task(SynchronizeTask(future))
    await asyncio.wait_for(future, 10)
    await manager.async_put_plan(
        {
            "anchor_id": manager.records[-1].id,
            "lots": [
                {"month": "2026-10", "export_kwh": "250", "expires_on": "2027-10-31"}
            ],
            "target_day": "2027-03-31",
        },
        manager.revision,
    )
    october = next(
        row for row in manager.data["comparison"] if row["month"] == "2026-10"
    )
    assert float(october["previous_kwh"]) == pytest.approx(745)
    assert float(october["current_kwh"]) > 0
    assert manager.data["planning"]["forecast"]["complete"] is True
    assert manager.data["planning"]["forecast"]["first_shortfall_day"] is not None
