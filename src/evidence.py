from __future__ import annotations

from hashlib import sha256
from pathlib import Path

from render import RenderResult
from scene import ROOT


def _relative_asset(path: str, project_root: str | Path | None = None) -> str:
    p = Path(path).resolve()
    root = Path(project_root).resolve() if project_root is not None else ROOT.resolve()
    try:
        return p.relative_to(root).as_posix()
    except ValueError:
        return p.as_posix()


def frame_evidence(result: RenderResult, state: dict, *, elapsed: int, project_root: str | Path | None = None) -> dict:
    raw = result.framebuffer.to_vlsb()
    visible = []
    for item in result.resolved_elements:
        if not item.get('visible'):
            continue
        visible.append({
            'id': item.get('id'),
            'type': item.get('type'),
            'x': item.get('x'), 'y': item.get('y'),
            'w': item.get('w'), 'h': item.get('h'),
            'text': item.get('text'),
            'assets': [_relative_asset(p, project_root) for p in item.get('assets', [])],
            'placeholder': bool(item.get('placeholder', False)),
        })
    return {
        'elapsed': int(elapsed),
        'state': dict(sorted(state.items())),
        'framebuffer_bytes': len(raw),
        'sha256': sha256(raw).hexdigest(),
        'lit_pixels': sum(sum(row) for row in result.framebuffer.to_rows()),
        'visible_elements': visible,
    }
