from __future__ import annotations

from pathlib import Path

import pytest

from font_pack import FontPack, create_font_pack, rasterize_characters

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / 'src'
TOOLS = ROOT / 'tools'


def _text(path: Path) -> str:
    return path.read_text(encoding='utf-8')


def _function_body(source: str, name: str) -> str:
    marker = f'def {name}('
    start = source.index(marker)
    tail = source[start:]
    next_def = tail.find('\ndef ', len(marker))
    return tail if next_def < 0 else tail[:next_def]


def test_startup_theme_palette_covers_status_tokens_and_uses_qt6_qss_names():
    source = _text(SRC / 'qt_theme.py')
    assert "'status.success': QPalette" in source
    assert "'status.warning': QPalette" in source
    assert "'status.success': '" in source
    assert "'status.warning': '" in source
    assert "'tool-tip-base'" not in source
    assert "'tool-tip-text'" not in source
    assert "'tooltip-base'" in source
    assert "'tooltip-text'" in source


def test_editor_chrome_is_safe_before_actions_are_constructed():
    source = _text(SRC / 'gui.py')
    body = source.split('        def _sync_editor_chrome(self):', 1)[1].split('\n        def ', 1)[0]
    assert "self._actions['undo']" not in body
    assert "self._actions['redo']" not in body
    assert 'self._editor_sync_chrome()' in body


def test_startup_smoke_follows_real_preferences_theme_resolution_path():
    source = _text(SRC / 'gui.py')
    body = _function_body(source, 'run_startup_smoke')
    assert 'PreferencesStore.load()' in body
    assert 'RuntimeSettings.from_preferences' in body
    assert 'resolve_theme_name(' in body
    assert "_apply_application_theme(app,'monooled-light','comfortable',1.0)" not in body


def test_embedded_settings_can_shrink_and_native_controls_are_bounded():
    source = _text(SRC / 'preferences_qt.py')
    assert 'content_breakpoint = 700' in source
    assert 'self.setMinimumSize(0, 0)' in source
    assert 'QComboBox' in source and 'QSpinBox' in source
    bounded_line = next(line for line in source.splitlines() if 'bounded = isinstance(self.control' in line)
    assert 'QComboBox' in bounded_line
    assert 'QSpinBox' in bounded_line
    assert 'label.setWordWrap(True)' in source
    assert 'self.nav.setFixedWidth' not in source
    assert 'self.nav.setMinimumWidth' in source


def test_settings_violation_gate_detects_wrapped_text_clipping():
    source = _text(SRC / 'preferences_qt.py')
    body = source.split('    def layout_violations(self) -> list[str]:', 1)[1].split('\n\n\nclass PreferencesWindow', 1)[0]
    assert 'setting_label_vertical_clipping' in body
    assert 'setting_help_vertical_clipping' in body


def test_font_lab_existing_pack_open_does_not_rewrite_pack_and_generation_is_async():
    source = _text(SRC / 'font_lab_qt.py')
    init_body = source.split('    def __init__', 1)[1].split('\n    @property', 1)[0]
    assert 'manifest_exists' in init_body
    assert 'if not manifest_exists:' in init_body
    assert 'class _FontGenerateWorker' in source
    assert 'QThread' in source
    assert 'self._generation_thread' in source
    generate_body = source.split('    def generate(self):', 1)[1].split('\n    def save(self):', 1)[0]
    assert 'rasterize_characters(' not in generate_body
    assert 'QMessageBox.information' not in generate_body
    assert 'font.generate.progress' in source


def test_font_lab_generation_lifecycle_has_close_guard_and_busy_until_thread_finish():
    source = _text(SRC / 'font_lab_qt.py')
    assert 'def closeEvent(self,event)' in source
    assert 'def _generation_finished' in source
    assert 'def _set_generation_busy' in source
    assert 'self._generation_thread.isRunning()' in source
    finished_body = source.split('    def _generation_finished', 1)[1].split('\n    def ', 1)[0]
    assert '_set_generation_busy(False)' in finished_body



def test_main_window_refuses_to_destroy_font_editor_while_generation_is_running():
    source = _text(SRC / 'gui.py')
    close_tab = source.split('        def _close_editor_tab(self,index):', 1)[1].split('\n        def ', 1)[0]
    confirm = source.split('        def _confirm_open_editor_changes(self):', 1)[1].split('\n        def ', 1)[0]
    assert 'can_close' in close_tab
    assert 'can_close' in confirm

def _ink_bounds(pack: FontPack, ch: str) -> tuple[int, int]:
    rows = pack.glyph(ch).pixels
    ys = [y for y, row in enumerate(rows) if any(row)]
    assert ys
    return min(ys), max(ys)


