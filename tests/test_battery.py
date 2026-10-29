from types import SimpleNamespace

import pytest
from homeassistant.core import State

from custom_components.pge_storage.battery import BatteryEstimate, options
from custom_components.pge_storage.energy import validate_energy_config
from custom_components.pge_storage.ledger import LedgerError


def fixture(**extra):
    states = {
        "sensor.minimum": State("sensor.minimum", "20", {"unit_of_measurement": "%"}),
        "sensor.current": State("sensor.current", "10", {"unit_of_measurement": "A"}),
        "sensor.voltage": State("sensor.voltage", "50", {"unit_of_measurement": "V"}),
        "sensor.pv": State("sensor.pv", "6", {"unit_of_measurement": "kWh"}),
        "sensor.home": State("sensor.home", "2", {"unit_of_measurement": "kWh"}),
    }
    hass = SimpleNamespace(states=SimpleNamespace(get=states.get))
    config = validate_energy_config(
        {
            "battery_capacity_kwh": "5",
            "battery_forecast": {"min_soc_entity": "sensor.minimum", **extra},
        }
    )
    return hass, config


def run(model, hass, config, power, soc=50, start=0, stop=61):
    for second in range(start, stop):
        result = model.update(
            hass,
            config,
            {
                "battery_soc": soc,
                "battery_charge_power": max(0, power),
                "battery_discharge_power": max(0, -power),
            },
            second,
        )
    return result


def test_charge_discharge_reserve_average_and_pause():
    hass, config = fixture()
    model = BatteryEstimate()
    result = run(model, hass, config, 1000)
    assert result["charge_seconds"] == 9000 and result["discharge_seconds"] is None
    result = run(model, hass, config, -1000, start=61, stop=122)
    assert result["discharge_seconds"] == 5400 and result["charge_seconds"] is None
    assert (
        run(model, hass, config, 10, start=122, stop=160)["discharge_seconds"] is None
    )


def test_learning_requires_independent_bms_limit_and_complete_future_soc_bins():
    hass, config = fixture(learn=True)
    model = BatteryEstimate()
    run(model, hass, config, 500, soc=95, stop=181)
    assert not model.profile
    hass, config = fixture(
        learn=True,
        bms_current_entity="sensor.current",
        voltage_entity="sensor.voltage",
        pv_forecast_entity="sensor.pv",
        home_forecast_entity="sensor.home",
        forecast_hours=4,
    )
    model = BatteryEstimate()
    result = run(model, hass, config, 500, soc=95, stop=181)
    assert result["model_range_seconds"] == [1530, 2160]
    assert result["forecast_range_seconds"] == [1440, 2340]
    saved = BatteryEstimate()
    saved.restore(model.profile)
    assert saved.profile == model.profile
    # Missing lower SOC bins are never fabricated from the high-SOC profile.
    assert (
        run(model, hass, config, 500, soc=80, start=181, stop=220)[
            "model_range_seconds"
        ]
        is None
    )


def test_bad_configuration_and_missing_capacity_do_not_invent_time():
    with pytest.raises(LedgerError):
        options({"average_minutes": 10})
    with pytest.raises(LedgerError):
        options({"min_soc_entity": "switch.wrong"})
    hass, _ = fixture()
    result = run(BatteryEstimate(), hass, validate_energy_config({}), 1000)
    assert result["charge_seconds"] is None and result["quality"] == "missing_capacity"


