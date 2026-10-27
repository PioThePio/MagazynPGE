"""Delayed interpolation of reported power; never used for energy accounting."""

from bisect import bisect_right
from collections import deque
from copy import deepcopy


def interpolate(rows, at):
    rows = list(rows)
    if not rows:
        return 0.0
    index = bisect_right([r[0] for r in rows], at)
    if index == 0:
        return rows[0][1]
    if index == len(rows):
        return rows[-1][1]
    left, right = rows[index - 1], rows[index]
    ratio = (at - left[0]) / (right[0] - left[0])
    return left[1] + (right[1] - left[1]) * ratio


class AlignedFlow:
    def __init__(self):
        self.identity = None
        self.reports = {}
        self.samples = deque(maxlen=2048)
        self.frame = None
        self.sequence = 0
        self.last = None

    def report(self, entity, value, now):
        rows = self.reports.setdefault(entity, deque(maxlen=256))
        if rows and now < rows[-1][0]:
            rows.clear()
        if rows and now == rows[-1][0]:
            rows[-1] = (now, float(value or 0))
        else:
            rows.append((now, float(value or 0)))

    def capture(self, view, available, now, identity, mode="aligned"):
        if identity != self.identity or (self.samples and now < self.samples[-1][0]):
            self.samples.clear()
            self.frame, self.last = None, None
            self.identity = identity
        values = {
            k: float(v or 0) for k, v in view["values"].items() if k.endswith("_power")
        }
        values["home_power"] = float(
            view.get("home_power_live", values.get("home_power", 0))
        )
        self.samples.append((now, values))
        while len(self.samples) > 2 and self.samples[1][0] < now - 90:
            self.samples.popleft()
        if self.frame is not None and now - self.last < 3:
            return self.frame
        output = deepcopy(view)
        ready = mode == "aligned" and now - self.samples[0][0] >= 27
        target = now - 12 if ready else now
        arrays = view.get("pv_arrays", [])
        keys = list(values)

        def at(stamp):
            point = {
                key: interpolate(
                    [(t, row.get(key, 0)) for t, row in self.samples], stamp
                )
                for key in keys
            }
            pv = {}
            for array in arrays:
                entity = array.get("power_entity")
                rows = self.reports.get(entity)
                pv[array["id"]] = (
                    interpolate(rows, stamp)
                    if rows
                    else float(array.get("power_w") or 0)
                )
                if rows and stamp - rows[-1][0] > 25:
                    pv[array["id"]] = 0.0
            if arrays:
                point["pv_power"] = sum(pv.values())
            if (
                view.get("calculation", {}).get("home_power", {}).get("basis")
                == "balance"
            ):
                point["home_power"] = max(
                    0,
                    point.get("pv_power", 0)
                    + point.get("grid_import_power", 0)
                    + point.get("battery_discharge_power", 0)
                    - point.get("grid_export_power", 0)
                    - point.get("battery_charge_power", 0),
                )
            return point, pv

        if ready:
            windows = {}
            for seconds in (1, 5, 10, 15):
                # Uniform quadrature avoids weighting frequent reports more heavily.
                readings = [
                    at(target - seconds + (i + 0.5) / 2) for i in range(seconds * 2)
                ]
                windows[str(seconds)] = {
                    "covered_seconds": seconds,
                    "values": {
                        k: sum(p[0][k] for p in readings) / len(readings) for k in keys
                    },
                    "pv_arrays": {
                        a["id"]: sum(p[1][a["id"]] for p in readings) / len(readings)
                        for a in arrays
                    },
                }
            output["power_windows"] = windows
            output["values"].update(at(target)[0])
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
