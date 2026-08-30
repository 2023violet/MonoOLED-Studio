from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter


@dataclass(frozen=True)
class RefreshWorkPlan:
    """Explicit hot-path/deferred-work contract for editor refreshes."""

    render: bool = True
    properties: bool = True
    runtime: bool = True
    validation: bool = False
    diff: bool = False
    evidence: bool = False
    asset_watcher: bool = False
    validation_deferred: bool = True
    diff_deferred: bool = True
    evidence_deferred: bool = True
    asset_watcher_deferred: bool = True

    @classmethod
    def for_interaction(cls, _name: str = 'interaction') -> 'RefreshWorkPlan':
        return cls()

    @classmethod
    def for_scene_commit(cls) -> 'RefreshWorkPlan':
        return cls()


class InteractionTrace:
    """Small monotonic trace used for startup and interaction latency evidence."""

    def __init__(self, name: str):
        self.name = str(name)
        self._started = perf_counter()
        self._marks: list[dict[str, float | str]] = []

    def mark(self, stage: str) -> float:
        elapsed = (perf_counter() - self._started) * 1000.0
        self._marks.append({'stage': str(stage), 'elapsed_ms': elapsed})
        return elapsed

    def as_dict(self) -> dict:
        elapsed = (perf_counter() - self._started) * 1000.0
        return {'name': self.name, 'elapsed_ms': elapsed, 'marks': [dict(v) for v in self._marks]}
