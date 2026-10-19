"""Production renderer frames for every export state of the reference scenes.

Inputs come from `fixtures/golden/inputs/` (frozen copies of the V1 builtin
scenes plus a synthetic scene set covering every element kind and error
branch) and `test_assets/projects/curing_lite`, so the corpus stays usable
after V1 is removed.
"""
from __future__ import annotations

from pathlib import Path

from .common import ROOT, byte_result, case, replace_root

from export_matrix import build_export_states
from project_workspace import ProjectWorkspace
from render import render_scene
from scene import load_scene, scene_root

NAME = 'scenes'
SOURCES = ('src/render.py', 'src/scene.py', 'src/export_matrix.py', 'src/batch_validate.py', 'src/state_schema.py',
           'src/assets.py', 'src/resource_cache.py', 'src/framebuffer.py', 'src/font_pack.py')

INPUTS = ROOT / 'fixtures' / 'golden' / 'inputs'
PROJECT = ROOT / 'test_assets' / 'projects' / 'curing_lite' / 'project.oled.json'


def _rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def _scenes() -> list[tuple[str, Path, Path]]:
    """(label, scene file, project root)."""
    builtin = INPUTS / 'builtin'
    scenes = [(f'builtin_{name}', builtin / 'src' / 'scenes' / f'{name}.json', builtin) for name in ('main_scene', 'example_placeholder')]
    synthetic = INPUTS / 'synthetic'
    scenes += [(f'synthetic_{path.stem}', path, synthetic) for path in sorted((synthetic / 'scenes').glob('*.json'))]
    project = ProjectWorkspace.load(PROJECT)
    scenes += [(f'curing_lite_{screen.id}', project.screen_path(screen.id), project.root) for screen in project.screens]
    return scenes


def _error(exc: Exception, root: Path) -> dict:
    missing = getattr(exc, 'filename', None)
    return {'error': type(exc).__name__, 'message': replace_root(str(exc), root),
            'missing_file': replace_root(Path(missing).as_posix(), root) if missing else None}


def build(work: Path) -> list[dict]:
    cases = []
    for label, path, project_root in _scenes():
        scene = load_scene(path, project_root=project_root)
        root = scene_root(scene)
        expect_errors = label.startswith('synthetic_err_')
        source = {'scene': _rel(path), 'project_root': _rel(project_root)}
        try:
            states = build_export_states(scene)
        except ValueError as exc:
            if not expect_errors:
                raise
            cases.append(case(f'scene-{label}-matrix', 'scene_render', 'strict', source, _error(exc, root)))
            continue
        for state_name, state in states.items():
            try:
                result = render_scene(scene, state)
            except FileNotFoundError as exc:
                # V1 defect evidence: example_placeholder references a removed legacy asset root.
                cases.append(case(f'scene-{label}-{state_name}', 'scene_render', 'strict', {**source, 'state': state}, _error(exc, root)))
                continue
            except Exception as exc:  # noqa: BLE001 - only the deliberate error scenes may fail
                if not expect_errors:
                    raise
                cases.append(case(f'scene-{label}-{state_name}', 'scene_render', 'strict', {**source, 'state': state}, _error(exc, root)))
                continue
            if expect_errors:
                raise AssertionError(f'{label} was expected to fail but rendered')
            fb = result.framebuffer
            cases.append(case(f'scene-{label}-{state_name}', 'scene_render', 'strict', {**source, 'state': state}, {
                'width': fb.width,
                'height': fb.height,
                'vlsb': byte_result(fb.to_vlsb()),
                'resolved_elements': replace_root([dict(item) for item in result.resolved_elements], root),
                'used_files': replace_root([p.as_posix() for p in result.used_files], root),
            }))
    return cases
