from __future__ import annotations

from PySide6.QtCore import QObject, QEvent, Qt
from PySide6.QtWidgets import QWidget


def repolish(widget: QWidget) -> None:
    style = widget.style()
    style.unpolish(widget)
    style.polish(widget)
    widget.update()


def set_button_role(widget: QWidget, role: str) -> None:
    widget.setObjectName(str(role))
    repolish(widget)


class FocusOriginFilter(QObject):
    """Shows focus styling only when focus arrived via keyboard navigation."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.keyboard_navigation = False

    def eventFilter(self, obj, event):  # noqa: N802
        et = event.type()
        if et in (QEvent.MouseButtonPress, QEvent.MouseButtonDblClick):
            self.keyboard_navigation = False
            if isinstance(obj, QWidget) and obj.property('keyboardFocusVisible'):
                obj.setProperty('keyboardFocusVisible', False)
                repolish(obj)
        elif et == QEvent.KeyPress:
            key = event.key()
            if key in (Qt.Key_Tab, Qt.Key_Backtab):
                self.keyboard_navigation = True
        elif et == QEvent.FocusIn and isinstance(obj, QWidget):
            keyboard_focus = self.keyboard_navigation or event.reason() in (Qt.TabFocusReason, Qt.BacktabFocusReason)
            obj.setProperty('keyboardFocusVisible', bool(keyboard_focus))
            repolish(obj)
        elif et == QEvent.FocusOut and isinstance(obj, QWidget):
            if obj.property('keyboardFocusVisible'):
                obj.setProperty('keyboardFocusVisible', False)
                repolish(obj)
        return False
