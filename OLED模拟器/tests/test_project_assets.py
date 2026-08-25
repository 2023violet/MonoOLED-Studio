from pathlib import Path
import sys

from PIL import Image

SIM = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SIM))

from editor_model import EditorSession


def _scene(project_root: Path):
    scene_path = project_root / 'scene.json'
    scene = {
        '_path': str(scene_path),
        '_root': str(project_root),
        'canvas': {'w': 128, 'h': 32},
        'storage': {'layout': 'VLSB', 'polarity': '1 = lit', 'bytes_per_frame': 512},
        'states': {},
        'elements': [{'id': 'draft', 'type': 'placeholder', 'x': 1, 'y': 2, 'w': 3, 'h': 4}],
        'timeline': [],
    }
    return scene


def test_assign_external_bitmap_imports_portable_copy_into_project(tmp_path):
    project = tmp_path / 'project'
    project.mkdir()
    external = tmp_path / 'new_assets' / 'icon.png'
    external.parent.mkdir()
    image = Image.new('1', (5, 7), 0)
    image.putpixel((2, 3), 1)
    image.save(external)

    session = EditorSession(_scene(project))
    session.assign_bitmap('draft', external)

    element = session.document.element('draft')
    assert element['asset'].startswith('assets/imported/')
    imported = project / element['asset']
    assert imported.exists()
    assert imported.read_bytes() == external.read_bytes()
    assert (element['w'], element['h']) == (5, 7)


def test_assign_bitmap_already_inside_project_keeps_relative_path(tmp_path):
    project = tmp_path / 'project'
    asset = project / 'custom' / 'icons' / 'fresh.png'
    asset.parent.mkdir(parents=True)
    Image.new('1', (4, 4), 0).save(asset)
    session = EditorSession(_scene(project))
    session.assign_bitmap('draft', asset)
    assert session.document.element('draft')['asset'] == 'custom/icons/fresh.png'
