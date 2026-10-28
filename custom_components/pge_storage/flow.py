"""Shared delayed power frames and time-weighted windows, never settlement kWh."""

from bisect import bisect_right
from collections import deque
from copy import deepcopy

WINDOWS = (1, 5, 10, 15, 60, 300, 900, 1800)


def interpolate(rows, at):
    rows = list(rows)
    if not rows:
        return 0.0
    index = bisect_right([r[0] for r in rows], at)
    if not index:
        return rows[0][1]
    if index == len(rows):
        return rows[-1][1]
    left, right = rows[index - 1], rows[index]
    return left[1] + (right[1] - left[1]) * (at - left[0]) / (right[0] - left[0])


class Series:
    def __init__(self, rows, linear):
        self.rows = rows
        self.times = [row[0] for row in rows]
        self.linear = linear
        self.area = [0.0]
        self.last_unknown = [-1]
        for i in range(len(rows) - 1):
            left, right = rows[i], rows[i + 1]
            a = float(left[1] or 0)
            b = float(right[1] or 0) if linear else a
            self.area.append(self.area[-1] + (a + b) / 2 * (right[0] - left[0]))
            self.last_unknown.append(i if left[1] is None else self.last_unknown[-1])

    def primitive(self, at):
        index = max(0, bisect_right(self.times, at) - 1)
        stamp, value = self.rows[index]
        dt = max(0, at - stamp)
        a = float(value or 0)
        slope = 0.0
        if self.linear and index + 1 < len(self.rows):
            stop, b = self.rows[index + 1]
            slope = (float(b or 0) - a) / (stop - stamp) if stop > stamp else 0
        return self.area[index] + a * dt + slope * dt * dt / 2

    def mean(self, end, seconds):
        if not self.rows or end < self.times[0]:
            return None, 0.0
        last = max(0, bisect_right(self.times, end) - 1)
        unknown = last if self.rows[last][1] is None else self.last_unknown[last]
        start = max(
            end - seconds,
            self.times[0],
            self.times[unknown + 1]
            if unknown >= 0 and unknown + 1 < len(self.times)
            else end
            if unknown == last
            else self.times[0],
        )
        if unknown == last:
            return None, 0.0
        duration = max(0, end - start)
        reading = (
            (self.primitive(end) - self.primitive(start)) / duration
            if duration
            else float(self.rows[last][1])
        )
        return reading, duration


def flatten(view):
    known = view.get("power_history_known", {})
    result = {
        key: float(value or 0) if known.get(key, True) else None
        for key, value in view["values"].items()
        if key.endswith("_power")
    }
    if view.get("calculation", {}).get("home_power", {}).get(
        "basis"
    ) == "balance" and known.get("home_power", True):
        result["home_power"] = sum(
            float(result.get(k) or 0) * factor
            for k, factor in (
                ("pv_power", 1),
                ("grid_import_power", 1),
                ("grid_export_power", -1),
                ("battery_discharge_power", 1),
                ("battery_charge_power", -1),
            )
        )
    for item in view.get("consumers", []):
        ident = (
            item.get("id")
            or item.get("statistic")
            or item.get("energy")
            or item.get("power")
        )
        result[f"consumer:{ident}"] = (
            float(item.get("power_w") or 0)
            if view.get("consumer_history_known", {}).get(ident, True)
            else None
        )
    for array in view.get("pv_arrays", []):
        result[f"pv:{array['id']}"] = (
            float(array.get("power_w") or 0)
            if view.get("pv_history_known", {}).get(array["id"], True)
            else None
        )
    return result


