import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import pytest
pytest.importorskip('PySide6'); pytest.importorskip('pytestqt')

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QWidget, QVBoxLayout, QLabel

from ui_controls import PopupManager, StudioSelect


def _combo(qtbot, labels=('Off','1 px','2 px','4 px','8 px'), width=86):
    c=StudioSelect(); qtbot.addWidget(c); c.addItems(labels); c.resize(width,34); c.show(); qtbot.wait(5); return c


def test_first_anchor_click_opens_second_anchor_click_closes_and_stays_closed(qtbot):
    combo=_combo(qtbot)
    QTest.mouseClick(combo.button,Qt.LeftButton); qtbot.wait(5)
    assert combo.popup.isVisible() and PopupManager.visible_count()==1
    QTest.mouseClick(combo.button,Qt.LeftButton); qtbot.wait(1)
    assert not combo.popup.isVisible()
    qtbot.wait(20)
    assert not combo.popup.isVisible() and PopupManager.visible_count()==0


def test_public_qcombobox_compatible_show_hide_api(qtbot):
    combo=_combo(qtbot)
    combo.showPopup(); qtbot.wait(2); assert combo.popup.isVisible()
    combo.hidePopup(); qtbot.wait(2); assert not combo.popup.isVisible()


def test_item_commit_closes_before_signal_and_next_anchor_can_open(qtbot):
    combo=_combo(qtbot,('A','B','C'),160)
    seen=[]; combo.currentIndexChanged.connect(lambda _i: seen.append(combo.popup.isVisible()))
    combo.showPopup(); qtbot.wait(2)
    item=combo.list.item(1); rect=combo.list.visualItemRect(item)
    QTest.mouseClick(combo.list.viewport(),Qt.LeftButton,Qt.NoModifier,rect.center()); qtbot.wait(10)
    assert combo.currentIndex()==1 and seen[-1] is False and not combo.popup.isVisible()
    QTest.mouseClick(combo.button,Qt.LeftButton); qtbot.wait(2); assert combo.popup.isVisible()


def test_small_snap_select_popup_is_not_forced_to_180_px(qtbot):
    combo=_combo(qtbot,width=86); combo.showPopup(); qtbot.wait(2)
    assert combo.popup.width() < 140
    assert combo.popup.width() >= combo.width()


def test_only_one_popup_and_clicking_owner_twice_does_not_reopen(qtbot):
    host=QWidget(); qtbot.addWidget(host); layout=QVBoxLayout(host)
    a=StudioSelect(); b=StudioSelect(); layout.addWidget(a); layout.addWidget(b)
    for c in (a,b): c.addItems(['A','B','C'])
    host.show(); qtbot.wait(5)
    QTest.mouseClick(a.button,Qt.LeftButton); qtbot.wait(2); assert a.popup.isVisible()
    QTest.mouseClick(b.button,Qt.LeftButton); qtbot.wait(2)
    assert not a.popup.isVisible() and b.popup.isVisible() and PopupManager.visible_count()==1
    QTest.mouseClick(b.button,Qt.LeftButton); qtbot.wait(5)
    assert not a.popup.isVisible() and not b.popup.isVisible() and PopupManager.visible_count()==0


def test_popup_content_surface_is_opaque_not_bleedthrough(qtbot):
    host=QWidget(); qtbot.addWidget(host); host.resize(420,280); layout=QVBoxLayout(host)
    under=QLabel('BLEEDTHROUGH TEST'); under.setStyleSheet('background:#ff0000;color:#00ff00;font-size:28px;'); layout.addWidget(under)
    combo=StudioSelect(host); combo.addItems(['First','Second','Third']); combo.resize(220,34); layout.addWidget(combo)
    host.show(); qtbot.wait(10); combo.showPopup(); qtbot.wait(10)
    image=combo.popup.grab().toImage()
    # Ignore the masked 2px corner fringe; the content plane must be opaque.
    alphas=[]; reds=[]
    for y in range(6,max(7,image.height()-6),max(1,(image.height()-12)//8 or 1)):
        for x in range(6,max(7,image.width()-6),max(1,(image.width()-12)//8 or 1)):
            color=image.pixelColor(x,y); alphas.append(color.alpha()); reds.append((color.red(),color.green(),color.blue()))
    assert alphas and min(alphas)==255
    assert not any(r>240 and g<20 and b<20 for r,g,b in reds)


def test_escape_closes_without_changing_value(qtbot):
    combo=_combo(qtbot,('A','B','C'),160); before=combo.currentIndex()
    combo.showPopup(); qtbot.wait(2); QTest.keyClick(combo.list,Qt.Key_Escape); qtbot.wait(2)
    assert not combo.popup.isVisible() and combo.currentIndex()==before


def test_popup_rows_do_not_overlap_after_density_metrics(qtbot):
    combo=_combo(qtbot,('96×16','128×32','128×64','256×64','Custom'),220); combo.showPopup(); qtbot.wait(5)
    rects=[combo.list.visualItemRect(combo.list.item(i)) for i in range(combo.list.count())]
    assert all(r.height()>0 for r in rects)
    assert all(rects[i].bottom() < rects[i+1].top() for i in range(len(rects)-1))

