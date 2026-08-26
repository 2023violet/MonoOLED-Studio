from __future__ import annotations

from PySide6.QtGui import QColor, QPalette

from theme_system import get_theme
from ui_metrics import build_ui_metrics

# Legacy paint code imports COLORS directly. Keep a stable light-theme compatibility
# mapping while the stylesheet itself is fully semantic/theme-driven.
_LIGHT = get_theme('monooled-light')
COLORS = {
    'app_bg': _LIGHT['app.background'],
    'card': _LIGHT['surface.panel'],
    'card_soft': _LIGHT['surface.toolbar'],
    'text': _LIGHT['text.primary'],
    'text_secondary': '#6E6E73',
    'text_muted': '#86868B',
    'text_tertiary': '#6E6E73',
    'separator': _LIGHT['border.normal'],
    'separator_soft': _LIGHT['border.subtle'],
    'accent': _LIGHT['accent.primary'],
    'accent_hover': _LIGHT['accent.hover'],
    'success': _LIGHT['status.success'],
    'warning': _LIGHT['status.warning'],
    'danger': _LIGHT['status.error'],
    'oled_bg': '#000000',
    'oled_fg': '#FFFFFF',
    'canvas_surround': _LIGHT['surface.canvas'],
    'canvas_border': _LIGHT['border.normal'],
    'selection': _LIGHT['canvas.selection'],
    'overlay': _LIGHT['text.muted'],
}

METRICS = {
    'grid': 8,
    'gap': 20,
    'radius_large': 24,
    'radius_medium': 20,
    'radius_small': 16,
    'radius_inner': 12,
    'padding_large': 20,
    'padding_medium': 14,
    'padding_small': 10,
    'shadow_blur': 14, 'shadow_hover_blur': 18,
    'shadow_alpha': 24, 'shadow_hover_alpha': 34,
}

_DENSITY = {
    'compact': {'control': 28, 'pad': 8, 'row': 28},
    'comfortable': {'control': 32, 'pad': 10, 'row': 32},
    'spacious': {'control': 36, 'pad': 12, 'row': 38},
}


SEMANTIC_PALETTE_ROLES = {
    'app.background': QPalette.Window,
    'surface.panel': QPalette.Base,
    'surface.canvas': QPalette.AlternateBase,
    'surface.toolbar': QPalette.Button,
    'surface.hover': QPalette.Light,
    'surface.pressed': QPalette.Midlight,
    'surface.selected': QPalette.ToolTipBase,
    'text.primary': QPalette.WindowText,
    'text.secondary': QPalette.Text,
    'text.muted': QPalette.PlaceholderText,
    'text.disabled': QPalette.ButtonText,
    'border.normal': QPalette.Dark,
    'border.subtle': QPalette.Mid,
    'border.focus': QPalette.Link,
    'accent.primary': QPalette.Highlight,
    'accent.hover': QPalette.LinkVisited,
    'accent.soft': QPalette.Shadow,
    'accent.on_primary': QPalette.HighlightedText,
    'status.error': QPalette.ToolTipText,
}

_PALETTE_QSS_NAMES = {
    'app.background': 'window',
    'surface.panel': 'base',
    'surface.canvas': 'alternate-base',
    'surface.toolbar': 'button',
    'surface.hover': 'light',
    'surface.pressed': 'midlight',
    'surface.selected': 'tool-tip-base',
    'text.primary': 'window-text',
    'text.secondary': 'text',
    'text.muted': 'placeholder-text',
    'text.disabled': 'button-text',
    'border.normal': 'dark',
    'border.subtle': 'mid',
    'border.focus': 'link',
    'accent.primary': 'highlight',
    'accent.hover': 'link-visited',
    'accent.soft': 'shadow',
    'accent.on_primary': 'highlighted-text',
    'status.error': 'tool-tip-text',
}