class AlignedFlow:
    def __init__(self):
        self.identity = None
        self.reports = {}
        self.samples = deque(maxlen=8192)
        self.frame = None
        self.sequence = 0
        self.last = None
        self.started = None
        self.live_reports = {}

    def report(self, entity, value, now):
        rows = self.reports.setdefault(entity, deque(maxlen=8192))
        if rows and now < rows[-1][0]:
            rows.clear()
        if rows and now == rows[-1][0]:
            rows[-1] = (now, float(value or 0))
        else:
            rows.append((now, float(value or 0)))
        while len(rows) > 2 and rows[1][0] < now - 1845:
            rows.popleft()
        self.live_reports[entity] = now

    def seed(self, frames, reports, identity):
        self.identity = identity
        self.samples = deque(
            ((stamp, flatten(view)) for stamp, view in frames), maxlen=8192
        )
        self.reports = {
            entity: deque(values, maxlen=8192) for entity, values in reports.items()
        }
        self.frame, self.last = None, None
        self.started = self.samples[-1][0] if self.samples else None
        self.live_reports = {}

    def capture(self, view, available, now, identity, mode="aligned"):
        if identity != self.identity or (self.samples and now < self.samples[-1][0]):
            self.samples.clear()
            self.frame, self.last = None, None
            self.identity = identity
            self.started = now
        current = flatten(view)
        # Display-only 2 Hz buffer: high-frequency devices must not grow the
        # thirty-minute history without bound or monopolize HA's event loop.
        if self.samples and now - self.samples[-1][0] < 0.5:
            self.samples[-1] = (self.samples[-1][0], current)
        else:
            self.samples.append((now, current))
        while len(self.samples) > 2 and self.samples[1][0] < now - 1845:
            self.samples.popleft()
        if self.frame is not None and now - self.last < 3:
            return self.frame
        output = deepcopy(view)
        output.pop("diagram_frame", None)
        required = (
            "pv_power",
            "grid_import_power",
            "grid_export_power",
            "battery_charge_power",
            "battery_discharge_power",
            "home_power",
        )
        starts = []
        for key in required:
            rows = list(self.samples)
            missing = next(
                (
                    i
                    for i in range(len(rows) - 1, -1, -1)
                    if rows[i][1].get(key) is None
                ),
                -1,
            )
            starts.append(rows[missing + 1][0] if missing + 1 < len(rows) else now)
        ready = mode == "aligned" and now - max(starts) >= 27
        target = now - 12 if ready else now
        series = {
            key: Series([(t, row.get(key)) for t, row in self.samples], ready)
            for key in current
        }
        arrays = view.get("pv_arrays", [])
        if ready:
            for array in arrays:
                entity = array.get("power_entity")
                reports = list(self.reports.get(entity, []))
                if reports:
                    threshold = self.live_reports.get(entity, self.started or now) + 25
                    if (
                        entity in view.get("stale_power_sources", [])
                        and threshold <= now
                    ):
                        reports.append((max(threshold, reports[-1][0] + 0.001), 0.0))
                    series[f"pv:{array['id']}"] = Series(reports, True)
        windows = {}
        for seconds in WINDOWS:
            home_terms = (
                (
                    "pv_power",
                    "grid_import_power",
                    "grid_export_power",
                    "battery_discharge_power",
                    "battery_charge_power",
                )
                if view.get("calculation", {}).get("home_power", {}).get("basis")
                == "balance"
                else ("home_power",)
            )
            spans = [
                series[key].mean(target, seconds)[1]
                for key in home_terms
                if key in series
            ]
            if arrays and ready:
                spans.extend(
                    series[f"pv:{array['id']}"].mean(target, seconds)[1]
                    for array in arrays
                )
            effective = min([seconds] + spans)
            means = {
                key: column.mean(target, effective) for key, column in series.items()
            }
            selected = {
                key: reading[0]
                for key, reading in means.items()
                if not key.startswith(("consumer:", "pv:"))
            }
            coverage = {key: reading[1] for key, reading in means.items()}
            if arrays and ready:
                vals = [means.get(f"pv:{a['id']}", (None, 0)) for a in arrays]
                selected["pv_power"] = (
                    sum(v[0] for v in vals)
                    if all(v[0] is not None for v in vals)
                    else None
                )
                coverage["pv_power"] = min(v[1] for v in vals)
            if (
                view.get("calculation", {}).get("home_power", {}).get("basis")
                == "balance"
            ):
                terms = (
                    ("pv_power", 1),
                    ("grid_import_power", 1),
                    ("grid_export_power", -1),
                    ("battery_discharge_power", 1),
                    ("battery_charge_power", -1),
                )
                selected["home_power"] = (
                    max(
                        0,
                        sum((selected.get(key) or 0) * factor for key, factor in terms),
                    )
                    if all(selected.get(key) is not None for key, _ in terms)
                    else None
                )
                coverage["home_power"] = min(coverage.get(key, 0) for key, _ in terms)
            devices = {
                key.removeprefix("consumer:"): v[0]
                for key, v in means.items()
                if key.startswith("consumer:")
            }
            counted = [
                item.get("id")
                or item.get("statistic")
                or item.get("energy")
                or item.get("power")
                for item in view.get("consumers", [])
                if item.get("counted_power")
            ]
            tracked = (
                sum(devices.get(key) or 0 for key in counted)
                if all(devices.get(key) is not None for key in counted)
                else None
            )
            house = selected.get("home_power")
            matched_tracking = all(
                coverage.get(f"consumer:{key}", 0) + 0.01
                >= coverage.get("home_power", 0)
                for key in counted
            )
            windows[str(seconds)] = {
                "covered_seconds": round(coverage.get("home_power", 0), 3),
                "values": selected,
                "consumers": devices,
                "consumer_coverage_seconds": {
                    key: coverage.get(f"consumer:{key}", 0) for key in devices
                },
                "home_power_w": house,
                "tracked_power_w": tracked,
                "untracked_power_w": house - tracked
                if house is not None and tracked is not None and matched_tracking
                else None,
                "untracked_covered_seconds": min(
                    [coverage.get("home_power", 0)]
                    + [coverage.get(f"consumer:{key}", 0) for key in counted]
                ),
                "pv_arrays": {
                    a["id"]: means.get(f"pv:{a['id']}", (None, 0))[0] for a in arrays
                },
                "as_of": target,
            }
        point = windows["1"]
        output["values"].update(point["values"])
        output["home_power_live"] = point["home_power_w"]
        for consumer in output.get("consumers", []):
            ident = (
                consumer.get("id")
                or consumer.get("statistic")
                or consumer.get("energy")
                or consumer.get("power")
            )
            consumer["power_w"] = point["consumers"].get(ident)
        output["power_windows"] = windows
        # Both clients use exactly these immutable windows from the same frame.
        self.sequence += 1
        self.last = now
        self.frame = {
            "sequence": self.sequence,
            "observed_at": now,
            "measurement_at": target,
            "mode": "aligned_12s"
            if ready
            else "warming_up"
            if mode == "aligned"
            else "latest_3s",
            "energy": output,
            "available_energy": available,
        }
        return self.frame
