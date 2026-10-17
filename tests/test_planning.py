from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from unittest.mock import patch
from uuid import uuid4

import pytest

from custom_components.pge_storage.ledger import (
    LedgerError,
    Sample,
    Settlement,
    boundary,
    combine_counters,
    energy,
)
from custom_components.pge_storage.planning import (
    Inventory,
    expires_on,
    inventory_now,
    planning_snapshot,
    validate_checkpoints,
    validate_plan,
)
from custom_components.pge_storage.planning_history import async_daily, seasonal_profile


def sample(day, imported, exported):
    stamp = (boundary(day) - timedelta(minutes=1)).isoformat()
    return combine_counters(Sample(str(imported), stamp), Sample(str(exported), stamp))


def opening():
    row = Settlement(
        str(uuid4()), "2026-09-30", sample("2026-09-30", 1000, 1000), "200"
    )
    plan = validate_plan(
        {
            "anchor_id": row.id,
            "lots": [
                {"month": "2026-05", "export_kwh": "125", "expires_on": "2027-05-31"},
                {"month": "2026-06", "export_kwh": "125", "expires_on": "2027-06-30"},
            ],
        }
    )
    return row, plan


def test_fifo_consumes_oldest_even_when_balance_grows():
    row, plan = opening()
    inventory = inventory_now(
        plan, [row], [], sample("2026-10-17", 1150, 1250).components, date(2026, 10, 17)
    )
    assert inventory.balance == 250
    assert inventory.serialize() == [
        {"month": "2026-06", "expires_on": "2027-06-30", "kwh": "50"},
        {"month": "2026-10", "expires_on": "2027-10-31", "kwh": "200"},
    ]


def test_expiry_is_inclusive_and_leap_year_uses_month_end():
    inventory = Inventory()
    inventory.credit("2024-02", Decimal(10))
    assert expires_on("2024-02") == "2025-02-28"
    assert expires_on("2023-02") == "2024-02-29"
    inventory.expire(date(2025, 2, 28))
    assert inventory.balance == 10
    inventory.expire(date(2025, 3, 1))
    assert inventory.balance == 0 and inventory.expired == 10


def test_unknown_lots_do_not_produce_a_winter_verdict():
    row, _plan = opening()
    result = planning_snapshot(
        validate_plan({}),
        [row],
        [],
        row.sample.components,
        "200",
        datetime(2026, 9, 30, 22, tzinfo=UTC),
    )
    assert result["forecast"] is None
    assert result["inventory"] is None
    assert result["daily_budget_kwh"] is not None


def test_partial_profile_does_not_assume_missing_winter_months_are_zero():
    row, plan = opening()
    plan["profile"] = [{"month": 10, "import_kwh": "310", "export_kwh": "0"}]
    result = planning_snapshot(
        plan,
        [row],
        [],
        row.sample.components,
        "200",
        datetime(2026, 9, 30, 22, tzinfo=UTC),
    )
    assert result["missing_profile_months"] == [1, 2, 3, 11, 12]
    assert result["forecast"] is None


def test_projection_reports_depletion_deficit_and_future_counter_readings():
    row, plan = opening()
    plan.update(
        {
            "profile": [{"month": 10, "import_kwh": "310", "export_kwh": "0"}],
            "target_day": "2026-10-31",
        }
    )
    forecast = planning_snapshot(
        plan,
        [row],
        [],
        row.sample.components,
        "200",
        datetime(2026, 9, 30, 22, tzinfo=UTC),
    )["forecast"]
    assert forecast["balance_kwh"] == "-110"
    assert forecast["shortfall_kwh"] == "110"
    assert forecast["first_shortfall_day"] == "2026-10-21"
    assert forecast["rows"][-1]["import_counter"] == "1310"
    assert forecast["rows"][-1]["export_counter"] == "1000"


def test_current_day_is_only_projected_from_now_and_dst_is_respected():
    row, plan = opening()
    plan.update(
        {
            "profile": [{"month": 10, "import_kwh": "310", "export_kwh": "0"}],
            "target_day": "2026-10-25",
        }
    )
    # 25 October is a 25-hour local day. 11 UTC is 12 local: 12 hours remain.
    result = planning_snapshot(
        plan,
        [row],
        [],
        row.sample.components,
        "200",
        datetime(2026, 10, 25, 11, tzinfo=UTC),
    )["forecast"]
    assert energy(result["rows"][0]["import_kwh"]) == Decimal("4.8")


def test_inventory_requires_every_month_and_rejects_resets_and_wrong_totals():
    row, plan = opening()
    with pytest.raises(LedgerError, match="końca miesiąca"):
        inventory_now(
            plan,
            [row],
            [],
            sample("2026-11-17", 1200, 1500).components,
            date(2026, 11, 17),
        )
    with pytest.raises(LedgerError, match="zmalał"):
        inventory_now(
            plan,
            [row],
            [],
            sample("2026-10-17", 100, 1500).components,
            date(2026, 10, 17),
        )
    plan["lots"][0]["export_kwh"] = "100"
    with pytest.raises(LedgerError, match="Suma partii"):
        inventory_now(plan, [row], [], row.sample.components, date(2026, 10, 17))


