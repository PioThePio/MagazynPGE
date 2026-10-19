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
    async_track_point_in_utc_time,
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
    VERSION,
)
from .energy import (
    ROLES,
    energy_snapshot,
    energy_sources,
    refresh_energy_cache,
    source_ids,
    valid_source,
    validate_energy_cache,
    validate_energy_config,
)
from .energy_panel import (
    async_panel_config,
    async_statistics_today,
    merge_panel_config,
    upgrade_consumer_parents,
)
from .history import async_read_counters, async_read_samples, sample_from_state
from .ledger import (
    WARSAW,
    LedgerError,
    Sample,
    Settlement,
    boundary,
    calculate,
    check_counter_progression,
    combine_counters,
    energy,
    energy_text,
    optional_energy,
    validate_records,
)
from .overview import async_usage, usage_target
from .planning import (
    inventory_now,
    planning_snapshot,
    validate_checkpoints,
    validate_daily_cache,
    validate_plan,
)
from .planning_history import async_checkpoints, async_daily
from .power import PowerWindows

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
        self.energy_config = validate_energy_config({})
        self.energy_cache = {}
        self.energy_statistics = {}
        self.power_windows = PowerWindows()
        self.energy_import_warnings = []
        self.energy_panel_defaults = None
        self.comparison = []
        self._energy_unsub = None
        self.usage_error = None
        self.usage_baseline = None
        self._midnight_cancel = None

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
        if data is not None:
            self.energy_config = validate_energy_config(data.get("energy_config", {}))
            self.energy_cache = validate_energy_cache(data.get("energy_cache", {}))
        await self._auto_energy_defaults()
        await self.async_refresh_planning_history()
        await self.async_refresh_energy()
        await self.async_refresh_usage()
        self._watch_energy()
        self.entry.async_on_unload(
            lambda: self._energy_unsub() if self._energy_unsub else None
        )
        self.publish()
        self.entry.async_on_unload(
            async_track_time_interval(self.hass, self._power_tick, timedelta(seconds=1))
        )
        self._schedule_midnight()
        self.entry.async_on_unload(
            lambda: self._midnight_cancel() if self._midnight_cancel else None
        )
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
        self.entry.async_on_unload(
            async_track_time_interval(
                self.hass, self._energy_statistics_tick, timedelta(minutes=5)
            )
        )

    async def _auto_energy_defaults(self):
        try:
            result = await async_panel_config(self.hass)
        except LedgerError:
            return
        self.energy_panel_defaults = result
        self.energy_import_warnings = result["warnings"]
        if self.energy_config.get("imported_from_energy"):
            config = validate_energy_config(
                upgrade_consumer_parents(self.energy_config, result["config"])
            )
            if config == self.energy_config:
                return
        else:
            config = validate_energy_config(
                merge_panel_config(self.energy_config, result["config"])
            )
        async with self.lock:
            await self.store.async_save(
                {
                    **self._payload(),
                    "energy_config": config,
                    "revision": self.revision + 1,
                }
            )
            self.energy_config = config
            self.revision += 1

    def _schedule_midnight(self):
        when = boundary(
            dt_util.utcnow().astimezone(WARSAW).date().isoformat()
        ) + timedelta(seconds=2)

        @callback
        def refresh(now):
            self.hass.async_create_task(self._planning_tick(now))
            self._schedule_midnight()

        self._midnight_cancel = async_track_point_in_utc_time(self.hass, refresh, when)

    @callback
    def _power_tick(self, _now):
        if self.energy_config["sources"] or self.energy_config["consumers"]:
            self.publish()

    async def _energy_statistics_tick(self, _now):
        if self.energy_config.get("statistics") or any(
            item.get("statistic") for item in self.energy_config["consumers"]
        ):
            await self.async_refresh_energy()
            self.publish()

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
        await self.async_refresh_energy()
        await self.async_refresh_usage()
        self.publish()

    def _watch_energy(self):
        if self._energy_unsub:
            self._energy_unsub()
        ids = energy_sources(self.energy_config) - set(self.sources.values())
        self._energy_unsub = (
            async_track_state_change_event(self.hass, list(ids), self._source_changed)
            if ids
            else None
        )

    async def async_refresh_energy(self):
        try:
            try:
                self.energy_panel_defaults = await async_panel_config(self.hass)
                self.energy_import_warnings = self.energy_panel_defaults["warnings"]
            except LedgerError:
                self.energy_panel_defaults = None
                self.energy_import_warnings = []
            async with self.lock:
                updated = await refresh_energy_cache(
                    self.hass,
                    self.energy_config,
                    self.sources,
                    self.energy_cache,
                    self.max_age_hours,
                )
                if updated != self.energy_cache:
                    await self.store.async_save(
                        {**self._payload(), "energy_cache": updated}
                    )
                    self.energy_cache = updated
            self.energy_statistics = await async_statistics_today(
                self.hass, self.energy_config
            )
        except Exception:
            self.energy_statistics = {}
            _LOGGER.exception("Cannot refresh optional PGE energy boundaries")

    async def async_refresh_usage(self):
        try:
            now = dt_util.utcnow()
            self.comparison = await async_usage(
                self.hass,
                self.sources["import"],
                usage_target(self.planning, self.records, now),
                now,
            )
            self.usage_error = None
            month_start = now.astimezone(WARSAW).date().replace(day=1)
            day = (month_start - timedelta(days=1)).isoformat()
            frozen = self.daily_cache.get(day) or self.checkpoint_cache["samples"].get(
                day
            )
            frozen = next(
                (asdict(row.sample) for row in self.records if row.day == day), frozen
            )
            self.usage_baseline = None
            if frozen:
                sample = Sample(**frozen)
                self.usage_baseline = (
                    month_start.strftime("%Y-%m"),
                    sample.components["import"]["value"],
                )
            else:
                try:
                    samples = await async_read_samples(
                        self.hass,
                        {"import": self.sources["import"]},
                        day,
                        self.max_age_hours,
                        now,
                    )
                    self.usage_baseline = (
                        month_start.strftime("%Y-%m"),
                        samples["import"].value,
                    )
                except LedgerError:
                    pass
        except Exception:
            self.comparison = []
            self.usage_error = "Brak historii poboru."
            _LOGGER.exception("Cannot read PGE annual consumption")

    def _payload(self):
        return {
            "sources": self.sources,
            "revision": self.revision,
            "records": [row.to_dict() for row in self.records],
            "planning": self.planning,
            "checkpoint_cache": self.checkpoint_cache,
            "daily_cache": self.daily_cache,
            "energy_config": self.energy_config,
            "energy_cache": self.energy_cache,
        }

    async def async_put_energy(self, raw, revision):
        try:
            native = await async_panel_config(self.hass)
        except LedgerError:
            native = None
        async with self.lock:
            self._check_revision(revision)
            config = validate_energy_config(raw)
            from homeassistant.helpers import entity_registry as er

            registry = er.async_get(self.hass)

            def imported_missing(role, entity_id):
                """Allow a native historical reference, never arbitrary invalid input."""
                state = self.hass.states.get(entity_id)
                if state is not None and state.state not in ("unknown", "unavailable"):
                    return False
                if not config.get("imported_from_energy"):
                    return False
                for accepted in (
                    native["config"] if native else None,
                    self.energy_config
                    if self.energy_config.get("imported_from_energy")
                    else None,
                ):
                    if accepted and entity_id in source_ids(
                        accepted["sources"].get(role)
                    ):
                        return True
                return False

            for entity_id in energy_sources(config):
                registered = registry.async_get(entity_id)
                if registered and registered.platform == DOMAIN:
                    raise LedgerError(
                        "invalid_energy",
                        "Wybierz źródłowy sensor, nie encję obliczoną przez Magazyn PGE.",
                    )
            for role, selected in config["sources"].items():
                for entity_id in source_ids(selected):
                    if not valid_source(
                        self.hass,
                        entity_id,
                        ROLES[role][1],
                        role in ("grid_power", "battery_power"),
                    ) and not imported_missing(role, entity_id):
                        raise LedgerError(
                            "invalid_energy",
                            f"Sprawdź wartość i jednostkę: {ROLES[role][0]} ({entity_id}). Dla mocy ze znakiem wybierz wariant +/−, a dla osobnych kierunków wartości nieujemne.",
                        )
            for consumer in config["consumers"]:
                for key, unit in (("power", "W"), ("energy", "kWh")):
                    if consumer.get(key) and not valid_source(
                        self.hass, consumer[key], unit
                    ):
                        accepted = [
                            item
                            for candidate in (
                                native["config"] if native else None,
                                self.energy_config
                                if self.energy_config.get("imported_from_energy")
                                else None,
                            )
                            if candidate
                            for item in candidate["consumers"]
                        ]
                        state = self.hass.states.get(consumer[key])
                        if (
                            config.get("imported_from_energy")
                            and (
                                state is None
                                or state.state in ("unknown", "unavailable")
                            )
                            and any(item.get(key) == consumer[key] for item in accepted)
                        ):
                            continue
                        raise LedgerError(
                            "invalid_energy",
                            f"Sprawdź źródło odbiorcy: {consumer['name']}.",
                        )
            await self._commit(self.records, energy_config=config)
            self._watch_energy()
        await self.async_refresh_energy()
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
                    "energy_config": self.energy_config,
                    "energy_cache": self.energy_cache,
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
                        "energy_config": self.energy_config,
                        "energy_cache": self.energy_cache,
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
        effective = self.planning
        if self.comparison:
            effective = {
                **self.planning,
                "profile": [
                    {
                        "month": int(row["month"][5:]),
                        "import_kwh": row["previous_kwh"],
                        "export_kwh": "0",
                        "source_month": row["previous_month"],
                    }
                    for row in self.comparison
                    if row["previous_kwh"] is not None
                ],
            }
        snapshot["planning"] = planning_snapshot(
            effective,
            self.records,
            self.checkpoints,
            sample.components if sample and current is not None else None,
            snapshot["current"]["estimated_balance"],
            dt_util.utcnow(),
            self.planning_history_error,
        )
        snapshot["planning"]["config"] = self.planning
        snapshot["comparison"] = [dict(row) for row in self.comparison]
        if self.usage_baseline and source_values.get("import") is not None:
            key, baseline = self.usage_baseline
            delta = energy(source_values["import"]) - energy(baseline)
            for row in snapshot["comparison"]:
                if row["month"] == key:
                    row["current_kwh"] = energy_text(delta) if delta >= 0 else None
        snapshot["energy"] = energy_snapshot(
            self.hass,
            self.energy_config,
            self.sources,
            self.energy_cache,
            self.energy_statistics,
            self.energy_panel_defaults,
        )
        energy_view = snapshot["energy"]
        energy_view["power_windows"] = self.power_windows.update(
            energy_view, dt_util.utcnow().timestamp(), repr(self.energy_config)
        )
        stable = energy_view["power_windows"]["15"]
        energy_view["home_power_live"] = energy_view["values"].get("home_power")
        if stable["covered_seconds"] >= 15:
            energy_view["values"]["home_power"] = str(stable["home_power_w"])
        snapshot["energy"]["import_warnings"] = self.energy_import_warnings
        snapshot["energy"]["import_report"] = (
            self.energy_panel_defaults["report"] if self.energy_panel_defaults else []
        )
        from homeassistant.helpers import entity_registry as er

        registry = er.async_get(self.hass)
        from .sensor import SENSOR_DEFINITIONS

        snapshot["entities"] = {
            key: registry.async_get_entity_id(
                "sensor", DOMAIN, f"{self.entry.entry_id}_{key}"
            )
            for key in SENSOR_DEFINITIONS
        }
        snapshot.update(
            {
                "entry_id": self.entry.entry_id,
                "loaded": True,
                "version": VERSION,
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
        energy_config=None,
        energy_cache=None,
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
        energy_config = (
            self.energy_config
            if energy_config is None
            else validate_energy_config(energy_config)
        )
        energy_cache = (
            self.energy_cache
            if energy_cache is None
            else validate_energy_cache(energy_cache)
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
                "energy_config": energy_config,
                "energy_cache": energy_cache,
            }
        )
        self.records = records
        self.revision = revision
        self.planning = planning
        self.checkpoint_cache = cache
        self.daily_cache = daily_cache
        self.energy_config = energy_config
        self.energy_cache = energy_cache
        await self._async_refresh_planning_history()
        await self.async_refresh_usage()
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
            "energy_config": self.energy_config,
            "energy_cache": self.energy_cache,
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
                validate_energy_config(document.get("energy_config", {})),
                validate_energy_cache(document.get("energy_cache", {})),
            )
            self._watch_energy()
