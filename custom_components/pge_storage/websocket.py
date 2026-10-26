"""Authenticated HA websocket API for the Lovelace card."""

import logging

import probatio as vol
from homeassistant.auth.permissions.const import POLICY_READ
from homeassistant.components import recorder, websocket_api
from homeassistant.core import callback
from homeassistant.exceptions import Unauthorized
from homeassistant.helpers.dispatcher import async_dispatcher_connect

from .const import DOMAIN, SIGNAL_LEDGER_UPDATED
from .dashboard import async_create_dashboard
from .energy import energy_sources, validate_energy_config
from .energy_panel import async_panel_config
from .history import async_read_counters, async_statistics_metadata
from .hourly_views import months as async_months
from .ledger import LedgerError
from .period import PERIODS, async_energy_period

_LOGGER = logging.getLogger(__name__)
ENTRY = {vol.Optional("entry_id"): str}
WRITE = {**ENTRY, vol.Required("revision"): vol.All(vol.Coerce(int), vol.Range(min=0))}


def _get(hass, connection, msg):
    entries = hass.data.get(DOMAIN, {})
    if msg.get("entry_id"):
        coordinator = entries.get(msg["entry_id"])
    elif len(entries) == 1:
        coordinator = next(iter(entries.values()))
    else:
        coordinator = None
    if coordinator is None:
        raise LedgerError(
            "select_entry",
            "Dodaj integrację Magazyn PGE. Przy wielu magazynach podaj entry_id w konfiguracji karty.",
        )
    if connection.user is None or not all(
        connection.user.permissions.check_entity(entity_id, POLICY_READ)
        for entity_id in set(coordinator.sources.values())
        | energy_sources(coordinator.energy_config)
    ):
        raise Unauthorized
    return coordinator


@callback
def async_register(hass):
    for command in (
        subscribe,
        put,
        delete,
        refresh_sample,
        export,
        import_records,
        diagnose,
        daily,
        profile,
        put_plan,
        refresh_plan,
        months,
        put_energy,
        energy_defaults,
        create_dashboard,
        energy_period,
    ):
        websocket_api.async_register_command(hass, command)


@websocket_api.websocket_command(
    {vol.Required("type"): "pge_storage/subscribe", **ENTRY}
)
@callback
def subscribe(hass, connection, msg):
    try:
        coordinator = _get(hass, connection, msg)
    except LedgerError as err:
        connection.send_error(msg["id"], err.code, str(err))
        return

    @callback
    def emit(snapshot):
        # Recheck permissions on each emission, including after role changes.
        if all(
            connection.user.permissions.check_entity(entity_id, POLICY_READ)
            for entity_id in set(coordinator.sources.values())
            | energy_sources(coordinator.energy_config)
        ):
            connection.send_message(websocket_api.event_message(msg["id"], snapshot))

    @callback
    def updated(snapshot):
        if snapshot["entry_id"] == coordinator.entry.entry_id:
            emit(snapshot)

    # Dispatcher survives reloads and does not copy the ledger into Recorder.
    connection.subscriptions[msg["id"]] = async_dispatcher_connect(
        hass, SIGNAL_LEDGER_UPDATED, updated
    )
    connection.send_result(msg["id"])
    emit(coordinator.data)


async def _write(connection, msg, operation):
    try:
        await operation
    except LedgerError as err:
        connection.send_error(msg["id"], err.code, str(err))
    except Exception:
        _LOGGER.exception("PGE ledger write failed")
        connection.send_error(
            msg["id"],
            "write_failed",
            "Nie udało się zapisać rejestru. Sprawdź log Home Assistant; zapis nie został potwierdzony.",
        )
    else:
        connection.send_result(msg["id"])


@websocket_api.require_admin
@websocket_api.websocket_command(
    {vol.Required("type"): "pge_storage/put", **WRITE, vol.Required("record"): dict}
)
@websocket_api.async_response
async def put(hass, connection, msg):
    coordinator = _get(hass, connection, msg)
    await _write(connection, msg, coordinator.async_put(msg["record"], msg["revision"]))


