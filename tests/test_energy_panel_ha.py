import asyncio
from copy import deepcopy
from datetime import UTC, datetime, time, timedelta

import pytest
from homeassistant.components.energy.data import async_get_manager
from homeassistant.components.recorder.core import SynchronizeTask
from homeassistant.components.recorder.models.statistics import StatisticMeanType
from homeassistant.components.recorder.statistics import (
    async_add_external_statistics,
    async_import_statistics,
)
from homeassistant.const import EVENT_STATE_CHANGED
from homeassistant.core import State
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.recorder import get_instance
from homeassistant.util import dt as dt_util

from custom_components.pge_storage.ledger import WARSAW, LedgerError

pytestmark = pytest.mark.asyncio(loop_scope="module")


async def test_native_energy_autofill_statistics_resets_home_and_manual_override(ha):
    hass, _port = ha
    now = dt_util.utcnow()
    midnight = datetime.combine(
        now.astimezone(WARSAW).date(), time(), WARSAW
    ).astimezone(UTC)
    end = now.replace(minute=0, second=0, microsecond=0)
    count = int((end - midnight).total_seconds() / 3600)
    core = {"import": "sensor.raw_import", "export": "sensor.raw_export"}
    for entity_id, value in [(core["import"], "1010"), (core["export"], "2005")]:
        hass.states.async_set(entity_id, value, {"unit_of_measurement": "kWh"})
    for entity_id, value in [(core["import"], "1000"), (core["export"], "2000")]:
        moment = midnight - timedelta(minutes=1)
        state = State(
            entity_id, value, {"unit_of_measurement": "kWh"}, last_updated=moment
        )
        hass.bus.async_fire_internal(
            EVENT_STATE_CHANGED,
            {"entity_id": entity_id, "old_state": None, "new_state": state},
            time_fired=moment.timestamp(),
        )
    rates = {
        "sensor.native_import": 2000,
        "sensor.native_export": 250,
        "sensor.pv": 3000,
        "sensor.charge": 750,
        "sensor.discharge": 500,
        "supplier:pump": 1000,
    }
    for entity_id, rate in rates.items():
        if entity_id.startswith("sensor."):
            # These states reset every hour; only statistics sums are suitable.
            hass.states.async_set(entity_id, "5", {"unit_of_measurement": "Wh"})
        importer = (
            async_import_statistics
            if entity_id.startswith("sensor.")
            else async_add_external_statistics
        )
        importer(
            hass,
            {
                "statistic_id": entity_id,
                "source": "recorder" if entity_id.startswith("sensor.") else "supplier",
                "name": None,
                "unit_class": "energy",
                "unit_of_measurement": "Wh",
                "mean_type": StatisticMeanType.NONE,
                "has_sum": True,
            },
            [
                {
                    "start": midnight - timedelta(hours=1) + timedelta(hours=index),
                    "sum": 1000000 + index * rate,
                    "state": index % 2 * 1000,
                }
                for index in range(count + 1)
            ],
        )
    for entity_id, value in [
        ("sensor.pv_w", "3000"),
        ("sensor.grid_w", "-500"),
        ("sensor.battery_w", "-100"),
        ("sensor.manual_home", "4000"),
    ]:
        hass.states.async_set(entity_id, value, {"unit_of_measurement": "W"})
    manager = await async_get_manager(hass)
    await manager.async_update(
        {
            "energy_sources": [
                {
                    "type": "grid",
                    "stat_energy_from": "sensor.native_import",
                    "stat_energy_to": "sensor.native_export",
                    "stat_rate": "sensor.grid_w",
                },
                {
                    "type": "solar",
                    "stat_energy_from": "sensor.pv",
                    "stat_rate": "sensor.pv_w",
                    "config_entry_solar_forecast": None,
                },
                {
                    "type": "battery",
                    "stat_energy_from": "sensor.discharge",
                    "stat_energy_to": "sensor.charge",
                    "stat_rate": "sensor.battery_w",
                },
            ],
            "device_consumption": [
                {"stat_consumption": "supplier:pump", "name": "Pompa"}
            ],
        }
    )
    original = deepcopy(manager.data)
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
    entry = result["result"]
    ledger = entry.runtime_data
    assert ledger.energy_config["imported_from_energy"] is True
    assert ledger.sources == core
    assert ledger.data["energy"]["values"]["home_power"] == "2400"
    assert float(ledger.data["energy"]["today"]["home_energy"]) == pytest.approx(
        count * 4.5
    )
    assert float(ledger.data["energy"]["today"]["grid_import_energy"]) == pytest.approx(
        count * 2
    )
    assert ledger.data["energy"]["today"]["credited_energy"] == "4"
    assert float(ledger.data["energy"]["consumers"][0]["today_kwh"]) == pytest.approx(
        count
    )
    entity_id = er.async_get(hass).async_get_entity_id(
        "sensor", "pge_storage", f"{entry.entry_id}_home_power"
    )
    assert float(hass.states.get(entity_id).state) == 2400
    override = deepcopy(ledger.energy_config)
    override["sources"]["home_power"] = "sensor.manual_home"
    await ledger.async_put_energy(override, ledger.revision)
    await hass.async_block_till_done()
    assert ledger.data["energy"]["values"]["home_power"] == "4000"
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.runtime_data.data["energy"]["values"]["home_power"] == "4000"
    assert entry.runtime_data.sources == core
    assert manager.data == original