@pytest.mark.parametrize(
    "profile",
    [
        [{"month": 1, "import_kwh": "-1", "export_kwh": "0"}],
        [{"month": 13, "import_kwh": "0", "export_kwh": "0"}],
        [{"month": 1, "import_kwh": "NaN", "export_kwh": "0"}],
        [{"month": 1, "import_kwh": "0", "export_kwh": "0"}] * 2,
    ],
)
def test_invalid_profiles_are_rejected(profile):
    with pytest.raises(LedgerError):
        validate_plan({"profile": profile})


def test_monthly_checkpoints_are_validated_as_real_counter_snapshots():
    row, _plan = opening()
    checkpoint = sample("2026-10-31", 1100, 1300)
    from dataclasses import asdict

    cache = {"anchor_id": row.id, "samples": {"2026-10-31": asdict(checkpoint)}}
    assert validate_checkpoints(cache, [row]) == cache
    cache["samples"]["2026-10-15"] = cache["samples"].pop("2026-10-31")
    with pytest.raises(LedgerError):
        validate_checkpoints(cache, [row])


def test_seasonal_profile_uses_changes_not_counter_states_and_requires_full_hours():
    start = datetime(2026, 8, 31, 22, tzinfo=UTC)
    end = datetime(2026, 9, 30, 22, tzinfo=UTC)
    stamps = range(int(start.timestamp()) - 3600, int(end.timestamp()), 3600)
    rows = {
        "sensor.i": [
            {"start": stamp, "sum": 100000 + index}
            for index, stamp in enumerate(stamps)
        ],
        "sensor.e": [
            {"start": stamp, "sum": 200000 + index * 2}
            for index, stamp in enumerate(stamps)
        ],
    }
    sources = {"import": "sensor.i", "export": "sensor.e"}
    result = seasonal_profile(rows, sources, date(2026, 10, 17))
    assert result["profile"] == [
        {"month": 9, "import_kwh": "720", "export_kwh": "1440"}
    ]
    rows["sensor.e"].pop(50)
    assert seasonal_profile(rows, sources, date(2026, 10, 17))["profile"] == []


async def test_daily_flows_and_invoice_balance_and_partial_today():
    row, _plan = opening()
    readings = {"2026-10-01": sample("2026-10-01", 1010, 1025)}

    async def read(_hass, _sources, day, _age, _now):
        if day in readings:
            return readings[day]
        raise LedgerError("missing_history", "Brak danych")

    with (
        patch(
            "custom_components.pge_storage.planning_history.dt_util.utcnow",
            return_value=datetime(2026, 10, 2, 10, tzinfo=UTC),
        ),
        patch(
            "custom_components.pge_storage.planning_history.async_read_counters",
            side_effect=read,
        ),
    ):
        result = await async_daily(
            None, {}, [row], sample("2026-10-02", 1025, 1030), "2026-10", 24
        )
    first, today = result["rows"]
    assert first["import_kwh"] == "10"
    assert first["export_kwh"] == "25"
    assert first["credited_kwh"] == "20"
    assert first["net_kwh"] == "10"
    assert first["balance_kwh"] == "210"
    assert today["partial"] and today["balance_kwh"] == "199"


async def test_missing_daily_history_stays_unknown_not_zero():
    row, _plan = opening()

    async def missing(*_args):
        raise LedgerError("missing_history", "Usunięte odczyty")

    with (
        patch(
            "custom_components.pge_storage.planning_history.dt_util.utcnow",
            return_value=datetime(2026, 10, 2, 10, tzinfo=UTC),
        ),
        patch(
            "custom_components.pge_storage.planning_history.async_read_counters",
            side_effect=missing,
        ),
    ):
        result = await async_daily(None, {}, [row], row.sample, "2026-10", 24)
    first, today = result["rows"]
    assert first["import_kwh"] is None and first["balance_kwh"] is None
    assert today["import_kwh"] is None and today["balance_kwh"] == "200"
    assert today["error"]


async def test_daily_expired_energy_cannot_cover_grid_import():
    row, plan = opening()
    plan["lots"] = [
        {"month": "2025-10", "export_kwh": "250", "expires_on": "2026-10-31"}
    ]
    checkpoint = sample("2026-10-31", 1000, 1000)
    with patch(
        "custom_components.pge_storage.planning_history.dt_util.utcnow",
        return_value=datetime(2026, 11, 1, 12, tzinfo=UTC),
    ):
        result = await async_daily(
            None,
            {},
            [row],
            sample("2026-11-01", 1010, 1000),
            "2026-11",
            24,
            plan,
            [(date(2026, 10, 31), checkpoint.components)],
            {
                "2026-10-31": {
                    "value": checkpoint.value,
                    "recorded_at": checkpoint.recorded_at,
                    "components": checkpoint.components,
                }
            },
        )
    day = result["rows"][0]
    assert day["balance_kwh"] == "-10"
    assert day["expired_kwh"] == "200"
    assert day["withdrawn_kwh"] == "0"
    assert day["uncovered_import_kwh"] == "10"


def test_past_forecast_target_does_not_hide_current_inventory():
    row, plan = opening()
    plan["target_day"] = "2026-10-01"
    result = planning_snapshot(
        plan,
        [row],
        [],
        row.sample.components,
        "200",
        datetime(2026, 10, 17, 10, tzinfo=UTC),
    )
    assert result["inventory"]["balance_kwh"] == "200"
    assert result["forecast"] is None and result["error"]
