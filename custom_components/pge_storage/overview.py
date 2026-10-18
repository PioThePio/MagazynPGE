"""Compact monthly ledger and comparable annual consumption (read-only)."""

from datetime import UTC, date, datetime, time, timedelta
from functools import partial

from homeassistant.components.recorder import statistics
from homeassistant.helpers.recorder import get_instance
from homeassistant.util import dt as dt_util

from .history import async_read_counters
from .ledger import (
    WARSAW,
    LedgerError,
    Sample,
    calculate,
    check_counter_progression,
    energy,
    energy_text,
)
from .planning import inventory_now, month_end, next_settlement


def shift_month(day, offset):
    year, month = divmod(day.year * 12 + day.month - 1 + offset, 12)
    return date(year, month + 1, 1)


def usage_month(rows, start, now):
    """All hourly sums plus a baseline; current month ends at last full hour."""
    begin = datetime.combine(start, time(), WARSAW).astimezone(UTC)
    end = datetime.combine(shift_month(start, 1), time(), WARSAW).astimezone(UTC)
    end = min(end, now.replace(minute=0, second=0, microsecond=0))
    if end <= begin:
        return None
    try:
        stamps = range(int(begin.timestamp()) - 3600, int(end.timestamp()), 3600)
        values = [energy(rows[stamp]) for stamp in stamps]
        if any(b < a for a, b in zip(values, values[1:], strict=False)):
            return None
        return energy_text(values[-1] - values[0])
    except KeyError, TypeError, LedgerError:
        return None


async def async_usage(hass, source, target, now):
    today = now.astimezone(WARSAW).date()
    start = today.replace(day=1)
    # Only projection months, max two years; current-year future values stay unknown.
    months, cursor = [], start
    while cursor <= target and len(months) < 25:
        months.append(cursor)
        cursor = shift_month(cursor, 1)
    if not months:
        return []
    first = shift_month(start, -12)
    rows = await get_instance(hass).async_add_executor_job(
        partial(
            statistics.statistics_during_period,
            hass,
            datetime.combine(first, time(), WARSAW).astimezone(UTC)
            - timedelta(hours=1),
            now,
            {source},
            "hour",
            {"energy": "kWh"},
            {"sum"},
        )
    )
    sums = {int(item["start"]): item.get("sum") for item in rows.get(source, [])}
    return [
        {
            "month": month.strftime("%Y-%m"),
            "previous_month": shift_month(month, -12).strftime("%Y-%m"),
            "previous_kwh": usage_month(sums, shift_month(month, -12), now)
            if shift_month(month, -12) < start
            else None,
            "current_kwh": usage_month(sums, month, now) if month <= start else None,
            "partial": month == start,
        }
        for month in months
    ]


async def async_months(manager, count=12):
    now = dt_util.utcnow()
    today = now.astimezone(WARSAW).date()
    records = list(manager.records)
    live = None
    try:
        live = manager.live_sample()
    except LedgerError:
        pass
    known = {
        day: Sample(**value)
        for day, value in {
            **manager.daily_cache,
            **manager.checkpoint_cache["samples"],
        }.items()
    }
    known.update({record.day: record.sample for record in records})

    async def sample(day):
        if day == today:
            if live is None:
                raise LedgerError("missing_source", "Brak bieżących odczytów.")
            return live
        if day.isoformat() in known:
            return known[day.isoformat()]
        value = await async_read_counters(
            manager.hass, manager.sources, day.isoformat(), manager.max_age_hours, now
        )
        known[day.isoformat()] = value
        return value

    result = []
    first = (
        date.fromisoformat(records[0].day).replace(day=1)
        if records
        else today.replace(day=1)
    )
    for index in reversed(range(count)):
        start = shift_month(today.replace(day=1), -index)
        if start < first:
            continue
        end = min(today, month_end(start))
        row = {
            "month": start.strftime("%Y-%m"),
            "partial": end == today,
            "import_kwh": None,
            "credited_kwh": None,
            "net_kwh": None,
            "balance_kwh": None,
        }
        try:
            closing = await sample(end)
            relevant = [record for record in records if record.day <= end.isoformat()]
            if relevant:
                check_counter_progression(relevant[-1].sample, closing)
            row["balance_kwh"] = calculate(relevant, closing.value)["current"][
                "estimated_balance"
            ]
            if relevant and manager.planning["anchor_id"] == relevant[-1].id:
                try:
                    row["balance_kwh"] = energy_text(
                        inventory_now(
                            manager.planning,
                            relevant,
                            [(d, c) for d, c in manager.checkpoints if d < end],
                            closing.components,
                            end,
                        ).balance
                    )
                except LedgerError:
                    row["balance_kwh"] = None
            opening = await sample(start - timedelta(days=1))
            check_counter_progression(opening, closing)
            imported = energy(closing.components["import"]["value"]) - energy(
                opening.components["import"]["value"]
            )
            credited = (
                energy(closing.components["export"]["value"])
                - energy(opening.components["export"]["value"])
            ) * energy("0.8")
            row.update(
                import_kwh=energy_text(imported),
                credited_kwh=energy_text(credited),
                net_kwh=energy_text(credited - imported),
            )
        except LedgerError:
            pass
        result.append(row)
    return {"rows": result, "updated_at": now.isoformat()}


def usage_target(plan, records, now):
    return (
        date.fromisoformat(plan["target_day"])
        if plan["target_day"]
        else next_settlement(records, now.astimezone(WARSAW).date())
    )
