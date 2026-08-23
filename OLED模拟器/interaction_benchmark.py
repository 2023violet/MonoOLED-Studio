from __future__ import annotations

from dataclasses import dataclass
from statistics import mean
from time import perf_counter

from editor_model import EditorSession
from evidence import frame_evidence
from scene import load_scene, scene_root


@dataclass(frozen=True)
class BenchMetric:
    avg_ms: float
    p95_ms: float
    max_ms: float


@dataclass(frozen=True)
class InteractionBenchmark:
    iterations: int
    render: BenchMetric
    validation: BenchMetric
    evidence: BenchMetric
    full_pipeline: BenchMetric


def _measure(fn, iterations: int) -> BenchMetric:
    values=[]
    for _ in range(max(1, int(iterations))):
        t=perf_counter(); fn(); values.append((perf_counter()-t)*1000.0)
    values.sort()
    idx=max(0,min(len(values)-1,int(round((len(values)-1)*0.95))))
    return BenchMetric(mean(values), values[idx], max(values))


def benchmark_scene(source: str='main_scene', *, iterations: int=120) -> InteractionBenchmark:
    scene=load_scene(source); session=EditorSession(scene); root=scene_root(scene)
    latest=[session.render()]

    def render_once():
        latest[0]=session.render()

    def validate_once():
        session.validate()

    def evidence_once():
        result=latest[0]
        frame_evidence(result, dict(session.runtime.state), elapsed=session.runtime.elapsed, project_root=root)

    def full_once():
        result=session.render()
        session.validate()
        frame_evidence(result, dict(session.runtime.state), elapsed=session.runtime.elapsed, project_root=root)

    return InteractionBenchmark(
        max(1,int(iterations)),
        _measure(render_once, iterations),
        _measure(validate_once, iterations),
        _measure(evidence_once, iterations),
        _measure(full_once, iterations),
    )


def main() -> int:
    r=benchmark_scene('main_scene',iterations=120)
    print(f'Render avg={r.render.avg_ms:.3f}ms p95={r.render.p95_ms:.3f}ms')
    print(f'Validation avg={r.validation.avg_ms:.3f}ms p95={r.validation.p95_ms:.3f}ms')
    print(f'Evidence avg={r.evidence.avg_ms:.3f}ms p95={r.evidence.p95_ms:.3f}ms')
    print(f'Full pipeline avg={r.full_pipeline.avg_ms:.3f}ms p95={r.full_pipeline.p95_ms:.3f}ms')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
