import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SIM = ROOT / 'src'
sys.path.insert(0, str(SIM))

from project_workspace import ProjectWorkspace
from scene import load_scene


def test_delivery_contains_openable_curing_regression_fixture():
    path = ROOT / 'test_assets/projects/curing_lite/project.oled.json'
    assert path.exists()
    project = ProjectWorkspace.load(path)
    assert project.name == 'Curing-Lite OLED'
    assert any(screen.id == project.active_screen for screen in project.screens)
    assert len(project.screens) >= 1
    scene = load_scene(project.screen_path(project.active_screen), project_root=project.root)
    assert scene['canvas'] == {'w': 128, 'h': 32, 'preview_scale': 6}
    assert project.asset_dirs == ('assets',)
