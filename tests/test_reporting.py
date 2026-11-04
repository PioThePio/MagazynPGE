"""Report cadence counts HA writes, not power changes."""

from custom_components.pge_storage.reporting import ReportCadence


def test_rolling_window_and_reconfiguration():
    cadence = ReportCadence()
    cadence.configure(["sensor.fast", "sensor.slow"])
    for second in range(601):
        cadence.report("sensor.fast", second)
        if second % 30 == 0:
            cadence.report("sensor.slow", second)
    result = cadence.snapshot(600)
    assert result["sensor.fast"]["reports"] == 301
    assert result["sensor.fast"]["mean_seconds"] == 1
    assert result["sensor.slow"]["typical_seconds"] == 30
    cadence.configure(["sensor.slow", "sensor.new"])
    result = cadence.snapshot(601)
    assert "sensor.fast" not in result
    assert result["sensor.slow"]["reports"] == 10
    assert result["sensor.new"]["mean_seconds"] is None
    assert cadence.snapshot(1000)["sensor.slow"]["reports"] == 0


def test_irregular_reports_and_single_sample():
    cadence = ReportCadence()
    cadence.configure(["sensor.power"])
    for timestamp in [0, 1, 2, 3, 30]:
        cadence.report("sensor.power", timestamp)
    data = cadence.snapshot(30)["sensor.power"]
    assert data["typical_seconds"] == 1
    assert data["mean_seconds"] == 7.5
    assert data["longest_seconds"] == 27
    cadence.report("sensor.ignored", 30)
    cadence.report("sensor.power", 30)
    assert cadence.snapshot(30)["sensor.power"]["reports"] == 5
    assert cadence.snapshot(302)["sensor.power"]["reports"] == 3
    assert cadence.snapshot(303.5)["sensor.power"]["mean_seconds"] is None
