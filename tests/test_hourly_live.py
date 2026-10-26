from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from homeassistant.core import State

from custom_components.pge_storage.hourly import (
    HourBook,
    accounting_snapshot,
    extend_accounting,
    make_hour,
)
from custom_components.pge_storage.hourly_live import LiveHour
from custom_components.pge_storage.planning import validate_plan
from tests.test_hourly import anchor


def test_native_offset_projects_current_hour_and_waits_after_restart_or_reset():
    begin = datetime(2026, 10, 1, 12, tzinfo=UTC)
    now = begin + timedelta(minutes=6)
    sources = {"import": "sensor.i", "export": "sensor.e"}
    states = {
        entity: State(entity, value, {"unit_of_measurement": "kWh"}, last_updated=now)
        for entity, value in [("sensor.i", "5.5"), ("sensor.e", "1")]
    }
    hass = SimpleNamespace(states=SimpleNamespace(get=states.get))
    context = {
        "start": begin.isoformat(),
        "positions": {
            "import": {
                "opening_sum": "100",
                "sum": "102.5",
                "state": "5",
                "end": (begin + timedelta(minutes=5)).isoformat(),
            },
            "export": {
                "opening_sum": "100",
                "sum": "101",
                "state": "0.8",
                "end": (begin + timedelta(minutes=5)).isoformat(),
            },
        },
    }
    projector = LiveHour(begin - timedelta(hours=1))
    row = projector.project(context, hass, sources, now)
    assert row["raw_import_kwh"] == "3" and row["raw_export_kwh"] == "1.2"
    assert row["net_kwh"] == "-1.8"
    restarted = LiveHour(now)
    assert restarted.project(context, hass, sources, now) is None
    old = states["sensor.i"]
    states["sensor.i"] = State(
        "sensor.i", "0.1", {"unit_of_measurement": "kWh"}, last_updated=now
    )
    projector.observe(
        SimpleNamespace(
            data={
                "entity_id": "sensor.i",
                "old_state": old,
                "new_state": states["sensor.i"],
            }
        ),
        sources,
        now,
    )
    assert projector.project(context, hass, sources, now) is None
    later = begin + timedelta(minutes=11)
    for position in context["positions"].values():
        position["end"] = (begin + timedelta(minutes=10)).isoformat()
    context["positions"]["import"].update(sum="103", state="0.5")
    context["positions"]["export"].update(sum="101.2", state="1")
    states["sensor.i"] = State(
        "sensor.i", "0.7", {"unit_of_measurement": "kWh"}, last_updated=later
    )
    repaired = projector.project(context, hass, sources, later)
    assert repaired["raw_import_kwh"] == "3.2"
    states["sensor.e"] = State(
        "sensor.e", "unavailable", {"unit_of_measurement": "kWh"}
    )
    assert projector.project(context, hass, sources, later) is None


def test_successive_provisional_values_replace_instead_of_accumulate():
    first = anchor(balance="0")
    from custom_components.pge_storage.ledger import boundary

    begin = boundary(first.day)
    closed = make_hour(begin, 0, 1)
    prefix = accounting_snapshot(
        HourBook({closed["start"]: closed}),
        [first],
        validate_plan({}),
        begin + timedelta(hours=1),
    )
    assert prefix["current"]["available_energy"] == "0.8"
    row = make_hour(
        begin + timedelta(hours=1),
        "0.2",
        0,
        "live_native_projection",
        end=begin + timedelta(hours=1, minutes=5),
    )
    assert extend_accounting(prefix, row)["current"]["available_energy"] == "0.6"
    row = make_hour(
        begin + timedelta(hours=1),
        "0.5",
        0,
        "live_native_projection",
        end=begin + timedelta(hours=1, minutes=10),
    )
    assert extend_accounting(prefix, row)["current"]["available_energy"] == "0.3"
    assert prefix["current"]["available_energy"] == "0.8"
