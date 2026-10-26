"""Clock-hour net metering. UTC identities, Warsaw calendars, no guessed gaps."""

from copy import deepcopy
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from .ledger import WARSAW, LedgerError, boundary, energy, energy_text
from .planning import Inventory, expires_on

MODEL = "clock_hour_net_0.8_v1"
FINALIZATION_DELAY = timedelta(0)
ZERO = Decimal(0)


def hour_floor(moment):
    return moment.astimezone(UTC).replace(minute=0, second=0, microsecond=0)


def settlement_flows(imported, exported):
    p, e = energy(imported), energy(exported)
    if min(p, e) < 0:
        raise LedgerError(
            "invalid_hour", "Przyrost liczników energii nie może być ujemny."
        )
    consumed, surplus = max(p - e, ZERO), max(e - p, ZERO)
    credit = surplus * Decimal("0.8")
    return {
        "raw_import_kwh": energy_text(p),
        "raw_export_kwh": energy_text(e),
        "import_kwh": energy_text(consumed),
        "export_kwh": energy_text(surplus),
        "credited_kwh": energy_text(credit),
        "net_kwh": energy_text(credit - consumed),
        "balance_kwh": energy_text(e - p),
    }


def make_hour(start, imported, exported, basis="native_hourly_sum", *, end=None):
    start = start.astimezone(UTC)
    if start != hour_floor(start):
        raise LedgerError(
            "invalid_hour", "Początek godziny musi być pełną godziną UTC."
        )
    end = end or start + timedelta(hours=1)
    if not start <= end <= start + timedelta(hours=1):
        raise LedgerError("invalid_hour", "Nieprawidłowy koniec przedziału godziny.")
    return {
        "start": start.isoformat(),
        "end": end.isoformat(),
        "basis": basis,
        **settlement_flows(imported, exported),
    }


def validate_archive(raw, sources, now):
    if raw is None:
        return {"model": MODEL, "sources": dict(sources), "hours": {}}
    try:
        if (
            set(raw) != {"model", "sources", "hours"}
            or raw["model"] != MODEL
            or raw["sources"] != sources
        ):
            raise ValueError
        hours = raw["hours"]
        if not isinstance(hours, dict) or len(hours) > 200000:
            raise ValueError
        checked = {}
        for key, row in hours.items():
            start = datetime.fromisoformat(key)
            if start.tzinfo is None:
                raise ValueError
            expected = make_hour(
                start, row["raw_import_kwh"], row["raw_export_kwh"], row["basis"]
            )
            if (
                row != expected
                or key != expected["start"]
                or datetime.fromisoformat(row["end"]) > now - FINALIZATION_DELAY
            ):
                raise ValueError
            if row["basis"] not in (
                "native_hourly_sum",
                "native_short_term_sum",
                "recorder_boundaries",
            ):
                raise ValueError
            checked[key] = expected
        return {"model": MODEL, "sources": dict(sources), "hours": checked}
    except (KeyError, TypeError, ValueError, AttributeError) as err:
        raise LedgerError(
            "invalid_hourly_archive",
            "Nieprawidłowe archiwum godzinowe lub inna para liczników.",
        ) from err


class HourBook:
    def __init__(self, hours=None, pending=None):
        self.hours = {**(hours or {}), **(pending or {})}

    def interval(self, begin, end):
        """Strict totals of independently netted hours; missing is never zero."""
        begin, end = begin.astimezone(UTC), end.astimezone(UTC)
        if begin != hour_floor(begin) or end < begin:
            raise LedgerError(
                "invalid_hour_range", "Okres musi zaczynać się na granicy godziny."
            )
        totals = dict.fromkeys(
            (
                "raw_import_kwh",
                "raw_export_kwh",
                "import_kwh",
                "export_kwh",
                "credited_kwh",
                "net_kwh",
            ),
            ZERO,
        )
        missing, count, cursor = [], 0, begin
        while cursor < end:
            stop = min(cursor + timedelta(hours=1), end)
            row = self.hours.get(cursor.isoformat())
            if row is None or datetime.fromisoformat(row["end"]) != stop:
                missing.append(cursor.isoformat())
            else:
                for key in totals:
                    totals[key] += energy(row[key])
                count += 1
            cursor += timedelta(hours=1)
        return {
            **{
                key: energy_text(value) if not missing else None
                for key, value in totals.items()
            },
            "complete": not missing,
            "missing_count": len(missing),
            "first_missing": missing[0] if missing else None,
            "known_hours": count,
            "start": begin.isoformat(),
            "end": end.isoformat(),
        }

    def ordered(self, begin, end):
        summary = self.interval(begin, end)
        if not summary["complete"]:
            raise LedgerError(
                "missing_hourly_history",
                f"Brak danych godzinowych: {summary['missing_count']} godz.; pierwsza {summary['first_missing']}. Nie zastępujemy ich zerami.",
            )
        cursor = begin
        while cursor < end:
            yield self.hours[cursor.isoformat()]
            cursor += timedelta(hours=1)


