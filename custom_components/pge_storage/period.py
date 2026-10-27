"""Read-only calendar-period energy totals from native Recorder statistics."""

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from functools import partial

from homeassistant.components.recorder import history, statistics
from homeassistant.helpers.recorder import get_instance
from homeassistant.util import dt as dt_util

from .energy import consumer_summary, source_ids
from .energy_statistics import async_available_statistics, balanced_total
from .history import sample_from_state
from .ledger import WARSAW, LedgerError, energy, energy_text

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
        min(
            end,
            now.astimezone(UTC).replace(
                minute=now.minute // 5 * 5, second=0, microsecond=0
            ),
        ),
        start <= today < stop,
    )


def pending_statistics_hour(series, end):
    """Align all balance components to the same last compiled hour."""
    last = int(end.timestamp()) - 3600
    return any(
        last not in points and last - 3600 in points for points in series.values()
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
    observed, coverage = await async_available_statistics(
        hass, statistical, bounds.begin, bounds.as_of, rows
    )
    values_by_id = {
        stat: row["value"] if row else None for stat, row in coverage.items()
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

    def partial_sum(ids):
        known = [
            values_by_id[source]
            for source in ids
            if values_by_id.get(source) is not None
        ]
        return (
            energy_text(sum((energy(value) for value in known), energy(0)))
            if known
            else None
        )

    values = {role: partial_sum(mappings[role]) for role in ENERGY_ROLES}
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
        if all(source in statistical for role in terms for source in mappings[role]):
            signed = {
                source: sign
                for role, sign in terms.items()
                for source in mappings[role]
            }
            balanced = balanced_total(
                {source: observed.get(source, {}) for source in signed},
                signed,
                bounds.begin,
                bounds.as_of,
            )
            values["home_energy"] = balanced["value"] if balanced else None
        elif all(values[role] is not None for role in terms):
            home = sum(
                (energy(values[role]) * sign for role, sign in terms.items()), energy(0)
            )
            values["home_energy"] = energy_text(home) if home >= 0 else None
    from .hourly_views import period_values

    billing_end = min(bounds.as_of, manager.hourly_as_of)
    if billing_end < bounds.begin:
        billing_end = bounds.begin
    values.update(period_values(manager, bounds.begin, billing_end))
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
        "coverage": coverage,
        "partial": any(row is None or row["partial"] for row in coverage.values())
        or any(values_by_id.get(source) is None for source in ids),
        "consumers": consumers,
        "consumer_totals": totals,
        "pv_arrays": arrays,
        "pge_withdrawn_basis": "clock_hour_net_fifo"
        if values["pge_withdrawn_energy"] is not None
        else "missing_stock_history",
    }
