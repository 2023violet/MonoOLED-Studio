from __future__ import annotations

import json
import os
from pathlib import Path
import sys

import pytest
from PIL import Image

SIM = Path(__file__).resolve().parents[1] / 'src'
sys.path.insert(0, str(SIM))


def test_preferences_semantic_corruption_is_normalized_without_losing_future_keys(tmp_path):
    from preferences import PreferencesStore
    p = tmp_path / 'prefs.json'
    p.write_text(json.dumps({
        'schema_version': 'future',
        'language': ['bad'],
        'appearance': {'theme_mode': [], 'color_theme': 'nope', 'density': 99, 'ui_scale': {'x': 1}, 'future': 7},
        'input': {'wheel_action': {}, 'middle_drag': 123, 'space_drag': None},
        'autosave': {'interval_minutes': 'abc', 'snapshots': -99, 'prompt_recovery': 'yes'},
        'performance': {'undo_history': 0, 'asset_cache_mb': 'huge', 'overlay': 'yes'},
        'future_section': {'keep_me': True},
    }), encoding='utf-8')
    store = PreferencesStore.load(p)
    assert store.get('language') == 'zh_CN'
    assert store.get('appearance.theme_mode') == 'system'
    assert store.get('appearance.color_theme') == 'monooled-light'
    assert store.get('appearance.density') == 'comfortable'
    assert store.get('appearance.ui_scale') == 'auto'
    assert store.get('autosave.interval_minutes') == 3
    assert store.get('autosave.snapshots') == 10
    assert store.get('autosave.prompt_recovery') is True
    assert store.get('performance.undo_history') == 200
    assert store.get('appearance.future') == 7
    assert store.get('future_section.keep_me') is True


def test_project_rejects_screen_path_escape_and_unsafe_ids(tmp_path):
    from project_workspace import ProjectWorkspace, create_project
    project = create_project(tmp_path / 'p', name='P')
    with pytest.raises(ValueError):
        project.add_screen('../../escape')
    payload = json.loads(project.path.read_text(encoding='utf-8'))
    payload['screens'][0]['path'] = '../outside.json'
    project.path.write_text(json.dumps(payload), encoding='utf-8')
    with pytest.raises(ValueError):
        ProjectWorkspace.load(project.path)


def test_project_rejects_external_asset_dirs(tmp_path):
    from project_workspace import ProjectWorkspace, create_project
    project = create_project(tmp_path / 'p', name='P')
    payload = json.loads(project.path.read_text(encoding='utf-8'))
    payload['asset_dirs'] = ['../external-assets']
    project.path.write_text(json.dumps(payload), encoding='utf-8')
    with pytest.raises(ValueError):
        ProjectWorkspace.load(project.path)


def _write_bitmap(path: Path, white_at: tuple[int, int]):
    path.parent.mkdir(parents=True, exist_ok=True)
    image = Image.new('1', (8, 8), 0)
    image.putpixel(white_at, 255)
    image.save(path)


def test_asset_cache_detects_same_size_same_mtime_content_change(tmp_path):
    from asset_library import AssetLibrary
    root = tmp_path / 'p'; root.mkdir()
    f = root / 'assets' / 'x.bmp'
    _write_bitmap(f, (1, 1))
    stat = f.stat()
    lib = AssetLibrary(root, ['assets'])
    first = lib.scan()[0].sha256
    _write_bitmap(f, (2, 2))
    assert f.stat().st_size == stat.st_size
    os.utime(f, ns=(stat.st_atime_ns, stat.st_mtime_ns))
    second = AssetLibrary(root, ['assets']).scan()[0].sha256
    assert second != first


def test_asset_library_rejects_external_roots_and_import_targets(tmp_path):
    from asset_library import AssetLibrary
    root = tmp_path / 'p'; root.mkdir()
    outside = tmp_path / 'outside'; outside.mkdir()
    with pytest.raises(ValueError):
        AssetLibrary(root, ['../outside']).scan()
    source = tmp_path / 'source.bmp'; _write_bitmap(source, (1, 1))
    lib = AssetLibrary(root, ['assets'])
    with pytest.raises(ValueError):
        lib.import_asset(source, target_dir='../outside')


def _scene(tmp_path: Path):
    scene_path = tmp_path / 'scene.json'
    scene_path.write_text('{}', encoding='utf-8')
    return {
        '_path': str(scene_path), '_root': str(tmp_path),
        'canvas': {'w': 128, 'h': 32}, 'states': {}, 'elements': [], 'timeline': [],
    }


def test_autosave_is_atomic_and_skips_corrupt_newest(tmp_path):
    from autosave import AutoSaveManager
    scene = _scene(tmp_path)
    manager = AutoSaveManager(scene, keep=5)
    good = manager.snapshot(reason='good')
    bad = manager.directory / '99999999T999999_999999Z.autosave.json'
    bad.write_text('{broken', encoding='utf-8')
    assert manager.latest_recovery() == good
    assert not list(manager.directory.glob('*.tmp'))
    assert any(p.name.startswith(bad.name) for p in (manager.directory / 'quarantine').glob('*'))


def test_pixel_image_import_has_preallocation_guard(tmp_path):
    from pixel_studio import PixelDocument
    p = tmp_path / 'big.png'
    Image.new('1', (101, 101), 0).save(p)
    with pytest.raises(ValueError, match='too large'):
        PixelDocument.from_image(p, max_pixels=10_000)


def test_c_symbols_are_strict_ascii_identifiers():
    from c_export import _ident
    from pixel_studio import PixelDocument
    assert _ident('中文 123') == '_123'
    text = PixelDocument(8, 8).to_c_header('中文 123')
    assert 'static const unsigned char bitmap_123[]' in text
    assert all(ord(ch) < 128 for ch in text)