def seed_inventory(plan, records):
    if (
        not records
        or plan.get("anchor_id") != records[-1].id
        or records[-1].invoice_balance is None
    ):
        raise LedgerError(
            "missing_lots",
            "Dodaj partie energii z ostatniej faktury, aby ustalić terminy ważności.",
        )
    anchor = records[-1]
    total = sum(
        (energy(row["export_kwh"]) * Decimal("0.8") for row in plan["lots"]), ZERO
    )
    if total != max(ZERO, energy(anchor.invoice_balance)):
        raise LedgerError(
            "lots_mismatch", "Suma partii po opuście musi odpowiadać saldu faktury."
        )
    inventory = Inventory(debt=max(ZERO, -energy(anchor.invoice_balance)))
    for row in plan["lots"]:
        if row["month"] > anchor.day[:7] or row["expires_on"] < anchor.day:
            raise LedgerError(
                "invalid_lots", "Partie muszą istnieć i być ważne na dzień faktury."
            )
        inventory.credit(
            row["month"], energy(row["export_kwh"]) * Decimal("0.8"), row["expires_on"]
        )
    return inventory


def replay(book, records, plan, end):
    """Apply actual hourly events in order; invoice resets and FIFO are explicit."""
    relevant = [row for row in records if boundary(row.day) <= end]
    if not relevant:
        raise LedgerError(
            "missing_anchor", "Dodaj fakturę lub punkt początkowy z saldem."
        )
    last = relevant[-1]
    begin = boundary(last.day)
    # Carry through invoice-free records, with strict hour coverage for every leg.
    balance, previous = None, None
    for record in relevant:
        if previous and balance is not None:
            flows = book.interval(boundary(previous.day), boundary(record.day))
            balance = balance + energy(flows["net_kwh"]) if flows["complete"] else None
        if record.invoice_balance is not None:
            balance = energy(record.invoice_balance)
        elif balance is not None and record.correction is not None:
            balance += energy(record.correction)
        previous = record
    if balance is None:
        raise LedgerError(
            "missing_hourly_history",
            "Brak godzin lub znanego salda po ostatnim rozliczeniu.",
        )
    inventory = None
    lot_error = None
    if plan.get("anchor_id") == last.id:
        inventory = seed_inventory(plan, relevant)
    else:
        lot_error = (
            "Brak partii z terminami ważności; saldo bez uwzględnienia wygaśnięć."
        )
    withdrawn, uncovered = ZERO, ZERO
    for row in book.ordered(begin, end):
        at = datetime.fromisoformat(row["start"]).astimezone(WARSAW)
        consumed, credited = energy(row["import_kwh"]), energy(row["credited_kwh"])
        if inventory is not None:
            inventory.expire(at.date())
            inventory.credit(
                at.strftime("%Y-%m"), credited, expires_on(at.strftime("%Y-%m"))
            )
            available = max(ZERO, inventory.balance)
            taken = min(consumed, available)
            inventory.consume(consumed)
            balance = inventory.balance
        else:
            taken = min(consumed, max(ZERO, balance + credited))
            balance += credited - consumed
        withdrawn += taken
        uncovered += consumed - taken
    if inventory is not None:
        inventory.expire(end.astimezone(WARSAW).date())
        balance = inventory.balance
    return {
        "balance": balance,
        "inventory": inventory,
        "inventory_error": lot_error,
        "withdrawn_kwh": energy_text(withdrawn),
        "uncovered_kwh": energy_text(uncovered),
        "flows": book.interval(begin, end),
        "start_day": last.day,
    }


