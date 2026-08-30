from __future__ import annotations
from support import load_curing_scene

from copy import deepcopy
import json
from pathlib import Path
import sys

import pytest
from PIL import Image

SIM = Path(__file__).resolve().parents[1] / 'src'
sys.path.insert(0, str(SIM))

from asset_library import AssetLibrary
from autosave import AutoSaveManager
from exporter import export_scene
from pixel_studio import PixelDocument
from responsive_layout import plan_layout, header_policy
from scene import init_state, load_scene


def test_export_spec_uses_project_or_product_name_not_curing_lite(tmp_path):
    scene = load_curing_scene()
    scene = deepcopy(scene)
    scene['product'] = 'Ortho-Pro 256'
    state = init_state(scene)
    export_scene(scene, tmp_path, {'preview': state})
    spec = (tmp_path / 'UI_SPEC.md').read_text(encoding='utf-8')
    assert spec.startswith('# Ortho-Pro 256 OLED UI Specification')
    assert '# Curing-Lite OLED UI Specification' not in spec


def test_compact_header_policy_hides_low_priority_actions():
    compact = header_policy(plan_layout(960, 680))
    assert compact.compact is True
    assert compact.show_subtitle is False
    assert compact.show_status is False
    assert compact.show_project is False
    assert compact.show_validate is False
    assert compact.show_save is True
    assert compact.show_handoff is True

    wide = header_policy(plan_layout(1600, 1000))
    assert wide.compact is False
    assert wide.show_subtitle is True
    assert wide.show_status is True
    assert wide.show_project is True
    assert wide.show_validate is True


def test_asset_library_reuses_cached_decode_for_unchanged_files(tmp_path, monkeypatch):
    assets = tmp_path / 'assets'; assets.mkdir()
    Image.new('1', (8, 8), 255).save(assets / 'a.png')
    import asset_library as module
    real = module.load_bitmap
    calls = {'count': 0}

    def counted(path):
        calls['count'] += 1
        return real(path)

    monkeypatch.setattr(module, 'load_bitmap', counted)
    library = AssetLibrary(tmp_path, ('assets',))
    first = library.scan()
    second = library.scan()
    assert len(first) == len(second) == 1
    assert calls['count'] == 1

    Image.new('1', (8, 8), 0).save(assets / 'a.png')
    library.scan()
    assert calls['count'] == 2


def test_autosave_strict_recovery_only_when_snapshot_is_newer(tmp_path):
    scene_path = tmp_path / 'scene.json'
    scene_path.write_text('{}', encoding='utf-8')
    scene = {'_path': str(scene_path), '_root': str(tmp_path), 'canvas': {'w': 128, 'h': 32}, 'states': {}, 'elements': [], 'timeline': []}
    manager = AutoSaveManager(scene)
    snap = manager.snapshot(reason='edit')
    assert manager.recovery_candidate() == snap
    # Simulate an explicit save after the autosave.
    import os, time
    time.sleep(0.003)
    scene_path.write_text('{"saved":true}', encoding='utf-8')
    os.utime(scene_path, None)
    assert manager.recovery_candidate() is None


def test_pixel_document_undo_restores_dimensions_after_rotate():
    doc = PixelDocument(8, 16)
    doc.pencil(1, 2)
    doc.rotate90()
    assert (doc.width, doc.height) == (16, 8)
    assert doc.undo() is True
    assert (doc.width, doc.height) == (8, 16)
    assert doc.get(1, 2) == 1


def test_pixel_document_limits_undo_history():
    doc = PixelDocument(8, 8, max_undo=5)
    for x in range(7):
        doc.pencil(x, 0)
    undo_count = 0
    while doc.undo():
        undo_count += 1
    assert undo_count == 5


def test_release_dev_requirements_include_real_qt_gui_test_stack():
    dev = (SIM.parent / 'requirements-dev.txt').read_text(encoding='utf-8')
    assert 'pytest-qt==4.5.0' in dev


def test_windows_workflow_has_dpi_and_real_gui_test_matrix():
    workflow = (SIM.parent / '.github' / 'workflows' / 'release-windows.yml').read_text(encoding='utf-8')
    assert 'QT_SCALE_FACTOR' in workflow
    for scale in ('1.0', '1.25', '1.5', '2.0'):
        assert scale in workflow
    assert 'test_qt_real_interactions_v51.py' in workflow

def test_asset_library_persistent_cache_survives_new_session(tmp_path, monkeypatch):
    assets = tmp_path / 'assets'; assets.mkdir()
    Image.new('1', (8, 8), 255).save(assets / 'a.png')
    first = AssetLibrary(tmp_path, ('assets',))
    first.scan()
    cache_file = tmp_path / '.oled' / 'asset_cache_v1.json'
    assert cache_file.exists()

    import asset_library as module
    real = module.load_bitmap
    calls = {'count': 0}
    def counted(path):
        calls['count'] += 1
        return real(path)
    monkeypatch.setattr(module, 'load_bitmap', counted)
    second = AssetLibrary(tmp_path, ('assets',))
    assert len(second.scan()) == 1
    assert calls['count'] == 0


def test_v51_release_version_and_manifest_are_consistent():
    version=(SIM / 'VERSION').read_text(encoding='utf-8').strip()
    manifest = json.loads((SIM.parent / 'DELIVERY_MANIFEST.json').read_text(encoding='utf-8'))
    assert manifest['version'] == version
    assert tuple(map(int,version.split('.'))) >= (5,1,0)


def test_windows_builder_has_soak_gate():
    script = (SIM.parent / 'tools' / 'BUILD_WINDOWS_GA.bat').read_text(encoding='utf-8')
    assert '--soak-smoke' in script
    workflow = (SIM.parent / '.github' / 'workflows' / 'release-windows.yml').read_text(encoding='utf-8')
    assert '--soak-smoke' in workflow

def test_editor_session_limits_history_growth():
    from editor_model import EditorSession
    scene = load_curing_scene()
    session = EditorSession(scene, max_history=7)
    target = next(e['id'] for e in scene['elements'] if e.get('x') is not None and e.get('type') != 'text')
    for i in range(10):
        session.move(target, dx=1)
        session.end_coalesced_edit()
    count = 0
    while session.undo(): count += 1
    assert count == 7
