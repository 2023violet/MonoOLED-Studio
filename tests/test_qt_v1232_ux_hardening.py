import os
from pathlib import Path

import pytest
pytest.importorskip('PySide6')
pytest.importorskip('pytestqt')

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / 'src'
import sys
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from i18n import Translator
from preferences import PreferencesStore
from preferences_qt import PreferencesView
from ui_controls import StudioSelect


def test_settings_search_reveals_offscreen_matching_row_and_escape_clears(qtbot, tmp_path):
    view = PreferencesView(PreferencesStore.load(tmp_path / 'prefs.json'), Translator('en_US'))
    qtbot.addWidget(view); view.resize(760, 520); view.show(); QApplication.processEvents()
    view.search.setText('reset all preferences'); QApplication.processEvents(); qtbot.wait(10)
    assert view.nav.currentRow() == view.SECTIONS.index('advanced')
    current = view.stack.currentWidget()
    target = next(row for section,row,label,help in view._search_rows if section == 'advanced' and label is not None and 'Reset all preferences' in label.text())
    top = target.mapTo(current.viewport(), target.rect().topLeft()).y()
    bottom = target.mapTo(current.viewport(), target.rect().bottomLeft()).y()
    assert bottom >= 0 and top < current.viewport().height()
    QTest.keyClick(view.search, Qt.Key_Escape); QApplication.processEvents()
    assert view.search.text() == ''


def test_studio_select_keyboard_down_opens_escape_closes(qtbot):
    combo = StudioSelect(); combo.addItems(['System', 'Light', 'Dark']); qtbot.addWidget(combo); combo.show(); combo.button.setFocus()
    QTest.keyClick(combo.button, Qt.Key_Down); qtbot.wait(5)
    assert combo.popup.isVisible()
    QTest.keyClick(combo.list, Qt.Key_Escape); qtbot.wait(5)
    assert not combo.popup.isVisible()


def test_setting_control_accessibility_tracks_language(qtbot, tmp_path):
    view = PreferencesView(PreferencesStore.load(tmp_path / 'prefs.json'), Translator('en_US'))
    qtbot.addWidget(view); view.show(); QApplication.processEvents()
    assert view.theme_mode.accessibleName() == 'Appearance mode'
    assert view.theme_mode.accessibleDescription()
    view.set_language('zh_CN'); QApplication.processEvents()
    assert view.theme_mode.accessibleName() == '外观模式'


def test_save_failure_is_visible_and_next_success_recovers(qtbot, tmp_path, monkeypatch):
    store = PreferencesStore.load(tmp_path / 'prefs.json')
    view = PreferencesView(store, Translator('en_US')); qtbot.addWidget(view); view.show()
    real_save = store.save
    monkeypatch.setattr(store, 'save', lambda: (_ for _ in ()).throw(OSError('read only')))
    assert view._save_now() is False
    assert view.save_status.isVisible() and view.save_status.property('saveState') == 'failed'
    monkeypatch.setattr(store, 'save', real_save)
    assert view._save_now() is True
    assert view.save_status.property('saveState') == 'saved'


def test_settings_search_is_bilingual_and_jumps_to_specific_row(qtbot, tmp_path):
    view = PreferencesView(PreferencesStore.load(tmp_path / 'prefs.json'), Translator('zh_CN'))
    qtbot.addWidget(view); view.resize(900, 620); view.show(); QApplication.processEvents()
    view.search.setText('Interface scale'); QApplication.processEvents(); qtbot.wait(10)
    assert view.nav.currentRow() == view.SECTIONS.index('appearance')
    assert view._search_match is not None
    assert '界面缩放' in view._search_match.text()


