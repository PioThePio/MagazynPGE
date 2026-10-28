import asyncio
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest
from homeassistant.components.recorder import statistics
from homeassistant.components.recorder.core import SynchronizeTask
from homeassistant.components.recorder.db_schema import StatisticsShortTerm
from homeassistant.components.recorder.models.statistics import StatisticMeanType
from homeassistant.components.recorder.statistics import (
    async_add_external_statistics,
    async_import_statistics,
)
from homeassistant.const import EVENT_STATE_CHANGED
from homeassistant.core import State
from homeassistant.helpers.recorder import get_instance

from custom_components.pge_storage.energy_panel import async_statistics_today
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
    assert result["values"]["pge_credited_energy"] == "19.2"
    assert result["values"]["pge_withdrawn_energy"] == "0"
    assert result["consumers"][0]["id"] == "AC"
    assert result["consumer_totals"]["tracked_kwh"] == "48"
    assert result["consumer_totals"]["untracked_kwh"] == "90"
    assert manager.export() == saved
    # The latest completed hour is not yet compiled; every component uses
    # the same preceding boundary rather than hiding all today's counters.
    current_time = begin + timedelta(hours=23, minutes=15)
    original = statistics.statistics_during_period

    def pending(*args, **kwargs):
        rows = original(*args, **kwargs)
        missing = int((begin + timedelta(hours=22)).timestamp())
        return {
            stat: [row for row in values if int(row["start"]) != missing]
            for stat, values in rows.items()
        }

    with patch.object(statistics, "statistics_during_period", side_effect=pending):
        current = await async_energy_period(manager, "day", "2026-10-01", current_time)
        with patch(
            "custom_components.pge_storage.energy_panel.dt_util.utcnow",
            return_value=current_time,
        ):
            today = await async_statistics_today(hass, manager.energy_config)
    assert current["values"]["home_energy"] == "126.5"
    assert current["values"]["pv_energy"] == "66"
    assert (
        current["coverage"]["period:pv"]["end"]
        == (begin + timedelta(hours=22)).isoformat()
    )
    assert today["values"]["period:pv"] == "66"
    assert today["as_of"] == current["as_of"]
    config["statistics"]["pv_energy"] = ["period:broken"]
    await manager.async_put_energy(config, manager.revision)
    result = await async_energy_period(manager, "day", "2026-10-01", now)
    assert result["values"]["pv_energy"] == "24"
    assert result["values"]["home_energy"] == "90"
    assert result["values"]["pge_credited_energy"] == "19.2"
    assert result["values"]["pge_withdrawn_energy"] == "0"


async def test_year_uses_available_history_and_today_uses_native_five_minute_rows(ha):
    hass, _ = ha
    begin = datetime(2026, 10, 1, tzinfo=WARSAW).astimezone(UTC)
    rates = {
        "fresh:pv": 3000,
        "fresh:grid_i": 4000,
        "fresh:grid_e": 500,
        "fresh:charge": 1000,
        "fresh:out": 250,
        "fresh:ac": 2000,
    }
    for stat, rate in rates.items():
        async_add_external_statistics(
            hass,
            {
                "statistic_id": stat,
                "source": "fresh",
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
            ],
        )
    await hass.async_block_till_done()
    future = hass.loop.create_future()
    get_instance(hass).queue_task(SynchronizeTask(future))
    await asyncio.wait_for(future, 10)
    for entity in ("sensor.fresh_i", "sensor.fresh_e"):
        hass.states.async_set(entity, "0", {"unit_of_measurement": "kWh"})
    flow = await hass.config_entries.flow.async_init(
        "pge_storage", context={"source": "user"}
    )
    configured = await hass.config_entries.flow.async_configure(
        flow["flow_id"],
        {
            "import_entity_id": "sensor.fresh_i",
            "export_entity_id": "sensor.fresh_e",
            "max_age_hours": 24,
        },
    )
    await hass.async_block_till_done()
    manager = configured["result"].runtime_data
    await manager.async_put_energy(
        {
            "sources": {},
            "statistics": {
                "pv_energy": ["fresh:pv"],
                "grid_import_energy": ["fresh:grid_i"],
                "grid_export_energy": ["fresh:grid_e"],
                "battery_charge_energy": ["fresh:charge"],
                "battery_discharge_energy": ["fresh:out"],
            },
            "consumers": [{"id": "AC", "name": "AC", "statistic": "fresh:ac"}],
        },
        manager.revision,
    )
    year = await async_energy_period(
        manager, "year", "2026-01-01", datetime(2026, 10, 19, 12, tzinfo=UTC)
    )
    assert year["values"]["pv_energy"] == "72"
    assert year["values"]["home_energy"] == "138"
    assert year["consumers"][0]["period_kwh"] == "48"
    assert year["partial"] is True

    # Actual native short-term rows use the same sums as hourly statistics.
    recorder = get_instance(hass)
    metadata = await recorder.async_add_executor_job(
        lambda: statistics.get_metadata(
            hass,
            statistic_ids={
                "fresh:pv",
                "fresh:grid_i",
                "fresh:grid_e",
                "fresh:charge",
                "fresh:out",
                "fresh:ac",
            },
        )
    )

    def insert_short():
        with recorder.get_session() as session:
            for stat, rate in {
                "fresh:pv": 3000,
                "fresh:grid_i": 4000,
                "fresh:grid_e": 500,
                "fresh:charge": 1000,
                "fresh:out": 250,
                "fresh:ac": 2000,
            }.items():
                for i in range(4):
                    session.add(
                        StatisticsShortTerm.from_stats(
                            metadata[stat][0],
                            {
                                "start": begin + timedelta(minutes=5 * i - 5),
                                "sum": 100000 + i * rate / 12,
                                "state": i % 2 * 1000,
                            },
                            begin.timestamp(),
                        )
                    )
            session.commit()

    await recorder.async_add_executor_job(insert_short)
    now = begin + timedelta(minutes=17)
    result = await async_energy_period(manager, "day", "2026-10-01", now)
    assert result["values"]["pv_energy"] == "0.75"
    assert float(result["values"]["home_energy"]) == pytest.approx(1.4375)
    assert result["consumers"][0]["period_kwh"] == "0.5"
    with patch(
        "custom_components.pge_storage.energy_panel.dt_util.utcnow", return_value=now
    ):
        today = await async_statistics_today(hass, manager.energy_config)
    assert today["values"]["fresh:pv"] == "0.75"
    assert float(today["home_energy"]) == pytest.approx(1.4375)


