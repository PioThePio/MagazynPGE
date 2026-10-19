"""Bounded, time-weighted power windows shared by all dashboard clients."""

from collections import deque

WINDOWS = (1, 5, 10, 15)


class PowerWindows:
    def __init__(self):
        self.samples = deque(maxlen=4096)
        self.identity = None

    def update(self, snapshot, now, identity):
        if self.identity != identity or (self.samples and now < self.samples[-1][0]):
            self.samples.clear()
            self.identity = identity
        values = {
            key: float(value or 0)
            for key, value in snapshot["values"].items()
            if key.endswith("_power")
        }
        consumers = snapshot["consumers"]
        for item in consumers:
            key = (
                item.get("id")
                or item.get("statistic")
                or item.get("energy")
                or item.get("power")
            )
            values[f"consumer:{key}"] = float(item.get("power_w") or 0)
        for array in snapshot.get("pv_arrays", []):
            values[f"pv:{array['id']}"] = float(array.get("power_w") or 0)
        # Avoid a bias from clipping negative asynchronous intermediate balances.
        if snapshot["calculation"].get("home_power", {}).get("basis") == "balance":
            values["home_power"] = (
                values.get("pv_power", 0)
                + values.get("grid_import_power", 0)
                + values.get("battery_discharge_power", 0)
                - values.get("grid_export_power", 0)
                - values.get("battery_charge_power", 0)
            )
        if self.samples and self.samples[-1][0] == now:
            self.samples[-1] = (now, values)
        elif not self.samples or self.samples[-1][1] != values:
            self.samples.append((now, values))
        while len(self.samples) > 1 and self.samples[1][0] <= now - max(WINDOWS):
            self.samples.popleft()
        results = {}
        for seconds in WINDOWS:
            start = max(now - seconds, self.samples[0][0])
            duration = now - start
            sums = dict.fromkeys(values, 0.0)
            rows = list(self.samples)
            for index, (stamp, reading) in enumerate(rows):
                stop = rows[index + 1][0] if index + 1 < len(rows) else now
                weight = max(0, stop - max(start, stamp))
                for key in sums:
                    sums[key] += reading.get(key, 0) * weight
            averages = {
                key: round(sums[key] / duration if duration else value, 3)
                for key, value in values.items()
            }
            averages["home_power"] = max(0, averages.get("home_power", 0))
            selected = {
                key: value
                for key, value in averages.items()
                if not key.startswith(("consumer:", "pv:"))
            }
            devices = {
                key.removeprefix("consumer:"): value
                for key, value in averages.items()
                if key.startswith("consumer:")
            }
            tracked = sum(
                devices.get(
                    item.get("id")
                    or item.get("statistic")
                    or item.get("energy")
                    or item.get("power"),
                    0,
                )
                for item in consumers
                if item.get("counted_power")
            )
            results[str(seconds)] = {
                "pv_arrays": {
                    key.removeprefix("pv:"): value
                    for key, value in averages.items()
                    if key.startswith("pv:")
                },
                "values": selected,
                "consumers": devices,
                "home_power_w": selected["home_power"],
                "tracked_power_w": round(tracked, 3),
                "untracked_power_w": round(selected["home_power"] - tracked, 3),
                "covered_seconds": round(duration, 3),
            }
        return results