async def test_missing_imported_pv_keeps_statistics_and_can_be_saved(ha):
    hass, _port = ha
    now = dt_util.utcnow()
    midnight = datetime.combine(
        now.astimezone(WARSAW).date(), time(), WARSAW
    ).astimezone(UTC)
    count = int(
        (now.replace(minute=0, second=0, microsecond=0) - midnight).total_seconds()
        / 3600
    )
    for entity_id in ("sensor.second_core_import", "sensor.second_core_export"):
        hass.states.async_set(entity_id, "1000", {"unit_of_measurement": "kWh"})
    hass.states.async_set("sensor.mppt_energy", "50", {"unit_of_measurement": "kWh"})
    hass.states.async_set("sensor.mppt_power", "1000", {"unit_of_measurement": "W"})
    for entity_id, rate in (
        ("sensor.solar_total_kwh", 1),
        ("sensor.mppt_energy", 2),
        ("sensor.second_core_import", 4),
        ("sensor.second_core_export", 1),
    ):
        async_import_statistics(
            hass,
            {
                "statistic_id": entity_id,
                "source": "recorder",
                "name": None,
                "unit_class": "energy",
                "unit_of_measurement": "kWh",
                "mean_type": StatisticMeanType.NONE,
                "has_sum": True,
            },
            [
                {
                    "start": midnight - timedelta(hours=1) + timedelta(hours=index),
                    "sum": 100 + index * rate,
                    "state": 100 + index * rate,
                }
                for index in range(count + 1)
            ],
        )
    native = await async_get_manager(hass)
    await native.async_update(
        {
            "energy_sources": [
                {
                    "type": "grid",
                    "stat_energy_from": "sensor.second_core_import",
                    "stat_energy_to": "sensor.second_core_export",
                },
                {"type": "solar", "stat_energy_from": "sensor.solar_total_kwh"},
                {
                    "type": "solar",
                    "stat_energy_from": "sensor.mppt_energy",
                    "stat_rate": "sensor.mppt_power",
                },
            ],
            "device_consumption": [],
        }
    )
    original = deepcopy(native.data)
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
            "import_entity_id": "sensor.second_core_import",
            "export_entity_id": "sensor.second_core_export",
            "max_age_hours": 24,
        },
    )
    await hass.async_block_till_done()
    ledger = result["result"].runtime_data
    config = deepcopy(ledger.energy_config)
    assert config["statistics"]["pv_energy"] == [
        "sensor.solar_total_kwh",
        "sensor.mppt_energy",
    ]
    await ledger.async_put_energy(config, ledger.revision)
    assert ledger.data["energy"]["today"]["pv_energy"] == str(count * 3)
    assert ledger.data["energy"]["values"]["pv_power"] == "1000"
    assert ledger.data["energy"]["values"]["home_power"] == "1000"
    assert ledger.data["energy"]["source_status"]["pv_energy"][0]["status"] == "missing"
    assert (
        len(
            [
                item
                for item in ledger.data["energy"]["import_report"]
                if item["type"] == "solar"
            ]
        )
        == 2
    )
    manual = deepcopy(config)
    manual["sources"]["pv_power"] = "sensor.does_not_exist"
    with pytest.raises(LedgerError, match="Sprawdź wartość"):
        await ledger.async_put_energy(manual, ledger.revision)
    # A failed array contributes zero without hiding other arrays or the house.
    for entity_id, value in (
        ("sensor.first_pv_power", "unavailable"),
        ("sensor.grid_import_power", "720"),
        ("sensor.battery_discharge_power", "5"),
    ):
        hass.states.async_set(entity_id, value, {"unit_of_measurement": "W"})
    config["sources"].update(
        {
            "pv_power": ["sensor.first_pv_power", "sensor.mppt_power"],
            "grid_import_power": "sensor.grid_import_power",
            "battery_discharge_power": "sensor.battery_discharge_power",
        }
    )
    await ledger.async_put_energy(config, ledger.revision)
    assert ledger.data["energy"]["values"]["pv_power"] == "1000"
    assert ledger.data["energy"]["values"]["home_power"] == "1725"
    hass.states.async_set(
        "sensor.mppt_power", "unavailable", {"unit_of_measurement": "W"}
    )
    await hass.async_block_till_done()
    assert ledger.data["energy"]["values"]["pv_power"] == "0"
    assert ledger.data["energy"]["values"]["home_power"] == "725"
    assert ledger.data["energy"]["today"]["pv_energy"] == str(count * 3)
    home_entity = er.async_get(hass).async_get_entity_id(
        "sensor", "pge_storage", f"{ledger.entry.entry_id}_home_power"
    )
    assert float(hass.states.get(home_entity).state) == 725
    assert native.data == original


