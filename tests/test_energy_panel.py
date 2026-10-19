from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import patch

import pytest
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


def test_missing_power_contributes_zero_and_manual_home_wins():
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
    assert result["values"]["home_power"] == "1000"
    assert result["values"]["pv_power"] == "0"
    assert result["calculation"]["home_power"]["missing"] == []
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


def test_all_native_pv_entries_remain_visible_when_one_live_entity_is_missing():
    hass = hass_with({"sensor.mppt": (120, "kWh"), "sensor.mppt_w": (2000, "W")})
    prefs = {
        "energy_sources": [
            {"type": "solar", "stat_energy_from": "sensor.solar_total_kwh"},
            {
                "type": "solar",
                "stat_energy_from": "sensor.mppt",
                "stat_rate": "sensor.mppt_w",
            },
        ]
    }
    with patch(
        "custom_components.pge_storage.energy_panel.er.async_get",
        return_value=SimpleNamespace(async_get=lambda _id: None),
    ):
        native = panel_config(hass, prefs)
    config = native["config"]
    assert config["sources"]["pv_energy"] == [
        "sensor.solar_total_kwh",
        "sensor.mppt",
    ]
    assert config["statistics"]["pv_energy"] == config["sources"]["pv_energy"]
    assert len(native["report"]) == 2
    assert native["report"][0]["energy"][0]["status"] == "missing"
    assert native["report"][0]["missing"] == ["pv_power"]
    assert native["report"][0]["missing_power_origin"] == {
        "path": "energy_sources[0].stat_rate"
    }
    assert native["report"][1]["power"][0]["origin"] == {
        "path": "energy_sources[1].stat_rate"
    }
    with patch(
        "custom_components.pge_storage.energy.dt_util.utcnow",
        return_value=datetime(2026, 10, 18, 12, tzinfo=UTC),
    ):
        result = energy_snapshot(
            hass,
            config,
            {"import": "sensor.i", "export": "sensor.e"},
            {},
            {
                "day": "2026-10-18",
                "values": {"sensor.solar_total_kwh": "10", "sensor.mppt": "5"},
            },
            native,
        )
        assert result["today"]["pv_energy"] == "15"
        assert result["values"]["pv_power"] == "2000"
        assert result["values"]["home_power"] == "2000"
        assert result["power_zero_fallback"]["pv_power"][0]["status"] == "unconfigured"
        assert result["source_status"]["pv_energy"][0]["id"] == "sensor.solar_total_kwh"
        result = energy_snapshot(
            hass,
            config,
            {"import": "sensor.i", "export": "sensor.e"},
            {},
            {
                "day": "2026-10-18",
                "values": {"sensor.solar_total_kwh": None, "sensor.mppt": "5"},
            },
            native,
        )
        assert result["today"]["pv_energy"] == "5"


def test_battery_power_config_precedence_and_registered_renamed_transform():
    from homeassistant.components.energy.helpers import generate_power_sensor_unique_id

    for power in (
        {"stat_rate_inverted": "sensor.victron_battery"},
        {"stat_rate_from": "sensor.discharge_w", "stat_rate_to": "sensor.charge_w"},
    ):
        prefs = preferences()
        prefs["energy_sources"][-1]["power_config"] = power
        registry = SimpleNamespace(
            async_get=lambda _id: None,
            async_get_entity_id=lambda domain, platform, unique, power=power: (
                "sensor.battery_renamed"
                if (domain, platform, unique)
                == (
                    "sensor",
                    "energy",
                    generate_power_sensor_unique_id("battery", power),
                )
                else None
            ),
        )
        hass = hass_with(
            {"sensor.battery_renamed": (-400, "W"), "sensor.soc": (65, "%")}
        )
        with patch(
            "custom_components.pge_storage.energy_panel.er.async_get",
            return_value=registry,
        ):
            imported = panel_config(hass, prefs)
        assert (
            imported["config"]["sources"]["battery_power"] == "sensor.battery_renamed"
        )
        assert imported["config"]["sources"]["battery_soc"] == "sensor.soc"
        assert imported["config"]["battery_capacity_kwh"] == "10"
        battery = next(item for item in imported["report"] if item["type"] == "battery")
        assert battery["power"][0]["status"] == "available"
        assert battery["soc"][0]["status"] == "available"
        assert battery["power"][0]["origin"] == {
            "path": "energy_sources[2].power_config",
            "transform": "energy_helper",
            "inputs": power,
            "resolved_by": "entity_registry",
        }