def test_command_registry_can_apply_preference_bindings_atomically():
    from commands import CommandRegistry, ShortcutConflictError
    r = CommandRegistry(); r.register('project.save', shortcut='Ctrl+S'); r.register('designer.undo', shortcut='Ctrl+Z')
    r.apply_bindings({'project.save': 'Ctrl+Shift+S', 'designer.undo': 'Ctrl+Alt+Z'})
    assert r.shortcut('project.save') == 'Ctrl+Shift+S'
    assert r.shortcut('designer.undo') == 'Ctrl+Alt+Z'
    before = r.bindings()
    with pytest.raises(ShortcutConflictError):
        r.apply_bindings({'project.save': 'Ctrl+X', 'designer.undo': 'ctrl+x'})
    assert r.bindings() == before


def _flatten(data, prefix=''):
    out = []
    for key, value in data.items():
        dotted = f'{prefix}.{key}' if prefix else key
        if isinstance(value, dict):
            out.extend(_flatten(value, dotted))
        else:
            out.append(dotted)
    return out


def test_every_default_preference_has_named_runtime_effect():
    from preferences import default_preferences
    from runtime_settings import EXPOSED_RUNTIME_KEYS, RUNTIME_EFFECTS
    expected = set(_flatten(default_preferences())) - {'schema_version'}
    assert expected == set(EXPOSED_RUNTIME_KEYS) == set(RUNTIME_EFFECTS)
    assert all(str(v).strip() for v in RUNTIME_EFFECTS.values())


def test_runtime_settings_materialize_all_interaction_and_recovery_controls():
    from preferences import default_preferences
    from runtime_settings import RuntimeSettings
    p = default_preferences()
    p['appearance']['ui_scale'] = '125%'
    p['input']['wheel_action'] = 'none'; p['input']['middle_drag'] = 'none'; p['input']['space_drag'] = 'none'
    p['pixel_studio']['brush_size'] = 4
    p['autosave']['prompt_recovery'] = False; p['autosave']['snapshots'] = 17
    p['performance']['drag_preview'] = 'exact'; p['performance']['validation_mode'] = 'continuous'; p['performance']['overlay'] = True
    r = RuntimeSettings.from_preferences(p)
    assert r.ui_scale == 1.25
    assert (r.wheel_action, r.middle_pan, r.space_pan) == ('none', False, False)
    assert r.brush_size == 4 and r.prompt_recovery is False and r.autosave_snapshots == 17
    assert r.drag_preview == 'exact' and r.validation_mode == 'continuous' and r.performance_overlay is True


def _luminance(hex_color: str) -> float:
    raw = hex_color.lstrip('#')
    values = [int(raw[i:i+2], 16) / 255.0 for i in (0, 2, 4)]
    linear = [v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4 for v in values]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def _contrast(a: str, b: str) -> float:
    hi, lo = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def test_all_themes_have_readable_primary_and_muted_token_pairs():
    from theme_system import THEME_NAMES, get_theme
    for name in THEME_NAMES:
        t = get_theme(name)
        assert _contrast(t['accent.on_primary'], t['accent.primary']) >= 4.5
        assert _contrast(t['text.muted'], t['surface.panel']) >= 4.5


def test_theme_mode_and_ui_scale_have_real_resolution_policy():
    import pytest
    pytest.importorskip('PySide6')
    from theme_system import resolve_theme_name
    from qt_theme import build_stylesheet
    assert resolve_theme_name('monooled-light', 'dark', system_dark=False) == 'monooled-dark'
    assert resolve_theme_name('monooled-dark', 'light', system_dark=True) == 'monooled-light'
    assert resolve_theme_name('monooled-light', 'system', system_dark=True) == 'monooled-dark'
    normal = build_stylesheet('monooled-light', 'comfortable', ui_scale=1.0)
    scaled = build_stylesheet('monooled-light', 'comfortable', ui_scale=1.25)
    assert 'min-height: 32px' in normal
    assert 'min-height: 40px' in scaled


def test_pixel_brush_size_applies_continuous_single_undo_stroke():
    from pixel_studio import PixelDocument
    d = PixelDocument(16, 8, max_undo=10)
    before = [row[:] for row in d.pixels]
    d.begin_gesture(); d.brush_segment(2, 3, 8, 3, value=1, size=3); d.end_gesture()
    assert all(d.get(x, 3) == 1 for x in range(2, 9))
    assert d.get(4, 2) == 1 and d.get(4, 4) == 1
    assert len(d._undo) == 1
    assert d.undo() and d.pixels == before

def test_preferences_qt_exposes_real_maintenance_shortcuts_and_brush_controls():
    source=(SIM/'preferences_qt.py').read_text(encoding='utf-8')
    assert 'clearAssetCacheRequested = Signal()' in source
    assert 'resetWorkspaceRequested = Signal()' in source
    assert 'self.shortcut_edits' in source
    assert 'self.brush_size' in source
    assert "startup.reopen_last_project" in source
    version=(SIM/'VERSION').read_text(encoding='utf-8').strip()
    assert 'Version {APP_VERSION}' in source
    assert 'self.shortcuts_text = QLabel' not in source

def test_pixel_qt_import_surfaces_invalid_or_unreadable_image_as_user_error_instead_of_crashing():
    source=(SIM/'pixel_studio_qt.py').read_text(encoding='utf-8')
    body=source[source.index('    def open_image(self):'):source.index('    def save_png(self):')]
    assert 'except (OSError, ValueError) as exc' in body
    assert 'QMessageBox.warning' in body
