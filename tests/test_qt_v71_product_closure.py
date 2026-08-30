from __future__ import annotations

import os
from pathlib import Path
import sys
import pytest

pytest.importorskip('PySide6')
pytest.importorskip('pytestqt')

from PySide6.QtCore import Qt, QPoint, QSettings
from PySide6.QtGui import QImage
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QHBoxLayout, QScrollArea, QVBoxLayout, QWidget

SIM=Path(__file__).resolve().parents[1] / 'src'
sys.path.insert(0,str(SIM))

from gui import OLEDDesignerWindow
from i18n import Translator
from pixel_studio import PixelDocument
from pixel_studio_qt import PixelCanvas, PixelStudioWindow
from preferences import PreferencesStore, default_preferences
from preferences_qt import PreferencesWindow
from qt_interaction import FocusOriginFilter
from qt_theme import build_stylesheet
from ui_controls import StudioButton, StudioToolButton


def _rgba(widget):
    image=widget.grab().toImage().convertToFormat(QImage.Format_RGBA8888)
    return bytes(image.bits())


def _stable_rgba(qtbot, widget):
    samples=[]
    def settled():
        samples.append(_rgba(widget))
        if len(samples)>2:samples.pop(0)
        return len(samples)==2 and samples[0]==samples[1] and any(samples[1])
    qtbot.waitUntil(settled,timeout=1000)
    return samples[-1]


def _install_focus_filter(app):
    f=FocusOriginFilter(app)
    app.installEventFilter(f)
    return f


def test_production_tool_button_hover_leave_and_unselect_return_to_exact_raster(qtbot):
    app=QApplication.instance(); app.setStyleSheet(build_stylesheet('monooled-light'))
    focus_filter=_install_focus_filter(app)
    host=QWidget(); layout=QHBoxLayout(host)
    a=StudioToolButton(); a.setObjectName('ToolRailButton'); a.setText('A'); a.setCheckable(True)
    b=StudioToolButton(); b.setObjectName('ToolRailButton'); b.setText('B'); b.setCheckable(True)
    layout.addWidget(a); layout.addWidget(b); qtbot.addWidget(host); host.show(); qtbot.waitExposed(host)
    QTest.mouseMove(b,b.rect().center()); app.processEvents(); baseline=_stable_rgba(qtbot,a)
    QTest.mouseMove(a,a.rect().center()); app.processEvents(); QTest.mouseMove(b,b.rect().center()); app.processEvents()
    qtbot.waitUntil(lambda:_rgba(a)==baseline,timeout=1000)
    a.setChecked(True); app.processEvents(); QTest.mouseMove(a,a.rect().center()); app.processEvents(); QTest.mouseMove(b,b.rect().center()); app.processEvents()
    a.setChecked(False); app.processEvents()
    qtbot.waitUntil(lambda:_rgba(a)==baseline,timeout=1000)
    app.removeEventFilter(focus_filter)


def test_keyboard_focus_ring_clears_immediately_on_same_control_mouse_click(qtbot):
    app=QApplication.instance(); focus_filter=_install_focus_filter(app)
    host=QWidget(); layout=QVBoxLayout(host); a=StudioButton('A'); b=StudioButton('B'); layout.addWidget(a); layout.addWidget(b)
    qtbot.addWidget(host); host.show(); qtbot.waitExposed(host)
    b.setFocus(Qt.OtherFocusReason); app.processEvents()
    a.setFocus(Qt.TabFocusReason); app.processEvents(); assert bool(a.property('keyboardFocusVisible'))
    QTest.mouseClick(a,Qt.LeftButton); app.processEvents(); assert not bool(a.property('keyboardFocusVisible'))
    app.removeEventFilter(focus_filter)


