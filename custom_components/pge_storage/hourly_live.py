"""Provisional live hour: native reset-safe sums plus subsequent raw increments."""

from datetime import datetime

from .history import sample_from_state
from .hourly import hour_floor, make_hour
from .ledger import LedgerError, energy


class LiveHour:
    def __init__(self, started):
        self.started = started
        self.invalid_after = {}

    def observe(self, event, sources, now):
        entity = event.data.get("entity_id")
        if entity not in sources.values():
            return
        try:
            current = energy(sample_from_state(event.data.get("new_state")).value)
            old = event.data.get("old_state")
            if old is not None and current < energy(sample_from_state(old).value):
                self.invalid_after[entity] = now
        except LedgerError:
            self.invalid_after[entity] = now

    def project(self, context, hass, sources, now):
        if not context or datetime.fromisoformat(context["start"]) != hour_floor(now):
            return None
        totals, observed = {}, []
        try:
            for direction, entity in sources.items():
                point = context["positions"][direction]
                stamp = datetime.fromisoformat(point["end"])
                if stamp < max(
                    self.started, self.invalid_after.get(entity, self.started)
                ):
                    return None
                state = hass.states.get(entity)
                raw = sample_from_state(state)
                value = energy(raw.value)
                last = energy(point["state"])
                if value < last or (state.last_updated < stamp and value != last):
                    return None
                totals[direction] = (
                    energy(point["sum"]) - energy(point["opening_sum"]) + value - last
                )
                observed.append(max(stamp, min(now, state.last_reported)))
            return make_hour(
                hour_floor(now),
                totals["import"],
                totals["export"],
                "live_native_projection",
                end=min(observed),
            )
        except LedgerError, ValueError, TypeError, KeyError, AttributeError:
            return None
