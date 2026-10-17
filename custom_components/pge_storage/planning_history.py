"""Read-only history for daily flows and an explicitly seasonal scenario."""

from dataclasses import asdict
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
from .planning import inventory_now, month_end


async def async_checkpoints(hass, sources, anchor, max_age, known=None):
    today = dt_util.utcnow().astimezone(WARSAW).date()
    cursor = month_end(date.fromisoformat(anchor.day))
    if cursor.isoformat() == anchor.day:
        cursor = month_end(cursor + timedelta(days=1))
    result = []
    while cursor < today:
        if len(result) >= 24:
            raise LedgerError(
                "old_anchor",
                "Dodaj nowszą fakturę do planowania roczników (maksymalnie 24 miesiące od ostatniej faktury).",
            )
        sample = (known or {}).get(cursor.isoformat())
        if sample is None:
            sample = await async_read_counters(
                hass, sources, cursor.isoformat(), max_age, dt_util.utcnow()
            )
        result.append((cursor, sample))
        cursor = month_end(cursor + timedelta(days=1))
    return result


def seasonal_profile(rows, sources, today):
    """Require every hourly sum and its baseline; never turn gaps into zero."""
    end = today.replace(day=1)
    profile, basis = {}, {}
    sums = {}
    for direction, entity_id in sources.items():
        sums[direction] = {
            int(item["start"]): item.get("sum") for item in rows.get(entity_id, [])
        }
    cursor = end
    for _ in range(12):
        previous = (cursor - timedelta(days=1)).replace(day=1)
        start_utc = datetime.combine(previous, time(), WARSAW).astimezone(UTC)
        end_utc = datetime.combine(cursor, time(), WARSAW).astimezone(UTC)
        stamps = range(
            int(start_utc.timestamp()) - 3600, int(end_utc.timestamp()), 3600
        )
        values = {}
        try:
            for direction in ("import",):
                series = [energy(sums[direction][stamp]) for stamp in stamps]
                if any(
                    current < prior
                    for prior, current in zip(series, series[1:], strict=False)
                ):
                    raise ValueError
                values[f"{direction}_kwh"] = energy_text(series[-1] - series[0])
        except KeyError, ValueError, TypeError:
            cursor = previous
            continue
        if previous.month not in profile:
            profile[previous.month] = {
                "month": previous.month,
                **values,
                "export_kwh": "0",
                "source_month": previous.strftime("%Y-%m"),
            }
            basis[str(previous.month)] = previous.strftime("%Y-%m")
        cursor = previous
    return {
        "profile": sorted(profile.values(), key=lambda x: x["month"]),
        "basis": basis,
        "missing": sorted(set(range(1, 13)) - profile.keys()),
        "note": "Pobór z sieci z ostatnich 12 zakończonych miesięcy. Dla każdego miesiąca projekcji używamy tego samego miesiąca rok wcześniej. Brak pełnych statystyk importu pozostaje pusty; eksport nie jest potrzebny. Nie zwiększamy zużycia i nie dodajemy przyszłej produkcji.",
    }


async def async_seasonal_profile(hass, sources):
    today = dt_util.utcnow().astimezone(WARSAW).date()
    end = datetime.combine(today.replace(day=1), time(), WARSAW).astimezone(UTC)
    start = datetime.combine(
        date(today.year - 1, today.month, 1), time(), WARSAW
    ).astimezone(UTC) - timedelta(hours=1)
    metadata = await get_instance(hass).async_add_executor_job(
        partial(statistics.get_metadata, hass, statistic_ids={sources["import"]})
    )
    for entity_id in (sources["import"],):
        if (
            entity_id not in metadata
            or not metadata[entity_id][1].get("has_sum")
            or metadata[entity_id][1].get("unit_class") != "energy"
        ):
            raise LedgerError(
                "missing_statistics",
                f"Brak statystyk poboru energii dla {entity_id}. Nie można odtworzyć zużycia z zeszłego roku.",
            )
    rows = await get_instance(hass).async_add_executor_job(
        partial(
            statistics.statistics_during_period,
            hass,
            start,
            end,
            {sources["import"]},
            "hour",
            {"energy": "kWh"},
            {"sum"},
        )
    )
    return seasonal_profile(rows, sources, today)


