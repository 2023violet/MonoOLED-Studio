from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

def text(name): return (ROOT/name).read_text(encoding='utf-8')


def test_gui_uses_preference_delta_and_editor_registry_not_legacy_pixel_windows():
    s=text('gui.py')
    assert 'PreferenceDelta' in s
    start=s.index('        def apply_preferences')
    end=s.index('        def open_preferences',start)
    body=s[start:end]
    assert 'editor_registry.apply_runtime_delta' in body
    assert '_pixel_windows' not in body
    assert 'refresh_all(' not in body


def test_studio_select_defers_commit_until_popup_is_hidden_and_uses_geometry_engine():
    s=text('ui_controls.py')
    assert 'PopupManager' in s
    assert 'place_popup' in s
    assert 'QTimer.singleShot(0' in s
    assert 'itemActivated.connect' in s
    # selection must close before the deferred index change is scheduled
    start=s.index('        def _item_clicked')
    end=s.index('        def toggle_popup',start)
    body=s[start:end]
    assert body.index('hidePopup(') < body.index('QTimer.singleShot')


def test_pixel_and_font_editors_have_runtime_delta_consumers():
    assert 'def apply_runtime_delta' in text('pixel_studio_qt.py')
    font=text('font_lab_qt.py')
    assert 'def apply_runtime_delta' in font
    assert 'def retranslate_ui' in font


def test_status_pill_no_longer_uses_legacy_light_color_mapping():
    s=text('qt_widgets.py')
    start=s.index('class StatusPill')
    body=s[start:]
    assert 'COLORS[' not in body
    assert 'get_theme(' in body


def test_v81_version_and_release_docs_present():
    s=text('gui.py')
    version=(ROOT/'VERSION').read_text(encoding='utf-8').strip()
    assert f"APP_VERSION = '{version}'" in s
    assert (ROOT/'INTERACTION_VISUAL_RELIABILITY_V81.md').exists()
    assert (ROOT/'TEST_MATRIX_V81.md').exists()


def test_font_lab_and_new_pixel_dialog_copy_no_longer_hardcodes_known_english_ui_strings():
    font=text('font_lab_qt.py')
    pixel=text('pixel_studio_qt.py')
    for phrase in ("'Browse Font…'","'Font Size'","'Resize font pack'","'Changing cell size regenerates glyphs. Continue?'"):
        assert phrase not in font
    for phrase in ("'Canvas Size'","'Insert Bitmap Text'","'Font Pack'","'Tracking'"):
        assert phrase not in pixel

def test_language_and_metric_refresh_paths_do_not_recompute_validation_or_retranslate_twice():
    gui=text('gui.py')
    block=gui[gui.index('        def retranslate_ui(self):'):gui.index('        def change_language(')]
    assert '_update_validation_panel()' not in block
    prefs=text('preferences_qt.py')
    apply=prefs[prefs.index('    def apply_runtime_settings('):prefs.index('    def _reset_all(')]
    assert '_retranslate()' not in apply

def test_v81_runtime_status_and_multiselect_measurement_are_translated():
    gui=text('gui.py')
    for phrase in ("QLabel('Preview —')","f'Preview {summary.latest_ms", "f'Full refresh: {summary.latest_ms", "selected · Bounds"):
        assert phrase not in gui
    assert "self.tr('performance.preview_live'" in gui
    assert "self.tr('measure.multi'" in gui
