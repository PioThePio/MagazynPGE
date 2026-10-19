from copy import deepcopy
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from homeassistant.core import State

from custom_components.pge_storage.energy import (
    battery_capacity,
    energy_snapshot,
    energy_sources,
    pv_arrays,
    validate_energy_config,
)
from custom_components.pge_storage.energy_panel import (
    panel_config,
    upgrade_consumer_parents,
)
from custom_components.pge_storage.ledger import LedgerError


def hierarchy():
    return validate_energy_config(
        {
            "sources": {"home_power": "sensor.home_w", "battery_soc": "sensor.soc"},
            "statistics": {"home_energy": ["sensor.home"]},
            "consumers": [
                {"name": "AC", "statistic": "sensor.ac"},
                {
                    "name": "AC Dół",
                    "statistic": "sensor.ac_dol",
                    "power": "sensor.ac_dol_w",
                    "parent_id": "sensor.ac",
                },
                {
                    "name": "AC Góra",
                    "statistic": "sensor.ac_gora",
                    "power": "sensor.ac_gora_w",
                    "parent_id": "sensor.ac",
                },
                {
                    "name": "Lodówka",
                    "statistic": "sensor.fridge",
                    "power": "sensor.fridge_w",
                },
            ],
        }
    )


def snapshot(config, home_w=1000, home_kwh="25", ac_kwh="12"):
    states = {
        key: State(key, str(value), {"unit_of_measurement": unit})
        for key, value, unit in [
            ("sensor.home_w", home_w, "W"),
            ("sensor.ac_w", 500, "W"),
            ("sensor.ac_dol_w", 300, "W"),
            ("sensor.ac_gora_w", 400, "W"),
            ("sensor.fridge_w", 100, "W"),
            ("sensor.soc", 50, "%"),
        ]
    }
    with patch(
        "custom_components.pge_storage.energy.dt_util.utcnow",
        return_value=datetime(2026, 10, 19, 12, tzinfo=UTC),
    ):
        return energy_snapshot(
            SimpleNamespace(states=SimpleNamespace(get=states.get)),
            config,
            {"import": "sensor.i", "export": "sensor.e"},
            {},
            {
                "day": "2026-10-19",
                "values": {
                    "sensor.home": home_kwh,
                    "sensor.ac": ac_kwh,
                    "sensor.ac_dol": "7",
                    "sensor.ac_gora": "5",
                    "sensor.fridge": "2",
                },
            },
        )


def test_consumer_hierarchy_counts_ancestors_per_metric_and_exposes_signed_remainder():
    config = hierarchy()
    result = snapshot(config)
    assert result["consumer_totals"] == {
        "home_power_w": "1000",
        "home_kwh": "25",
        "tracked_power_w": "800",
        "tracked_kwh": "14",
        "untracked_power_w": "200",
        "untracked_kwh": "11",
        "overcount_power": False,
        "overcount_energy": False,
    }
    ac, lower, upper, _fridge = result["consumers"]
    assert ac["has_children"] is True
    assert ac["counted_power"] is False
    assert ac["counted_energy"] is True
    assert lower["parent_id"] == upper["parent_id"] == "sensor.ac"
    assert lower["counted_power"] is True
    assert lower["counted_energy"] is False
    config["consumers"][0]["power"] = "sensor.ac_w"
    result = snapshot(config, 100, "5")
    assert result["consumer_totals"]["tracked_power_w"] == "600"
    assert result["consumer_totals"]["untracked_power_w"] == "-500"
    assert result["consumer_totals"]["untracked_kwh"] == "-9"
    assert result["consumer_totals"]["overcount_power"] is True
    assert result["consumer_totals"]["overcount_energy"] is True
    assert all(item["counted_power"] is False for item in result["consumers"][1:3])
    result = snapshot(config, ac_kwh=None)
    assert result["consumer_totals"]["tracked_kwh"] is None
    assert result["consumer_totals"]["untracked_kwh"] is None
    assert "sensor.ac" in energy_sources(config)
    assert None not in energy_sources(config)


@pytest.mark.parametrize(
    "consumers",
    [
        [{"name": "A", "power": "sensor.a", "parent_id": "missing"}],
        [{"name": "A", "power": "sensor.a", "parent_id": "sensor.a"}],
        [
            {"name": "A", "power": "sensor.a", "parent_id": "sensor.b"},
            {"name": "B", "power": "sensor.b", "parent_id": "sensor.a"},
        ],
        [{"name": "A", "power": "sensor.a"}, {"name": "Repeated", "power": "sensor.a"}],
    ],
)
def test_invalid_consumer_hierarchy_is_rejected(consumers):
    with pytest.raises(LedgerError):
        validate_energy_config({"consumers": consumers})


