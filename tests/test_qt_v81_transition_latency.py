import os,time
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import pytest
pytest.importorskip('PySide6');pytest.importorskip('pytestqt')

from PySide6.QtGui import QColor, QImage
from PySide6.QtWidgets import QApplication, QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout, QWidget
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest

from gui import OLEDDesignerWindow
from qt_theme import SEMANTIC_PALETTE_ROLES, build_adaptive_stylesheet, build_stylesheet, build_theme_palette
from theme_system import THEME_NAMES, get_theme
from ui_controls import StudioSelect
from ui_latency import LATENCY_BUDGET_MS,percentile


def _elapsed_ms(fn):
    t=time.perf_counter();fn();QApplication.processEvents();return (time.perf_counter()-t)*1000.0


def _representative_surface():
    root=QWidget();root.setObjectName('AppRoot');layout=QVBoxLayout(root)
    panel=QFrame();panel.setObjectName('ProfessionalPanel');row=QHBoxLayout(panel)
    title=QLabel('MonoOLED Studio');title.setObjectName('PanelTitle');row.addWidget(title)
    primary=QPushButton('Primary');primary.setObjectName('PrimaryButton');row.addWidget(primary)
    secondary=QPushButton('Secondary');secondary.setObjectName('SecondaryButton');row.addWidget(secondary)
    field=QLineEdit('ORTHO 5/5');row.addWidget(field);layout.addWidget(panel)
    root.resize(640,120);root.show();QApplication.processEvents();return root


@pytest.mark.parametrize('theme',THEME_NAMES)
def test_adaptive_palette_preserves_every_stylesheet_theme_token(theme):
    expected=get_theme(theme);palette=build_theme_palette(theme)
    for token,role in SEMANTIC_PALETTE_ROLES.items():
        assert palette.color(role).name(QColor.HexArgb).upper()==QColor(expected[token]).name(QColor.HexArgb).upper(),token


@pytest.mark.parametrize('theme',THEME_NAMES)
def test_adaptive_stylesheet_renders_representative_surface_like_literal_stylesheet(qtbot,theme):
    app=QApplication.instance();surface=_representative_surface();qtbot.addWidget(surface)
    app.setPalette(build_theme_palette(theme));app.setStyleSheet(build_stylesheet(theme));QApplication.processEvents()
    literal=surface.grab().toImage().convertToFormat(QImage.Format_RGBA8888)
    app.setPalette(build_theme_palette(theme));app.setStyleSheet(build_adaptive_stylesheet());QApplication.processEvents()
    adaptive=surface.grab().toImage().convertToFormat(QImage.Format_RGBA8888)
    assert literal==adaptive


def test_v81_popup_open_and_close_latency_budget(qtbot):
    combo=StudioSelect();qtbot.addWidget(combo);combo.addItems([f'Item {i}' for i in range(20)]);combo.resize(260,34);combo.show();qtbot.wait(5)
    opens=[];commits=[]
    for i in range(20):
        opens.append(_elapsed_ms(combo.showPopup));assert combo.popup.isVisible()
        item=combo.list.item(i%combo.list.count());rect=combo.list.visualItemRect(item)
        t=time.perf_counter();QTest.mouseClick(combo.list.viewport(),Qt.LeftButton,Qt.NoModifier,rect.center());assert not combo.popup.isVisible();QApplication.processEvents();commits.append((time.perf_counter()-t)*1000.0)
    assert percentile(opens,.95)<=LATENCY_BUDGET_MS['popup_open'],opens
    assert percentile(commits,.95)<=LATENCY_BUDGET_MS['popup_select_close'],commits


def test_theme_only_switch_keeps_application_stylesheet_identity(qtbot,tmp_path,monkeypatch):
    monkeypatch.setenv('LOCALAPPDATA',str(tmp_path/'local'));monkeypatch.setenv('XDG_CONFIG_HOME',str(tmp_path/'config'))
    app=QApplication.instance();w=OLEDDesignerWindow('main_scene');qtbot.addWidget(w);w.resize(1440,900);w.show();qtbot.wait(20)
    before=app.styleSheet()
    w.preferences.set('appearance.color_theme','monooled-dark',save=False);w.preferences.set('appearance.theme_mode','dark',save=False);w.apply_preferences();QApplication.processEvents()
    assert app.styleSheet()==before
    assert app.palette().color(SEMANTIC_PALETTE_ROLES['app.background']).name().upper()==get_theme('one-dark-pro')['app.background']


def test_v81_language_and_theme_switch_latency_budget(qtbot,tmp_path,monkeypatch):
    monkeypatch.setenv('LOCALAPPDATA',str(tmp_path/'local'));monkeypatch.setenv('XDG_CONFIG_HOME',str(tmp_path/'config'))
    w=OLEDDesignerWindow('main_scene');qtbot.addWidget(w);w.resize(1440,900);w.show();qtbot.wait(20)
    language=[];theme=[]
    for i in range(20):
        lang='en_US' if i%2 else 'zh_CN'
        language.append(_elapsed_ms(lambda l=lang:(w.preferences.set('language',l,save=False),w.apply_preferences())))
    for i in range(20):
        name='one-dark-pro' if i%2 else 'monooled-light';mode='dark' if i%2 else 'light'
        theme.append(_elapsed_ms(lambda n=name,m=mode:(w.preferences.set('appearance.color_theme',n,save=False),w.preferences.set('appearance.theme_mode',m,save=False),w.apply_preferences())))
    assert percentile(language,.95)<=LATENCY_BUDGET_MS['language_switch'],language
    assert percentile(theme,.95)<=LATENCY_BUDGET_MS['theme_switch'],theme
