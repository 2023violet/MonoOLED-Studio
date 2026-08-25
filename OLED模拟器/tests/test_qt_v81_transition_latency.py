import os,time
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import pytest
pytest.importorskip('PySide6');pytest.importorskip('pytestqt')

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest

from gui import OLEDDesignerWindow
from ui_controls import StudioSelect
from ui_latency import LATENCY_BUDGET_MS,percentile


def _elapsed_ms(fn):
    t=time.perf_counter();fn();QApplication.processEvents();return (time.perf_counter()-t)*1000.0


def test_v81_popup_open_and_close_latency_budget(qtbot):
    combo=StudioSelect();qtbot.addWidget(combo);combo.addItems([f'Item {i}' for i in range(20)]);combo.resize(260,34);combo.show();qtbot.wait(5)
    opens=[];commits=[]
    for i in range(20):
        opens.append(_elapsed_ms(combo.showPopup));assert combo.popup.isVisible()
        item=combo.list.item(i%combo.list.count());rect=combo.list.visualItemRect(item)
        t=time.perf_counter();QTest.mouseClick(combo.list.viewport(),Qt.LeftButton,Qt.NoModifier,rect.center());assert not combo.popup.isVisible();QApplication.processEvents();commits.append((time.perf_counter()-t)*1000.0)
    assert percentile(opens,.95)<=LATENCY_BUDGET_MS['popup_open'],opens
    assert percentile(commits,.95)<=LATENCY_BUDGET_MS['popup_select_close'],commits


def test_v81_language_and_theme_switch_latency_budget(qtbot,tmp_path,monkeypatch):
    monkeypatch.setenv('LOCALAPPDATA',str(tmp_path/'local'));monkeypatch.setenv('XDG_CONFIG_HOME',str(tmp_path/'config'))
    w=OLEDDesignerWindow('main_scene');qtbot.addWidget(w);w.resize(1440,900);w.show();qtbot.wait(20)
    language=[];theme=[]
    for i in range(20):
        lang='en_US' if i%2 else 'zh_CN'
        language.append(_elapsed_ms(lambda l=lang:(w.preferences.set('language',l,save=False),w.apply_preferences())))
    for i in range(20):
        name='monooled-dark' if i%2 else 'monooled-light';mode='dark' if i%2 else 'light'
        theme.append(_elapsed_ms(lambda n=name,m=mode:(w.preferences.set('appearance.color_theme',n,save=False),w.preferences.set('appearance.theme_mode',m,save=False),w.apply_preferences())))
    assert percentile(language,.95)<=LATENCY_BUDGET_MS['language_switch'],language
    assert percentile(theme,.95)<=LATENCY_BUDGET_MS['theme_switch'],theme
