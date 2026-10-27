from custom_components.pge_storage.flow import AlignedFlow, interpolate


def view(pv, export):
    return {
        "values": {
            "pv_power": pv,
            "home_power": 9999,
            "grid_import_power": 0,
            "grid_export_power": export,
            "battery_charge_power": 0,
            "battery_discharge_power": 0,
        },
        "home_power_live": 9999,
        "calculation": {"home_power": {"basis": "balance"}},
        "pv_arrays": [{"id": "pv", "power_entity": "sensor.rest", "power_w": pv}],
        "power_windows": {},
    }


def test_delayed_interpolation_recovers_home_despite_asynchronous_pv_and_fast_grid():
    flow = AlignedFlow()
    for second in range(46):
        # Piecewise-linear underlying PV, REST reports it only every ten seconds.
        phase = second % 20
        actual = 1000 + 200 * phase if phase <= 10 else 5000 - 200 * phase
        if second % 10 == 0:
            held = actual
            flow.report("sensor.rest", actual, second)
        frame = flow.capture(view(held, actual - 500), 100, second, "config")
    assert frame["mode"] == "aligned_12s"
    assert frame["measurement_at"] == 33
    for window in frame["energy"]["power_windows"].values():
        assert abs(window["values"]["home_power"] - 500) < 0.001
    same = flow.capture(view(0, 0), 100, 46, "config")
    assert same is frame
    assert frame["energy"]["values"]["pv_power"] > 0


def test_latest_mode_updates_each_three_seconds_not_on_each_report():
    flow = AlignedFlow()
    first = flow.capture(view(1000, 0), 100, 0, "config", "latest")
    assert flow.capture(view(2000, 0), 100, 1, "config", "latest") is first
    assert flow.capture(view(2000, 0), 100, 3, "config", "latest")["sequence"] == 2
    assert interpolate([(0, 0), (10, 1000)], 5) == 500
    assert flow.capture(view(0, 0), 100, 4, "new-config")["mode"] == "warming_up"