async def async_daily(
    hass,
    sources,
    records,
    live,
    month,
    max_age,
    plan=None,
    checkpoints=None,
    month_samples=None,
    daily_samples=None,
):
    try:
        start = date.fromisoformat(f"{month}-01")
        if start.strftime("%Y-%m") != month:
            raise ValueError
    except TypeError, ValueError:
        raise LedgerError("invalid_date", "Wybierz miesiąc RRRR-MM.") from None
    now = dt_util.utcnow()
    today = now.astimezone(WARSAW).date()
    end = min(month_end(start), today)
    if start > today:
        raise LedgerError(
            "future_date",
            "Tabela dzienna pokazuje odczyty rzeczywiste. Przyszłe daty znajdziesz w prognozie.",
        )
    frozen = {day: Sample(**value) for day, value in (daily_samples or {}).items()}
    frozen.update({row.day: row.sample for row in records})
    for day, value in (month_samples or {}).items():
        frozen.setdefault(day, Sample(**value))

    def balance_at(point_day, reading):
        relevant = [item for item in records if item.day <= point_day.isoformat()]
        if relevant:
            check_counter_progression(relevant[-1].sample, reading)
        if plan and relevant and plan["anchor_id"] == relevant[-1].id:
            points = [
                (day, components)
                for day, components in checkpoints or []
                if day < point_day
            ]
            return energy_text(
                inventory_now(
                    plan, relevant, points, reading.components, point_day
                ).balance
            )
        return calculate(relevant, reading.value)["current"]["estimated_balance"]

    archived = {}

    async def sample(day):
        if day == today:
            if live is None:
                raise LedgerError("missing_source", "Bieżący licznik jest niedostępny.")
            return live
        reading = frozen.get(day.isoformat())
        if reading is None:
            reading = await async_read_counters(
                hass, sources, day.isoformat(), max_age, now
            )
        archived[day.isoformat()] = asdict(reading)
        return reading

    try:
        previous = await sample(start - timedelta(days=1))
    except LedgerError:
        previous = None
    rows = []
    cursor = start
    while cursor <= end:
        row = {
            "day": cursor.isoformat(),
            "partial": cursor == today,
            "import_kwh": None,
            "export_kwh": None,
            "credited_kwh": None,
            "net_kwh": None,
            "balance_kwh": None,
            "withdrawn_kwh": None,
            "uncovered_import_kwh": None,
            "invoice": any(item.day == cursor.isoformat() for item in records),
        }
        current = None
        try:
            current = await sample(cursor)
            row["recorded_at"] = current.components
            try:
                row["balance_kwh"] = balance_at(cursor, current)
            except LedgerError as err:
                row["error"] = str(err)
            if previous is None:
                raise LedgerError(
                    "missing_history",
                    "Brak odczytu początku dnia; przepływy tego dnia są nieznane.",
                )
            check_counter_progression(previous, current)
            imported = energy(current.components["import"]["value"]) - energy(
                previous.components["import"]["value"]
            )
            exported = energy(current.components["export"]["value"]) - energy(
                previous.components["export"]["value"]
            )
            credited = exported * energy("0.8")
            row.update(
                {
                    "import_kwh": energy_text(imported),
                    "export_kwh": energy_text(exported),
                    "credited_kwh": energy_text(credited),
                    "net_kwh": energy_text(credited - imported),
                }
            )
            try:
                opening = balance_at(cursor - timedelta(days=1), previous)
            except LedgerError:
                opening = None
            if opening is not None:
                expired = energy(0)
                if (
                    plan
                    and plan["anchor_id"]
                    and row["balance_kwh"] is not None
                    and not row["invoice"]
                ):
                    expired = max(
                        energy(0),
                        energy(opening)
                        + credited
                        - imported
                        - energy(row["balance_kwh"]),
                    )
                row["expired_kwh"] = energy_text(expired)
                available = max(energy(0), energy(opening) + credited - expired)
                withdrawn = min(imported, available)
                row["withdrawn_kwh"] = energy_text(withdrawn)
                row["uncovered_import_kwh"] = energy_text(imported - withdrawn)
        except LedgerError as err:
            row["error"] = str(err)
        rows.append(row)
        previous = current
        cursor += timedelta(days=1)
    return {
        "month": month,
        "rows": rows,
        "archived_samples": archived,
        "basis": "Różnice rzeczywistych odczytów Recorder; dzień faktury może ustalać nowe saldo. Dla skonfigurowanych partii saldo uwzględnia miesięczny model FIFO i wygaśnięcia. Dla pozostałych faktur jest saldem pomiarowym bez wygaśnięć. Braki danych pozostają puste. Czasy odczytów są dostępne w szczegółach dnia.",
    }
