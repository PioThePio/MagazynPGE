from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from homeassistant.core import State

from custom_components.pge_storage.battery import BatteryEstimate
from custom_components.pge_storage.energy import (
    battery_capacity,
    validate_energy_config,
)
from custom_components.pge_storage.energy_panel import (
    remember_consumer_removals,
    sync_consumers,
)
from custom_components.pge_storage.flow import AlignedFlow
from custom_components.pge_storage.view_history import (
    frames_from_states,
    learn_chunk,
)


def state(entity, number, unit, stamp):
    return State(entity, str(number), {"unit_of_measurement": unit}, last_updated=stamp)


def test_dynamic_capacity_fallback_reserve_and_no_model_reset_for_value_change():
    now = datetime(2026, 10, 28, tzinfo=UTC)
    states = {
        "sensor.cap": state("sensor.cap", 99, "Ah", now),
        "sensor.installed": state("sensor.installed", 100, "Ah", now),
        "sensor.minimum": state("sensor.minimum", 20, "%", now),
    }
    hass = SimpleNamespace(states=SimpleNamespace(get=states.get))
    config = validate_energy_config(
        {
            "battery_capacity_entity": "sensor.cap",
            "battery_installed_capacity_entity": "sensor.installed",
            "battery_voltage": "51.2",
            "battery_forecast": {"min_soc_entity": "sensor.minimum"},
        }
    )
    cap = battery_capacity(config, hass)
    assert float(cap["kwh"]) == pytest.approx(5.0688) and cap["basis"] == "bms_capacity"
    estimate = BatteryEstimate()
    estimate.update(hass, config, {"battery_soc": 60}, now.timestamp())
    estimate.profile = {"95": {"watts": 500, "count": 3}}
    states["sensor.cap"] = state("sensor.cap", 98, "Ah", now)
    result = estimate.update(hass, config, {"battery_soc": 60}, now.timestamp() + 1)
    assert result["stored_kwh"] == pytest.approx(3.01056)
    assert result["available_to_minimum_kwh"] == pytest.approx(2.00704)
    assert estimate.profile["95"]["count"] == 3
    states["sensor.cap"] = state("sensor.cap", "unavailable", "Ah", now)
    assert battery_capacity(config, hass)["basis"] == "installed_capacity_fallback"
    states["sensor.installed"] = state("sensor.installed", "unknown", "Ah", now)
    assert battery_capacity(config, hass)["kwh"] is None


def test_automatic_consumer_additions_preserve_manual_names_bindings_and_removals():
    old = validate_energy_config(
        {
            "consumers": [
                {
                    "id": "a",
                    "name": "Moja nazwa",
                    "energy": "sensor.a",
                    "power": "sensor.manual",
                }
            ]
        }
    )
    native = validate_energy_config(
        {
            "consumers": [
                {
                    "id": "a",
                    "name": "Energia A",
                    "energy": "sensor.a",
                    "power": "sensor.native",
                },
                {"id": "b", "name": "Nowy", "energy": "sensor.b"},
            ]
        }
    )
    merged, notes = sync_consumers(old, native)
    assert merged["consumers"][0] == old["consumers"][0]
    assert len(merged["consumers"]) == 2 and notes
    assert sync_consumers(merged, native)[0] == merged
    changed = validate_energy_config({**merged, "consumers": [merged["consumers"][0]]})
    changed = remember_consumer_removals(merged, changed, native)
    assert len(sync_consumers(changed, native)[0]["consumers"]) == 1
    custom = validate_energy_config(
        {"consumers": [{"id": "custom-parent", "name": "AC", "energy": "sensor.ac"}]}
    )
    with_child = validate_energy_config(
        {
            "consumers": [
                {"id": "native-parent", "name": "AC", "energy": "sensor.ac"},
                {
                    "id": "child",
                    "parent_id": "native-parent",
                    "name": "Dół",
                    "energy": "sensor.down",
                },
            ]
        }
    )
    assert (
        sync_consumers(custom, with_child)[0]["consumers"][1]["parent_id"]
        == "custom-parent"
    )


