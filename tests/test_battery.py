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
