from custom_components.pge_storage.power import PowerWindows


def view(pv=1000, exported=0, charge=0, load=100):
    return {
        "values": {
            "pv_power": str(pv),
            "grid_import_power": "0",
            "grid_export_power": str(exported),
            "battery_charge_power": str(charge),
            "battery_discharge_power": "0",
            "home_power": str(max(0, pv - exported - charge)),
        },
        "calculation": {"home_power": {"basis": "balance"}},
        "consumers": [
            {"id": "ac", "power_w": str(load), "counted_power": True},
            {"id": "child", "power_w": "80", "counted_power": False},
        ],
    }


def test_time_weighted_average_is_independent_of_report_frequency():
    window = PowerWindows()
    window.update(view(pv=100), 0, "sources")
    window.update(view(pv=500), 1, "sources")
    for stamp in (1.1, 1.2, 1.3, 1.4, 2, 3, 4):
        window.update(view(pv=500), stamp, "sources")
    result = window.update(view(pv=500), 5, "sources")
    assert result["5"]["home_power_w"] == 420
    assert result["1"]["home_power_w"] == 500
    assert result["5"]["tracked_power_w"] == 100
    assert result["5"]["untracked_power_w"] == 320
    assert len(window.samples) == 2


def test_asynchronous_pv_grid_spike_is_damped_and_charge_is_not_home_load():
    window = PowerWindows()
    window.update(view(pv=3000, exported=2000, charge=500), 0, "sources")
    # Fast grid meter sees the reduction before the slow solar inverter.
    window.update(view(pv=3000, exported=500, charge=500), 14, "sources")
    result = window.update(view(pv=1500, exported=500, charge=500), 15, "sources")
    assert result["15"]["home_power_w"] == 600
    assert result["15"]["untracked_power_w"] == 500
    assert result["15"]["covered_seconds"] == 15
    result = window.update(view(pv=1500, exported=500, charge=500), 30, "sources")
    assert result["15"]["home_power_w"] == 500
    assert result["15"]["untracked_power_w"] == 400


def test_source_change_and_clock_reversal_reset_history_without_inventing_samples():
    window = PowerWindows()
    window.update(view(pv=100), 0, "old")
    result = window.update(view(pv=500), 10, "new")
    assert result["15"]["home_power_w"] == 500
    assert result["15"]["covered_seconds"] == 0
    result = window.update(view(pv=250), 5, "new")
    assert result["15"]["home_power_w"] == 250
    assert result["15"]["covered_seconds"] == 0


def test_signed_balance_is_averaged_before_clipping_negative_intermediate_values():
    window = PowerWindows()
    window.update(view(pv=0, exported=1000), 0, "source")
    window.update(view(pv=2000, exported=1000), 5, "source")
    result = window.update(view(pv=2000, exported=1000), 10, "source")
    assert result["10"]["home_power_w"] == 0
