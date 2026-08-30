from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout, QWidget

from theme_system import get_theme
from ui_metrics import build_ui_metrics


class ProfessionalPanel(QFrame):
    """Dense professional-editor panel with semantic header/body rhythm."""
    def __init__(self, title: str = '', subtitle: str = '', *, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName('ProfessionalPanel')
        self._layout = QVBoxLayout(self)
        self.title_label = QLabel(title)
        self.title_label.setObjectName('PanelTitle')
        self.subtitle_label = QLabel(subtitle)
        self.subtitle_label.setObjectName('PanelSubtitle')
        self.subtitle_label.setWordWrap(True)
        self._body = QVBoxLayout()
        self._layout.addWidget(self.title_label)
        self._layout.addWidget(self.subtitle_label)
        self._layout.addLayout(self._body)
        self.title_label.setVisible(bool(title))
        self.subtitle_label.setVisible(bool(subtitle))
        self.apply_metrics(build_ui_metrics())

    @property
    def body(self) -> QVBoxLayout:
        return self._body

    def apply_metrics(self, metrics: dict[str, int]) -> None:
        pad=int(metrics.get('panel_margin',10))
        self._layout.setContentsMargins(pad,pad,pad,pad)
        self._layout.setSpacing(int(metrics.get('space_group',12)))
        self._body.setSpacing(int(metrics.get('space_normal',8)))

    def set_title(self, text: str) -> None:
        self.title_label.setText(text)
        self.title_label.setVisible(bool(text))

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
        # StatusPill uses 10px radius - distinctly rounded pill shape (V9 systematic scale)
        self.setStyleSheet(
            f'QLabel {{ background:{bg}; color:{fg}; border-radius:10px; '
            'padding:4px 10px; font-weight:600; }'
        )