def _stylesheet_from_tokens(c: dict[str, str], d: dict[str, int]) -> str:
    return f'''
QMainWindow, QWidget#AppRoot {{
    background: {c['app.background']}; color: {c['text.primary']};
    font-family: "Inter", "Segoe UI", "Microsoft YaHei UI", "PingFang SC", sans-serif;
    font-size: {d['font_body']}px;
}}
QWidget {{ color: {c['text.primary']}; }}
QFrame#BentoCard, QFrame#BentoMediumCard, QFrame#BentoSmallCard {{
    background: {c['surface.panel']}; border: 1px solid {c['border.subtle']}; border-radius: 10px;
}}
QLabel#CardTitle {{ color: {c['text.primary']}; font-size: {d['font_heading']}px; font-weight: 600; }}
QLabel#CardSubtitle, QLabel#Muted, QLabel#PanelSubtitle {{ color: {c['text.muted']}; font-size: {d['font_small']}px; }}
QLabel#HeroTitle {{ color: {c['text.primary']}; font-size: {max(d['font_heading']+8,d['font_heading'])}px; font-weight: 600; }}
QLabel#SectionEyebrow, QLabel#InspectorSection {{ color: {c['text.muted']}; font-size: {max(9,d['font_small']-2)}px; font-weight: 700; }}
QLabel#PanelTitle {{ color: {c['text.primary']}; font-size: {d['font_body']}px; font-weight: 700; }}

QPushButton {{
    min-height: {d['control']}px; padding: 0 {d['pad']}px; border-radius: 7px;
    border: 1px solid {c['border.subtle']}; background: {c['surface.toolbar']};
    color: {c['text.primary']}; font-weight: 600;
}}
QPushButton[hoverVisible="true"] {{ background: {c['surface.hover']}; border-color: {c['border.normal']}; }}
QPushButton[pressedVisible="true"] {{ background: {c['surface.pressed']}; }}
/* Mouse click may give Qt focus, but visible focus is keyboard-origin only. */
QPushButton[keyboardFocusVisible="true"]:focus {{ border: 1px solid {c['border.focus']}; }}
QPushButton:disabled {{ color: {c['text.disabled']}; background: {c['surface.toolbar']}; border-color: {c['border.subtle']}; }}
QPushButton#PrimaryButton {{ background: {c['accent.primary']}; color: {c['accent.on_primary']}; border: 1px solid {c['accent.primary']}; }}
QPushButton#PrimaryButton[hoverVisible="true"] {{ background: {c['accent.hover']}; }}
QPushButton#SecondaryButton {{ background: {c['surface.toolbar']}; border-color: {c['border.subtle']}; }}
QPushButton#SecondaryButton[hoverVisible="true"] {{ background: {c['surface.hover']}; }}
QPushButton#DangerButton {{ color: {c['status.error']}; }}

QToolButton#GhostButton {{
    min-height: {d['control']}px; padding: 0 {d['pad']}px; border: 1px solid transparent;
    border-radius: 7px; background: transparent; color: {c['text.secondary']};
}}
QToolButton#GhostButton[hoverVisible="true"] {{ background: {c['surface.hover']}; color: {c['text.primary']}; }}
QToolButton#GhostButton[keyboardFocusVisible="true"]:focus {{ border: 1px solid {c['border.focus']}; }}
QToolButton#ToolRailButton {{
    min-width: 38px; min-height: 38px; max-width: 38px;
    border: 1px solid transparent; border-radius: 7px; background: transparent;
    color: {c['text.secondary']}; font-weight: 700;
}}
QToolButton#ToolRailButton[hoverVisible="true"] {{ background: {c['surface.hover']}; color: {c['text.primary']}; }}
QToolButton#ToolRailButton[pressedVisible="true"] {{ background: {c['surface.pressed']}; }}
QToolButton#ToolRailButton:checked {{ background: {c['surface.selected']}; color: {c['accent.primary']}; border: 1px solid transparent; }}
QToolButton#ToolRailButton:checked[hoverVisible="true"] {{ background: {c['accent.soft']}; color: {c['accent.hover']}; }}
QToolButton#ToolRailButton[keyboardFocusVisible="true"]:focus {{ border: 1px solid {c['border.focus']}; }}
QToolButton#ToolRailButton:disabled {{ color: {c['text.disabled']}; background: transparent; border: 1px solid transparent; }}

QWidget#StudioSelect {{ background: transparent; }}
QPushButton#StudioSelectButton {{
    min-height: {d['control']}px; padding: 0 30px 0 10px; text-align: left;
    border-radius: 8px; border: 1px solid {c['border.subtle']}; background: {c['surface.toolbar']};
    color: {c['text.primary']}; font-weight: 500;
}}
QPushButton#StudioSelectButton[popupOpen="true"] {{ background: {c['surface.selected']}; border-color: {c['border.focus']}; }}
QPushButton#StudioSelectButton[hoverVisible="true"] {{ background: {c['surface.hover']}; border-color: {c['border.normal']}; }}
QLabel#StudioSelectChevron {{ color: {c['text.muted']}; background: transparent; }}
QFrame#StudioSelectPopup {{ background: {c['surface.panel']}; border: 1px solid {c['border.normal']}; border-radius: 10px; }}
QListWidget#StudioSelectList {{ background: {c['surface.panel']}; border: none; padding: 0; outline: none; }}
QListWidget#StudioSelectList QWidget {{ background: {c['surface.panel']}; }}
QListWidget#StudioSelectList::item {{ min-height: {d['row']}px; padding: 2px 9px; border-radius: 7px; }}
QListWidget#StudioSelectList::item:hover {{ background: {c['surface.hover']}; }}
QListWidget#StudioSelectList::item:selected {{ background: {c['surface.selected']}; color: {c['accent.primary']}; }}
QSpinBox#StudioNumericInput {{ padding: 0 10px; border-radius: 8px; }}
QPushButton#StudioSegment {{ border-radius: 0px; margin: 0px; }}
QPushButton#StudioSegment:checked {{ background: {c['surface.selected']}; color: {c['accent.primary']}; border-color: {c['border.normal']}; }}

QLineEdit, QSpinBox, QComboBox {{
    min-height: {d['control']}px; background: {c['surface.toolbar']}; border: 1px solid {c['border.subtle']};
    border-radius: 7px; padding: 0 8px; color: {c['text.primary']}; selection-background-color: {c['accent.primary']};
}}
/* Focus changes color only; width stays 1px so geometry never jumps. */
QLineEdit:focus, QSpinBox:focus, QComboBox:focus {{ border: 1px solid {c['border.focus']}; background: {c['surface.panel']}; }}
QListWidget, QListView, QPlainTextEdit {{
    background: {c['surface.toolbar']}; border: 1px solid {c['border.subtle']}; border-radius: 8px;
    padding: 4px; color: {c['text.primary']};
}}
QListWidget::item {{ min-height: {d['row']}px; padding: 2px 7px; border-radius: 6px; }}
QListWidget::item:hover {{ background: {c['surface.hover']}; }}
QListWidget::item:selected {{ background: {c['surface.selected']}; color: {c['accent.primary']}; }}
QCheckBox {{ spacing: 7px; color: {c['text.secondary']}; }}
QTabWidget::pane {{ border: none; background: transparent; }}
QTabBar::tab {{ min-height: 28px; padding: 5px 10px; margin-right: 2px; border-radius: 6px; color: {c['text.secondary']}; }}
QTabBar::tab:hover {{ background: {c['surface.hover']}; }}
QTabBar::tab:selected {{ background: {c['surface.selected']}; color: {c['accent.primary']}; font-weight: 600; }}
QSplitter::handle {{ background: transparent; width: 8px; height: 8px; }}

QWidget#PreferencesRoot {{ background: {c['app.background']}; color: {c['text.primary']}; }}
QListWidget#PreferencesNavigation {{ background: {c['surface.toolbar']}; border: 1px solid {c['border.subtle']}; }}
QStackedWidget#PreferencesStack, QScrollArea#PreferencesScroll, QWidget#PreferencesViewport, QWidget#PreferencesPage {{
    background: {c['app.background']}; color: {c['text.primary']};
}}

QScrollArea {{ border: none; background: transparent; }}
QScrollBar:vertical {{ width: 10px; background: transparent; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {c['border.normal']}; min-height: 28px; border-radius: 5px; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QMenuBar {{ background: {c['app.background']}; color: {c['text.primary']}; }}
QMenuBar::item:selected {{ background: {c['surface.hover']}; border-radius: 5px; }}
QMenu {{ background: {c['surface.panel']}; color: {c['text.primary']}; border: 1px solid {c['border.subtle']}; padding: 5px; }}
QMenu::item {{ padding: 7px 24px 7px 12px; border-radius: 5px; }}
QMenu::item:selected {{ background: {c['surface.selected']}; color: {c['accent.primary']}; }}
QStatusBar {{ background: {c['app.background']}; color: {c['text.secondary']}; }}

QFrame#ProfessionalPanel {{ background: {c['surface.panel']}; border: 1px solid {c['border.subtle']}; border-radius: 8px; }}
QFrame#CanvasWorkspace {{ background: {c['surface.canvas']}; border: 1px solid {c['border.normal']}; border-radius: 8px; }}
QWidget#InspectorRoot, QWidget#WorkspaceRail {{ background: {c['surface.toolbar']}; }}
QWidget#ToolRail {{ background: {c['surface.toolbar']}; border-right: 1px solid {c['border.subtle']}; }}
QFrame#SectionDivider {{ background: {c['border.subtle']}; min-height: 1px; max-height: 1px; border: none; }}
QToolTip {{ background: {c['text.primary']}; color: {c['app.background']}; border: none; padding: 6px; }}
'''.strip()


def build_stylesheet(theme_name: str = 'monooled-light', density: str = 'comfortable', ui_scale: float = 1.0) -> str:
    return _stylesheet_from_tokens(get_theme(theme_name), build_ui_metrics(density, ui_scale))


def build_theme_palette(theme_name: str = 'monooled-light') -> QPalette:
    theme = get_theme(theme_name)
    palette = QPalette()
    for token, role in SEMANTIC_PALETTE_ROLES.items():
        palette.setColor(role, QColor(theme[token]))
    return palette


def build_adaptive_stylesheet(density: str = 'comfortable', ui_scale: float = 1.0) -> str:
    tokens = {token: f'palette({name})' for token, name in _PALETTE_QSS_NAMES.items()}
    return _stylesheet_from_tokens(tokens, build_ui_metrics(density, ui_scale))
