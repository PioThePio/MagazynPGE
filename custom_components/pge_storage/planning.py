"""Explicit invoice lots and seasonal scenarios, separate from the signed ledger."""

from calendar import monthrange
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal

from .ledger import (
    WARSAW,
    LedgerError,
    Sample,
    boundary,
    check_counter_progression,
    energy,
    energy_text,
)

ZERO = Decimal(0)
OPUST = Decimal("0.8")


def validate_daily_cache(raw, now):
    if not isinstance(raw, dict) or len(raw) > 20000:
        raise LedgerError("invalid_daily_cache", "Nieprawidłowe archiwum dzienne.")
    try:
        for day, value in raw.items():
            sample = Sample(**value)
            sample.validate(day)
            if sample.components is None or boundary(day) > now:
                raise ValueError
    except (TypeError, ValueError) as err:
        raise LedgerError(
            "invalid_daily_cache", "Nieprawidłowy odczyt w archiwum dziennym."
        ) from err
    return raw


def validate_checkpoints(raw, records):
    empty = {"anchor_id": None, "samples": {}}
    if raw is None:
        return empty
    try:
        if (
            set(raw) != {"anchor_id", "samples"}
            or not isinstance(raw["samples"], dict)
            or len(raw["samples"]) > 24
        ):
            raise ValueError
        anchor = next((r for r in records if r.id == raw["anchor_id"]), None)
        if anchor is None:
            return empty
        previous = anchor.sample
        for day, data in sorted(raw["samples"].items()):
            parsed = date.fromisoformat(day)
            if parsed != month_end(parsed) or day <= anchor.day:
                raise ValueError
            sample = Sample(**data)
            sample.validate(day)
            check_counter_progression(previous, sample)
            previous = sample
        return raw
    except (TypeError, KeyError, ValueError) as err:
        raise LedgerError(
            "invalid_checkpoints", "Nieprawidłowe zapisane odczyty końców miesięcy."
        ) from err


def month_end(day: date) -> date:
    return day.replace(day=monthrange(day.year, day.month)[1])


def expires_on(month: str) -> str:
    start = date.fromisoformat(f"{month}-01")
    return month_end(start.replace(year=start.year + 1)).isoformat()


def winter_end(today: date) -> date:
    end = date(today.year, 3, 31)
    return end if today <= end else end.replace(year=today.year + 1)


def validate_plan(raw: object) -> dict:
    if not isinstance(raw, dict) or set(raw) - {
        "anchor_id",
        "lots",
        "profile",
        "target_day",
    }:
        raise LedgerError("invalid_plan", "Nieprawidłowy plan magazynu.")
    try:
        anchor = raw.get("anchor_id")
        if anchor is not None and not isinstance(anchor, str):
            raise ValueError
        target = raw.get("target_day") or None
        if target is not None and date.fromisoformat(target).isoformat() != target:
            raise ValueError
        lots, profile = [], []
        if not isinstance(raw.get("lots", []), list) or not isinstance(
            raw.get("profile", []), list
        ):
            raise ValueError
        if len(raw.get("lots", [])) > 120 or len(raw.get("profile", [])) > 12:
            raise ValueError
        for item in raw.get("lots", []):
            if set(item) != {"month", "export_kwh", "expires_on"}:
                raise ValueError
            month = item["month"]
            start = date.fromisoformat(f"{month}-01")
            if start.strftime("%Y-%m") != month:
                raise ValueError
            expiry = date.fromisoformat(item["expires_on"])
            amount = energy(item["export_kwh"])
            if expiry <= month_end(start) or expiry != month_end(expiry) or amount < 0:
                raise ValueError
            lots.append(
                {
                    "month": month,
                    "export_kwh": energy_text(amount),
                    "expires_on": expiry.isoformat(),
                }
            )
        for item in raw.get("profile", []):
            if set(item) != {"month", "import_kwh", "export_kwh"}:
                raise ValueError
            month = item["month"]
            if type(month) is not int or not 1 <= month <= 12:
                raise ValueError
            imported, exported = energy(item["import_kwh"]), energy(item["export_kwh"])
            if min(imported, exported) < 0:
                raise ValueError
            profile.append(
                {
                    "month": month,
                    "import_kwh": energy_text(imported),
                    "export_kwh": energy_text(exported),
                }
            )
        if len({item["month"] for item in lots}) != len(lots) or len(
            {item["month"] for item in profile}
        ) != len(profile):
            raise ValueError
        return {
            "anchor_id": anchor,
            "lots": sorted(lots, key=lambda x: x["month"]),
            "profile": sorted(profile, key=lambda x: x["month"]),
            "target_day": target,
        }
    except (TypeError, ValueError, KeyError, AttributeError) as err:
        raise LedgerError(
            "invalid_plan",
            "Sprawdź miesiące, nieujemne kWh i daty ważności. Każdy miesiąc wpisz raz.",
        ) from err


