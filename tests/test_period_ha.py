import asyncio
from copy import deepcopy
from datetime import UTC, datetime, timedelta

import pytest
from homeassistant.components.recorder.core import SynchronizeTask
from homeassistant.components.recorder.models.statistics import StatisticMeanType
from homeassistant.components.recorder.statistics import (
    async_add_external_statistics,
    async_import_statistics,
)
from homeassistant.const import EVENT_STATE_CHANGED
from homeassistant.core import State
from homeassistant.helpers.recorder import get_instance

from custom_components.pge_storage.ledger import WARSAW
from custom_components.pge_storage.period import async_energy_period

pytestmark = pytest.mark.asyncio(loop_scope="module")


async def test_native_period_sums_units_parent_totals_stock_and_missing_history(ha):
    hass, _ = ha
    begin = datetime(2026, 10, 1, tzinfo=WARSAW).astimezone(UTC)
    core = {"import": "sensor.period_core_i", "export": "sensor.period_core_e"}
    for entity in core.values():
        hass.states.async_set(entity, "200", {"unit_of_measurement": "kWh"})
        moment = begin - timedelta(minutes=1)
        state = State(
            entity, "100", {"unit_of_measurement": "kWh"}, last_updated=moment
        )
        hass.bus.async_fire_internal(
            EVENT_STATE_CHANGED,
            {"entity_id": entity, "old_state": None, "new_state": state},
            time_fired=moment.timestamp(),
        )
    rates = {
        core["import"]: 1000,
        core["export"]: 2000,
        "period:grid_i": 4000,
        "period:grid_e": 500,
        "period:pv": 3000,
        "period:charge": 1000,
        "period:out": 250,
        "period:ac": 2000,
        "period:down": 750,
        "period:broken": 1000,
    }
    for entity, rate in rates.items():
        importer = (
            async_import_statistics
            if entity.startswith("sensor.")
            else async_add_external_statistics
        )
        importer(
            hass,
            {
                "statistic_id": entity,
                "source": "recorder" if entity.startswith("sensor.") else "period",
                "name": None,
                "unit_class": "energy",
                "unit_of_measurement": "Wh",
                "mean_type": StatisticMeanType.NONE,
                "has_sum": True,
            },
            [
                {
                    "start": begin + timedelta(hours=i - 1),
                    "sum": 100000 + i * rate,
                    "state": i % 2 * 1000,
                }
                for i in range(25)
                if not (entity == "period:broken" and i == 12)
            ],
        )
    await hass.async_block_till_done()
    future = hass.loop.create_future()
    get_instance(hass).queue_task(SynchronizeTask(future))
    await asyncio.wait_for(future, 10)
    flow = await hass.config_entries.flow.async_init(
        "pge_storage", context={"source": "user"}
    )
    result = await hass.config_entries.flow.async_configure(
        flow["flow_id"],
        {
            "import_entity_id": core["import"],
            "export_entity_id": core["export"],
            "max_age_hours": 24,
        },
    )
    await hass.async_block_till_done()
    manager = result["result"].runtime_data
    await manager.async_put(
        {"day": "2026-09-30", "invoice_balance": "50"}, manager.revision
    )
    config = {
        "sources": {},
        "statistics": {
            "pv_energy": ["period:pv"],
            "grid_import_energy": ["period:grid_i"],
            "grid_export_energy": ["period:grid_e"],
            "battery_charge_energy": ["period:charge"],
            "battery_discharge_energy": ["period:out"],
        },
        "presence": {"solar": True, "battery": True},
        "consumers": [
            {"id": "AC", "name": "AC", "statistic": "period:ac"},
            {
                "id": "Down",
                "name": "AC-Dół",
                "statistic": "period:down",
                "parent_id": "AC",
            },
        ],
    }
    await manager.async_put_energy(config, manager.revision)
    saved = deepcopy(manager.export())
    now = datetime(2026, 10, 19, 12, tzinfo=UTC)
    result = await async_energy_period(manager, "day", "2026-10-01", now)
    assert result["values"]["pv_energy"] == "72"
    assert result["values"]["home_energy"] == "138"
    assert result["values"]["pge_credited_energy"] == "38.4"
    assert result["values"]["pge_withdrawn_energy"] == "24"
    assert result["consumers"][0]["id"] == "AC"
    assert result["consumer_totals"]["tracked_kwh"] == "48"
    assert result["consumer_totals"]["untracked_kwh"] == "90"
    assert manager.export() == saved
    config["statistics"]["pv_energy"] = ["period:broken"]
    await manager.async_put_energy(config, manager.revision)
    result = await async_energy_period(manager, "day", "2026-10-01", now)
    assert result["values"]["pv_energy"] is None
    assert result["values"]["home_energy"] is None
    assert result["values"]["pge_credited_energy"] == "38.4"
    assert result["values"]["pge_withdrawn_energy"] == "24"
