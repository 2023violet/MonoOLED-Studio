"""Code AI handoff ZIP contents.

Text, JSON, C header and BIN entries are compared byte-for-byte. PNG entries
and the ZIP container depend on the deflate implementation, so they are
compared by decoded pixels; their encoded bytes are recorded for reference only.
"""
from __future__ import annotations

from hashlib import sha256
import io
from pathlib import Path
import zipfile

from PIL import Image

from .common import ROOT, case, digest_result, replace_root

from export_matrix import build_export_states
from handoff import build_handoff_package
from project_workspace import ProjectWorkspace
from scene import load_scene, scene_root

NAME = 'handoff'
SOURCES = ('src/handoff.py', 'src/exporter.py', 'src/batch_validate.py', 'src/c_export.py', 'src/design_rules.py',
           'src/thumbnail_wall.py', 'src/asset_library.py', 'src/render.py', 'src/validate.py')

PROJECT = ROOT / 'test_assets' / 'projects' / 'curing_lite' / 'project.oled.json'


def _entry(name: str, data: bytes, root: Path) -> dict:
    if name.endswith('.png'):
        image = Image.open(io.BytesIO(data))
        pixels = image.convert('L').tobytes()
        return {'name': name, 'kind': 'png', 'size': list(image.size),
                'pixels_l_sha256': sha256(pixels).hexdigest(), 'encoded_reference': digest_result(data)}
    if name.endswith(('.md', '.json', '.h')):
        text = data.decode('utf-8')
        normalized = replace_root(text, root)
        return {'name': name, 'kind': 'text', **digest_result(normalized.encode('utf-8')),
                'root_substituted': normalized != text}
    return {'name': name, 'kind': 'binary', **digest_result(data)}


def build(work: Path) -> list[dict]:
    project = ProjectWorkspace.load(PROJECT)
    sources = [
        ('builtin_main_scene', load_scene('main_scene'), 'src/scenes/main_scene.json', None),
        ('curing_lite_main', load_scene(project.screen_path('main'), project_root=project.root),
         'test_assets/projects/curing_lite/scenes/main_scene.json', 4),
    ]
    cases = []
    for label, scene, source, limit in sources:
        states = build_export_states(scene)
        if limit is not None:
            states = dict(list(states.items())[:limit])
        for policy in ('boundaries', 'representative'):
            target = work / f'{label}-{policy}.zip'
            build_handoff_package(scene, target, states=states, integer_policy=policy)
            with zipfile.ZipFile(target) as archive:
                entries = [_entry(info.filename, archive.read(info.filename), scene_root(scene))
                           for info in sorted(archive.infolist(), key=lambda item: item.filename)]
            cases.append(case(
                f'handoff-{label}-{policy}', 'handoff_zip', 'strict',
                {'scene': source, 'states': sorted(states), 'integer_policy': policy},
                {'entries': entries, 'zip_reference': digest_result(target.read_bytes())},
                note='text/bin entries strict by bytes; png entries strict by decoded L pixels; zip_reference informational',
            ))
    return cases