@websocket_api.require_admin
@websocket_api.websocket_command(
    {
        vol.Required("type"): "pge_storage/delete",
        **WRITE,
        vol.Required("record_id"): str,
    }
)
@websocket_api.async_response
async def delete(hass, connection, msg):
    coordinator = _get(hass, connection, msg)
    await _write(
        connection, msg, coordinator.async_delete(msg["record_id"], msg["revision"])
    )


@websocket_api.require_admin
@websocket_api.websocket_command(
    {
        vol.Required("type"): "pge_storage/refresh_sample",
        **WRITE,
        vol.Required("record_id"): str,
    }
)
@websocket_api.async_response
async def refresh_sample(hass, connection, msg):
    coordinator = _get(hass, connection, msg)
    await _write(
        connection,
        msg,
        coordinator.async_refresh_sample(msg["record_id"], msg["revision"]),
    )


@websocket_api.require_admin
@websocket_api.websocket_command({vol.Required("type"): "pge_storage/export", **ENTRY})
@callback
def export(hass, connection, msg):
    coordinator = _get(hass, connection, msg)
    connection.send_result(msg["id"], coordinator.export())


@websocket_api.require_admin
@websocket_api.websocket_command(
    {
        vol.Required("type"): "pge_storage/import",
        **WRITE,
        vol.Required("document"): dict,
    }
)
@websocket_api.async_response
async def import_records(hass, connection, msg):
    coordinator = _get(hass, connection, msg)
    await _write(
        connection, msg, coordinator.async_import(msg["document"], msg["revision"])
    )


@websocket_api.websocket_command(
    {vol.Required("type"): "pge_storage/diagnose", **ENTRY, vol.Required("day"): str}
)
@websocket_api.async_response
async def diagnose(hass, connection, msg):
    coordinator = _get(hass, connection, msg)
    result = {
        "sources": coordinator.sources,
        "recorder_filter_includes_sources": {
            name: recorder.is_entity_recorded(hass, entity_id)
            for name, entity_id in coordinator.sources.items()
        },
        "max_age_hours": coordinator.max_age_hours,
        "accounting": coordinator.data.get("hourly"),
        "accounting_model": coordinator.data.get("accounting_model"),
        "accounting_as_of": coordinator.data.get("accounting_as_of"),
    }
    try:
        result["statistics"] = {
            name: await async_statistics_metadata(hass, entity_id)
            for name, entity_id in coordinator.sources.items()
        }
        from homeassistant.util import dt as dt_util

        sample = await async_read_counters(
            hass,
            coordinator.sources,
            msg["day"],
            coordinator.max_age_hours,
            dt_util.utcnow(),
        )
        result["sample"] = {
            "value": sample.value,
            "value_basis": "legacy_snapshot_index_only_not_used_for_settlement",
            "recorded_at": sample.recorded_at,
            "components": sample.components,
        }
    except LedgerError as err:
        result["error"] = {"code": err.code, "message": str(err)}
    except Exception:
        _LOGGER.exception("PGE Recorder diagnosis failed")
        connection.send_error(
            msg["id"],
            "recorder_error",
            "Nie udało się odczytać bazy Recorder. Sprawdź log Home Assistant.",
        )
        return
    connection.send_result(msg["id"], result)


@websocket_api.websocket_command(
    {vol.Required("type"): "pge_storage/daily", **ENTRY, vol.Required("month"): str}
)
@websocket_api.async_response
async def daily(hass, connection, msg):
    coordinator = _get(hass, connection, msg)
    try:
        result = await coordinator.async_daily(msg["month"])
    except LedgerError as err:
        connection.send_error(msg["id"], err.code, str(err))
    else:
        connection.send_result(msg["id"], result)


@websocket_api.websocket_command({vol.Required("type"): "pge_storage/profile", **ENTRY})
@websocket_api.async_response
async def profile(hass, connection, msg):
    coordinator = _get(hass, connection, msg)
    try:
        result = await coordinator.async_profile()
    except LedgerError as err:
        connection.send_error(msg["id"], err.code, str(err))
    else:
        connection.send_result(msg["id"], result)


