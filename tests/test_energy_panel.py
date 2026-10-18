from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import patch

from homeassistant.core import State

from custom_components.pge_storage.energy import energy_snapshot, validate_energy_config
from custom_components.pge_storage.energy_panel import merge_panel_config, panel_config


def hass_with(values):
    states = {
        key: State(key, str(value), {"unit_of_measurement": unit})
        for key, (value, unit) in values.items()
    }
    return SimpleNamespace(states=SimpleNamespace(get=states.get))


def preferences():
    return {
        "energy_sources": [
            {
                "type": "grid",
                "stat_energy_from": "sensor.native_import",
                "stat_energy_to": "sensor.native_export",
                "stat_rate": "sensor.native_power",
            },
            {
                "type": "solar",
                "stat_energy_from": "sensor.pv_energy",
                "stat_rate": "sensor.pv_power",
            },
            {
                "type": "battery",
                "stat_energy_from": "sensor.battery_discharge",
                "stat_energy_to": "sensor.battery_charge",
                "stat_rate": "sensor.battery_power",
                "stat_soc": "sensor.soc",
                "capacity": 10,
            },
        ],
        "device_consumption": [{"stat_consumption": "supplier:pump", "name": "Pompa"}],
    }


def test_panel_mapping_home_balance_and_external_consumers():
    hass = hass_with(
        {
            "sensor.native_power": (-500, "W"),
            "sensor.pv_power": (3.5, "kW"),
            "sensor.battery_power": (-200, "W"),
            "sensor.soc": (70, "%"),
        }
    )
    with patch(
        "custom_components.pge_storage.energy_panel.er.async_get",
        return_value=SimpleNamespace(async_get=lambda _id: None),
    ):
        imported = panel_config(hass, preferences())["config"]
    assert "home_power" not in imported["sources"]
    assert imported["directions"]["battery"] == "discharge"
    assert imported["consumers"][0]["statistic"] == "supplier:pump"
    stats = {
        "day": "2026-10-18",
        "values": {
            "sensor.native_import": "20",
            "sensor.native_export": "3",
            "sensor.pv_energy": "8",
            "sensor.battery_discharge": "1",
            "sensor.battery_charge": "2",
            "supplier:pump": "4",
        },
    }
    with patch(
        "custom_components.pge_storage.energy.dt_util.utcnow",
        return_value=datetime(2026, 10, 18, 12, tzinfo=UTC),
    ):
        result = energy_snapshot(
            hass, imported, {"import": "sensor.i", "export": "sensor.e"}, {}, stats
        )
    assert result["values"]["home_power"] == "2800"
    assert result["today"]["home_energy"] == "24"
    assert result["values"]["battery_stored"] == "7"
    assert result["consumers"][0]["today_kwh"] == "4"
    assert result["calculation"]["home_power"]["basis"] == "balance"


def test_missing_measurement_is_not_assumed_zero_and_manual_home_wins():
    hass = hass_with({"sensor.grid": (1000, "W"), "sensor.home": (2, "kW")})
    config = validate_energy_config(
        {
            "sources": {"grid_power": "sensor.grid"},
            "presence": {"solar": True, "battery": False},
        }
    )
    result = energy_snapshot(
        hass, config, {"import": "sensor.i", "export": "sensor.e"}, {}
    )
    assert result["values"]["home_power"] is None
    assert "pv_power" in result["calculation"]["home_power"]["missing"]
    config["sources"]["home_power"] = "sensor.home"
    assert (
        energy_snapshot(hass, config, {"import": "sensor.i", "export": "sensor.e"}, {})[
            "values"
        ]["home_power"]
        == "2000"
    )
    config["sources"].pop("home_power")
    config["presence"]["solar"] = False
    assert (
        energy_snapshot(hass, config, {"import": "sensor.i", "export": "sensor.e"}, {})[
            "values"
        ]["home_power"]
        == "1000"
    )


def test_multiple_pv_arrays_and_legacy_grid_are_mapped_without_discarding_sources():
    prefs = preferences()
    prefs["energy_sources"].append(
        {
            "type": "solar",
            "stat_energy_from": "supplier:pv",
            "stat_rate": "sensor.pv_second",
        }
    )
    prefs["energy_sources"][0] = {
        "type": "grid",
        "flow_from": [{"stat_energy_from": "sensor.native_import"}],
        "flow_to": [{"stat_energy_to": "sensor.native_export"}],
        "power": [{"stat_rate": "sensor.native_power"}],
    }
    hass = hass_with({})
    with patch(
        "custom_components.pge_storage.energy_panel.er.async_get",
        return_value=SimpleNamespace(async_get=lambda _id: None),
    ):
        config = panel_config(hass, prefs)["config"]
    assert config["statistics"]["pv_energy"] == ["sensor.pv_energy", "supplier:pv"]
    assert config["sources"]["pv_power"] == ["sensor.pv_power", "sensor.pv_second"]
    assert config["sources"]["grid_power"] == "sensor.native_power"


def test_one_time_defaults_preserve_manual_roles_and_do_not_mutate_original():
    old = validate_energy_config(
        {
            "sources": {
                "pv_power": "sensor.manual",
                "battery_charge_power": "sensor.charge",
            }
        }
    )
    imported = validate_energy_config(
        {
            "sources": {"pv_power": "sensor.auto", "battery_power": "sensor.bat"},
            "statistics": {"pv_energy": ["sensor.pv"]},
            "presence": {"solar": True, "battery": True},
            "directions": {"battery": "discharge"},
        }
    )
    merged = merge_panel_config(old, imported)
    assert merged["sources"]["pv_power"] == "sensor.manual"
    assert "battery_power" not in merged["sources"]
    assert old["directions"]["grid"] == "import"
    assert old["imported_from_energy"] is False