class Inventory:
    """FIFO by expiry; all amounts are usable kWh, never raw exported energy."""

    def __init__(self, lots=None, debt=ZERO):
        self.lots = [dict(item) for item in lots or []]
        self.debt = debt
        self.expired = ZERO

    @property
    def balance(self):
        return sum((item["kwh"] for item in self.lots), ZERO) - self.debt

    def expire(self, day):
        for item in self.lots:
            if item["expires_on"] < day.isoformat():
                self.expired += item["kwh"]
                item["kwh"] = ZERO

    def credit(self, month, amount, expiry=None):
        repaid = min(self.debt, amount)
        self.debt -= repaid
        amount -= repaid
        if amount <= 0:
            return
        expiry = expiry or expires_on(month)
        item = next(
            (x for x in self.lots if x["month"] == month and x["expires_on"] == expiry),
            None,
        )
        if item:
            item["kwh"] += amount
        else:
            self.lots.append({"month": month, "expires_on": expiry, "kwh": amount})

    def consume(self, amount):
        for item in sorted(self.lots, key=lambda x: (x["expires_on"], x["month"])):
            taken = min(item["kwh"], amount)
            item["kwh"] -= taken
            amount -= taken
        self.debt += amount

    def serialize(self, include_empty=False):
        return [
            {**item, "kwh": energy_text(item["kwh"])}
            for item in sorted(self.lots, key=lambda x: (x["expires_on"], x["month"]))
            if include_empty or item["kwh"] > 0
        ]


def inventory_now(plan, records, checkpoints, live, today):
    """Replay gross counter changes; a net gain does not preserve old FIFO lots."""
    if not records or plan["anchor_id"] != records[-1].id:
        raise LedgerError(
            "missing_lots",
            "Dodaj partie energii z ostatniej faktury, aby ustalić terminy ważności.",
        )
    anchor = records[-1]
    if anchor.invoice_balance is None:
        raise LedgerError("missing_lots", "Wpis odniesienia musi mieć saldo z faktury.")
    total = sum((energy(item["export_kwh"]) * OPUST for item in plan["lots"]), ZERO)
    if total != max(ZERO, energy(anchor.invoice_balance)):
        raise LedgerError(
            "lots_mismatch",
            "Suma partii po opuście musi odpowiadać dodatniemu saldu wybranej faktury.",
        )
    if any(
        item["month"] > anchor.day[:7] or item["expires_on"] < anchor.day
        for item in plan["lots"]
    ):
        raise LedgerError(
            "invalid_lots", "Partie muszą istnieć i być ważne na dzień faktury."
        )
    inventory = Inventory(debt=max(ZERO, -energy(anchor.invoice_balance)))
    for item in plan["lots"]:
        inventory.credit(
            item["month"], energy(item["export_kwh"]) * OPUST, item["expires_on"]
        )
    previous = anchor.sample.components
    last = date.fromisoformat(anchor.day)
    for point_day, components in [*checkpoints, (today, live)]:
        if components is None:
            raise LedgerError(
                "missing_source",
                "Brak bieżących odczytów do wyznaczenia partii energii.",
            )
        if point_day <= last:
            continue
        end = (
            month_end(last)
            if last != month_end(last)
            else month_end(last + timedelta(days=1))
        )
        # Every completed month must have a real boundary sample. Do not put
        # several months of exports in one invented vintage.
        if point_day > end:
            raise LedgerError(
                "missing_month",
                "Brakuje odczytu końca miesiąca do ustalenia roczników energii. Odśwież historię planu.",
            )
        deltas = {
            key: energy(components[key]["value"]) - energy(previous[key]["value"])
            for key in ("import", "export")
        }
        if min(deltas.values()) < 0:
            raise LedgerError(
                "counter_reset", "Licznik zmalał od faktury lub końca miesiąca."
            )
        # Month-level replay: expire previous-month lots, credit this month's
        # export, draw the oldest lots, expire at the end of the interval.
        inventory.expire(last + timedelta(days=1))
        inventory.credit(point_day.strftime("%Y-%m"), OPUST * deltas["export"])
        inventory.consume(deltas["import"])
        inventory.expire(point_day)
        previous, last = components, point_day
    return inventory


