"""Read-only calendar-period energy totals from native Recorder statistics."""

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from functools import partial

from homeassistant.components.recorder import history, statistics
from homeassistant.helpers.recorder import get_instance
from homeassistant.util import dt as dt_util

from .energy import aggregate, consumer_summary, source_ids
from .history import async_read_counters, sample_from_state
from .ledger import WARSAW, LedgerError, Sample, calculate, energy, energy_text
from .planning import inventory_now

PERIODS = ("day", "week", "month", "year")
ENERGY_ROLES = (
    "pv_energy",
    "home_energy",
    "grid_import_energy",
    "grid_export_energy",
    "battery_charge_energy",
    "battery_discharge_energy",
)


@dataclass(frozen=True)
class Period:
    kind: str
    start: date
    stop: date
    begin: datetime
    end: datetime
    as_of: datetime
    is_current: bool


def period_bounds(kind, anchor_day, now):
    """Use local calendar boundaries, with UTC hours across 23/25-hour days."""
    try:
        anchor = date.fromisoformat(anchor_day)
        if anchor.isoformat() != anchor_day or kind not in PERIODS:
            raise ValueError
        if kind == "day":
            start, stop = anchor, anchor + timedelta(days=1)
        elif kind == "week":
            start = anchor - timedelta(days=anchor.weekday())
            stop = start + timedelta(days=7)
        elif kind == "month":
            start = anchor.replace(day=1)
            stop = date(start.year + (start.month == 12), start.month % 12 + 1, 1)
        else:
            start, stop = date(anchor.year, 1, 1), date(anchor.year + 1, 1, 1)
        begin = datetime.combine(start, time(), WARSAW).astimezone(UTC)
        end = datetime.combine(stop, time(), WARSAW).astimezone(UTC)
        if start <= date.min or now.tzinfo is None:
            raise ValueError
    except ValueError, TypeError, OverflowError:
        raise LedgerError(
            "invalid_date", "Wybierz dzień RRRR-MM-DD i poprawny okres."
        ) from None
    today = now.astimezone(WARSAW).date()
    if start > today:
        raise LedgerError("future_date", "Wybierz bieżący lub zakończony okres.")
    return Period(
        kind,
        start,
        stop,
        begin,
        end,
        min(end, now.astimezone(UTC).replace(minute=0, second=0, microsecond=0)),
        start <= today < stop,
    )


def sum_delta(points, begin, end):
    """Require the baseline and every completed hour, never invent gaps as zero."""
    try:
        sequence = [
            energy(points[stamp])
            for stamp in range(
                int(begin.timestamp()) - 3600, int(end.timestamp()), 3600
            )
        ]
        if not sequence or any(
            b < a for a, b in zip(sequence, sequence[1:], strict=False)
        ):
            return None
        return energy_text(sequence[-1] - sequence[0])
    except KeyError, TypeError, ValueError, LedgerError:
        return None


async def _raw_at(hass, ids, moment, max_age):
    """Actual cumulative states for manual sensors without sum statistics."""
    if not ids:
        return {}
    begin = moment - timedelta(hours=max_age)
    rows = await get_instance(hass).async_add_executor_job(
        partial(
            history.get_significant_states,
            hass,
            begin,
            moment,
            list(ids),
            include_start_time_state=False,
            significant_changes_only=False,
            minimal_response=False,
            no_attributes=False,
        )
    )
    result = {}
    for entity_id in ids:
        candidates = [
            state
            for state in rows.get(entity_id, [])
            if begin <= state.last_updated < moment
        ]
        try:
            result[entity_id] = sample_from_state(
                max(candidates, key=lambda state: state.last_updated)
            ).value
        except ValueError, LedgerError:
            result[entity_id] = None
    return result


def _absent(config, role):
    kind, prefix = (
        ("solar", "pv_")
        if role.startswith("pv_")
        else ("battery", "battery_")
        if role.startswith("battery_")
        else ("grid_export", "grid_export")
    )
    configured = any(key.startswith(prefix) for key in config["sources"]) or any(
        key.startswith(prefix) for key in config.get("statistics", {})
    )
    return config.get("presence", {}).get(kind) is False and not configured


