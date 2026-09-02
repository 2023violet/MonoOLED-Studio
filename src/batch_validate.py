from __future__ import annotations

from dataclasses import dataclass
import itertools
from pathlib import Path
import re

from validate import Finding, validate_scene
from resource_cache import RenderResources
from state_schema import schema_from_scene, validate_state
from atomic_io import atomic_write_text


@dataclass(frozen=True)
class MatrixValidationSummary:
    cases: int
    findings: int
    blockers: int
    by_case: tuple[tuple[str, tuple[Finding, ...]], ...]


def _int_values(spec: dict, policy: str) -> list[int]:
    if 'values' in spec:
        values = list(spec.get('values', []))
        if not values:
            return []
        return values
    lo=int(spec.get('min',0)); hi=int(spec.get('max',lo)); init=int(spec.get('init',lo))
    if policy=='boundaries':
        return sorted({lo, (lo + hi) // 2, init, hi})
    if policy=='representative':
        if hi-lo <= 12:
            return list(range(lo, hi+1))
        candidates={lo, min(hi,lo+1), init, hi}
        # Decimal transition boundaries catch the OLED timing/number-format cases
        # that matter most without exploding a 0..999 state into 1000 cases.
        for value in (9,10,99,100,300,999):
            if lo <= value <= hi:
                candidates.add(value)
        return sorted(candidates)
    if policy=='full':
        if hi-lo>2000: raise ValueError('full integer range too large')
        return list(range(lo,hi+1))
    raise ValueError(f'unsupported integer policy: {policy}')


def build_state_matrix(scene: dict, *, integer_policy: str='boundaries') -> list[dict]:
    names=[]; domains=[]
    for name,spec in scene.get('states',{}).items():
        names.append(name)
        if spec.get('type')=='enum': domains.append(list(spec.get('values',[])))
        elif spec.get('type')=='int': domains.append(_int_values(spec,integer_policy))
        else: domains.append([spec.get('init')])
    if not names: return [{}]
    schema = schema_from_scene(scene)
    matrix=[]
    for values in itertools.product(*domains):
        state=dict(zip(names,values))
        if not validate_state(schema,state):
            matrix.append(state)
    return matrix


_SAFE_COMPONENT = re.compile(r'[^A-Za-z0-9_.-]')


def case_name(index: int, state: dict) -> str:
    if not state:
        return f'case_{index:04d}'
    fields = '__'.join(
        f'{name}-{_SAFE_COMPONENT.sub("_", str(value)).replace("..", "__") or "_"}'
        for name, value in state.items()
    )
    return f'case_{index:04d}__{fields}'


def validate_matrix(scene:dict,matrix:list[dict],*,progress=None,cancel=None)->MatrixValidationSummary:
    rows=[]; total=0; blockers=0
    count=len(matrix)
    resources=RenderResources()
    for index,state in enumerate(matrix):
        if callable(cancel) and cancel(): raise RuntimeError('operation cancelled')
        findings=tuple(validate_scene(scene,dict(state),resources=resources))
        total+=len(findings); blockers+=sum(1 for f in findings if f.severity in {'ERROR','BLOCKER'})
        rows.append((case_name(index, state),findings))
        if callable(progress): progress('validation',index+1,count)
    return MatrixValidationSummary(len(matrix),total,blockers,tuple(rows))


def write_matrix_report(summary:MatrixValidationSummary,path:str|Path)->Path:
    lines=['# Batch Validation Matrix','',f'- Cases: **{summary.cases}**',f'- Findings: **{summary.findings}**',f'- Blockers: **{summary.blockers}**','']
    for name,findings in summary.by_case:
        if findings:
            lines.append(f'## {name}')
            for f in findings: lines.append(f'- **{f.severity}/{f.code}**: {f.message}')
            lines.append('')
    if summary.findings==0: lines.append('PASS — all state combinations have zero findings.')
    target=Path(path); atomic_write_text(target,'\n'.join(lines).rstrip()+'\n'); return target
