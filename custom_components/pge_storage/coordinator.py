"""Durable per-entry ledger, with serialized and revision-checked writes."""

import asyncio
import logging
from dataclasses import asdict, replace
from datetime import date, timedelta
from uuid import uuid4

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import (
    async_track_state_change_event,
    async_track_time_interval,
)
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
    WARSAW,
    LedgerError,
    Sample,
    Settlement,
    calculate,
    check_counter_progression,
    combine_counters,
    energy,
    energy_text,
    optional_energy,
    validate_records,
)
from .planning import (
    inventory_now,
    planning_snapshot,
    validate_checkpoints,
    validate_daily_cache,
    validate_plan,
)
from .planning_history import async_checkpoints, async_daily

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
        self.planning = validate_plan({})
        self.checkpoints = []
        self.planning_history_error = None
        self.checkpoint_cache = {"anchor_id": None, "samples": {}}
        self.daily_cache = {}

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
            self.planning = validate_plan(data.get("planning", {}))
            self.checkpoint_cache = validate_checkpoints(
                data.get("checkpoint_cache"), self.records
            )
            self.daily_cache = validate_daily_cache(
                data.get("daily_cache", {}), dt_util.utcnow()
            )
        await self.async_refresh_planning_history()
        self.publish()
        self.entry.async_on_unload(
            async_track_state_change_event(
                self.hass, list(self.sources.values()), self._source_changed
            )
        )
        self.entry.async_on_unload(
            async_track_time_interval(
                self.hass, self._planning_tick, timedelta(hours=1)
            )
        )

    async def _planning_tick(self, _now):
        day = (
            dt_util.utcnow().astimezone(WARSAW).date() - timedelta(days=1)
        ).isoformat()
        if day not in self.daily_cache:
            try:
                sample = await async_read_counters(
                    self.hass, self.sources, day, self.max_age_hours, dt_util.utcnow()
                )
                await self._archive_daily({day: asdict(sample)})
            except LedgerError:
                pass  # No invented zero; a later read can fill a genuine sample.
            except Exception:
                _LOGGER.exception("Cannot archive PGE daily reading")
        await self.async_refresh_planning_history()
        self.publish()

    async def _archive_daily(self, samples):
        async with self.lock:
            updated = {**self.daily_cache, **samples}
            if updated == self.daily_cache:
                return
            validate_daily_cache(updated, dt_util.utcnow())
            await self.store.async_save(
                {
                    "sources": self.sources,
                    "revision": self.revision,
                    "records": [row.to_dict() for row in self.records],
                    "planning": self.planning,
                    "checkpoint_cache": self.checkpoint_cache,
                    "daily_cache": updated,
                }
            )
            self.daily_cache = updated

    async def async_refresh_planning_history(self):
        async with self.lock:
            await self._async_refresh_planning_history()

    async def _async_refresh_planning_history(self):
        self.checkpoints = []
        self.planning_history_error = None
        if not self.records or self.planning["anchor_id"] != self.records[-1].id:
            return
        try:
            anchor = self.records[-1]
            known = (
                self.checkpoint_cache["samples"]
                if self.checkpoint_cache["anchor_id"] == anchor.id
                else {}
            )
            samples = await async_checkpoints(
                self.hass,
                self.sources,
                anchor,
                self.max_age_hours,
                {
                    day: Sample(**value)
                    for day, value in {**self.daily_cache, **known}.items()
                },
            )
            cache = {
                "anchor_id": anchor.id,
                "samples": {day.isoformat(): asdict(value) for day, value in samples},
            }
            validate_checkpoints(cache, self.records)
            if cache != self.checkpoint_cache:
                await self.store.async_save(
                    {
                        "sources": self.sources,
                        "revision": self.revision,
                        "records": [row.to_dict() for row in self.records],
                        "planning": self.planning,
                        "checkpoint_cache": cache,
                        "daily_cache": self.daily_cache,
                    }
                )
                self.checkpoint_cache = cache
            self.checkpoints = [(day, sample.components) for day, sample in samples]
        except LedgerError as err:
            self.planning_history_error = str(err)
        except Exception:
            _LOGGER.exception("Cannot refresh durable PGE month boundaries")
            self.planning_history_error = "Nie udało się odczytać lub utrwalić końców miesięcy. Sprawdź log HA. Rejestr faktur pozostaje zapisany."

    def live_sample(self):
        return combine_counters(
            *[
                sample_from_state(self.hass.states.get(self.sources[name]))
                for name in ("import", "export")
            ]
        )

    async def async_daily(self, month):
        try:
            live = self.live_sample()
        except LedgerError:
            live = None
        result = await async_daily(
            self.hass,
            self.sources,
            list(self.records),
            live,
            month,
            self.max_age_hours,
            self.planning,
            self.checkpoints,
            self.checkpoint_cache["samples"],
            self.daily_cache,
        )
        archived = result.pop("archived_samples")
        try:
            await self._archive_daily(archived)
        except Exception:
            _LOGGER.exception("Cannot persist queried PGE daily readings")
            result["basis"] += (
                " UWAGA: nie udało się utrwalić odczytów dziennych; sprawdź log HA i pobierz kopię."
            )
        result["updated_at"] = dt_util.utcnow().isoformat()
        return result

    @callback
    def _source_changed(self, _event) -> None:
        self.publish()

    @callback
    def publish(self) -> None:
        current = None
        sample = None
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
        if self.records and current is not None:
            previous = self.records[-1].sample.components
            imported = energy(sample.components["import"]["value"]) - energy(
                previous["import"]["value"]
            )
            exported = energy(sample.components["export"]["value"]) - energy(
                previous["export"]["value"]
            )
            snapshot["current"].update(
                {
                    "import_since_settlement_kwh": energy_text(imported),
                    "export_since_settlement_kwh": energy_text(exported),
                    "credited_since_settlement_kwh": energy_text(
                        exported * energy("0.8")
                    ),
                }
            )
        snapshot["planning"] = planning_snapshot(
            self.planning,
            self.records,
            self.checkpoints,
            sample.components if sample and current is not None else None,
            snapshot["current"]["estimated_balance"],
            dt_util.utcnow(),
            self.planning_history_error,
        )
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

    async def _commit(
        self,
        records: list[Settlement],
        planning=None,
        checkpoint_cache=None,
        daily_cache=None,
    ) -> None:
        records = self._validated([row.to_dict() for row in records])
        planning = self.planning if planning is None else validate_plan(planning)
        cache = validate_checkpoints(
            self.checkpoint_cache if checkpoint_cache is None else checkpoint_cache,
            records,
        )
        daily_cache = (
            self.daily_cache
            if daily_cache is None
            else validate_daily_cache(daily_cache, dt_util.utcnow())
        )
        revision = self.revision + 1
        # Persist first. A failed write must not change the running ledger.
        await self.store.async_save(
            {
                "sources": self.sources,
                "revision": revision,
                "records": [row.to_dict() for row in records],
                "planning": planning,
                "checkpoint_cache": cache,
                "daily_cache": daily_cache,
            }
        )
        self.records = records
        self.revision = revision
        self.planning = planning
        self.checkpoint_cache = cache
        self.daily_cache = daily_cache
        await self._async_refresh_planning_history()
        self.publish()

    async def async_put_plan(self, raw, revision):
        async with self.lock:
            self._check_revision(revision)
            plan = validate_plan(raw)
            if plan["anchor_id"] is not None:
                if not self.records or self.records[-1].id != plan["anchor_id"]:
                    raise LedgerError(
                        "invalid_anchor",
                        "Wybierz ostatni wpis rozliczenia jako podstawę partii.",
                    )
                anchor = self.records[-1]
                inventory_now(
                    plan,
                    self.records,
                    [],
                    anchor.sample.components,
                    date.fromisoformat(anchor.day),
                )
            elif plan["lots"]:
                raise LedgerError(
                    "invalid_anchor",
                    "Wybierz fakturę dla wprowadzonych partii energii.",
                )
            await self._commit(self.records, plan)

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
            "format_version": 3,
            "sources": self.sources,
            "time_zone": TIME_ZONE,
            "unit": "kWh",
            "records": [row.to_dict() for row in self.records],
            "planning": self.planning,
            "checkpoint_cache": self.checkpoint_cache,
            "daily_cache": self.daily_cache,
        }

    async def async_import(self, document: dict, revision: int) -> None:
        async with self.lock:
            self._check_revision(revision)
            if not isinstance(document, dict) or (
                document.get("format_version") not in (2, 3)
                or document.get("sources") != self.sources
                or document.get("time_zone") != TIME_ZONE
                or document.get("unit") != "kWh"
            ):
                raise LedgerError(
                    "invalid_import",
                    "Kopia musi mieć zgodny format, sensor źródłowy, strefę i jednostkę kWh.",
                )
            records = validate_records(document.get("records"), dt_util.utcnow())
            await self._commit(
                records,
                document.get("planning", {}),
                validate_checkpoints(document.get("checkpoint_cache"), records),
                validate_daily_cache(document.get("daily_cache", {}), dt_util.utcnow()),
            )