@pytest.mark.parametrize("missing", ["missing", "unknown", "unavailable", "invalid"])
def test_power_sums_each_array_with_zero_for_an_absent_reading(missing):
    values = {"sensor.pv_one": (2, "kW")}
    if missing != "missing":
        values["sensor.pv_two"] = (
            ("1", "kWh") if missing == "invalid" else (missing, "W")
        )
    hass = hass_with(values)
    config = validate_energy_config(
        {"sources": {"pv_power": ["sensor.pv_one", "sensor.pv_two"]}}
    )
    result = energy_snapshot(
        hass, config, {"import": "sensor.i", "export": "sensor.e"}, {}
    )
    assert result["values"]["pv_power"] == "2000"
    assert result["values"]["home_power"] == "2000"
    assert result["power_zero_fallback"]["pv_power"][0]["id"] == "sensor.pv_two"
    assert result["power_zero_fallback"]["pv_power"][0]["status"] == missing
    hass.states.get = lambda _id: None
    result = energy_snapshot(
        hass, config, {"import": "sensor.i", "export": "sensor.e"}, {}
    )
    assert result["values"]["pv_power"] == "0"
    assert result["values"]["home_power"] == "0"
    assert len(result["power_zero_fallback"]["pv_power"]) == 2
    assert result["values"]["battery_soc"] is None
    assert result["values"]["battery_stored"] is None
    assert result["today"]["pv_energy"] is None


def test_zero_pv_with_grid_and_discharge_computes_home_without_direction_overwrite():
    hass = hass_with(
        {
            "sensor.grid_import": (720, "W"),
            "sensor.battery_discharge": (5, "W"),
            "sensor.pv": ("unavailable", "W"),
            "sensor.pump": ("unknown", "W"),
        }
    )
    config = validate_energy_config(
        {
            "sources": {
                "grid_import_power": "sensor.grid_import",
                "battery_discharge_power": "sensor.battery_discharge",
                "pv_power": "sensor.pv",
            },
            "consumers": [{"name": "Pompa", "power": "sensor.pump"}],
        }
    )
    result = energy_snapshot(
        hass, config, {"import": "sensor.i", "export": "sensor.e"}, {}
    )
    assert result["values"]["grid_import_power"] == "720"
    assert result["values"]["grid_export_power"] == "0"
    assert result["values"]["battery_discharge_power"] == "5"
    assert result["values"]["battery_charge_power"] == "0"
    assert result["values"]["home_power"] == "725"
    assert result["consumers"][0]["power_w"] == "0"
    assert result["power_zero_fallback"]["consumers"][0]["status"] == "unknown"


def test_signed_grid_and_battery_derive_zero_on_absent_sensor_and_clamp_house():
    hass = hass_with({"sensor.grid": (-500, "W"), "sensor.battery": (-100, "W")})
    config = validate_energy_config(
        {
            "sources": {"grid_power": "sensor.grid", "battery_power": "sensor.battery"},
            "directions": {"grid": "import", "battery": "discharge"},
        }
    )
    result = energy_snapshot(
        hass, config, {"import": "sensor.i", "export": "sensor.e"}, {}
    )
    assert result["values"]["grid_export_power"] == "500"
    assert result["values"]["battery_charge_power"] == "100"
    assert result["values"]["home_power"] == "0"
    assert result["calculation"]["home_power"]["negative"] is True
    hass.states.get = lambda _id: None
    result = energy_snapshot(
        hass, config, {"import": "sensor.i", "export": "sensor.e"}, {}
    )
    assert result["values"]["grid_import_power"] == "0"
    assert result["values"]["grid_export_power"] == "0"
    assert result["values"]["battery_charge_power"] == "0"
    assert result["values"]["battery_discharge_power"] == "0"
    assert result["values"]["home_power"] == "0"
