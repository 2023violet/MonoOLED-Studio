import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SIM = ROOT / 'OLED模拟器'
sys.path.insert(0, str(SIM))

from project_workspace import ProjectWorkspace
from scene import load_scene


def test_delivery_contains_openable_default_project_workspace():
    path = ROOT / 'CuringLite.project.oled.json'
    assert path.exists()
    project = ProjectWorkspace.load(path)
    assert project.name == 'Curing-Lite OLED'
    assert project.active_screen == 'main'
    assert len(project.screens) >= 1
    scene = load_scene(project.screen_path(project.active_screen), project_root=project.root)
    assert scene['canvas'] == {'w': 128, 'h': 32, 'preview_scale': 6}
    assert 'Curing_Lite光固化机产品 - UI设计初稿' in project.asset_dirs