@websocket_api.require_admin
@websocket_api.websocket_command(
    {
        vol.Required("type"): "pge_storage/put_plan",
        **WRITE,
        vol.Required("planning"): dict,
    }
)
@websocket_api.async_response
async def put_plan(hass, connection, msg):
    coordinator = _get(hass, connection, msg)
    await _write(
        connection, msg, coordinator.async_put_plan(msg["planning"], msg["revision"])
    )


@websocket_api.require_admin
@websocket_api.websocket_command(
    {vol.Required("type"): "pge_storage/refresh_plan", **ENTRY}
)
@websocket_api.async_response
async def refresh_plan(hass, connection, msg):
    coordinator = _get(hass, connection, msg)
    await coordinator.async_refresh_planning_history()
    coordinator.publish()
    connection.send_result(msg["id"])


@websocket_api.websocket_command({vol.Required("type"): "pge_storage/months", **ENTRY})
@websocket_api.async_response
async def months(hass, connection, msg):
    coordinator = _get(hass, connection, msg)
    try:
        connection.send_result(msg["id"], await async_months(coordinator))
    except LedgerError as err:
        connection.send_error(msg["id"], err.code, str(err))


@websocket_api.require_admin
@websocket_api.websocket_command(
    {
        vol.Required("type"): "pge_storage/put_energy",
        **WRITE,
        vol.Required("config"): dict,
    }
)
@websocket_api.async_response
async def put_energy(hass, connection, msg):
    coordinator = _get(hass, connection, msg)
    try:
        config = validate_energy_config(msg["config"])
    except LedgerError as err:
        connection.send_error(msg["id"], err.code, str(err))
        return
    if not all(
        connection.user.permissions.check_entity(entity_id, POLICY_READ)
        for entity_id in energy_sources(config)
    ):
        raise Unauthorized
    await _write(connection, msg, coordinator.async_put_energy(config, msg["revision"]))


@websocket_api.require_admin
@websocket_api.websocket_command(
    {vol.Required("type"): "pge_storage/energy_defaults", **ENTRY}
)
@websocket_api.async_response
async def energy_defaults(hass, connection, msg):
    _get(hass, connection, msg)
    try:
        result = await async_panel_config(hass)
        if not all(
            connection.user.permissions.check_entity(entity_id, POLICY_READ)
            for entity_id in energy_sources(result["config"])
        ):
            raise Unauthorized
        connection.send_result(msg["id"], result)
    except LedgerError as err:
        connection.send_error(msg["id"], err.code, str(err))


@websocket_api.require_admin
@websocket_api.websocket_command(
    {vol.Required("type"): "pge_storage/create_dashboard", **ENTRY}
)
@websocket_api.async_response
async def create_dashboard(hass, connection, msg):
    coordinator = _get(hass, connection, msg)
    try:
        result = await async_create_dashboard(hass, coordinator.entry.entry_id)
    except LedgerError as err:
        connection.send_error(msg["id"], err.code, str(err))
    except Exception:
        _LOGGER.exception("PGE dashboard creation failed")
        connection.send_error(
            msg["id"],
            "dashboard_failed",
            "Nie udało się utworzyć dashboardu. Sprawdź log Home Assistant.",
        )
    else:
        connection.send_result(msg["id"], result)


@websocket_api.websocket_command(
    {
        vol.Required("type"): "pge_storage/energy_period",
        **ENTRY,
        vol.Required("period"): vol.In(PERIODS),
        vol.Required("anchor_day"): str,
    }
)
@websocket_api.async_response
async def energy_period(hass, connection, msg):
    coordinator = _get(hass, connection, msg)
    try:
        result = await async_energy_period(
            coordinator, msg["period"], msg["anchor_day"]
        )
    except LedgerError as err:
        connection.send_error(msg["id"], err.code, str(err))
    else:
        connection.send_result(msg["id"], result)
