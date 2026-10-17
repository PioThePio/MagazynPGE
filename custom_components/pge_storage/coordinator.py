"""Durable per-entry ledger, with serialized and revision-checked writes."""

import asyncio
import logging
from dataclasses import replace
from uuid import uuid4

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from .const import (
    DEFAULT_MAX_AGE_HOURS,
    DOMAIN,
    SIGNAL_LEDGER_UPDATED,
    STORAGE_VERSION,
    TIME_ZONE,
)
from .history import async_read_counters, sample_from_state
from .ledger import (
    LedgerError,
    Settlement,
    calculate,
    check_counter_progression,
    combine_counters,
    optional_energy,
    validate_records,
)

_LOGGER = logging.getLogger(__name__)


class LedgerCoordinator(DataUpdateCoordinator):
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(hass, _LOGGER, config_entry=entry, name=DOMAIN)
        self.entry = entry
        self.sources = dict(entry.data["sources"])
        self.records: list[Settlement] = []
        self.revision = 0
        self.lock = asyncio.Lock()
        self.store = Store(hass, STORAGE_VERSION, f"{DOMAIN}.{entry.entry_id}")

    @property
    def max_age_hours(self) -> int:
        return self.entry.options.get("max_age_hours", DEFAULT_MAX_AGE_HOURS)

    async def async_load(self) -> None:
        data = await self.store.async_load()
        if data is not None:
            if data.get("sources") != self.sources or not isinstance(
                data.get("revision"), int
            ):
                raise LedgerError(
                    "invalid_storage", "Nieprawidłowy rejestr. Przywróć kopię zapasową."
                )
            self.records = self._validated(data["records"])
            self.revision = data["revision"]
        self.publish()
        self.entry.async_on_unload(
            async_track_state_change_event(
                self.hass, list(self.sources.values()), self._source_changed
            )
        )

    @callback
    def _source_changed(self, _event) -> None:
        self.publish()

    @callback
    def publish(self) -> None:
        current = None
        source_values = {}
        source_error = None
        try:
            samples = {
                name: sample_from_state(self.hass.states.get(entity_id))
                for name, entity_id in self.sources.items()
            }
            source_values = {name: sample.value for name, sample in samples.items()}
            sample = combine_counters(samples["import"], samples["export"])
            if self.records:
                check_counter_progression(self.records[-1].sample, sample)
            current = sample.value
        except LedgerError as err:
            source_error = str(err)
        snapshot = calculate(self.records, current)
        snapshot.update(
            {
                "entry_id": self.entry.entry_id,
                "loaded": True,
                "sources": self.sources,
                "source_values": source_values,
                "source_error": source_error,
                "revision": self.revision,
                "time_zone": TIME_ZONE,
                "max_age_hours": self.max_age_hours,
                "updated_at": dt_util.utcnow().isoformat(),
            }
        )
        self.async_set_updated_data(snapshot)
        async_dispatcher_send(self.hass, SIGNAL_LEDGER_UPDATED, snapshot)

    def _check_revision(self, revision: int) -> None:
        if revision != self.revision:
            raise LedgerError(
                "conflict",
                "Rejestr zmienił się w innym oknie. Odśwież dane i ponów edycję.",
            )

    async def _commit(self, records: list[Settlement]) -> None:
        records = self._validated([row.to_dict() for row in records])
        revision = self.revision + 1
        # Persist first. A failed write must not change the running ledger.
        await self.store.async_save(
            {
                "sources": self.sources,
                "revision": revision,
                "records": [row.to_dict() for row in records],
            }
        )
        self.records = records
        self.revision = revision
        self.publish()

    def _validated(self, raw: list) -> list[Settlement]:
        records = validate_records(raw, dt_util.utcnow())
        previous = None
        for row in records:
            if row.sample.components is None:
                raise LedgerError(
                    "missing_counters",
                    "Wpis nie zawiera odczytów dwóch liczników energii. Nie importuj rejestru ze starego sensora bilansu.",
                )
            if previous is not None:
                check_counter_progression(previous.sample, row.sample)
            previous = row
        return records

    async def async_put(self, raw: dict, revision: int) -> None:
        allowed = {
            "id",
            "day",
            "invoice_balance",
            "correction",
            "note",
            "invoice_shortfall",
        }
        if not isinstance(raw, dict) or set(raw) - allowed or "day" not in raw:
            raise LedgerError("invalid_record", "Nieprawidłowe pola rozliczenia.")
        async with self.lock:
            self._check_revision(revision)
            previous = next(
                (row for row in self.records if row.id == raw.get("id")), None
            )
            if raw.get("id") and previous is None:
                raise LedgerError("not_found", "Rozliczenie już nie istnieje.")
            if any(row.day == raw["day"] and row != previous for row in self.records):
                raise LedgerError(
                    "duplicate_date", "Rozliczenie dla tej daty już istnieje."
                )
            invoice = optional_energy(raw.get("invoice_balance"))
            correction = optional_energy(raw.get("correction"))
            if invoice is not None and correction is not None:
                raise LedgerError(
                    "conflicting_balance",
                    "Podaj saldo z faktury albo korektę, nigdy oba naraz.",
                )
            # Invoice-only edits still work after Recorder has purged old states.
            sample = (
                previous.sample
                if previous and previous.day == raw["day"]
                else await async_read_counters(
                    self.hass,
                    self.sources,
                    raw["day"],
                    self.max_age_hours,
                    dt_util.utcnow(),
                )
            )
            candidate = Settlement(
                previous.id if previous else str(uuid4()),
                raw["day"],
                sample,
                invoice,
                correction,
                raw.get("note", ""),
                optional_energy(raw.get("invoice_shortfall")),
            )
            candidates = [row.to_dict() for row in self.records if row != previous]
            candidates.append(candidate.to_dict())
            await self._commit(validate_records(candidates, dt_util.utcnow()))

    async def async_delete(self, row_id: str, revision: int) -> None:
        async with self.lock:
            self._check_revision(revision)
            records = [row for row in self.records if row.id != row_id]
            if len(records) == len(self.records):
                raise LedgerError("not_found", "Rozliczenie już nie istnieje.")
            await self._commit(records)

    async def async_refresh_sample(self, row_id: str, revision: int) -> None:
        """Explicitly reread a frozen sample. Never refresh it silently."""
        async with self.lock:
            self._check_revision(revision)
            row = next((r for r in self.records if r.id == row_id), None)
            if row is None:
                raise LedgerError("not_found", "Nie znaleziono rozliczenia.")
            sample = await async_read_counters(
                self.hass, self.sources, row.day, self.max_age_hours, dt_util.utcnow()
            )
            await self._commit(
                [
                    replace(r, sample=sample) if r.id == row_id else r
                    for r in self.records
                ]
            )

    def export(self) -> dict:
        return {
            "format_version": STORAGE_VERSION,
            "sources": self.sources,
            "time_zone": TIME_ZONE,
            "unit": "kWh",
            "records": [row.to_dict() for row in self.records],
        }

    async def async_import(self, document: dict, revision: int) -> None:
        async with self.lock:
            self._check_revision(revision)
            if not isinstance(document, dict) or (
                document.get("format_version") != STORAGE_VERSION
                or document.get("sources") != self.sources
                or document.get("time_zone") != TIME_ZONE
                or document.get("unit") != "kWh"
            ):
                raise LedgerError(
                    "invalid_import",
                    "Kopia musi mieć zgodny format, sensor źródłowy, strefę i jednostkę kWh.",
                )
            records = validate_records(document.get("records"), dt_util.utcnow())
            await self._commit(records)