def planning_snapshot(
    plan, records, checkpoints, live, balance, now, history_error=None
):
    today = now.astimezone(WARSAW).date()
    target = (
        date.fromisoformat(plan["target_day"])
        if plan["target_day"]
        else winter_end(today)
    )
    result = {
        "config": plan,
        "target_day": target.isoformat(),
        "inventory": None,
        "forecast": None,
    }
    invalid_target = target < today or (target - today).days > 730
    if invalid_target:
        result["error"] = (
            "Wybierz przyszłą datę prognozy, maksymalnie dwa lata naprzód."
        )
    days = Decimal((target - today).days + 1)
    result["daily_budget_kwh"] = (
        energy_text(max(ZERO, energy(balance)) / days)
        if balance is not None and not invalid_target
        else None
    )
    try:
        if history_error:
            raise LedgerError("missing_month", history_error)
        inventory = inventory_now(plan, records, checkpoints, live, today)
        result["inventory"] = {
            "lots": inventory.serialize(include_empty=True),
            "balance_kwh": energy_text(inventory.balance),
            "expired_kwh": energy_text(inventory.expired),
            "next_expiry": next((x["expires_on"] for x in inventory.serialize()), None),
        }
    except LedgerError as err:
        result["inventory_error"] = str(err)
        return result
    if invalid_target:
        return result
    profiles = {item["month"]: item for item in plan["profile"]}
    cursor = today
    required = set()
    while cursor <= target:
        required.add(cursor.month)
        cursor = month_end(cursor) + timedelta(days=1)
    missing = sorted(required - profiles.keys())
    if missing:
        result["missing_profile_months"] = missing
        return result
    counters = {key: energy(live[key]["value"]) for key in ("import", "export")}
    start = inventory.balance
    low, first_shortfall, rows = start, today.isoformat() if start < 0 else None, []
    imported = exported = ZERO
    cursor = today
    while cursor <= target:
        # Current counters are "now", so project only the remainder of today.
        fraction = Decimal(1)
        if cursor == today:
            start_day = datetime.combine(cursor, time(), WARSAW).astimezone(UTC)
            end_day = datetime.combine(
                cursor + timedelta(days=1), time(), WARSAW
            ).astimezone(UTC)
            fraction = Decimal(str((end_day - now).total_seconds())) / Decimal(
                str((end_day - start_day).total_seconds())
            )
        profile = profiles[cursor.month]
        count = Decimal(monthrange(cursor.year, cursor.month)[1])
        day_import = energy(profile["import_kwh"]) / count * fraction
        day_export = energy(profile["export_kwh"]) / count * fraction
        imported += day_import
        exported += day_export
        inventory.expire(cursor)
        inventory.credit(cursor.strftime("%Y-%m"), OPUST * day_export)
        inventory.consume(day_import)
        low = min(low, inventory.balance)
        if inventory.balance < 0 and first_shortfall is None:
            first_shortfall = cursor.isoformat()
        if cursor == month_end(cursor) or cursor == target:
            rows.append(
                {
                    "day": cursor.isoformat(),
                    "import_counter": energy_text(counters["import"] + imported),
                    "export_counter": energy_text(counters["export"] + exported),
                    "balance_kwh": energy_text(inventory.balance),
                    "expired_kwh": energy_text(inventory.expired),
                    "import_kwh": energy_text(imported),
                    "export_kwh": energy_text(exported),
                }
            )
        cursor += timedelta(days=1)
    result["forecast"] = {
        "rows": rows,
        "balance_kwh": energy_text(inventory.balance),
        "shortfall_kwh": energy_text(max(ZERO, -inventory.balance)),
        "first_shortfall_day": first_shortfall,
        "minimum_balance_kwh": energy_text(low),
        "expired_kwh": energy_text(inventory.expired),
        "opening_balance_kwh": energy_text(start),
        "lots": inventory.serialize(),
    }
    return result
