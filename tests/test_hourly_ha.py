"""Native Recorder sums, clock boundaries, gaps, durable migration and hourly stock."""

import asyncio
from datetime import UTC, datetime, time, timedelta
from unittest.mock import patch

import pytest
from homeassistant.components.recorder.core import SynchronizeTask
from homeassistant.components.recorder.models.statistics import StatisticMeanType
from homeassistant.components.recorder.statistics import async_import_statistics
from homeassistant.const import EVENT_STATE_CHANGED
from homeassistant.core import State
from homeassistant.helpers.recorder import get_instance
from homeassistant.util import dt as dt_util

from custom_components.pge_storage.hourly import MODEL
from custom_components.pge_storage.ledger import WARSAW

pytestmark = pytest.mark.asyncio(loop_scope="module")


async def prepare(hass, *, missing=False, suffix="ok"):
    date = dt_util.utcnow().astimezone(WARSAW).date() - timedelta(days=2)
    begin = datetime.combine(date, time(), WARSAW).astimezone(UTC)
    sources = {
        "import": f"sensor.hourly_{suffix}_import",
        "export": f"sensor.hourly_{suffix}_export",
    }
    count = int(
        (
            dt_util.utcnow().replace(minute=0, second=0, microsecond=0) - begin
        ).total_seconds()
        // 3600
    )
    for direction, entity in sources.items():
        hass.states.async_set(entity, "5", {"unit_of_measurement": "kWh"})
        moment = begin - timedelta(minutes=1)
        baseline = State(
            entity, "1000", {"unit_of_measurement": "kWh"}, last_updated=moment
        )
        hass.bus.async_fire_internal(
            EVENT_STATE_CHANGED,
            {"entity_id": entity, "old_state": None, "new_state": baseline},
            time_fired=moment.timestamp(),
        )
        totals = [0, 1, 2, 5] if direction == "import" else [0, 1, 4, 5]
        async_import_statistics(
            hass,
            {
                "statistic_id": entity,
                "source": "recorder",
                "name": None,
                "unit_class": "energy",
                "unit_of_measurement": "Wh",
                "mean_type": StatisticMeanType.NONE,
                "has_sum": True,
            },
            [
                {
                    "start": begin + timedelta(hours=i - 1),
                    "sum": 100000 + total * 1000,
                    "state": (1000 if i == 0 else i) * 1000,
                }
                for i, total in [(i, totals[min(i, 3)]) for i in range(count + 1)]
                if not (missing and direction == "export" and i == 2)
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
            "import_entity_id": sources["import"],
            "export_entity_id": sources["export"],
            "max_age_hours": 24,
        },
    )
    await hass.async_block_till_done()
    manager = result["result"].runtime_data
    await manager.async_put(
        {"day": (date - timedelta(days=1)).isoformat(), "invoice_balance": "10"},
        manager.revision,
    )
    return result["result"], begin, sources


async def test_native_reset_sums_hourly_fifo_archive_and_reload(ha):
    hass, _ = ha
    entry, begin, sources = await prepare(hass)
    manager = entry.runtime_data
    # Every counter's state reset to a small number; only native sums carry
    # correct energy. Gross daily P=E=5 would wrongly produce -1 kWh.
    assert manager.data["accounting_model"] == MODEL
    assert manager.data["current"]["period_balance"] == "-0.4"
    assert manager.data["current"]["available_energy"] == "9.6"
    assert len(manager.hourly_cache["hours"]) >= 3
    assert manager.data["hourly"]["sources"]["import"]["entity_id"] == sources["import"]
    await manager.async_refresh_planning_history()
    manager.publish()
    assert len(manager.hourly_cache["hours"]) >= 3
    invoice = manager.records[-1]
    await manager.async_put_plan(
        {
            "anchor_id": invoice.id,
            "lots": [
                {
                    "month": invoice.day[:7],
                    "export_kwh": "12.5",
                    "expires_on": f"{date_year_plus(invoice.day)}",
                }
            ],
            "profile": [],
        },
        manager.revision,
    )
    assert manager.data["planning"]["inventory"]["balance_kwh"] == "9.6"
    exported = manager.export()
    assert exported["format_version"] == 5
    assert len(exported["hourly_cache"]["hours"]) >= 3
    # Simulate purged/unavailable statistics after a restart. Finalized
    # hours survive and are neither counted twice nor replaced by zeros.
    with patch(
        "custom_components.pge_storage.hourly_history.statistics.statistics_during_period",
        return_value={},
    ):
        assert await hass.config_entries.async_reload(entry.entry_id)
        await hass.async_block_till_done()
        manager = entry.runtime_data
        assert manager.data["current"]["available_energy"] == "9.6"
        assert len(manager.hourly_cache["hours"]) >= 3
        assert manager.data["hourly"]["current"]["known"] is False
        await manager.async_import(exported, manager.revision)
        assert manager.data["current"]["available_energy"] == "9.6"
        assert manager.sources == sources