def accounting_snapshot(book, records, plan, end):
    rows, previous, carry = [], None, None
    for record in records:
        flows = (
            book.interval(boundary(previous.day), boundary(record.day))
            if previous
            else None
        )
        delta = flows["net_kwh"] if flows else None
        before = (
            carry + energy(delta) if carry is not None and delta is not None else None
        )
        invoice = (
            energy(record.invoice_balance)
            if record.invoice_balance is not None
            else None
        )
        if invoice is not None:
            carry = invoice
        elif before is not None:
            carry = before + (
                energy(record.correction) if record.correction is not None else ZERO
            )
        else:
            carry = None
        rows.append(
            {
                **record.to_dict(),
                "start_day": previous.day if previous else None,
                "period_balance": delta,
                "estimated_before_invoice": energy_text(before)
                if before is not None
                else None,
                "invoice_difference": energy_text(invoice - before)
                if invoice is not None and before is not None
                else None,
                "correction_applied": record.correction is not None
                and before is not None,
                "carried_balance": energy_text(carry) if carry is not None else None,
                "boundary_utc": boundary(record.day).isoformat(),
                "coverage": flows,
            }
        )
        previous = record
    current = {
        "start_day": previous.day if previous else None,
        "source_value": None,
        "period_balance": None,
        "carried_balance": energy_text(carry) if carry is not None else None,
        "estimated_balance": None,
        "available_energy": None,
        "deficit": None,
        "import_since_settlement_kwh": None,
        "export_since_settlement_kwh": None,
        "credited_since_settlement_kwh": None,
    }
    result = {
        "records": rows,
        "current": current,
        "accounting_model": MODEL,
        "accounting_as_of": end.isoformat(),
    }
    try:
        state = replay(book, records, plan, end)
        balance, flows = state["balance"], state["flows"]
        current.update(
            {
                "estimated_balance": energy_text(balance),
                "available_energy": energy_text(max(ZERO, balance)),
                "deficit": energy_text(max(ZERO, -balance)),
                "period_balance": energy_text(
                    balance - energy(current["carried_balance"])
                ),
                "net_flow_since_settlement_kwh": flows["net_kwh"],
                "expired_since_settlement_kwh": energy_text(state["inventory"].expired)
                if state["inventory"] is not None
                else None,
                "import_since_settlement_kwh": state["withdrawn_kwh"],
                "net_import_since_settlement_kwh": flows["import_kwh"],
                "export_since_settlement_kwh": flows["export_kwh"],
                "credited_since_settlement_kwh": flows["credited_kwh"],
                "raw_import_since_settlement_kwh": flows["raw_import_kwh"],
                "raw_export_since_settlement_kwh": flows["raw_export_kwh"],
            }
        )
        result["inventory_error"] = state["inventory_error"]
        result["inventory_state"] = state["inventory"]
    except LedgerError as err:
        result["accounting_error"] = str(err)
        result["inventory_state"] = None
    return result


def copy_inventory(inventory):
    if inventory is None:
        return None
    result = Inventory(deepcopy(inventory.lots), inventory.debt)
    result.expired = inventory.expired
    return result


def extend_accounting(prefix, row):
    """Replace the provisional hour, never accumulate its successive readings."""
    result = deepcopy(prefix)
    result["accounting_as_of"] = row["end"]
    current = result["current"]
    if current["estimated_balance"] is None:
        return result
    inventory = result.get("inventory_state")
    used, credited = energy(row["import_kwh"]), energy(row["credited_kwh"])
    balance = energy(current["estimated_balance"])
    if inventory is not None:
        at = datetime.fromisoformat(row["start"]).astimezone(WARSAW)
        inventory.expire(at.date())
        inventory.credit(at.strftime("%Y-%m"), credited)
        withdrawn = min(used, max(ZERO, inventory.balance))
        inventory.consume(used)
        balance = inventory.balance
    else:
        withdrawn = min(used, max(ZERO, balance + credited))
        balance += credited - used
    additions = {
        "net_flow_since_settlement_kwh": row["net_kwh"],
        "import_since_settlement_kwh": energy_text(withdrawn),
        "net_import_since_settlement_kwh": row["import_kwh"],
        "export_since_settlement_kwh": row["export_kwh"],
        "credited_since_settlement_kwh": row["credited_kwh"],
        "raw_import_since_settlement_kwh": row["raw_import_kwh"],
        "raw_export_since_settlement_kwh": row["raw_export_kwh"],
    }
    for key, value in additions.items():
        current[key] = energy_text(energy(current.get(key) or "0") + energy(value))
    current.update(
        period_balance=energy_text(balance - energy(current["carried_balance"])),
        expired_since_settlement_kwh=energy_text(inventory.expired)
        if inventory is not None
        else None,
        estimated_balance=energy_text(balance),
        available_energy=energy_text(max(ZERO, balance)),
        deficit=energy_text(max(ZERO, -balance)),
    )
    return result
