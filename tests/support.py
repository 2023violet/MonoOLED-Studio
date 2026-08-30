from __future__ import annotations

from pathlib import Path

from scene import load_scene

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / 'src'
CURING_ROOT = REPO_ROOT / 'test_assets' / 'projects' / 'curing_lite'
CURING_PROJECT = CURING_ROOT / 'project.oled.json'
CURING_SCENE = CURING_ROOT / 'scenes' / 'main_scene.json'

def load_curing_scene():
    return load_scene(CURING_SCENE, project_root=CURING_ROOT)
