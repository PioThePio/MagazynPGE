"""All financial views use the same strict, independently balanced hour book."""

from datetime import UTC, date, datetime, time, timedelta

from homeassistant.util import dt as dt_util

from .hourly import replay
from .ledger import WARSAW, LedgerError, energy, energy_text
from .overview import shift_month, usage_target
from .planning import month_end


def midnight(day):
    return datetime.combine(day, time(), WARSAW).astimezone(UTC)


def period_values(manager, begin, end):
    book = manager.hour_book()
    flows = book.interval(begin, end)
    result = {
        "pge_credited_energy": flows["credited_kwh"],
        "pge_opust_deduction_energy": energy_text(
            energy(flows["export_kwh"]) * energy("0.2")
        )
        if flows["export_kwh"] is not None
        else None,
        "pge_withdrawn_energy": None,
        "pge_net_import_energy": flows["import_kwh"],
        "pge_net_export_energy": flows["export_kwh"],
        "pge_coverage": flows,
    }
    try:
        opening = replay(book, manager.records, manager.planning, begin)
        closing = replay(book, manager.records, manager.planning, end)
        if opening["start_day"] == closing["start_day"]:
            result["pge_withdrawn_energy"] = energy_text(
                energy(closing["withdrawn_kwh"]) - energy(opening["withdrawn_kwh"])
            )
        else:
            # Split at invoices; each interval has an independently known stock.
            cuts = [
                begin,
                *[
                    midnight(date.fromisoformat(row.day) + timedelta(days=1))
                    for row in manager.records
                    if begin
                    < midnight(date.fromisoformat(row.day) + timedelta(days=1))
                    < end
                ],
                end,
            ]
            total = energy(0)
            for start, stop in zip(cuts, cuts[1:], strict=False):
                segment = _withdrawn_segment(manager, start, stop)
                total += energy(segment)
            result["pge_withdrawn_energy"] = energy_text(total)
    except LedgerError:
        pass
    return result


def _withdrawn_segment(manager, begin, end):
    # Replay to just before a closing invoice boundary, so its reset cannot
    # erase the consumption in the interval that ends there.
    records = [
        row
        for row in manager.records
        if midnight(date.fromisoformat(row.day) + timedelta(days=1)) <= begin
    ]
    opening = replay(manager.hour_book(), records, manager.planning, begin)
    closing = replay(manager.hour_book(), records, manager.planning, end)
    return energy_text(
        energy(closing["withdrawn_kwh"]) - energy(opening["withdrawn_kwh"])
    )


def row_for(manager, start, stop, *, label, partial):
    book = manager.hour_book()
    flows = book.interval(start, stop)
    financial = period_values(manager, start, stop)
    row = {
        **label,
        "partial": partial,
        "import_kwh": financial["pge_withdrawn_energy"],
        "net_import_kwh": flows["import_kwh"],
        "export_kwh": flows["export_kwh"],
        "raw_import_kwh": flows["raw_import_kwh"],
        "raw_export_kwh": flows["raw_export_kwh"],
        "credited_kwh": flows["credited_kwh"],
        "net_kwh": flows["net_kwh"],
        "balance_kwh": None,
        "withdrawn_kwh": financial["pge_withdrawn_energy"],
        "coverage": flows,
        "estimated": flows.get("estimated", False),
        "accounting_model": "clock_hour_net_0.8_v1",
    }
    try:
        state = replay(book, manager.records, manager.planning, stop)
        row["balance_kwh"] = energy_text(state["balance"])
    except LedgerError as err:
        row["error"] = str(err)
    return row


def daily(manager, month):
    try:
        start = date.fromisoformat(f"{month}-01")
        if start.strftime("%Y-%m") != month:
            raise ValueError
    except TypeError, ValueError:
        raise LedgerError("invalid_date", "Wybierz miesiąc RRRR-MM.") from None
    now = dt_util.utcnow()
    today = now.astimezone(WARSAW).date()
    if start > today:
        raise LedgerError("future_date", "Wybierz bieżący lub zakończony miesiąc.")
    cursor, rows = start, []
    while cursor <= min(month_end(start), today):
        stop = min(midnight(cursor + timedelta(days=1)), manager.hourly_as_of)
        if stop < midnight(cursor):
            stop = midnight(cursor)
        rows.append(
            row_for(
                manager,
                midnight(cursor),
                stop,
                label={"day": cursor.isoformat()},
                partial=cursor == today,
            )
        )
        cursor += timedelta(days=1)
    return {
        "month": month,
        "rows": rows,
        "updated_at": now.isoformat(),
        "basis": "Bilans każdej godziny osobno, potem opust 0,8. Saldo uwzględnia FIFO i wygaśnięcia tylko przy znanych partiach; brakujące godziny pozostają nieznane.",
        "accounting_as_of": manager.hourly_as_of.isoformat(),
    }


async def months(manager, count=12):
    await manager.async_refresh_planning_history()
    now = dt_util.utcnow()
    today = now.astimezone(WARSAW).date()
    first = (
        date.fromisoformat(manager.records[0].day).replace(day=1)
        if manager.records
        else today.replace(day=1)
    )
    rows = []
    for i in reversed(range(count)):
        start = shift_month(today.replace(day=1), -i)
        if start < first:
            continue
        stop = min(midnight(shift_month(start, 1)), manager.hourly_as_of)
        rows.append(
            row_for(
                manager,
                midnight(start),
                max(midnight(start), stop),
                label={"month": start.strftime("%Y-%m")},
                partial=start == today.replace(day=1),
            )
        )
    return {"rows": rows, "updated_at": now.isoformat()}


def month_usage(book, start, as_of):
    begin, end = midnight(start), min(midnight(shift_month(start, 1)), as_of)
    if end <= begin:
        return None
    return book.interval(begin, end)["import_kwh"]


def comparison(book, plan, records, now, as_of):
    start, target = (
        now.astimezone(WARSAW).date().replace(day=1),
        usage_target(plan, records, now),
    )
    result, cursor = [], start
    while cursor <= target and len(result) < 25:
        previous = shift_month(cursor, -12)
        result.append(
            {
                "month": cursor.strftime("%Y-%m"),
                "previous_month": previous.strftime("%Y-%m"),
                "previous_kwh": month_usage(book, previous, as_of),
                "current_kwh": month_usage(book, cursor, as_of)
                if cursor <= start
                else None,
                "partial": cursor == start,
                "basis": "hourly_net_import",
            }
        )
        cursor = shift_month(cursor, 1)
    return result


def seasonal(book, now):
    cursor = now.astimezone(WARSAW).date().replace(day=1)
    profile, basis = [], {}
    for _ in range(12):
        month = shift_month(cursor, -1)
        value = month_usage(book, month, midnight(cursor))
        if value is not None:
            profile.append(
                {
                    "month": month.month,
                    "import_kwh": value,
                    "export_kwh": "0",
                    "source_month": month.strftime("%Y-%m"),
                }
            )
            basis[str(month.month)] = month.strftime("%Y-%m")
        cursor = month
    return {
        "profile": sorted(profile, key=lambda row: row["month"]),
        "basis": basis,
        "missing": sorted(set(range(1, 13)) - {row["month"] for row in profile}),
        "note": "Pobór po bilansowaniu każdej godziny. Potrzebne są oba liczniki i komplet godzin miesiąca; braków nie zastępujemy zerem.",
    }