def test_font_rasterizer_uses_pack_baseline_instead_of_independent_vertical_centering(tmp_path):
    upper = create_font_pack(tmp_path / 'upper', 'Upper', cell=(18, 24), baseline=12, advance=18)
    lower = create_font_pack(tmp_path / 'lower', 'Lower', cell=(18, 24), baseline=17, advance=18)
    rasterize_characters(upper, 'Ag', font_size=12)
    rasterize_characters(lower, 'Ag', font_size=12)
    for ch in 'Ag':
        upper_min, upper_max = _ink_bounds(upper, ch)
        lower_min, lower_max = _ink_bounds(lower, ch)
        assert lower_min - upper_min == 5
        assert lower_max - upper_max == 5



def test_font_rasterizer_reports_monotonic_progress(tmp_path):
    pack = create_font_pack(tmp_path / 'progress', 'Progress', cell=(12, 16), baseline=12, advance=12)
    updates=[]
    rasterize_characters(pack, 'AB01', font_size=10, progress=lambda done,total: updates.append((done,total)))
    assert updates == [(1,4),(2,4),(3,4),(4,4)]


def test_recommended_font_size_scales_to_small_oled_cells():
    source = _text(SRC / 'font_pack.py')
    assert 'def recommended_font_size' in source
    from font_pack import recommended_font_size
    assert 4 <= recommended_font_size((5, 8)) <= 8
    assert recommended_font_size((8, 16)) <= 16

def test_font_pack_io_and_rasterizer_emit_no_pillow_deprecation_warnings(tmp_path):
    import warnings

    pack = create_font_pack(tmp_path / 'warnings', 'Warnings', cell=(12, 16), baseline=12, advance=12)
    with warnings.catch_warnings():
        warnings.simplefilter('error', DeprecationWarning)
        rasterize_characters(pack, 'Ag01', font_size=10)
        reopened = FontPack.load(pack.root)
    assert set(reopened.characters()) == set('Ag01')


def test_font_pack_bulk_io_roundtrip_preserves_exact_pixels(tmp_path):
    pack = create_font_pack(tmp_path / 'bulk', 'Bulk', cell=(16, 16), baseline=12, advance=16)
    pixels = [[1 if (x * 3 + y * 5) % 7 == 0 else 0 for x in range(16)] for y in range(16)]
    for i in range(64):
        pack.set_glyph(chr(0x400 + i), pixels)
    pack.save()
    reopened = FontPack.load(pack.root)
    assert reopened.characters() == pack.characters()
    for ch in reopened.characters():
        assert reopened.glyph(ch).pixels == pixels


def test_windows_ga_runs_font_smoke_from_source_exe_and_final_package():
    gui = _text(SRC / 'gui.py')
    runner = _text(TOOLS / 'RUN_WINDOWS_TEST_GROUPS.py')
    ga = _text(TOOLS / 'BUILD_WINDOWS_GA.bat')
    assert "--font-smoke" in gui
    assert "('font', ['--font-smoke'])" in runner
    assert ga.count('--font-smoke') >= 3
    assert 'test_qt_v1240_windows_critical_paths.py' in '\n'.join(p.name for p in (ROOT / 'tests').glob('test_qt_*.py'))


def test_release_1240_identity_is_single_source_of_truth():
    version = _text(SRC / 'VERSION').strip()
    assert version == (SRC / 'VERSION').read_text(encoding='utf-8').strip()
    assert (SRC / 'version_info.py').exists()
    gui = _text(SRC / 'gui.py')
    prefs = _text(SRC / 'preferences_qt.py')
    ga = _text(TOOLS / 'BUILD_WINDOWS_GA.bat')
    quick = _text(TOOLS / 'BUILD_WINDOWS_QUICK.bat')
    wrapper = _text(TOOLS / 'BUILD_WINDOWS_EXE.bat')
    verifier = _text(ROOT / 'VERIFY_PACKAGE.py')
    delivery_readme = _text(ROOT / 'DELIVERY_README.md')
    import json
    manifest = json.loads(_text(ROOT / 'DELIVERY_MANIFEST.json'))
    assert 'font' in manifest['windows']['post_zip_exe_gate'].split('+')
    assert '12.3.9' not in delivery_readme
    assert version in delivery_readme
    assert "V12_VERSION='12.3.9'" not in verifier
    assert "ROOT/'src/VERSION'" in verifier or "ROOT / 'src' / 'VERSION'" in verifier
    assert "manifest['version']" in verifier or "manifest.get('version')" in verifier
    assert 'load_version' in gui and "APP_VERSION = '12.3.9'" not in gui
    assert 'load_version' in prefs and "v12.3.9" not in prefs
    for builder in (ga, quick, wrapper):
        assert 'src\\VERSION' in builder
        assert 'V12.3.9' not in builder