def test_recorded_power_restores_thirty_minute_means_without_waiting():
    end = datetime(2026, 10, 28, 12, tzinfo=UTC)
    begin = end - timedelta(seconds=1830)
    config = validate_energy_config(
        {
            "sources": {"pv_power": "sensor.pv", "grid_power": "sensor.grid"},
            "consumers": [{"id": "a", "name": "A", "power": "sensor.a"}],
        }
    )
    rows = {
        entity: [state(entity, power, "W", begin)]
        for entity, power in (
            ("sensor.pv", 1000),
            ("sensor.grid", 100),
            ("sensor.a", 400),
        )
    }
    rows["sensor.a"].append(state("sensor.a", 600, "W", end - timedelta(seconds=900)))
    frames, reports, missing = frames_from_states(
        rows, config, {"import": "sensor.i", "export": "sensor.e"}, begin, end
    )
    assert not missing
    flow = AlignedFlow()
    flow.seed(frames, reports, "setup")
    view = frames[-1][1]
    view.pop("power_history_known")
    frame = flow.capture(view, 0, end.timestamp(), "setup", "latest")
    means = frame["energy"]["power_windows"]["1800"]
    assert means["covered_seconds"] == 1800
    assert means["home_power_w"] == 1100
    assert means["consumers"]["a"] == pytest.approx(500, abs=1)
    assert means["untracked_power_w"] == pytest.approx(600, abs=1)


def test_bms_profile_is_reconstructed_only_from_synchronous_eligible_history():
    begin = datetime(2026, 10, 28, 12, tzinfo=UTC)
    config = validate_energy_config(
        {
            "sources": {"battery_soc": "sensor.soc", "battery_power": "sensor.power"},
            "battery_forecast": {
                "learn": True,
                "bms_current_entity": "sensor.limit",
                "voltage_entity": "sensor.voltage",
            },
        }
    )
    rows = {
        entity: [state(entity, number, unit, begin)]
        for entity, number, unit in (
            ("sensor.soc", 96, "%"),
            ("sensor.power", 500, "W"),
            ("sensor.limit", 10, "A"),
            ("sensor.voltage", 50, "V"),
        )
    }
    profile, coverage = learn_chunk(
        rows, config, begin, begin + timedelta(minutes=3), {}
    )
    assert profile == {"95": {"watts": 500, "count": 3}}
    assert coverage == {
        "covered_minutes": 3,
        "eligible_minutes": 3,
        "missing_minutes": 0,
    }
    rows["sensor.power"] = [state("sensor.power", 100, "W", begin)]
    assert not learn_chunk(rows, config, begin, begin + timedelta(minutes=3), {})[0]
    rows.pop("sensor.limit")
    assert (
        learn_chunk(rows, config, begin, begin + timedelta(minutes=3), {})[1][
            "missing_minutes"
        ]
        == 3
    )


