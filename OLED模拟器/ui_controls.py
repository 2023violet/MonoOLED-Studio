from __future__ import annotations

import weakref

try:
    from PySide6.QtCore import QEvent, QPoint, QTimer, Qt
    from PySide6.QtGui import QFontMetrics, QGuiApplication, QPainterPath, QRegion
    from PySide6.QtWidgets import (
        QAbstractSpinBox, QFrame, QHBoxLayout, QLabel, QListWidget,
        QListWidgetItem, QPushButton as _QPushButton, QSpinBox,
        QToolButton as _QToolButton, QVBoxLayout, QWidget,
    )
    PYSIDE_AVAILABLE = True
except Exception:  # pragma: no cover - host/core environments may omit Qt
    PYSIDE_AVAILABLE = False

from popup_geometry import Rect, Size, content_popup_width, place_popup
from popup_state import CloseReason, PopupInteractionState, PopupStateMachine


def _repolish(widget) -> None:
    style = widget.style()
    style.unpolish(widget)
    style.polish(widget)
    widget.update()


if PYSIDE_AVAILABLE:
    class _InteractionMixin:
        """Production interaction state used by every Studio button."""
        def _init_interaction(self) -> None:
            self.setProperty('hoverVisible', False)
            self.setProperty('pressedVisible', False)
            self.setProperty('keyboardFocusVisible', False)

        def _set_visual(self, name: str, value: bool) -> None:
            value = bool(value)
            if bool(self.property(name)) == value:
                return
            self.setProperty(name, value)
            _repolish(self)

        def enterEvent(self, event):  # noqa: N802
            self._set_visual('hoverVisible', self.isEnabled())
            super().enterEvent(event)

        def leaveEvent(self, event):  # noqa: N802
            self._set_visual('hoverVisible', False)
            self._set_visual('pressedVisible', False)
            super().leaveEvent(event)

        def mousePressEvent(self, event):  # noqa: N802
            self._set_visual('keyboardFocusVisible', False)
            self._set_visual('pressedVisible', self.isEnabled())
            super().mousePressEvent(event)

        def mouseReleaseEvent(self, event):  # noqa: N802
            self._set_visual('pressedVisible', False)
            super().mouseReleaseEvent(event)

        def focusInEvent(self, event):  # noqa: N802
            reason = event.reason()
            keyboard = reason in (Qt.TabFocusReason, Qt.BacktabFocusReason)
            self._set_visual('keyboardFocusVisible', keyboard)
            super().focusInEvent(event)

        def focusOutEvent(self, event):  # noqa: N802
            self._set_visual('keyboardFocusVisible', False)
            super().focusOutEvent(event)

        def changeEvent(self, event):  # noqa: N802
            if event.type() == QEvent.EnabledChange and not self.isEnabled():
                self._set_visual('hoverVisible', False)
                self._set_visual('pressedVisible', False)
                self._set_visual('keyboardFocusVisible', False)
            super().changeEvent(event)

    class StudioButton(_InteractionMixin, _QPushButton):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self._init_interaction()

    class StudioToolButton(_InteractionMixin, _QToolButton):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self._init_interaction()

    class PopupManager:
        """Single active Studio popup across the application."""
        _active_ref = None

        @classmethod
        def active(cls):
            return cls._active_ref() if cls._active_ref else None

        @classmethod
        def open(cls, popup):
            active = cls.active()
            if active is not None and active is not popup:
                owner = active.owner_select()
                if owner is not None:
                    owner.hidePopup(CloseReason.OTHER_POPUP_OPEN)
                else:
                    active.hide()
            cls._active_ref = weakref.ref(popup)

        @classmethod
        def closed(cls, popup):
            if cls.active() is popup:
                cls._active_ref = None

        @classmethod
        def close_all(cls):
            active = cls.active()
            if active is not None:
                owner = active.owner_select()
                if owner is not None:
                    owner.hidePopup(CloseReason.PROGRAMMATIC)
                else:
                    active.hide()
            cls._active_ref = None

        @classmethod
        def visible_count(cls):
            active = cls.active()
            return int(active is not None and active.isVisible())

    class StudioPopover(QFrame):
        """Opaque, rounded transient surface used by StudioSelect.

        The native window itself is intentionally *not* translucent.  V8.1
        used a translucent Qt.Popup with a transparent list viewport, which
        allowed the owner UI to bleed through on Windows.  Rounded corners are
        enforced with a window mask instead of depending on stylesheet alpha.

        V9: Uses systematic 8px panel radius (matches StudioSelectPopup QSS).
        """
        def __init__(self, owner, parent=None):
            super().__init__(parent, Qt.Popup | Qt.FramelessWindowHint)
            self._owner_ref = weakref.ref(owner)
            self._close_reason = None
            self.setObjectName('StudioSelectPopup')
            self.setAttribute(Qt.WA_StyledBackground, True)
            self.setAutoFillBackground(True)

        def owner_select(self):
            return self._owner_ref()

        def set_close_reason(self, reason):
            self._close_reason = reason

        def _apply_round_mask(self):
            if self.width() <= 0 or self.height() <= 0:
                return
            path = QPainterPath()
            # V9 systematic scale: panel surfaces use 8px radius
            path.addRoundedRect(0.0, 0.0, float(self.width()), float(self.height()), 8.0, 8.0)
            self.setMask(QRegion(path.toFillPolygon().toPolygon()))

        def resizeEvent(self, event):  # noqa: N802
            super().resizeEvent(event)
            self._apply_round_mask()

        def showEvent(self, event):  # noqa: N802
            PopupManager.open(self)
            self._apply_round_mask()
            owner = self.owner_select()
            if owner is not None:
                owner._popup_opened()
            super().showEvent(event)

        def hideEvent(self, event):  # noqa: N802
            reason = self._close_reason or CloseReason.OUTSIDE_CLICK
            self._close_reason = None
            PopupManager.closed(self)
            owner = self.owner_select()
            if owner is not None:
                owner._popup_hidden(reason)
            super().hideEvent(event)

        def keyPressEvent(self, event):  # noqa: N802
            if event.key() == Qt.Key_Escape:
                owner = self.owner_select()
                if owner is not None:
                    owner.hidePopup(CloseReason.ESCAPE)
                else:
                    self.hide()
                event.accept()
                return
            super().keyPressEvent(event)

    class StudioNumericInput(QSpinBox):
        """Modern numeric field without native Windows stepper chrome."""
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.setObjectName('StudioNumericInput')
            self.setButtonSymbols(QAbstractSpinBox.NoButtons)
            self.setKeyboardTracking(False)

    class StudioSelect(QWidget):
        """Studio-owned select with explicit toggle state and opaque popup."""
        from PySide6.QtCore import Signal
        currentIndexChanged = Signal(int)
        currentTextChanged = Signal(str)
        activated = Signal(int)

        def __init__(self, parent=None):
            super().__init__(parent)
            self.setObjectName('StudioSelect')
            self._items = []
            self._index = -1
            self._popup_state = PopupStateMachine()
            self._swallow_anchor_release = False
            # Keep callback-visible attributes defined from the first Qt event.
            self.popup = None
            self.list = None
            layout = QHBoxLayout(self)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(0)
            self.button = StudioButton('')
            self.button.setObjectName('StudioSelectButton')
            layout.addWidget(self.button)
            self.chevron = QLabel('⌄', self.button)
            self.chevron.setObjectName('StudioSelectChevron')
            self.chevron.setAttribute(Qt.WA_TransparentForMouseEvents, True)
            self.popup = StudioPopover(self)
            pl = QVBoxLayout(self.popup)
            pl.setContentsMargins(5, 5, 5, 5)
            pl.setSpacing(0)
            self.list = QListWidget()
            self.list.setObjectName('StudioSelectList')
            self.list.setAttribute(Qt.WA_StyledBackground, True)
            self.list.setAutoFillBackground(True)
            self.list.viewport().setAutoFillBackground(True)
            self.list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            pl.addWidget(self.list)
            # Activate callbacks only after every member used by eventFilter exists.
            self.button.installEventFilter(self)
            self.list.installEventFilter(self)
            self.button.clicked.connect(self.toggle_popup)
            self.list.itemClicked.connect(self._item_clicked)
            self.list.itemActivated.connect(self._item_clicked)
            self.setMinimumHeight(30)

        @property
        def popup_state(self):
            return self._popup_state.state

        def eventFilter(self, obj, event):  # noqa: N802
            if self.popup is None or self.list is None:
                return super().eventFilter(obj, event)
            if obj is self.list and event.type() == QEvent.KeyPress and event.key() == Qt.Key_Escape:
                self.hidePopup(CloseReason.ESCAPE)
                event.accept()
                return True
            if obj is self.button:
                if event.type() == QEvent.MouseButtonPress and event.button() == Qt.LeftButton:
                    # Handle the second anchor click at press time, before
                    # QAbstractButton.clicked can reopen a native Qt.Popup.
                    if self._popup_state.consume_anchor_click():
                        self._swallow_anchor_release = True
                        event.accept()
                        return True
                    if self.popup.isVisible() or self._popup_state.state in (
                        PopupInteractionState.OPEN, PopupInteractionState.OPENING,
                        PopupInteractionState.COMMIT_PENDING,
                    ):
                        self._popup_state.anchor_press()
                        self.hidePopup(CloseReason.ANCHOR_TOGGLE)
                        self._swallow_anchor_release = True
                        event.accept()
                        return True
                if event.type() == QEvent.MouseButtonRelease and self._swallow_anchor_release:
                    self._swallow_anchor_release = False
                    event.accept()
                    return True
            return super().eventFilter(obj, event)

        def resizeEvent(self, event):  # noqa: N802
            super().resizeEvent(event)
            self.chevron.adjustSize()
            self.chevron.move(max(0, self.button.width() - self.chevron.width() - 10), max(0, (self.button.height() - self.chevron.height()) // 2))
            if self.popup.isVisible():
                self._reposition_popup()

        def moveEvent(self, event):  # noqa: N802
            super().moveEvent(event)
            # A native popup anchored to a moving widget is visually unsafe;
            # closing is less surprising than leaving a stale floating list.
            if self.popup.isVisible():
                self.hidePopup(CloseReason.PROGRAMMATIC)

        def hideEvent(self, event):  # noqa: N802
            self.hidePopup(CloseReason.OWNER_HIDDEN)
            super().hideEvent(event)

        def changeEvent(self, event):  # noqa: N802
            if event.type() in (QEvent.EnabledChange, QEvent.StyleChange, QEvent.FontChange):
                if not self.isEnabled():
                    self.hidePopup(CloseReason.DISABLED)
                    self._popup_state.set_enabled(False)
                else:
                    self._popup_state.set_enabled(True)
                    if self.popup.isVisible():
                        # Theme/font metric changes invalidate the old native
                        # popup geometry; close and let the next click reopen.
                        self.hidePopup(CloseReason.PROGRAMMATIC)
            super().changeEvent(event)

        def addItem(self, text, userData=None):
            self._items.append((str(text), userData))
            self.list.addItem(QListWidgetItem(str(text)))
            if self._index < 0:
                self.setCurrentIndex(0)

        def addItems(self, texts):
            for text in texts:
                self.addItem(text)

        def clear(self):
            self.hidePopup(CloseReason.PROGRAMMATIC)
            self._items.clear()
            self.list.clear()
            self._index = -1
            self.button.setText('')

        def count(self): return len(self._items)
        def itemText(self, index): return self._items[index][0]
        def itemData(self, index): return self._items[index][1]

        def setItemText(self, index, text):
            data = self._items[index][1]
            self._items[index] = (str(text), data)
            self.list.item(index).setText(str(text))
            if index == self._index:
                self.button.setText(str(text))

        def findData(self, data):
            for i, (_label, value) in enumerate(self._items):
                if value == data:
                    return i
            return -1

        def currentIndex(self): return self._index
        def currentText(self): return self._items[self._index][0] if 0 <= self._index < len(self._items) else ''
        def currentData(self): return self._items[self._index][1] if 0 <= self._index < len(self._items) else None

        def setCurrentIndex(self, index):
            index = int(index)
            if not self._items:
                index = -1
            else:
                index = max(0, min(len(self._items) - 1, index))
            if index == self._index:
                return
            self._index = index
            if index >= 0:
                text = self._items[index][0]
                self.button.setText(text)
                self.list.setCurrentRow(index)
            else:
                text = ''
                self.button.setText('')
            self.currentIndexChanged.emit(index)
            self.currentTextChanged.emit(text)

        def setCurrentText(self, text):
            for i, (label, _data) in enumerate(self._items):
                if label == str(text):
                    self.setCurrentIndex(i)
                    return

        def findText(self, text):
            for i, (label, _data) in enumerate(self._items):
                if label == str(text):
                    return i
            return -1

        def _commit_index(self, row: int):
            if not (0 <= int(row) < len(self._items)):
                return
            self.setCurrentIndex(int(row))
            self.activated.emit(int(row))

        def _item_clicked(self, item):
            row = self.list.row(item)
            self._popup_state.begin_commit()
            # The popup disappears before theme/language callbacks execute.
            self.hidePopup(CloseReason.ITEM_COMMIT)
            QTimer.singleShot(0, lambda r=row: self._commit_index(r))

        def _desired_popup_size(self):
            metrics = QFontMetrics(self.list.font())
            fallback_row = max(30, metrics.height() + 12)
            row_heights = [max(fallback_row, self.list.sizeHintForRow(i)) for i in range(self.list.count())]
            text_widths = [metrics.horizontalAdvance(label) for label, _data in self._items]
            pos = self.mapToGlobal(QPoint(0, 0))
            screen = self._screen_geometry(pos)
            width = content_popup_width(
                self.width(), text_widths,
                horizontal_padding=34,
                minimum=min(72, max(1, self.width())),
                maximum=max(1, min(360, screen.w - 8)),
            )
            # Sum actual row metrics rather than assuming a fixed 30px row.
            # This prevents text/item overlap after density, DPI or font changes.
            content_h = sum(row_heights) if row_heights else fallback_row
            height = min(320, max(42, content_h + 12))
            return Size(width, height)

        def _screen_geometry(self, anchor_global):
            center = anchor_global + QPoint(max(1, self.width()) // 2, max(1, self.height()) // 2)
            screen = QGuiApplication.screenAt(center) or QGuiApplication.primaryScreen()
            if screen is None:
                return Rect(0, 0, 1920, 1080)
            g = screen.availableGeometry()
            return Rect(g.x(), g.y(), g.width(), g.height())

        def _reposition_popup(self):
            if not self.isVisible():
                return
            pos = self.mapToGlobal(QPoint(0, 0))
            anchor = Rect(pos.x(), pos.y(), max(1, self.width()), max(1, self.height()))
            rect = place_popup(anchor, self._desired_popup_size(), self._screen_geometry(pos), gap=4, margin=4)
            self.popup.resize(rect.w, rect.h)
            self.popup.move(rect.x, rect.y)

        def _popup_opened(self):
            self._popup_state.opened()
            self.button.setProperty('popupOpen', True)
            _repolish(self.button)

        def _popup_hidden(self, reason):
            # A native Qt.Popup may close itself before the anchor receives the
            # same physical mouse click.  Suppress only until the current event
            # loop drains; an independent later click is allowed to reopen.
            auto_outside = reason is CloseReason.OUTSIDE_CLICK
            self._popup_state.closed(reason, owner_anchor=auto_outside)
            self.button.setProperty('popupOpen', False)
            _repolish(self.button)
            if auto_outside or reason is CloseReason.ANCHOR_TOGGLE:
                QTimer.singleShot(0, self._popup_state.clear_anchor_suppression)

        def showPopup(self):  # noqa: N802 - QComboBox-compatible public API
            if not self.isEnabled() or not self._items or self.popup.isVisible():
                return
            if self._popup_state.state is PopupInteractionState.CLOSED:
                self._popup_state.anchor_press()
            PopupManager.open(self.popup)
            self._reposition_popup()
            self.popup.show()
            self.popup.raise_()
            if 0 <= self._index < self.list.count():
                self.list.setCurrentRow(self._index)
                self.list.scrollToItem(self.list.item(self._index))
            self.list.setFocus()

        def hidePopup(self, reason=CloseReason.PROGRAMMATIC):  # noqa: N802
            if not isinstance(reason, CloseReason):
                reason = CloseReason(str(reason))
            if self.popup.isVisible():
                self.popup.set_close_reason(reason)
                self.popup.hide()
            elif self._popup_state.state not in (PopupInteractionState.CLOSED, PopupInteractionState.DISABLED):
                self._popup_state.closed(reason)

        def toggle_popup(self):
            # If Qt auto-closed a Popup due to the same anchor mouse press, the
            # subsequent clicked signal must be swallowed rather than reopen it.
            if self._popup_state.consume_anchor_click():
                return
            action = self._popup_state.anchor_press()
            if action == 'close':
                self.hidePopup(CloseReason.ANCHOR_TOGGLE)
            elif action == 'open':
                self.showPopup()

        def keyPressEvent(self, event):  # noqa: N802
            if event.key() in (Qt.Key_Space, Qt.Key_Return, Qt.Key_Enter, Qt.Key_Down):
                self.toggle_popup()
                event.accept()
                return
            if event.key() == Qt.Key_Escape and self.popup.isVisible():
                self.hidePopup(CloseReason.ESCAPE)
                event.accept()
                return
            super().keyPressEvent(event)

        def setEnabled(self, value):
            super().setEnabled(value)
            self.button.setEnabled(value)
            if not value:
                self.hidePopup(CloseReason.DISABLED)
                self._popup_state.set_enabled(False)
            else:
                self._popup_state.set_enabled(True)

    class StudioSegmentedControl(QWidget):
        from PySide6.QtCore import Signal
        currentIndexChanged = Signal(int)
        def __init__(self,labels=(),parent=None):
            super().__init__(parent);self.setObjectName('StudioSegmentedControl');self._buttons=[];self._index=-1
            layout=QHBoxLayout(self);layout.setContentsMargins(0,0,0,0);layout.setSpacing(0)
            for i,label in enumerate(labels):
                b=StudioButton(str(label));b.setObjectName('StudioSegment');b.setCheckable(True);b.clicked.connect(lambda _=False,n=i:self.setCurrentIndex(n));layout.addWidget(b);self._buttons.append(b)
            if self._buttons:self.setCurrentIndex(0)
        def currentIndex(self):return self._index
        def setCurrentIndex(self,index):
            index=max(0,min(len(self._buttons)-1,int(index))) if self._buttons else -1
            if index==self._index:return
            self._index=index
            for i,b in enumerate(self._buttons):b.setChecked(i==index)
            self.currentIndexChanged.emit(index)
else:
    class _MissingQt:
        def __init__(self, *args, **kwargs):
            raise RuntimeError('PySide6 is required for Studio UI controls')
    StudioButton = StudioToolButton = StudioPopover = StudioNumericInput = StudioSelect = StudioSegmentedControl = _MissingQt
    class PopupManager:
        @classmethod
        def visible_count(cls): return 0
        @classmethod
        def close_all(cls): return None