def test_native_included_in_stat_import_and_non_destructive_parent_upgrade():
    prefs = {
        "energy_sources": [],
        "device_consumption": [
            {"stat_consumption": "sensor.ac", "name": "AC"},
            {
                "stat_consumption": "sensor.ac_dol",
                "stat_rate": "sensor.ac_dol_w",
                "included_in_stat": "sensor.ac",
                "name": "AC Dół",
            },
        ],
    }
    hass = SimpleNamespace(states=SimpleNamespace(get=lambda _id: None))
    with patch(
        "custom_components.pge_storage.energy_panel.er.async_get",
        return_value=SimpleNamespace(async_get=lambda _id: None),
    ):
        imported = panel_config(hass, prefs)["config"]
    assert imported["consumers"][1]["id"] == "sensor.ac_dol"
    assert imported["consumers"][1]["parent_id"] == "sensor.ac"
    existing = deepcopy(imported)
    existing["consumers"][1].pop("parent_id")
    existing["consumers"][1]["power"] = "sensor.manual_victron"
    existing["consumers"][1]["name"] = "Własna nazwa"
    upgraded = upgrade_consumer_parents(existing, imported)
    assert upgraded["consumers"][1]["parent_id"] == "sensor.ac"
    assert upgraded["consumers"][1]["power"] == "sensor.manual_victron"
    assert upgraded["consumers"][1]["name"] == "Własna nazwa"
    assert "parent_id" not in existing["consumers"][1]
    existing["consumers"][1]["parent_id"] = None
    assert (
        upgrade_consumer_parents(existing, imported)["consumers"][1]["parent_id"]
        is None
    )


def test_ah_capacity_requires_voltage_and_does_not_persist_a_stale_kwh_conversion():
    config = hierarchy()
    config["battery_capacity_ah"] = "99"
    assert battery_capacity(config)["kwh"] is None
    assert snapshot(config)["values"]["battery_stored"] is None
    config["battery_voltage"] = "51.2"
    config = validate_energy_config(config)
    result = snapshot(config)
    assert result["battery_capacity"] == {
        "kwh": "5.0688",
        "basis": "ah_voltage",
        "ah": "99",
        "voltage": "51.2",
    }
    assert result["values"]["battery_stored"] == "2.5344"
    assert config["battery_capacity_kwh"] is None
    config["battery_voltage"] = "25.6"
    assert snapshot(config)["battery_capacity"]["kwh"] == "2.5344"
    config["battery_capacity_kwh"] = "10"
    assert snapshot(config)["values"]["battery_stored"] == "5"
    assert snapshot(config)["battery_capacity"]["basis"] == "kwh"


@pytest.mark.parametrize(
    "field,value",
    [
        ("battery_capacity_ah", "0"),
        ("battery_capacity_ah", "-99"),
        ("battery_voltage", "-12"),
        ("battery_voltage", "NaN"),
    ],
)
def test_invalid_capacity_parameters_are_rejected(field, value):
    with pytest.raises(LedgerError):
        validate_energy_config({field: value})


def test_pv_arrays_show_every_native_array_and_selected_manual_power_without_double_sum():
    states = {
        "sensor.pv_w": State("sensor.pv_w", "1.5", {"unit_of_measurement": "kW"}),
        "sensor.total_pv_w": State(
            "sensor.total_pv_w", "2.5", {"unit_of_measurement": "kW"}
        ),
    }
    hass = SimpleNamespace(states=SimpleNamespace(get=states.get))
    prefs = {
        "energy_sources": [
            {"type": "solar", "stat_energy_from": "sensor.old_pv"},
            {
                "type": "solar",
                "stat_energy_from": "sensor.mppt",
                "stat_rate": "sensor.pv_w",
            },
        ]
    }
    with patch(
        "custom_components.pge_storage.energy_panel.er.async_get",
        return_value=SimpleNamespace(async_get=lambda _id: None),
    ):
        native = panel_config(hass, prefs)
    config = deepcopy(native["config"])
    rows = pv_arrays(hass, config, native)
    assert [item["id"] for item in rows] == ["sensor.old_pv", "sensor.mppt"]
    assert [item["power_w"] for item in rows] == ["0", "1500"]
    assert rows[1]["power_entity"] == "sensor.pv_w"
    config["sources"]["pv_power"] = "sensor.total_pv_w"
    rows = pv_arrays(hass, config, native)
    assert sum(float(item["power_w"]) for item in rows) == 2500
    assert [item["power_entity"] for item in rows] == ["sensor.total_pv_w"]
    assert rows[0]["energy_statistic"] is None
    assert rows[0]["energy_statistics"] == ["sensor.old_pv", "sensor.mppt"]