async def test_native_consumer_hierarchy_upgrades_without_replacing_manual_sources(ha):
    hass, _port = ha
    for entity_id, value, unit in (
        ("sensor.hierarchy_import", "100", "kWh"),
        ("sensor.hierarchy_export", "200", "kWh"),
        ("sensor.hierarchy_ac", "100", "kWh"),
        ("sensor.hierarchy_child", "60", "kWh"),
        ("sensor.hierarchy_ac_w", "500", "W"),
        ("sensor.hierarchy_child_w", "200", "W"),
        ("sensor.hierarchy_manual_child_w", "250", "W"),
        ("sensor.hierarchy_home_w", "800", "W"),
        ("sensor.hierarchy_soc", "50", "%"),
    ):
        hass.states.async_set(entity_id, value, {"unit_of_measurement": unit})
    manager = await async_get_manager(hass)
    await manager.async_update(
        {
            "energy_sources": [
                {
                    "type": "grid",
                    "stat_energy_from": "sensor.hierarchy_import",
                    "stat_energy_to": "sensor.hierarchy_export",
                }
            ],
            "device_consumption": [
                {
                    "stat_consumption": "sensor.hierarchy_ac",
                    "stat_rate": "sensor.hierarchy_ac_w",
                    "name": "AC",
                },
                {
                    "stat_consumption": "sensor.hierarchy_child",
                    "stat_rate": "sensor.hierarchy_child_w",
                    "included_in_stat": "sensor.hierarchy_ac",
                    "name": "AC Dół",
                },
            ],
        }
    )
    original = deepcopy(manager.data)
    flow = await hass.config_entries.flow.async_init(
        "pge_storage", context={"source": "user"}
    )
    result = await hass.config_entries.flow.async_configure(
        flow["flow_id"],
        {
            "import_entity_id": "sensor.hierarchy_import",
            "export_entity_id": "sensor.hierarchy_export",
            "max_age_hours": 24,
        },
    )
    await hass.async_block_till_done()
    entry = result["result"]
    ledger = entry.runtime_data
    config = deepcopy(ledger.energy_config)
    assert config["consumers"][1]["parent_id"] == "sensor.hierarchy_ac"
    config["consumers"][1].pop("parent_id")
    config["consumers"][1]["power"] = "sensor.hierarchy_manual_child_w"
    config["sources"]["home_power"] = "sensor.hierarchy_home_w"
    config["sources"]["battery_soc"] = "sensor.hierarchy_soc"
    config["battery_capacity_ah"] = "99"
    config["battery_voltage"] = "51.2"
    await ledger.async_put_energy(config, ledger.revision)
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    ledger = entry.runtime_data
    assert ledger.energy_config["consumers"][1]["parent_id"] == "sensor.hierarchy_ac"
    assert (
        ledger.energy_config["consumers"][1]["power"]
        == "sensor.hierarchy_manual_child_w"
    )
    assert ledger.data["energy"]["consumer_totals"]["tracked_power_w"] == "500"
    assert ledger.data["energy"]["consumer_totals"]["untracked_power_w"] == "300"
    assert ledger.data["energy"]["values"]["battery_stored"] == "2.5344"
    assert ledger.energy_config["battery_capacity_kwh"] is None
    assert manager.data == original
