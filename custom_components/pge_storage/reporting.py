"""Live HA entity report cadence, independent of value changes and power means."""

from collections import deque
from statistics import median


class ReportCadence:
    """Keep five minutes of report timestamps only for selected entities."""

    def __init__(self):
        self.reports = {}

    def configure(self, entities):
        self.reports = {
            entity: self.reports.get(entity, deque()) for entity in entities
        }

    def report(self, entity, now):
        if entity in self.reports:
            rows = self.reports[entity]
            if not rows or now > rows[-1]:
                rows.append(now)
            self._prune(rows, now)

    @staticmethod
    def _prune(rows, now):
        while rows and rows[0] < now - 300:
            rows.popleft()

    def snapshot(self, now):
        result = {}
        for entity, rows in self.reports.items():
            self._prune(rows, now)
            intervals = [b - a for a, b in zip(rows, list(rows)[1:], strict=False)]
            result[entity] = {
                "reports": len(rows),
                "mean_seconds": sum(intervals) / len(intervals) if intervals else None,
                "typical_seconds": median(intervals) if intervals else None,
                "longest_seconds": max(intervals) if intervals else None,
            }
        return result