@pytest.mark.asyncio(loop_scope="module")
async def test_native_recorder_restores_power_and_bms_samples(ha):
    import asyncio

    from homeassistant.components.recorder.tasks import SynchronizeTask
    from homeassistant.const import EVENT_STATE_CHANGED
    from homeassistant.helpers.recorder import get_instance
    from homeassistant.util import dt as dt_util

    from custom_components.pge_storage.view_history import (
        read_states,
        restore_power_history,
    )

    hass, _ = ha
    now = dt_util.utcnow()
    begin = now - timedelta(minutes=30, seconds=20)
    config = validate_energy_config(
        {
            "battery_capacity_kwh": "5",
            "sources": {
                "pv_power": "sensor.history_pv",
                "grid_power": "sensor.history_grid",
                "battery_soc": "sensor.history_soc",
                "battery_power": "sensor.history_battery",
            },
            "battery_forecast": {
                "learn": True,
                "bms_current_entity": "sensor.history_limit",
                "voltage_entity": "sensor.history_voltage",
            },
        }
    )
    for entity, number, unit in (
        ("sensor.history_pv", 1000, "W"),
        ("sensor.history_grid", 100, "W"),
        ("sensor.history_soc", 96, "%"),
        ("sensor.history_battery", 500, "W"),
        ("sensor.history_limit", 10, "A"),
        ("sensor.history_voltage", 50, "V"),
    ):
        hass.states.async_set(entity, str(number), {"unit_of_measurement": unit})
        recorded = state(entity, number, unit, begin)
        hass.bus.async_fire_internal(
            EVENT_STATE_CHANGED,
            {"entity_id": entity, "old_state": None, "new_state": recorded},
            time_fired=begin.timestamp(),
        )
        recent = now - timedelta(minutes=4, seconds=59)
        hass.bus.async_fire_internal(
            EVENT_STATE_CHANGED,
            {
                "entity_id": entity,
                "old_state": None,
                "new_state": state(entity, number, unit, recent),
            },
            time_fired=recent.timestamp(),
        )
    await hass.async_block_till_done()
    future = hass.loop.create_future()
    get_instance(hass).queue_task(SynchronizeTask(future))
    await asyncio.wait_for(future, 10)
    frames, reports, _missing = await restore_power_history(
        hass, config, {"import": "sensor.i", "export": "sensor.e"}, now
    )
    flow = AlignedFlow()
    estimator = BatteryEstimate()
    estimator.seed(frames, config, now.timestamp())
    eta = estimator.update(
        hass,
        config,
        {
            "battery_soc": "96",
            "battery_charge_power": "500",
            "battery_discharge_power": "0",
        },
        now.timestamp() + 0.01,
    )
    assert eta["history_seeded"] is True
    assert eta["averaging_seconds"] == 300
    assert eta["charge_seconds"] == 1440
    flow.seed(frames, reports, "native")
    result = flow.capture(frames[-1][1], 0, now.timestamp() + 0.01, "native", "latest")
    assert result["energy"]["power_windows"]["1800"]["covered_seconds"] == 1800, (
        frames[0][1]["power_history_known"],
        frames[-1][1]["power_history_known"],
        frames[-1][1]["values"],
        reports,
    )
    assert result["energy"]["power_windows"]["1800"]["home_power_w"] == 600
    rows = await read_states(
        hass,
        {
            "sensor.history_soc",
            "sensor.history_battery",
            "sensor.history_limit",
            "sensor.history_voltage",
        },
        now - timedelta(minutes=5),
        now,
    )
    profile, counts = learn_chunk(rows, config, now - timedelta(minutes=5), now, {})
    assert profile["95"]["count"] >= 4 and counts["eligible_minutes"] >= 4

    from unittest.mock import AsyncMock, patch

    from custom_components.pge_storage.view_history import restore_battery_profile

    profile, meta = await restore_battery_profile(hass, config, now, {}, {})
    assert profile["95"]["count"] >= 4 and meta["eligible_minutes"] >= 4
    with patch(
        "custom_components.pge_storage.view_history.read_states",
        side_effect=AssertionError("same interval queried again"),
    ):
        again, metadata = await restore_battery_profile(
            hass, config, now, profile, meta
        )
    assert again == profile and metadata == meta
    rebuilt, newmeta = await restore_battery_profile(
        hass, config, now, profile, meta, force=True
    )
    assert (
        rebuilt == profile and newmeta["eligible_minutes"] == meta["eligible_minutes"]
    )
    with patch(
        "custom_components.pge_storage.view_history.read_states",
        new=AsyncMock(return_value={}),
    ):
        retained, missing = await restore_battery_profile(
            hass, config, now + timedelta(minutes=10), profile, meta
        )
    assert retained == profile and missing["missing_minutes"] > meta["missing_minutes"]
