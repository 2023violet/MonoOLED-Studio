from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QFrame, QGraphicsDropShadowEffect, QLabel, QVBoxLayout, QWidget

from qt_theme import COLORS, METRICS
from theme_system import get_theme


class BentoCard(QFrame):
    def __init__(self, title: str = '', subtitle: str = '', *, size: str = 'large', small: bool = False, parent: QWidget | None = None):
        super().__init__(parent)
        if small:
            size = 'small'
        object_name = {'large': 'BentoCard', 'medium': 'BentoMediumCard', 'small': 'BentoSmallCard'}.get(size, 'BentoCard')
        self.setObjectName(object_name)
        padding = {'large': METRICS['padding_large'], 'medium': METRICS['padding_medium'], 'small': METRICS['padding_small']}.get(size, METRICS['padding_medium'])
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(padding, padding - 4, padding, padding)
        self._layout.setSpacing(12)

        self.title_label = QLabel(title)
        self.title_label.setObjectName('CardTitle')
        self.subtitle_label = QLabel(subtitle)
        self.subtitle_label.setObjectName('CardSubtitle')
        self.subtitle_label.setWordWrap(True)
        self._layout.addWidget(self.title_label)
        self._layout.addWidget(self.subtitle_label)
        self.subtitle_label.setVisible(bool(subtitle))

        self._shadow = QGraphicsDropShadowEffect(self)
        self._apply_shadow(False)
        self.setGraphicsEffect(self._shadow)

    def _apply_shadow(self, hover: bool) -> None:
        self._shadow.setBlurRadius(METRICS['shadow_hover_blur'] if hover else METRICS['shadow_blur'])
        self._shadow.setOffset(0, 8 if hover else 4)
        self._shadow.setColor(QColor(0, 0, 0, METRICS['shadow_hover_alpha'] if hover else METRICS['shadow_alpha']))

    def enterEvent(self, event) -> None:  # noqa: N802
        self._apply_shadow(True)
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        self._apply_shadow(False)
        super().leaveEvent(event)

    @property
    def body(self) -> QVBoxLayout:
        return self._layout

    def set_title(self, text: str) -> None:
        self.title_label.setText(text)

    def set_subtitle(self, text: str) -> None:
        self.subtitle_label.setText(text)
        self.subtitle_label.setVisible(bool(text))


class ProfessionalPanel(QFrame):
    """Dense professional-editor panel: no shadow, compact section chrome."""
    def __init__(self, title: str = '', subtitle: str = '', *, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName('ProfessionalPanel')
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(12, 10, 12, 12)
        self._layout.setSpacing(8)
        self.title_label = QLabel(title)
        self.title_label.setObjectName('PanelTitle')
        self.subtitle_label = QLabel(subtitle)
        self.subtitle_label.setObjectName('PanelSubtitle')
        self.subtitle_label.setWordWrap(True)
        self._layout.addWidget(self.title_label)
        self._layout.addWidget(self.subtitle_label)
        self.subtitle_label.setVisible(bool(subtitle))

    @property
    def body(self) -> QVBoxLayout:
        return self._layout

    def set_title(self, text: str) -> None:
        self.title_label.setText(text)

    def set_subtitle(self, text: str) -> None:
        self.subtitle_label.setText(text)
        self.subtitle_label.setVisible(bool(text))


class StatusPill(QLabel):
    """Semantic status badge that follows the active application theme."""
    def __init__(self, text: str = '', parent: QWidget | None = None):
        super().__init__(text, parent)
        self.setAlignment(Qt.AlignCenter)
        self.setMinimumHeight(28)
        self._theme_name='monooled-light'
        self._status='neutral'
        self.set_status('neutral')

    def set_theme(self, theme_name: str) -> None:
        self._theme_name=str(theme_name or 'monooled-light')
        self._apply_status_style()

    def set_status(self, status: str) -> None:
        self._status='error' if status=='danger' else str(status or 'neutral')
        self._apply_status_style()

    def _apply_status_style(self) -> None:
        t=get_theme(self._theme_name)
        status=self._status if self._status in {'neutral','accent','success','warning','error'} else 'neutral'
        bg=t[f'status.{status}.background']
        fg=t[f'status.{status}.foreground']
        self.setStyleSheet(
            f'QLabel {{ background:{bg}; color:{fg}; border-radius:10px; '
            'padding:4px 10px; font-weight:600; }'
        )