def test_adaptive_window_and_live_minimum_reserve_are_separate_from_total_energy():
    hass, config = fixture(average_minutes=5)
    model = BatteryEstimate()
    result = run(model, hass, config, -1000, soc=60, stop=31)
    assert result["averaging_seconds"] == 30
    assert result["discharge_seconds"] == 7200
    assert result["reserve_discharge_seconds"] == 3600
    assert result["total_discharge_seconds"] == 10800
    assert result["stored_kwh"] == 3 and result["available_to_minimum_kwh"] == 2
    result = run(model, hass, config, -1000, soc=60, start=31, stop=301)
    assert (
        result["averaging_seconds"] == 300 and result["target_averaging_seconds"] == 300
    )
    hass.states.get.__self__["sensor.minimum"] = State(
        "sensor.minimum", "30", {"unit_of_measurement": "%"}
    )
    result = run(model, hass, config, -1000, soc=60, start=301, stop=302)
    assert (
        result["discharge_seconds"] == 5400
        and result["reserve_discharge_seconds"] == 5400
    )
    assert result["reserve_kwh"] == 1.5
    hass.states.get.__self__["sensor.minimum"] = State(
        "sensor.minimum", "unavailable", {"unit_of_measurement": "%"}
    )
    result = run(model, hass, config, -1000, soc=60, start=302, stop=303)
    assert (
        result["discharge_seconds"] is None
        and result["reserve_discharge_seconds"] is None
    )


def test_battery_power_history_supplies_eta_immediately_and_direction_change_restarts_window():
    hass, config = fixture(average_minutes=5)
    config["sources"]["battery_power"] = "sensor.power"
    frames = [
        (
            stamp,
            {
                "values": {
                    "battery_discharge_power": "1000",
                    "battery_charge_power": "0",
                },
                "power_history_known": {"battery_power": True},
            },
        )
        for stamp in range(0, 301, 5)
    ]
    model = BatteryEstimate()
    model.seed(frames, config, 300)
    result = run(model, hass, config, -1000, soc=60, start=300, stop=301)
    assert result["history_seeded"] is True and result["averaging_seconds"] == 300
    assert result["discharge_seconds"] == 7200
    result = run(model, hass, config, 1000, soc=60, start=301, stop=302)
    assert result["history_seeded"] is False and result["charge_seconds"] is None
    assert result["direction"] == "charging"
    model = BatteryEstimate()
    frames[-1][1]["power_history_known"]["battery_power"] = False
    model.seed(frames, config, 300)
    assert (
        run(model, hass, config, -1000, soc=60, start=300, stop=301)[
            "discharge_seconds"
        ]
        is None
    )


def test_profile_view_has_unknown_bins_and_reserve_below_minimum_is_not_overstated():
    hass, config = fixture()
    model = BatteryEstimate()
    model.restore({"95": {"watts": 400, "count": 3}})
    result = run(model, hass, config, -1000, soc=10)
    assert len(result["profile_bins"]) == 20
    assert result["profile_bins"][0]["watts"] is None
    assert result["profile_bins"][-1]["usable"] is True
    assert result["reserve_kwh"] == 0.5
    assert result["discharge_seconds"] == 0
    assert result["reserve_discharge_seconds"] == 1800


async def test_shutdown_waits_for_background_history_before_database_can_close():
    import asyncio
    from unittest.mock import AsyncMock

    from custom_components.pge_storage.coordinator import LedgerCoordinator

    entered, release = asyncio.Event(), asyncio.Event()
    order = []

    async def reading():
        entered.set()
        await release.wait()
        order.append("history_done")

    async def checkpoint(_now):
        order.append("checkpoint")

    owner = SimpleNamespace(
        _recovery_closing=False,
        _shutdown_complete=False,
        _active_refreshes=set(),
        _recovery_task=None,
        async_refresh_planning_history=reading,
        async_refresh_energy=AsyncMock(),
        async_refresh_usage=AsyncMock(),
        publish=lambda: None,
        _checkpoint_recovery=checkpoint,
    )
    tick = asyncio.create_task(LedgerCoordinator._energy_statistics_tick(owner, None))
    await entered.wait()
    stop = asyncio.create_task(LedgerCoordinator._stop_recovery(owner))
    await asyncio.sleep(0)
    assert not stop.done()
    await LedgerCoordinator._energy_statistics_tick(owner, None)
    release.set()
    await asyncio.gather(tick, stop)
    assert order == ["history_done", "checkpoint"]
    assert not owner._active_refreshes
