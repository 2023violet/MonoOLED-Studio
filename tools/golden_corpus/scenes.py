"""Production renderer frames for every export state of the reference scenes."""
from __future__ import annotations

from pathlib import Path

from .common import ROOT, byte_result, case, replace_root

from export_matrix import build_export_states
from project_workspace import ProjectWorkspace
from render import render_scene
from scene import load_scene, scene_root

NAME = 'scenes'
SOURCES = ('src/render.py', 'src/scene.py', 'src/export_matrix.py', 'src/state_schema.py', 'src/assets.py',
           'src/resource_cache.py', 'src/framebuffer.py', 'src/font_pack.py')

PROJECT = ROOT / 'test_assets' / 'projects' / 'curing_lite' / 'project.oled.json'


def _scenes() -> list[tuple[str, dict, str]]:
    scenes = [(f'builtin_{name}', load_scene(name), f'src/scenes/{name}.json') for name in ('main_scene', 'example_placeholder')]
    project = ProjectWorkspace.load(PROJECT)
    for screen in project.screens:
        path = project.screen_path(screen.id)
        scenes.append((f'curing_lite_{screen.id}', load_scene(path, project_root=project.root),
                       path.relative_to(ROOT).as_posix()))
    return scenes


def _level(scene: dict) -> str:
    # Scene `text` elements use bitmap mode-font headers, not TTF, so every frame is strict.
    return 'strict'


def build(work: Path) -> list[dict]:
    cases = []
    for label, scene, source in _scenes():
        root = scene_root(scene)
        for state_name, state in build_export_states(scene).items():
            try:
                result = render_scene(scene, state)
            except (OSError, ValueError) as exc:
                # V1 defect evidence (e.g. example_placeholder references a removed legacy asset root).
                missing = getattr(exc, 'filename', None)
                cases.append(case(f'scene-{label}-{state_name}', 'scene_render', 'strict',
                                  {'scene': source, 'state': state},
                                  {'error': type(exc).__name__,
                                   'missing_file': replace_root(Path(missing).as_posix(), root) if missing else None}))
                continue
            fb = result.framebuffer
            expected = {
                'width': fb.width,
                'height': fb.height,
                'vlsb': byte_result(fb.to_vlsb()),
                'resolved_elements': replace_root([dict(item) for item in result.resolved_elements], root),
                'used_files': replace_root([path.as_posix() for path in result.used_files], root),
            }
            cases.append(case(f'scene-{label}-{state_name}', 'scene_render', _level(scene),
                              {'scene': source, 'state': state}, expected))
    return cases
