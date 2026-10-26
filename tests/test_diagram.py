import pytest

from custom_components.pge_storage.diagram import DiagramClock
from custom_components.pge_storage.energy import validate_energy_config
from custom_components.pge_storage.ledger import LedgerError


def test_explicit_clock_freezes_fast_changes_and_unchanged_report_updates_everything():
    clock = DiagramClock()
    clock.configure(["sensor.rest", "sensor.fast"], "sensor.rest", "setup", 0)
    clock.report("sensor.rest", 0, True)
    frame = clock.capture({"values": {"home_power": "1000"}}, "200", 0)
    clock.report("sensor.fast", 1, True)
    assert clock.capture({"values": {"home_power": "1500"}}, "201", 1) is frame
    assert clock.capture({"values": {"home_power": "1800"}}, "202", 9) is frame
    clock.report("sensor.rest", 10, True)  # same REST value still counts as a report
    updated = clock.capture({"values": {"home_power": "1800"}}, "202", 10)
    assert updated["sequence"] == frame["sequence"] + 1
    assert updated["available_energy"] == "202"
    assert updated["energy"]["values"]["home_power"] == "1800"
    assert frame["energy"]["values"]["home_power"] == "1000"


def test_auto_clock_uses_observed_cadence_not_entity_names():
    clock = DiagramClock()
    clock.configure(["sensor.a", "sensor.b"], None, "setup", 0)
    for second in range(31):
        clock.report("sensor.a", second, True)
        if second % 10 == 0:
            clock.report("sensor.b", second, True)
        clock.capture({}, None, second)
    assert clock.source(30) == "sensor.b"
    sequence = clock.frame["sequence"]
    clock.report("sensor.a", 31, True)
    assert clock.capture({}, None, 31)["sequence"] == sequence


def test_no_reports_and_unavailable_pv_use_ten_second_fallback():
    clock = DiagramClock()
    clock.configure(["sensor.rest"], "sensor.rest", "setup", 0)
    clock.report("sensor.rest", 0, True)
    first = clock.capture({"values": {"pv_power": "1000"}}, None, 0)
    clock.report("sensor.rest", 2, False)
    assert clock.capture({"values": {"pv_power": "0"}}, None, 9) is first
    second = clock.capture({"values": {"pv_power": "0"}}, None, 10)
    assert second["sequence"] == first["sequence"] + 1
    assert second["mode"] == "fallback_10s"
    assert clock.capture({}, None, 19) is second
    assert clock.capture({}, None, 20)["sequence"] == second["sequence"] + 1


def test_clock_must_be_an_explicitly_selected_pv_power_source():
    with pytest.raises(LedgerError):
        validate_energy_config(
            {
                "sources": {"pv_power": "sensor.pv"},
                "flow_clock_source": "sensor.unrelated",
            }
        )
    assert (
        validate_energy_config(
            {"sources": {"pv_power": "sensor.pv"}, "flow_clock_source": "sensor.pv"}
        )["flow_clock_source"]
        == "sensor.pv"
    )
