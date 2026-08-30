from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / 'src'


def test_preview_capabilities_are_generic_and_timeline_optional():
    from preview_capabilities import preview_capabilities, timeline_metadata

    static = {'canvas': {'w': 128, 'h': 32}, 'states': {}, 'timeline': []}
    assert preview_capabilities(static) == ('frame', 'validation')

    stateful = {'canvas': {'w': 96, 'h': 16}, 'states': {'page': {'type': 'enum', 'values': ['A','B'], 'init': 'A'}}, 'timeline': []}
    # Renderer state is not automatically exposed as workbench UI. Generic
    # projects explicitly opt into interactive preview capabilities.
    assert preview_capabilities(stateful) == ('frame', 'validation')
    stateful['preview'] = {'capabilities': ['state']}
    assert preview_capabilities(stateful) == ('frame', 'state', 'validation')

    animated = {**stateful, 'timeline': [{'at': 2, 'set': {'page': 'B'}}], 'preview': {'capabilities': ['state', 'timeline']}}
    assert preview_capabilities(animated) == ('frame', 'state', 'timeline', 'validation')
    meta = timeline_metadata(animated)
    assert meta['step'] == 1
    assert meta['unit'] == 'step'
    assert meta['label'] == 'Step'


def test_core_preview_copy_is_not_runtime_or_curing_specific():
    source = (ROOT / 'i18n.py').read_text(encoding='utf-8')
    assert '"panel.preview": "预览"' in source
    assert '"panel.preview": "Preview"' in source
    assert '"action.step": "步进"' in source
    assert '"action.step": "Step"' in source
    assert '"panel.runtime": "运行状态"' not in source
    assert '"panel.runtime": "Runtime"' not in source


def test_gui_uses_preview_capabilities_and_unit_neutral_step():
    source = (ROOT / 'gui.py').read_text(encoding='utf-8')
    assert 'from preview_capabilities import preview_capabilities, timeline_metadata' in source
    assert "self.preview_capabilities=preview_capabilities(self.scene)" in source.replace(' ', '')
    assert "self.inspector_tabs.addTab(self.state_page,'')" in source
    assert "t('panel.preview')" in source
    assert "session.step(self._timeline_meta['step'])" in source
    assert 'Step +1s' not in source


def test_preferences_view_is_reusable_and_settings_open_as_editor_tab():
    prefs = (ROOT / 'preferences_qt.py').read_text(encoding='utf-8')
    gui = (ROOT / 'gui.py').read_text(encoding='utf-8')
    assert 'class PreferencesView(QWidget):' in prefs
    assert 'class PreferencesWindow(QMainWindow):' in prefs
    assert 'PreferencesView' in gui
    assert "document_id='settings:preferences'" in gui
    assert 'self.editor_tabs.addTab' in gui
    open_region = gui[gui.index('def open_preferences'):gui.index('def _clear_asset_cache')]
    assert 'PreferencesWindow(' not in open_region
    assert 'PreferencesView(' in open_region


def test_settings_editor_tab_is_closable_but_designer_remains_pinned():
    source = (ROOT / 'gui.py').read_text(encoding='utf-8')
    assert 'ifindex<=0:return' in source.replace(' ', '')
    assert "settings:preferences" in source


def test_preview_panel_contains_frame_summary_and_capability_sections():
    source = (ROOT / 'gui.py').read_text(encoding='utf-8')
    for token in ('preview_frame_label', 'preview_state_section', 'preview_timeline_section', 'preview_validation_section'):
        assert token in source


def test_real_qt_v11_gate_covers_generic_preview_and_settings_tab():
    gate = ROOT.parent / 'tools' / 'VERIFY_V11_GENERIC_WORKBENCH.py'
    assert gate.is_file()
    source = gate.read_text(encoding='utf-8')
    for marker in (
        'STATIC_SCENE', 'STATE_SCENE', 'TIMELINE_SCENE', 'SETTINGS_EDITOR_TAB',
        'PreferencesView', "'timeline' not in", "'timeline' in", 'Step',
    ):
        assert marker in source


def test_windows_builder_runs_v11_gate():
    build = (ROOT.parent / 'tools' / 'BUILD_WINDOWS_GA.bat').read_text(encoding='utf-8')
    assert 'VERIFY_V11_GENERIC_WORKBENCH.py' in build


def test_runtime_step_api_is_unit_neutral_in_core_copy():
    editor = (ROOT / 'editor_model.py').read_text(encoding='utf-8')
    runtime = (ROOT / 'runtime.py').read_text(encoding='utf-8')
    assert 'def step(self, amount: int = 1)' in editor
    assert 'def step(self, amount: int = 1)' in runtime
    step_region = runtime[runtime.index('    def step('):]
    assert 'seconds' not in step_region
    assert 'preceding timeline step' in step_region
    assert '5..305' not in step_region