def test_pixel_middle_and_space_pan_are_real_and_preference_gated(qtbot):
    doc=PixelDocument(64,32); canvas=PixelCanvas(doc); canvas.zoom=20; canvas._sync_size()
    area=QScrollArea(); area.setWidget(canvas); area.setWidgetResizable(False); area.resize(320,220); qtbot.addWidget(area); area.show(); qtbot.waitExposed(area)
    h=area.horizontalScrollBar(); v=area.verticalScrollBar(); h.setValue(min(300,h.maximum())); v.setValue(min(200,v.maximum())); app=QApplication.instance(); app.processEvents()
    before=(h.value(),v.value()); p=QPoint(150,100)
    QTest.mousePress(canvas,Qt.MiddleButton,pos=p); QTest.mouseMove(canvas,QPoint(110,70),delay=10); QTest.mouseRelease(canvas,Qt.MiddleButton,pos=QPoint(110,70)); app.processEvents()
    assert (h.value(),v.value())!=before
    canvas.middle_pan_enabled=False; h.setValue(before[0]); v.setValue(before[1]); app.processEvents()
    QTest.mousePress(canvas,Qt.MiddleButton,pos=p); QTest.mouseMove(canvas,QPoint(110,70),delay=10); QTest.mouseRelease(canvas,Qt.MiddleButton,pos=QPoint(110,70)); app.processEvents()
    assert (h.value(),v.value())==before
    canvas.space_pan_enabled=True; canvas.setFocus(); QTest.keyPress(canvas,Qt.Key_Space); app.processEvents();
    QTest.mousePress(canvas,Qt.LeftButton,pos=p); QTest.mouseMove(canvas,QPoint(105,65),delay=10); QTest.mouseRelease(canvas,Qt.LeftButton,pos=QPoint(105,65)); QTest.keyRelease(canvas,Qt.Key_Space); app.processEvents()
    assert (h.value(),v.value())!=before


def test_preferences_shortcut_conflict_is_rejected_without_partial_save(qtbot,tmp_path):
    prefs=default_preferences(); store=PreferencesStore(tmp_path/'prefs.json',prefs); store.save(); tr=Translator('en_US')
    w=PreferencesWindow(store,tr); qtbot.addWidget(w); w.show(); qtbot.waitExposed(w)
    w.nav.setCurrentRow(w.SECTIONS.index('keyboard')); QApplication.processEvents()
    original=store.get('shortcuts.designer.undo')
    w.shortcut_edits['designer.undo'].setText('Ctrl+S'); w._shortcuts_changed(); QApplication.processEvents()
    assert w.shortcut_error.isVisible()
    reloaded=PreferencesStore.load(tmp_path/'prefs.json')
    assert reloaded.get('shortcuts.designer.undo')==original


def _config_store(tmp_path: Path, theme: str, language: str, density: str) -> PreferencesStore:
    prefs=default_preferences(); prefs['language']=language; prefs['appearance']['color_theme']=theme; prefs['appearance']['density']=density
    prefs['appearance']['theme_mode']='light' if theme=='monooled-light' else ('dark' if theme=='monooled-dark' else 'system')
    store=PreferencesStore(tmp_path/'prefs.json',prefs); store.save(); return store


@pytest.mark.parametrize('theme',['monooled-light','monooled-dark','one-dark-pro','high-contrast'])
@pytest.mark.parametrize('language',['zh_CN','en_US'])
@pytest.mark.parametrize('density',['compact','comfortable','spacious'])
def test_v71_three_surface_configuration_matrix(qtbot,tmp_path,monkeypatch,theme,language,density):
    # This is 24 configurations per DPI process. The Windows workflow runs it
    # at eight scales => 192 configuration rows x 3 production surfaces = 576 constructions.
    config_root=tmp_path/'config'; monkeypatch.setenv('XDG_CONFIG_HOME',str(config_root)); monkeypatch.setenv('LOCALAPPDATA',str(config_root))
    if os.name=='nt': pref_path=config_root/'MonoOLEDStudio'/'preferences.json'
    else: pref_path=config_root/'monooled-studio'/'preferences.json'
    prefs=default_preferences(); prefs['language']=language; prefs['appearance']['color_theme']=theme; prefs['appearance']['density']=density
    prefs['appearance']['theme_mode']='light' if theme=='monooled-light' else ('dark' if theme=='monooled-dark' else 'system')
    PreferencesStore(pref_path,prefs).save()
    local_store=PreferencesStore(tmp_path/'local.json',prefs); local_store.save()
    app=QApplication.instance()

    pixel=PixelStudioWindow(language=language,preferences=local_store); qtbot.addWidget(pixel); pixel.resize(1100,720); pixel.show(); qtbot.waitExposed(pixel); assert not pixel.layout_violations()
    pref=PreferencesWindow(local_store,Translator(language)); qtbot.addWidget(pref); pref.resize(920,660); pref.show(); qtbot.waitExposed(pref); assert not pref.layout_violations()
    QSettings('MonoOLEDStudio','MonoOLEDStudio').clear()
    designer=OLEDDesignerWindow('main_scene',language); qtbot.addWidget(designer); designer.resize(1180,720); designer.show(); qtbot.waitExposed(designer); assert not designer.layout_violations()
    designer.session.document.dirty=False; designer.close(); pixel.close(); pref.close(); app.processEvents()
