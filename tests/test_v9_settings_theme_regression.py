from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / 'src'
GUI = (ROOT / 'gui.py').read_text(encoding='utf-8')


def _function_body(source: str, name: str) -> str:
    marker = f'def {name}('
    start = source.index(marker)
    tail = source[start:]
    lines = tail.splitlines()
    indent = len(lines[0]) - len(lines[0].lstrip())
    body = [lines[0]]
    for line in lines[1:]:
        if line.strip() and (len(line) - len(line.lstrip())) <= indent:
            break
        body.append(line)
    return '\n'.join(body)


def test_preferences_open_as_owned_editor_tab_not_floating_window() -> None:
    body = _function_body(GUI, 'open_preferences')
    assert "doc_id='settings:preferences'" in body
    assert 'PreferencesView(self.preferences,self.tr,parent=self.editor_tabs)' in body
    assert 'self.editor_tabs.addTab' in body
    assert 'PreferencesWindow(self.preferences,self.tr,parent=self)' not in body


def test_main_close_flushes_embedded_preferences_view() -> None:
    body = _function_body(GUI, 'closeEvent')
    assert 'if self._preferences_view is not None' in body
    assert 'self._preferences_view.flush_pending_save()' in body
    assert body.index('self._preferences_view.flush_pending_save()') > body.index('QMessageBox.Cancel')


def test_theme_refresh_signature_includes_theme_and_forces_qss_reparse() -> None:
    body = _function_body(GUI, '_apply_application_theme')
    assert "signature = f'{theme}:{density}:{ui_scale}'" in body
    assert "app.setStyleSheet('')" not in body
    assert 'app.setStyleSheet(build_adaptive_stylesheet(density, ui_scale=ui_scale))' in body
    assert body.count('app.setStyleSheet(build_adaptive_stylesheet') == 1


def test_preferences_removes_inert_color_theme_control() -> None:
    prefs = (ROOT / 'preferences_qt.py').read_text(encoding='utf-8')
    assert 'self.theme = QComboBox()' not in prefs
    assert 'appearance.palette_hint_light' not in prefs
    assert "for data in ('system','light','dark')" in prefs
