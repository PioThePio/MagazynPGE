"""Report-driven diagram frames, separate from live sensors and accounting."""

from collections import deque
from copy import deepcopy
from statistics import median


class DiagramClock:
    def __init__(self):
        self.identity = None
        self.ids = ()
        self.explicit = None
        self.started = None
        self.last = {}
        self.valid = {}
        self.intervals = {}
        self.frame = None
        self.last_frame = None
        self.sequence = 0
        self.report_ready = False

    def configure(self, ids, explicit, identity, now):
        if identity == self.identity:
            return
        self.__init__()
        self.identity, self.ids, self.explicit, self.started = (
            identity,
            tuple(ids),
            explicit,
            now,
        )
        self.intervals = {entity: deque(maxlen=9) for entity in ids}

    def report(self, entity, now, valid):
        if entity not in self.ids:
            return
        prior = self.last.get(entity)
        if prior is not None and 0.2 <= now - prior <= 120:
            self.intervals[entity].append(now - prior)
        self.last[entity], self.valid[entity] = now, valid
        if valid and self.source(now) == entity:
            self.report_ready = True

    def source(self, now):
        if self.explicit:
            return self.explicit
        active = [entity for entity in self.ids if self.valid.get(entity)]
        if self.started is None or now - self.started < 20 or not active:
            return None
        if any(len(self.intervals[entity]) < 2 for entity in active):
            return None
        slowest = max(active, key=lambda entity: median(self.intervals[entity]))
        return slowest if median(self.intervals[slowest]) >= 5 else None

    def capture(self, energy_view, available, now):
        if self.last_frame is not None and now < self.last_frame:
            self.last_frame, self.frame = None, None
            self.last.clear()
            self.valid.clear()
            for intervals in self.intervals.values():
                intervals.clear()
            self.started = now
        source = self.source(now)
        alive = (
            source and self.valid.get(source) and now - self.last.get(source, -1e9) < 25
        )
        due = (
            self.frame is None
            or self.report_ready
            or (not alive and now - self.last_frame >= 10)
        )
        if due:
            self.sequence += 1
            self.last_frame = now
            self.frame = {
                "sequence": self.sequence,
                "observed_at": now,
                "clock_entity_id": source,
                "mode": "source_report" if alive else "fallback_10s",
                "energy": deepcopy(energy_view),
                "available_energy": available,
            }
        self.report_ready = False
        return self.frame