def _label(bounds):
    if bounds.kind == "day":
        return bounds.start.strftime("%d.%m.%Y")
    if bounds.kind == "week":
        return f"{bounds.start:%d.%m}–{bounds.stop - timedelta(days=1):%d.%m.%Y}"
    return bounds.start.strftime("%m.%Y" if bounds.kind == "month" else "%Y")


async def _opening_stock(manager, day, now):
    records = [record for record in manager.records if record.day <= day.isoformat()]
    if not records:
        return None, None
    archived = {
        **getattr(manager, "daily_cache", {}),
        **getattr(manager, "checkpoint_cache", {}).get("samples", {}),
    }
    samples = {key: Sample(**value) for key, value in archived.items()}
    samples.update({record.day: record.sample for record in records})
    opening = samples.get(day.isoformat())
    if opening is None:
        opening = await async_read_counters(
            manager.hass, manager.sources, day.isoformat(), manager.max_age_hours, now
        )
    plan = getattr(manager, "planning", {})
    if plan.get("anchor_id"):
        inventory = inventory_now(
            plan,
            records,
            [
                (point, components)
                for point, components in getattr(manager, "checkpoints", [])
                if point < day
            ],
            opening.components,
            day,
        )
        return inventory.balance, inventory
    balance = calculate(records, opening.value)["current"]["estimated_balance"]
    return energy(balance) if balance is not None else None, None


async def _withdrawn(manager, bounds, points, core_totals, now):
    """Reuse the ledger's daily stock model; a grid import is not a withdrawal."""
    try:
        balance, inventory = await _opening_stock(
            manager, bounds.start - timedelta(days=1), now
        )
        if balance is None:
            return None
        total = energy(0)
        cursor = bounds.start
        invoices = {record.day: record for record in manager.records}
        while cursor < bounds.stop:
            begin = datetime.combine(cursor, time(), WARSAW).astimezone(UTC)
            end = min(
                datetime.combine(cursor + timedelta(days=1), time(), WARSAW).astimezone(
                    UTC
                ),
                bounds.as_of,
            )
            if begin >= end:
                break
            flows = {
                direction: sum_delta(points.get(entity_id, {}), begin, end)
                for direction, entity_id in manager.sources.items()
            }
            if bounds.kind == "day":
                flows = core_totals
            if any(value is None for value in flows.values()):
                return None
            imported, credited = (
                energy(flows["import"]),
                energy(flows["export"]) * energy("0.8"),
            )
            if inventory is not None:
                inventory.expire(cursor)
                inventory.credit(cursor.strftime("%Y-%m"), credited)
                balance = inventory.balance
                total += min(imported, max(energy(0), balance))
                inventory.consume(imported)
                balance = inventory.balance
            else:
                total += min(imported, max(energy(0), balance + credited))
                balance += credited - imported
            invoice = invoices.get(cursor.isoformat())
            if invoice and end == datetime.combine(
                cursor + timedelta(days=1), time(), WARSAW
            ).astimezone(UTC):
                if inventory is not None:
                    return None
                closing = calculate(
                    [record for record in manager.records if record.day <= invoice.day],
                    invoice.sample.value,
                )["current"]["estimated_balance"]
                if closing is None:
                    return None
                balance = energy(closing)
            cursor += timedelta(days=1)
        return energy_text(total)
    except LedgerError, TypeError, ValueError:
        return None


