"""Pure accounting logic. No Home Assistant state or database writes."""

from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal, InvalidOperation
from uuid import UUID
from zoneinfo import ZoneInfo

from .const import TIME_ZONE

WARSAW = ZoneInfo(TIME_ZONE)


class LedgerError(ValueError):
    """An actionable validation error, safe to show in the UI."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def energy(value: object) -> Decimal:
    """Accept finite signed kWh; retain decimal accuracy, reject bool/NaN/inf."""
    try:
        if isinstance(value, bool):
            raise ValueError
        result = Decimal(str(value))
        if not result.is_finite() or abs(result) > Decimal("1e15"):
            raise ValueError
        return result
    except InvalidOperation, ValueError:
        raise LedgerError(
            "invalid_energy", "Wpisz skończoną liczbę kWh (kropka dziesiętna)."
        ) from None


def optional_energy(value: object) -> str | None:
    return None if value is None or value == "" else str(energy(value))


def energy_text(value: Decimal) -> str:
    text = str(value)
    if "." in text and "E" not in text:
        text = text.rstrip("0").rstrip(".")
    return "0" if value == 0 else text


def boundary(day: str) -> datetime:
    """Exclusive end of a billing date: next local midnight, converted to UTC."""
    try:
        parsed = date.fromisoformat(day)
        if parsed.isoformat() != day:
            raise ValueError
        return datetime.combine(parsed + timedelta(days=1), time(), WARSAW).astimezone(
            UTC
        )
    except TypeError, ValueError, OverflowError:
        raise LedgerError("invalid_date", "Data musi mieć format RRRR-MM-DD.") from None


@dataclass(frozen=True)
class Sample:
    value: str
    recorded_at: str
    components: dict | None = None

    def validate(self, day: str) -> None:
        energy(self.value)
        try:
            stamp = datetime.fromisoformat(self.recorded_at)
            if stamp.tzinfo is None or stamp >= boundary(day):
                raise ValueError
        except TypeError, ValueError:
            raise LedgerError(
                "invalid_sample",
                "Próbka musi pochodzić sprzed końca dnia i zawierać strefę czasową.",
            ) from None

        if self.components is not None:
            try:
                if set(self.components) != {"import", "export"}:
                    raise ValueError
                for component in self.components.values():
                    if set(component) != {"value", "recorded_at"}:
                        raise ValueError
                    Sample(**component).validate(day)
                    if energy(component["value"]) < 0:
                        raise ValueError
                expected = Decimal("0.8") * energy(
                    self.components["export"]["value"]
                ) - energy(self.components["import"]["value"])
                latest = max(
                    datetime.fromisoformat(c["recorded_at"])
                    for c in self.components.values()
                )
                if (
                    energy(self.value) != expected
                    or datetime.fromisoformat(self.recorded_at) != latest
                ):
                    raise ValueError
            except TypeError, ValueError, KeyError, AttributeError:
                raise LedgerError(
                    "invalid_sample",
                    "Nieprawidłowe odczyty liczników importu i eksportu.",
                ) from None


def combine_counters(imported: Sample, exported: Sample) -> Sample:
    """Compute the balance ourselves, preserving both normalized kWh readings."""
    if energy(imported.value) < 0 or energy(exported.value) < 0:
        raise LedgerError(
            "invalid_counter",
            "Narastające liczniki importu i eksportu muszą być nieujemne.",
        )
    value = Decimal("0.8") * energy(exported.value) - energy(imported.value)
    latest = max(
        datetime.fromisoformat(imported.recorded_at),
        datetime.fromisoformat(exported.recorded_at),
    )
    return Sample(
        energy_text(value),
        latest.isoformat(),
        {
            "import": {"value": imported.value, "recorded_at": imported.recorded_at},
            "export": {"value": exported.value, "recorded_at": exported.recorded_at},
        },
    )


def check_counter_progression(previous: Sample, current: Sample) -> None:
    for name in ("import", "export"):
        if not previous.components or not current.components:
            raise LedgerError(
                "missing_counters",
                "Próbka nie zawiera oddzielnych liczników importu i eksportu.",
            )
        if energy(current.components[name]["value"]) < energy(
            previous.components[name]["value"]
        ):
            raise LedgerError(
                "counter_reset",
                f"Licznik {name} zmalał pomiędzy odczytami. Nie można wiarygodnie wyliczyć okresu przez reset lub zmianę licznika.",
            )


@dataclass(frozen=True)
class Settlement:
    id: str
    day: str
    sample: Sample
    invoice_balance: str | None = None
    correction: str | None = None
    note: str = ""
    invoice_shortfall: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, raw: dict) -> Settlement:
        try:
            if set(raw) != {
                "id",
                "day",
                "sample",
                "invoice_balance",
                "correction",
                "note",
                "invoice_shortfall",
            }:
                raise ValueError
            UUID(raw["id"])
            sample = Sample(**raw["sample"])
            sample.validate(raw["day"])
            invoice = optional_energy(raw["invoice_balance"])
            correction = optional_energy(raw["correction"])
            shortfall = optional_energy(raw["invoice_shortfall"])
            if shortfall is not None and energy(shortfall) < 0:
                raise LedgerError(
                    "invalid_shortfall", "Niedobór z faktury musi być nieujemny."
                )
            if invoice is not None and correction is not None:
                raise LedgerError(
                    "conflicting_balance",
                    "Podaj saldo z faktury albo korektę, nigdy oba naraz.",
                )
            if not isinstance(raw["note"], str) or len(raw["note"]) > 2000:
                raise ValueError
            return cls(
                raw["id"],
                raw["day"],
                sample,
                invoice,
                correction,
                raw["note"],
                shortfall,
            )
        except (KeyError, TypeError, ValueError, AttributeError) as err:
            if isinstance(err, LedgerError):
                raise
            raise LedgerError(
                "invalid_record", "Nieprawidłowy wpis rozliczenia."
            ) from None


def validate_records(raw: list[dict], now: datetime) -> list[Settlement]:
    if not isinstance(raw, list):
        raise LedgerError("invalid_import", "Rozliczenia muszą być listą.")
    records = [Settlement.from_dict(row) for row in raw]
    if len({r.id for r in records}) != len(records) or len(
        {r.day for r in records}
    ) != len(records):
        raise LedgerError(
            "duplicate_date", "Każda data i identyfikator muszą być unikalne."
        )
    if any(boundary(r.day) > now for r in records):
        raise LedgerError("future_date", "Można zapisać tylko zakończone dni.")
    return sorted(records, key=lambda row: row.day)


def calculate(records: list[Settlement], current: object | None) -> dict:
    """Recalculate all dependent periods; unknown opening balances stay unknown."""
    rows = []
    carry: Decimal | None = None
    previous: Settlement | None = None

    def number(value: Decimal | None) -> str | None:
        return None if value is None else str(value)

    for row in sorted(records, key=lambda r: r.day):
        delta = (
            energy(row.sample.value) - energy(previous.sample.value)
            if previous
            else None
        )
        estimate = carry + delta if carry is not None and delta is not None else None
        invoice = (
            energy(row.invoice_balance) if row.invoice_balance is not None else None
        )
        correction = energy(row.correction) if row.correction is not None else None
        difference = (
            invoice - estimate if invoice is not None and estimate is not None else None
        )
        if invoice is not None:
            carry = invoice
        elif estimate is not None:
            carry = estimate + (correction if correction is not None else Decimal(0))
        else:
            carry = None
        rows.append(
            {
                **row.to_dict(),
                "start_day": previous.day if previous else None,
                "period_balance": number(delta),
                "estimated_before_invoice": number(estimate),
                "invoice_difference": number(difference),
                "correction_applied": correction is not None and estimate is not None,
                "carried_balance": number(carry),
                "boundary_utc": boundary(row.day).isoformat(),
            }
        )
        previous = row

    live = None
    try:
        if current is not None:
            live = energy(current)
    except LedgerError:
        pass
    delta = (
        live - energy(previous.sample.value) if live is not None and previous else None
    )
    balance = carry + delta if carry is not None and delta is not None else None
    return {
        "records": rows,
        "current": {
            "start_day": previous.day if previous else None,
            "source_value": number(live),
            "period_balance": number(delta),
            "carried_balance": number(carry),
            "estimated_balance": number(balance),
            "available_energy": number(max(balance, Decimal(0)))
            if balance is not None
            else None,
            "deficit": number(max(-balance, Decimal(0)))
            if balance is not None
            else None,
        },
    }
