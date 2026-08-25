from pathlib import Path
import sys
from PIL import Image

SIM = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SIM))

from render import render_scene
from evidence import frame_evidence


def test_frame_evidence_can_relativize_assets_to_external_project(tmp_path):
    project = tmp_path / 'project'; project.mkdir()
    asset = project / 'assets' / 'icon.png'; asset.parent.mkdir()
    Image.new('1', (2, 2), 0).save(asset)
    scene = {
        '_root': str(project),
        'canvas': {'w': 16, 'h': 8},
        'storage': {'bytes_per_frame': 16, 'layout': 'VLSB', 'polarity': '1 = lit'},
        'states': {},
        'elements': [{'id': 'icon', 'type': 'image', 'asset': 'assets/icon.png', 'x': 0, 'y': 0, 'w': 2, 'h': 2}],
        'timeline': [],
    }
    result = render_scene(scene, {})
    ev = frame_evidence(result, {}, elapsed=0, project_root=project)
    assert ev['visible_elements'][0]['assets'] == ['assets/icon.png']