async def async_energy_period(manager, kind, anchor_day, now=None):
    """Read energy only; never save source data, invoices, caches or preferences."""
    now = now or dt_util.utcnow()
    bounds = period_bounds(kind, anchor_day, now)
    config, hass = manager.energy_config, manager.hass
    mappings = {}
    manual = set(manager.sources.values())
    for role in ENERGY_ROLES:
        explicit = config.get("statistics", {}).get(role)
        mappings[role] = explicit or source_ids(config["sources"].get(role))
        if not explicit:
            manual.update(mappings[role])
    if not mappings["grid_import_energy"]:
        mappings["grid_import_energy"] = [manager.sources["import"]]
    if not mappings["grid_export_energy"] and not _absent(config, "grid_export_energy"):
        mappings["grid_export_energy"] = [manager.sources["export"]]
    ids = set(manager.sources.values()) | {
        value for values in mappings.values() for value in values
    }
    for item in config["consumers"]:
        source = item.get("statistic") or item.get("energy")
        if source:
            ids.add(source)
            if not item.get("statistic"):
                manual.add(source)
    recorder = get_instance(hass)
    metadata = await recorder.async_add_executor_job(
        partial(statistics.get_metadata, hass, statistic_ids=ids)
    )
    statistical = {
        stat
        for stat in ids
        if stat in metadata
        and metadata[stat][1].get("has_sum")
        and metadata[stat][1].get("unit_class") == "energy"
    }
    rows = (
        await recorder.async_add_executor_job(
            partial(
                statistics.statistics_during_period,
                hass,
                bounds.begin - timedelta(hours=1),
                bounds.as_of,
                statistical,
                "hour",
                {"energy": "kWh"},
                {"sum"},
            )
        )
        if statistical
        else {}
    )
    points = {
        stat: {int(row["start"]): row.get("sum") for row in values}
        for stat, values in rows.items()
    }
    values_by_id = {
        stat: sum_delta(points.get(stat, {}), bounds.begin, bounds.as_of)
        for stat in statistical
    }
    raw = manual - statistical
    if raw:
        opening = await _raw_at(hass, raw, bounds.begin, manager.max_age_hours)
        closing = await _raw_at(hass, raw, bounds.as_of, manager.max_age_hours)
        for source in raw:
            start, stop = opening.get(source), closing.get(source)
            values_by_id[source] = (
                energy_text(energy(stop) - energy(start))
                if start is not None
                and stop is not None
                and energy(stop) >= energy(start)
                else None
            )
    values = {
        role: aggregate([values_by_id.get(source) for source in mappings[role]])
        for role in ENERGY_ROLES
    }
    for role in (
        "pv_energy",
        "battery_charge_energy",
        "battery_discharge_energy",
        "grid_export_energy",
    ):
        if not mappings[role] and _absent(config, role):
            values[role] = "0"
    if not mappings["home_energy"]:
        terms = {
            "pv_energy": 1,
            "grid_import_energy": 1,
            "grid_export_energy": -1,
            "battery_discharge_energy": 1,
            "battery_charge_energy": -1,
        }
        if all(values[role] is not None for role in terms):
            home = sum(
                (energy(values[role]) * sign for role, sign in terms.items()), energy(0)
            )
            values["home_energy"] = energy_text(home) if home >= 0 else None
    core_totals = {
        direction: values_by_id.get(source)
        for direction, source in manager.sources.items()
    }
    values["pge_credited_energy"] = (
        energy_text(energy(core_totals["export"]) * energy("0.8"))
        if core_totals["export"] is not None
        else None
    )
    values["pge_withdrawn_energy"] = await _withdrawn(
        manager, bounds, points, core_totals, now
    )
    consumers = [
        {
            **item,
            "id": item.get("id")
            or item.get("statistic")
            or item.get("energy")
            or item.get("power")
            or str(index),
            "period_kwh": values_by_id.get(item.get("statistic") or item.get("energy")),
        }
        for index, item in enumerate(config["consumers"])
    ]
    totals = consumer_summary(
        consumers,
        manager.data.get("energy", {}).get("values", {}).get("home_power"),
        values["home_energy"],
        energy_key="period_kwh",
    )
    arrays = []
    for source in mappings["pv_energy"]:
        state = hass.states.get(source)
        name = state.attributes.get("friendly_name") if state else None
        if not name and source in metadata:
            name = metadata[source][1].get("name")
        arrays.append(
            {
                "id": source,
                "name": name or source,
                "period_kwh": values_by_id.get(source),
            }
        )
    return {
        "period": kind,
        "anchor_day": anchor_day,
        "start_day": bounds.start.isoformat(),
        "end_day": (bounds.stop - timedelta(days=1)).isoformat(),
        "label": _label(bounds),
        "is_current": bounds.is_current,
        "as_of": bounds.as_of.isoformat(),
        "values": values,
        "consumers": consumers,
        "consumer_totals": totals,
        "pv_arrays": arrays,
        "pge_withdrawn_basis": "daily_ledger_model"
        if values["pge_withdrawn_energy"] is not None
        else "missing_stock_history",
    }
