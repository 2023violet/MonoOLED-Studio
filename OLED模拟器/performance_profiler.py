from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass


@dataclass(frozen=True)
class PerformanceSummary:
    name: str
    count: int
    latest_ms: float
    avg_ms: float
    max_ms: float


class PerformanceProfiler:
    """Tiny bounded in-process profiler for editor interaction paths."""

    def __init__(self, max_samples: int = 120):
        self.max_samples = max(1, int(max_samples))
        self._samples: dict[str, deque[float]] = defaultdict(
            lambda: deque(maxlen=self.max_samples)
        )

    def record(self, name: str, milliseconds: float) -> None:
        self._samples[str(name)].append(max(0.0, float(milliseconds)))

    def summary(self, name: str) -> PerformanceSummary:
        values = tuple(self._samples.get(str(name), ()))
        if not values:
            return PerformanceSummary(str(name), 0, 0.0, 0.0, 0.0)
        return PerformanceSummary(
            str(name), len(values), values[-1], sum(values) / len(values), max(values)
        )

    def clear(self) -> None:
        self._samples.clear()