def test_settings_toggle_returns_to_same_document_after_tab_indices_shift(qtbot, tmp_path, monkeypatch):
    monkeypatch.setenv('MONOOLED_CONFIG_DIR', str(tmp_path / 'cfg'))
    from gui import OLEDDesignerWindow
    from PySide6.QtWidgets import QWidget
    window = OLEDDesignerWindow('main_scene', 'en_US'); qtbot.addWidget(window); window.show(); qtbot.wait(10)
    dummy = QWidget(); dummy.document_id = 'test:work-editor'; idx = window.editor_tabs.addTab(dummy, 'Work')
    window.editor_tabs.setCurrentIndex(idx); qtbot.wait(2)
    window.open_preferences(); qtbot.wait(5)
    # Insert a tab before the remembered work editor so its numeric index changes.
    inserted = QWidget(); inserted.document_id = 'test:inserted'; window.editor_tabs.insertTab(1, inserted, 'Inserted')
    window.toggle_preferences(); qtbot.wait(5)
    assert getattr(window.editor_tabs.currentWidget(), 'document_id', None) == 'test:work-editor'


def test_settings_tab_disables_undo_redo_and_does_not_route_to_hidden_editor(qtbot, tmp_path, monkeypatch):
    monkeypatch.setenv('MONOOLED_CONFIG_DIR', str(tmp_path / 'cfg'))
    from gui import OLEDDesignerWindow
    window = OLEDDesignerWindow('main_scene', 'en_US'); qtbot.addWidget(window); window.show(); qtbot.wait(10)
    view = window.open_preferences(); qtbot.wait(5)
    assert getattr(window.editor_tabs.currentWidget(), 'document_id', None) == 'settings:preferences'
    assert not window.header_undo.isEnabled()
    assert not window.header_redo.isEnabled()
    assert window.route_undo() is None
    assert window.route_redo() is None
    window.route_save()
    assert not view._save_timer.isActive()


def test_close_dirty_aux_editor_keeps_tab_when_save_does_not_clear_dirty(qtbot, tmp_path, monkeypatch):
    monkeypatch.setenv('MONOOLED_CONFIG_DIR', str(tmp_path / 'cfg'))
    from gui import OLEDDesignerWindow
    from PySide6.QtWidgets import QWidget, QMessageBox

    class DirtyDocument:
        dirty = True

    class DirtyEditor(QWidget):
        def __init__(self):
            super().__init__(); self.document_id='pixel:unsaved'; self.document=DirtyDocument()
        def save(self):
            return None

    window = OLEDDesignerWindow('main_scene', 'en_US'); qtbot.addWidget(window); window.show(); qtbot.wait(10)
    editor=DirtyEditor(); idx=window.editor_tabs.addTab(editor,'Unsaved'); window.editor_tabs.setCurrentIndex(idx)
    monkeypatch.setattr(QMessageBox,'question',lambda *args,**kwargs: QMessageBox.Save)
    before=window.editor_tabs.count(); window._close_editor_tab(idx); QApplication.processEvents()
    assert window.editor_tabs.count()==before
    assert window.editor_tabs.indexOf(editor)>=0


def test_language_switch_retranslates_scene_and_font_editor_tabs(qtbot, tmp_path, monkeypatch):
    monkeypatch.setenv('MONOOLED_CONFIG_DIR', str(tmp_path / 'cfg'))
    from gui import OLEDDesignerWindow
    from font_pack import create_font_pack
    root=tmp_path/'font'; create_font_pack(root,'Demo',cell=(5,8),baseline=6,advance=6).save()
    window=OLEDDesignerWindow('main_scene','en_US'); qtbot.addWidget(window); window.show(); qtbot.wait(10)
    font_editor=window.open_font_lab(root); qtbot.wait(5)
    window.preferences.set('language','zh_CN',save=False); window.apply_preferences(); QApplication.processEvents(); qtbot.wait(5)
    scene_idx=next(i for i in range(window.editor_tabs.count()) if getattr(window.editor_tabs.widget(i),'document_id',None)=='scene:active')
    font_idx=next(i for i in range(window.editor_tabs.count()) if str(getattr(window.editor_tabs.widget(i),'document_id','')).startswith('font:'))
    assert window.editor_tabs.tabText(scene_idx)=='设计'
    assert window.editor_tabs.tabText(font_idx).startswith('字库 · ')