def date_year_plus(day):
    from custom_components.pge_storage.planning import expires_on

    return expires_on(day[:7])


async def test_gap_is_unknown_late_data_repairs_and_no_raw_daily_fallback(ha):
    hass, _ = ha
    entry, begin, sources = await prepare(hass, missing=True, suffix="gap")
    manager = entry.runtime_data
    assert manager.data["current"]["available_energy"] is None
    assert "Brak" in manager.data["accounting_error"]
    async_import_statistics(
        hass,
        {
            "statistic_id": sources["export"],
            "source": "recorder",
            "name": None,
            "unit_class": "energy",
            "unit_of_measurement": "Wh",
            "mean_type": StatisticMeanType.NONE,
            "has_sum": True,
        },
        [{"start": begin + timedelta(hours=1), "sum": 104000, "state": 2000}],
    )
    await hass.async_block_till_done()
    future = hass.loop.create_future()
    get_instance(hass).queue_task(SynchronizeTask(future))
    await asyncio.wait_for(future, 10)
    await manager.async_refresh_planning_history()
    manager.publish()
    assert manager.data["current"]["available_energy"] == "9.6"
    assert manager.data["current"]["net_import_since_settlement_kwh"] == "2"
    assert manager.data["current"]["export_since_settlement_kwh"] == "2"
    assert manager.data["current"]["credited_since_settlement_kwh"] == "1.6"
    assert manager.data["current"]["import_since_settlement_kwh"] == "2"


async def test_ha_reports_latch_diagram_and_live_hour_has_real_sensor_attributes(ha):
    hass, _ = ha
    entry, _, sources = await prepare(hass, suffix="live")
    manager = entry.runtime_data
    hass.states.async_set("sensor.clock_pv", "1000", {"unit_of_measurement": "W"})
    await manager.async_put_energy(
        {
            "sources": {"pv_power": "sensor.clock_pv"},
            "flow_clock_source": "sensor.clock_pv",
        },
        manager.revision,
    )
    # Unchanged states emit state_reported rather than state_changed in HA.
    hass.states.async_set("sensor.clock_pv", "1000", {"unit_of_measurement": "W"})
    await hass.async_block_till_done()
    before = manager.data["energy"]["diagram_frame"]["sequence"]
    hass.states.async_set("sensor.clock_pv", "1000", {"unit_of_measurement": "W"})
    await hass.async_block_till_done()
    assert manager.data["energy"]["diagram_frame"]["sequence"] == before
    assert len(manager.aligned_flow.reports["sensor.clock_pv"]) >= 2
    frozen = manager.data["energy"]["diagram_frame"]["sequence"]
    now = dt_util.utcnow()
    manager.hourly_live_context = {
        "start": now.replace(minute=0, second=0, microsecond=0).isoformat(),
        "positions": {
            direction: {
                "opening_sum": "100",
                "sum": "100",
                "state": "5",
                "end": now.isoformat(),
            }
            for direction in sources
        },
    }
    hass.states.async_set(sources["import"], "6", {"unit_of_measurement": "kWh"})
    await hass.async_block_till_done()
    assert manager.data["energy"]["diagram_frame"]["sequence"] == frozen
    assert manager.data["energy"]["hourly_current"]["balance_kwh"] == "1"
    assert manager.data["current"]["available_energy"] == "9.6"
    assert manager.data["current"]["opust_deduction_since_settlement_kwh"] == "0.4"
    assert manager.data["hourly"]["current"]["net_kwh"] == "-1"
    entity = manager.data["entities"]["hourly_balance"]
    state = hass.states.get(entity)
    assert float(state.state) == 1
    assert state.attributes["known"] is True
    assert state.attributes["provisional"] is True
    assert state.attributes["quality"] == "live_native_projection"
    assert state.attributes["start"] != state.attributes["end"]
    hass.states.async_set(
        sources["import"], "unavailable", {"unit_of_measurement": "kWh"}
    )
    await hass.async_block_till_done()
    assert hass.states.get(entity).state == "unavailable"
