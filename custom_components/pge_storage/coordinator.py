"""Durable per-entry ledger, with serialized and revision-checked writes."""

import asyncio
import logging
from copy import deepcopy
from dataclasses import replace
from datetime import UTC, datetime, time, timedelta
from uuid import uuid4

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import (
    async_track_point_in_utc_time,
    async_track_state_change_event,
    async_track_state_report_event,
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
from .diagram import DiagramClock
from .energy import (
    ROLES,
    consumer_summary,
    energy_snapshot,
    energy_sources,
    reading,
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
from .history import async_read_counters, sample_from_state
from .hourly import (
    MODEL,
    HourBook,
    accounting_snapshot,
    extend_accounting,
    hour_floor,
    seed_inventory,
    validate_archive,
)
from .hourly_history import read_hours
from .hourly_live import LiveHour
from .ledger import (
    WARSAW,
    LedgerError,
    Settlement,
    boundary,
    combine_counters,
    energy,
    energy_text,
    optional_energy,
    validate_records,
)
from .planning import (
    planning_snapshot,
    validate_checkpoints,
    validate_daily_cache,
    validate_plan,
)
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
        self.diagram_clock = DiagramClock()
        self._report_unsub = None
        self.energy_import_warnings = []
        self.energy_panel_defaults = None
        self.comparison = []
        self._energy_unsub = None
        self.usage_error = None
        self.usage_baseline = None
        self._midnight_cancel = None
        self.hourly_cache = validate_archive(None, self.sources, dt_util.utcnow())
        self.hourly_pending = {}
        self.hourly_current = {}
        self.hourly_live_context = None
        self.hourly_projector = LiveHour(dt_util.utcnow())
        self._live_prefix_key = None
        self._live_prefix = None
        self._day_opening_key = None
        self._day_opening = None
        self._observed_hour = hour_floor(dt_util.utcnow())
        self.hourly_details = {}
        self.hourly_as_of = hour_floor(dt_util.utcnow())
        self.hourly_revision = 0
        self.hourly_error = None
        self.profile_basis = "hourly_net_import"
        self.hourly_accounting = accounting_snapshot(
            HourBook(), [], self.planning, self.hourly_as_of
        )

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
        self.profile_basis = (
            data.get("profile_basis", "legacy_gross_import")
            if data
            else "hourly_net_import"
        )
        self.hourly_cache = validate_archive(
            data.get("hourly_cache") if data else None, self.sources, dt_util.utcnow()
        )
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
        self.entry.async_on_unload(
            lambda: self._report_unsub() if self._report_unsub else None
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
        await self.async_refresh_planning_history()
        await self.async_refresh_energy()
        await self.async_refresh_usage()
        self.publish()

    async def _planning_tick(self, _now):
        await self._energy_statistics_tick(_now)

    def _watch_energy(self):
        if self._report_unsub:
            self._report_unsub()
        pv_ids = source_ids(self.energy_config["sources"].get("pv_power"))
        self.diagram_clock.configure(
            pv_ids,
            self.energy_config.get("flow_clock_source"),
            repr(self.energy_config),
            dt_util.utcnow().timestamp(),
        )
        self._report_unsub = (
            async_track_state_report_event(self.hass, pv_ids, self._pv_reported)
            if pv_ids
            else None
        )
        if self._energy_unsub:
            self._energy_unsub()
        ids = energy_sources(self.energy_config) - set(self.sources.values())
        self._energy_unsub = (
            async_track_state_change_event(self.hass, list(ids), self._source_changed)
            if ids
            else None
        )

    @callback
    def _pv_reported(self, event):
        entity = event.data["entity_id"]
        self.diagram_clock.report(
            entity,
            dt_util.utcnow().timestamp(),
            reading(self.hass, entity, "W") is not None,
        )
        self.publish()

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
        from .hourly_views import comparison

        self.comparison = comparison(
            self.hour_book(),
            self.planning,
            self.records,
            dt_util.utcnow(),
            self.hourly_as_of,
        )
        self.usage_baseline = None
        self.usage_error = None

    def hour_book(self):
        return HourBook(self.hourly_cache["hours"], self.hourly_pending)

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
            "hourly_cache": self.hourly_cache,
            "profile_basis": self.profile_basis,
            "accounting_model": MODEL,
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
                    "hourly_cache": self.hourly_cache,
                    "profile_basis": self.profile_basis,
                    "accounting_model": MODEL,
                }
            )
            self.daily_cache = updated

    async def async_refresh_planning_history(self):
        async with self.lock:
            await self._async_refresh_planning_history()

    async def _async_refresh_planning_history(self):
        now = dt_util.utcnow()
        local = now.astimezone(WARSAW).date().replace(day=1)
        start = datetime.combine(
            local.replace(year=local.year - 1), time(), WARSAW
        ).astimezone(UTC)
        if self.records:
            start = min(start, boundary(self.records[0].day))
        self.hourly_error = None
        try:
            result = await read_hours(self.hass, self.sources, start, now)
            hours = {
                key: row
                for key, row in self.hourly_cache["hours"].items()
                if key not in result["invalid"]
            }
            for key, row in result["finalized"].items():
                old = hours.get(key)
                if (
                    old
                    and old["basis"].startswith("native_")
                    and row["basis"] == "recorder_boundaries"
                ):
                    continue
                hours[key] = row
            updated = validate_archive(
                {"model": MODEL, "sources": self.sources, "hours": hours},
                self.sources,
                now,
            )
            if updated != self.hourly_cache:
                await self.store.async_save(
                    {**self._payload(), "hourly_cache": updated}
                )
                self.hourly_cache = updated
            self.hourly_pending = result["pending"]
            self.hourly_current = result["current"]
            self.hourly_live_context = result["live_context"]
            self._live_prefix_key = None
            self.hourly_details = result["sources"]
            self.hourly_as_of = result["as_of"]
            self.hourly_revision += 1
            self.hourly_accounting = accounting_snapshot(
                self.hour_book(), self.records, self.planning, self.hourly_as_of
            )
            closed = accounting_snapshot(
                HourBook(hours),
                self.records,
                self.planning,
                result["finalized_through"],
            )
            if (
                self.hourly_accounting.get("accounting_error")
                and closed["current"]["estimated_balance"] is not None
                and result["finalized_through"].astimezone(WARSAW).date()
                == self.hourly_as_of.astimezone(WARSAW).date()
            ):
                # Show an explicitly dated settled balance while the current
                # hour is unavailable; never pretend that missing hour is zero.
                error = self.hourly_accounting["accounting_error"]
                self.hourly_accounting = closed
                self.hourly_accounting["pending_error"] = error
            self.planning_history_error = None
        except Exception as err:
            self.hourly_error = str(err)
            self.hourly_accounting = accounting_snapshot(
                HourBook(self.hourly_cache["hours"]),
                self.records,
                self.planning,
                self.hourly_as_of,
            )
            self.hourly_accounting["accounting_error"] = (
                "Nie udało się odświeżyć lub utrwalić danych godzinowych. " + str(err)
            )
            for key in (
                "estimated_balance",
                "available_energy",
                "deficit",
                "period_balance",
                "import_since_settlement_kwh",
                "export_since_settlement_kwh",
                "credited_since_settlement_kwh",
            ):
                self.hourly_accounting["current"][key] = None
            _LOGGER.exception("Cannot refresh PGE hourly archive")

    def live_sample(self):
        return combine_counters(
            *[
                sample_from_state(self.hass.states.get(self.sources[name]))
                for name in ("import", "export")
            ]
        )

    async def async_daily(self, month):
        from .hourly_views import daily

        await self.async_refresh_planning_history()
        return daily(self, month)

    async def async_profile(self):
        from .hourly_views import seasonal

        await self.async_refresh_planning_history()
        return seasonal(self.hour_book(), dt_util.utcnow())

    @callback
    def _source_changed(self, _event) -> None:
        self.hourly_projector.observe(_event, self.sources, dt_util.utcnow())
        entity = _event.data.get("entity_id")
        if entity in source_ids(self.energy_config["sources"].get("pv_power")):
            self.diagram_clock.report(
                entity,
                dt_util.utcnow().timestamp(),
                reading(self.hass, entity, "W") is not None,
            )
        self.publish()

    def _update_live_hour(self):
        now = dt_util.utcnow()
        current_start = hour_floor(now)
        if current_start != self._observed_hour:
            self._observed_hour = current_start
            if (
                self.hourly_as_of.astimezone(WARSAW).date()
                != now.astimezone(WARSAW).date()
            ):
                self.hourly_accounting = accounting_snapshot(
                    self.hour_book(), self.records, self.planning, current_start
                )
            self.hourly_current = {
                "start": current_start.isoformat(),
                "end": (current_start + timedelta(hours=1)).isoformat(),
                "known": False,
                "provisional": True,
                "as_of": None,
                "balance_kwh": None,
                "net_kwh": None,
            }
            self.hass.async_create_task(self._energy_statistics_tick(now))
        row = self.hourly_projector.project(
            self.hourly_live_context, self.hass, self.sources, now
        )
        if row is None:
            invalid = False
            for entity in self.sources.values():
                try:
                    sample_from_state(self.hass.states.get(entity))
                except LedgerError:
                    invalid = True
            if self.hourly_live_context:
                invalid |= any(
                    self.hourly_projector.invalid_after.get(
                        entity, self.hourly_projector.started
                    )
                    > datetime.fromisoformat(
                        self.hourly_live_context["positions"][direction]["end"]
                    )
                    for direction, entity in self.sources.items()
                )
            if invalid:
                self.hourly_current = {
                    **self.hourly_current,
                    "known": False,
                    "balance_kwh": None,
                    "net_kwh": None,
                    "quality": "waiting_for_native_sum",
                }
            return
        key = (current_start.isoformat(), self.hourly_revision, self.revision)
        if self._live_prefix_key != key:
            self._live_prefix_key = key
            self._live_prefix = accounting_snapshot(
                self.hour_book(), self.records, self.planning, current_start
            )
        self.hourly_pending[row["start"]] = row
        self.hourly_as_of = datetime.fromisoformat(row["end"])
        self.hourly_current = {
            **row,
            "end": (current_start + timedelta(hours=1)).isoformat(),
            "as_of": row["end"],
            "known": True,
            "provisional": True,
            "quality": "live_native_projection",
        }
        self.hourly_accounting = extend_accounting(self._live_prefix, row)

    @callback
    def publish(self) -> None:
        self._update_live_hour()
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
            current = sample.value
        except LedgerError as err:
            source_error = str(err)
        snapshot = deepcopy(self.hourly_accounting)
        inventory_state = snapshot.pop("inventory_state", None)
        snapshot["hourly"] = {
            "model": MODEL,
            "current": self.hourly_current,
            "sources": self.hourly_details,
            "closed_hours": len(self.hourly_cache["hours"]),
            "finalization_delay_minutes": 0,
            "boundary_tolerance_seconds": 0,
            "source_contract": "configured cumulative totals across all phases; device behaviour is not autodetected",
        }
        snapshot["hourly_revision"] = self.hourly_revision
        effective = {
            **self.planning,
            "profile": self.planning["profile"]
            if self.profile_basis == "hourly_net_import"
            else [],
        }
        if self.comparison:
            profiles = {row["month"]: row for row in effective["profile"]}
            for row in self.comparison:
                if row["previous_kwh"] is not None:
                    profiles[int(row["month"][5:])] = {
                        "month": int(row["month"][5:]),
                        "import_kwh": row["previous_kwh"],
                        "export_kwh": "0",
                        "source_month": row["previous_month"],
                    }
            effective = {
                **effective,
                "profile": sorted(profiles.values(), key=lambda row: row["month"]),
            }
        snapshot["planning"] = planning_snapshot(
            effective,
            self.records,
            self.checkpoints,
            sample.components if sample and current is not None else None,
            snapshot["current"]["estimated_balance"],
            dt_util.utcnow(),
            snapshot.get("accounting_error"),
            hourly=True,
            inventory_state=inventory_state,
        )
        snapshot["planning"]["config"] = self.planning
        snapshot["comparison"] = [dict(row) for row in self.comparison]
        snapshot["energy"] = energy_snapshot(
            self.hass,
            self.energy_config,
            self.sources,
            self.energy_cache,
            self.energy_statistics,
            self.energy_panel_defaults,
        )
        from .hourly import replay

        beginning = datetime.combine(
            dt_util.utcnow().astimezone(WARSAW).date(), time(), WARSAW
        ).astimezone(UTC)
        if beginning <= self.hourly_as_of:
            flows = self.hour_book().interval(beginning, self.hourly_as_of)
            key = (beginning.isoformat(), self.hourly_revision, self.revision)
            if self._day_opening_key != key:
                self._day_opening_key = key
                try:
                    self._day_opening = replay(
                        self.hour_book(), self.records, self.planning, beginning
                    )
                except LedgerError:
                    self._day_opening = None
            withdrawn = None
            if (
                self._day_opening
                and snapshot["current"].get("import_since_settlement_kwh") is not None
            ):
                withdrawn = energy_text(
                    energy(snapshot["current"]["import_since_settlement_kwh"])
                    - energy(self._day_opening["withdrawn_kwh"])
                )
            snapshot["energy"]["today"].update(
                credited_energy=flows["credited_kwh"],
                pge_credited_energy=flows["credited_kwh"],
                pge_withdrawn_energy=withdrawn,
            )
        else:
            snapshot["energy"]["today"].update(
                credited_energy=None,
                pge_credited_energy=None,
                pge_withdrawn_energy=None,
            )
        snapshot["energy"]["hourly_current"] = self.hourly_current
        energy_view = snapshot["energy"]
        pv_sources = source_ids(self.energy_config["sources"].get("pv_power"))
        now_seconds = dt_util.utcnow().timestamp()
        stale = [
            entity
            for entity in pv_sources
            if now_seconds
            - self.diagram_clock.last.get(
                entity, self.diagram_clock.started or now_seconds
            )
            > 25
        ]
        if stale:
            values = energy_view["values"]
            values["pv_power"] = energy_text(
                sum(
                    (
                        energy(reading(self.hass, entity, "W") or "0")
                        for entity in pv_sources
                        if entity not in stale
                    ),
                    energy(0),
                )
            )
            if (
                energy_view["calculation"].get("home_power", {}).get("basis")
                == "balance"
            ):
                values["home_power"] = energy_text(
                    max(
                        energy(0),
                        energy(values["pv_power"])
                        + energy(values.get("grid_import_power") or "0")
                        + energy(values.get("battery_discharge_power") or "0")
                        - energy(values.get("grid_export_power") or "0")
                        - energy(values.get("battery_charge_power") or "0"),
                    )
                )
            for array in energy_view["pv_arrays"]:
                if array.get("power_entity") in stale:
                    array["power_w"] = "0"
            energy_view["consumer_totals"] = consumer_summary(
                energy_view["consumers"],
                values.get("home_power"),
                energy_view["today"].get("home_energy"),
            )
            energy_view["stale_power_sources"] = stale
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
        available = snapshot["planning"].get("inventory")
        available = (
            available["balance_kwh"]
            if available
            else snapshot["current"].get("available_energy")
        )
        energy_view["diagram_frame"] = self.diagram_clock.capture(
            energy_view, available, dt_util.utcnow().timestamp()
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
        hourly_cache=None,
        profile_basis=None,
    ) -> None:
        records = self._validated([row.to_dict() for row in records])
        changed_plan = planning is not None
        planning = self.planning if planning is None else validate_plan(planning)
        profile_basis = profile_basis or (
            "hourly_net_import" if changed_plan else self.profile_basis
        )
        if profile_basis not in ("hourly_net_import", "legacy_gross_import"):
            raise LedgerError("invalid_import", "Nieprawidłowy model profilu zużycia.")
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
        hourly_cache = (
            self.hourly_cache
            if hourly_cache is None
            else validate_archive(hourly_cache, self.sources, dt_util.utcnow())
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
                "hourly_cache": hourly_cache,
                "profile_basis": profile_basis,
                "accounting_model": MODEL,
            }
        )
        self.records = records
        self.revision = revision
        self.planning = planning
        self.checkpoint_cache = cache
        self.daily_cache = daily_cache
        self.energy_config = energy_config
        self.energy_cache = energy_cache
        self.hourly_cache = hourly_cache
        self.profile_basis = profile_basis
        self.diagram_clock.frame = None
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
                seed_inventory(plan, self.records)
            elif plan["lots"]:
                raise LedgerError(
                    "invalid_anchor",
                    "Wybierz fakturę dla wprowadzonych partii energii.",
                )
            await self._commit(self.records, plan)

    def _validated(self, raw: list) -> list[Settlement]:
        records = validate_records(raw, dt_util.utcnow())
        for row in records:
            if row.sample.components is None:
                raise LedgerError(
                    "missing_counters",
                    "Wpis nie zawiera oddzielnych liczników importu i eksportu.",
                )
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
            "format_version": 5,
            "sources": self.sources,
            "time_zone": TIME_ZONE,
            "unit": "kWh",
            "records": [row.to_dict() for row in self.records],
            "planning": self.planning,
            "checkpoint_cache": self.checkpoint_cache,
            "daily_cache": self.daily_cache,
            "energy_config": self.energy_config,
            "energy_cache": self.energy_cache,
            "hourly_cache": self.hourly_cache,
            "profile_basis": self.profile_basis,
            "accounting_model": MODEL,
        }

    async def async_import(self, document: dict, revision: int) -> None:
        async with self.lock:
            self._check_revision(revision)
            if not isinstance(document, dict) or (
                document.get("format_version") not in (2, 3, 4, 5)
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
                validate_archive(
                    document.get("hourly_cache"), self.sources, dt_util.utcnow()
                ),
                document.get("profile_basis", "legacy_gross_import"),
            )
            self._watch_energy()