async def test_sparse_daylight_pv_preserves_all_home_energy_today_and_closed_day(ha):
    """Regression: 17.32 kWh must not shrink to the shared PV daylight hours."""
    hass, _ = ha
    begin = datetime(2026, 10, 10, tzinfo=WARSAW).astimezone(UTC)
    terms = {
        "sparse:pv": ("pv_energy", 1, 2.47),
        "sparse:grid": ("grid_import_energy", 1, 13.65),
        "sparse:export": ("grid_export_energy", -1, 0.1),
        "sparse:charge": ("battery_charge_energy", -1, 2.2),
        "sparse:discharge": ("battery_discharge_energy", 1, 3.5),
    }
    for stat, (_role, _sign, total) in terms.items():
        if stat == "sparse:pv":
            # The inverter is off overnight. Its last actual cumulative sum
            # is from the preceding afternoon, not from the midnight bucket.
            samples = [(-7, 100), (8, 100.2), (12, 101.4), (16, 100 + total)]
        else:
            samples = [(h, 100 + total * min(h, 20) / 20) for h in range(25)]
        async_add_external_statistics(
            hass,
            {
                "statistic_id": stat,
                "source": "sparse",
                "name": None,
                "unit_class": "energy",
                "unit_of_measurement": "kWh",
                "mean_type": StatisticMeanType.NONE,
                "has_sum": True,
            },
            [
                {"start": begin + timedelta(hours=h - 1), "sum": value, "state": value}
                for h, value in samples
            ],
        )
    await hass.async_block_till_done()
    future = hass.loop.create_future()
    get_instance(hass).queue_task(SynchronizeTask(future))
    await asyncio.wait_for(future, 10)
    for entity in ("sensor.sparse_i", "sensor.sparse_e"):
        hass.states.async_set(entity, "0", {"unit_of_measurement": "kWh"})
    flow = await hass.config_entries.flow.async_init(
        "pge_storage", context={"source": "user"}
    )
    configured = await hass.config_entries.flow.async_configure(
        flow["flow_id"],
        {
            "import_entity_id": "sensor.sparse_i",
            "export_entity_id": "sensor.sparse_e",
            "max_age_hours": 24,
        },
    )
    await hass.async_block_till_done()
    manager = configured["result"].runtime_data
    await manager.async_put_energy(
        {
            "statistics": {
                role: [stat] for stat, (role, _sign, _value) in terms.items()
            },
            "presence": {"solar": True, "battery": True},
        },
        manager.revision,
    )
    closed = await async_energy_period(
        manager, "day", "2026-10-10", begin + timedelta(days=2)
    )
    now = begin + timedelta(hours=22)
    current = await async_energy_period(manager, "day", "2026-10-10", now)
    with patch(
        "custom_components.pge_storage.energy_panel.dt_util.utcnow", return_value=now
    ):
        today = await async_statistics_today(hass, manager.energy_config)
    for result in (closed, current):
        assert float(result["values"]["home_energy"]) == pytest.approx(17.32)
        assert float(result["values"]["pv_energy"]) == pytest.approx(2.47)
        assert float(result["values"]["grid_import_energy"]) == pytest.approx(13.65)
        assert result["home_coverage"]["partial"] is True
    assert float(today["home_energy"]) == pytest.approx(17.32)
    assert today["home_coverage"]["partial"] is True
    # Independent reference: the same native bucket changes used by HA Energy.
    reference = await get_instance(hass).async_add_executor_job(
        lambda: statistics.statistics_during_period(
            hass,
            begin,
            begin + timedelta(days=1),
            set(terms),
            "hour",
            {"energy": "kWh"},
            {"change"},
        )
    )
    expected = sum(
        terms[stat][1]
        * sum(row["change"] for row in rows if row.get("change") is not None)
        for stat, rows in reference.items()
    )
    assert expected == pytest.approx(17.32)
    assert float(closed["values"]["home_energy"]) == pytest.approx(expected)
