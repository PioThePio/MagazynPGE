from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from homeassistant.core import State

from custom_components.pge_storage.energy import (
    energy_snapshot,
    reading,
    validate_energy_config,
)
from custom_components.pge_storage.ledger import (
    LedgerError,
    Sample,
    Settlement,
    boundary,
    combine_counters,
)
from custom_components.pge_storage.overview import async_months, usage_month
from custom_components.pge_storage.planning import validate_plan


def test_optional_readings_units_negative_and_missing_are_not_zero():
    states = {
        "sensor.pv": State("sensor.pv", "2.4", {"unit_of_measurement": "kW"}),
        "sensor.bad": State("sensor.bad", "-12", {"unit_of_measurement": "W"}),
        "sensor.soc": State("sensor.soc", "105", {"unit_of_measurement": "%"}),
    }
    hass = SimpleNamespace(states=SimpleNamespace(get=states.get))
    assert reading(hass, "sensor.pv", "W") == "2400"
    assert reading(hass, "sensor.bad", "W") is None
    assert reading(hass, "sensor.soc", "%") is None
    assert reading(hass, None, "kWh") is None


def test_energy_day_uses_counter_differences_and_mapping_identity():
    states = {
        key: State(key, value, {"unit_of_measurement": "kWh"})
        for key, value in [
            ("sensor.i", "120"),
            ("sensor.e", "250"),
            ("sensor.pv", "600"),
            ("sensor.new", "900"),
        ]
    }
    hass = SimpleNamespace(states=SimpleNamespace(get=states.get))
    stamp = (boundary("2026-10-17") - timedelta(minutes=1)).isoformat()
    cache = {
        key: {"2026-10-17": {"value": value, "recorded_at": stamp}}
        for key, value in [
            ("sensor.i", "100"),
            ("sensor.e", "240"),
            ("sensor.pv", "590"),
        ]
    }
    with patch(
        "custom_components.pge_storage.energy.dt_util.utcnow",
        return_value=datetime(2026, 10, 18, 12, tzinfo=UTC),
    ):
        config = validate_energy_config({"sources": {"pv_energy": "sensor.pv"}})
        result = energy_snapshot(
            hass, config, {"import": "sensor.i", "export": "sensor.e"}, cache
        )
        assert result["today"]["pv_energy"] == "10"
        assert result["today"]["grid_import_energy"] == "20"
        assert result["today"]["credited_energy"] is None
        assert result["today"]["home_energy"] is None
        config["sources"]["pv_energy"] = "sensor.new"
        assert (
            energy_snapshot(
                hass, config, {"import": "sensor.i", "export": "sensor.e"}, cache
            )["today"]["pv_energy"]
            is None
        )


def test_source_config_rejects_arbitrary_entities_and_excess_consumers():
    with pytest.raises(LedgerError):
        validate_energy_config({"sources": {"pv_power": "light.room"}})
    with pytest.raises(LedgerError):
        validate_energy_config(
            {"consumers": [{"name": "Load", "power": "sensor.load"}] * 17}
        )


def test_usage_requires_complete_hours_including_dst_and_not_states():
    begin = datetime(2026, 9, 30, 22, tzinfo=UTC)
    end = datetime(2026, 10, 31, 23, tzinfo=UTC)
    rows = {
        stamp: str(index)
        for index, stamp in enumerate(
            range(int(begin.timestamp()) - 3600, int(end.timestamp()), 3600)
        )
    }
    assert (
        usage_month(rows, date(2026, 10, 1), datetime(2026, 11, 1, tzinfo=UTC)) == "745"
    )
    del rows[int(begin.timestamp()) + 3600]
    assert (
        usage_month(rows, date(2026, 10, 1), datetime(2026, 11, 1, tzinfo=UTC)) is None
    )


async def test_month_totals_survive_missing_intermediate_days():
    def sample(day, i, e):
        stamp = (boundary(day) - timedelta(minutes=1)).isoformat()
        return combine_counters(Sample(str(i), stamp), Sample(str(e), stamp))

    anchor = Settlement(
        str(uuid4()), "2026-09-30", sample("2026-09-30", 1000, 1000), "200"
    )
    manager = SimpleNamespace(
        hass=None,
        records=[anchor],
        live_sample=lambda: sample("2026-10-18", 1030, 1100),
        daily_cache={},
        checkpoint_cache={"samples": {}},
        sources={"import": "sensor.i", "export": "sensor.e"},
        max_age_hours=24,
        planning=validate_plan({}),
        checkpoints=[],
    )
    with (
        patch(
            "custom_components.pge_storage.overview.dt_util.utcnow",
            return_value=datetime(2026, 10, 18, 12, tzinfo=UTC),
        ),
        patch(
            "custom_components.pge_storage.overview.async_read_counters",
            new=AsyncMock(side_effect=LedgerError("missing_history", "Purged")),
        ),
    ):
        result = await async_months(manager)
    october = next(row for row in result["rows"] if row["month"] == "2026-10")
    assert october["import_kwh"] == "30"
    assert october["credited_kwh"] == "80"
    assert october["balance_kwh"] == "250"
    assert october["net_kwh"] == "50"


def test_signed_power_cannot_be_mixed_with_separate_direction_sources():
    with pytest.raises(LedgerError):
        validate_energy_config(
            {
                "sources": {
                    "grid_power": "sensor.grid",
                    "grid_import_power": "sensor.import_power",
                }
            }
        )


def test_missing_configured_pv_history_does_not_fall_back_to_partial_home_total():
    now = datetime(2026, 10, 28, 12, tzinfo=UTC)
    config = validate_energy_config(
        {
            "statistics": {
                "pv_energy": ["test:pv1", "test:pv2"],
                "grid_import_energy": ["test:grid"],
                "grid_export_energy": ["test:export"],
            },
            "presence": {"battery": False},
        }
    )
    stats = {
        "day": "2026-10-28",
        "values": {
            "test:pv1": "2",
            "test:pv2": None,
            "test:grid": "10",
            "test:export": "0",
        },
        "home_energy": None,
        "home_coverage": {"partial": True},
    }
    with patch("custom_components.pge_storage.energy.dt_util.utcnow", return_value=now):
        result = energy_snapshot(
            SimpleNamespace(states=SimpleNamespace(get=lambda _id: None)),
            config,
            {},
            {},
            stats,
        )
    assert result["today"]["home_energy"] is None
    assert result["calculation"]["home_energy"]["coverage"]["partial"] is True
