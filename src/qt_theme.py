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
    'status.success': QPalette.BrightText,
    'status.warning': QPalette.Accent,
    'status.error': QPalette.ToolTipText,
}

_PALETTE_QSS_NAMES = {
    'app.background': 'window',
    'surface.panel': 'base',
    'surface.canvas': 'alternate-base',
    'surface.toolbar': 'button',
    'surface.hover': 'light',
    'surface.pressed': 'midlight',
    'surface.selected': 'tooltip-base',
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
    'status.success': 'bright-text',
    'status.warning': 'accent',
    'status.error': 'tooltip-text',
}


def _stylesheet_from_tokens(c: dict[str, str], d: dict[str, int]) -> str:
    # Systematic border-radius scale (V9 professional editor refinement):
    # - Panel surfaces (8px): primary containment, popups, lists
    # - Controls (6px): buttons, inputs, tabs, list items - unified hierarchy
    # - Pills (10px): StatusPill - deliberately rounded badges
    # - Menus (5px): ephemeral transient surfaces
    r_panel = d.get('radius_panel', 8)
    r_control = d.get('radius_control', 6)
    r_pill = d.get('radius_pill', 10)
    r_menu = d.get('radius_menu', 5)
    r_popup = max(5, min(6, r_control))

    return f'''
QMainWindow, QWidget#AppRoot {{
    background: {c['app.background']}; color: {c['text.primary']};
    font-family: "Inter", "Segoe UI", "Microsoft YaHei UI", "PingFang SC", sans-serif;
    font-size: {d['font_body']}px;
}}
QWidget {{ color: {c['text.primary']}; }}
QLabel#PageTitle, QLabel#HeroTitle {{ color: {c['text.primary']}; font-size: {d['font_display']}px; font-weight: 600; }}
QLabel#PanelTitle {{ color: {c['text.primary']}; font-size: {d['font_body']}px; font-weight: 600; }}
QLabel#Muted, QLabel#PanelSubtitle, QLabel#SectionEyebrow, QLabel#InspectorSection, QLabel#SettingsHint, QLabel#EmptyStateGuidance {{ color: {c['text.muted']}; font-size: {d['font_metadata']}px; }}
QLabel#SectionEyebrow, QLabel#InspectorSection {{ font-weight: 600; }}
QLabel#EmptyStateTitle, QLabel#ErrorSummary {{ color: {c['text.primary']}; font-size: {d['font_body']}px; font-weight: 600; }}
QLabel#TechnicalValue, QLineEdit#TechnicalInput, QSpinBox#TechnicalInput {{ font-family: "Cascadia Code", "Consolas", "SFMono-Regular", monospace; font-size: {d['font_metadata']}px; }}

/* ACCENT RAIL IS PAINTED AS AN OVERLAY by StudioButton/StudioToolButton.
   Do not encode it as border/padding: interaction must never shift geometry. */
QPushButton {{
    min-height: {d['control']}px; padding: 0 {d['pad']}px; border-radius: {r_control}px;
    border: 1px solid {c['border.subtle']}; background: {c['surface.toolbar']};
    color: {c['text.primary']}; font-weight: 500;
}}
QPushButton[hoverVisible="true"] {{ background: {c['surface.hover']}; border-color: {c['border.normal']}; }}
QPushButton[pressedVisible="true"] {{ background: {c['surface.pressed']}; }}
/* Mouse click may give Qt focus, but visible focus is keyboard-origin only. */
QPushButton[keyboardFocusVisible="true"]:focus {{ border: 1px solid {c['border.focus']}; }}
QPushButton:disabled {{ color: {c['text.disabled']}; background: {c['surface.toolbar']}; border-color: {c['border.subtle']}; }}
QPushButton#PrimaryButton {{ background: {c['accent.primary']}; color: {c['accent.on_primary']}; border: 1px solid {c['accent.primary']}; }}
QPushButton#PrimaryButton[hoverVisible="true"] {{ background: {c['accent.hover']}; }}
QPushButton#PrimaryButton[pressedVisible="true"] {{ background: {c['accent.primary']}; border-color: {c['border.focus']}; }}
QPushButton#PrimaryButton:disabled {{ background: {c['surface.pressed']}; color: {c['text.disabled']}; border-color: {c['border.subtle']}; }}
QPushButton#SecondaryButton {{ background: {c['surface.toolbar']}; border-color: {c['border.subtle']}; }}
QPushButton#SecondaryButton[hoverVisible="true"] {{ background: {c['surface.hover']}; border-color: {c['border.normal']}; }}
QPushButton#SecondaryButton[pressedVisible="true"] {{ background: {c['surface.pressed']}; }}
QPushButton#DangerButton {{ color: {c['status.error']}; background: transparent; }}
QPushButton#DangerButton[hoverVisible="true"] {{ background: {c['surface.hover']}; border-color: {c['status.error']}; }}
QPushButton#DangerButton[pressedVisible="true"] {{ background: {c['surface.pressed']}; }}
QToolButton#GhostButton {{
    min-height: {d['control']}px; padding: 0 {d['pad']}px; border: 1px solid transparent;
    border-radius: {r_control}px; background: transparent; color: {c['text.secondary']};
}}
QToolButton#GhostButton[hoverVisible="true"] {{ background: {c['surface.hover']}; color: {c['text.primary']}; }}
QToolButton#GhostButton[pressedVisible="true"] {{ background: {c['surface.pressed']}; color: {c['text.primary']}; }}
QToolButton#GhostButton[keyboardFocusVisible="true"]:focus {{ border: 1px solid {c['border.focus']}; }}
QToolButton#GhostButton:disabled {{ background: transparent; color: {c['text.disabled']}; border-color: transparent; }}
QToolButton#ToolRailButton {{
    min-width: {d['control']}px; max-width: {d['control']}px; min-height: {d['control']}px; max-height: {d['control']}px;
    border: 1px solid transparent; border-radius: {r_control}px; background: transparent; padding: 0;
    color: {c['text.secondary']}; font-weight: 500;
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
    border-radius: {r_control}px; border: 1px solid {c['border.subtle']}; background: {c['surface.toolbar']};
    color: {c['text.primary']}; font-weight: 500;
}}
QPushButton#StudioSelectButton[popupOpen="true"] {{ background: {c['surface.selected']}; border-color: {c['border.focus']}; }}
QPushButton#StudioSelectButton[hoverVisible="true"] {{ background: {c['surface.hover']}; border-color: {c['border.normal']}; }}
QPushButton#StudioSelectButton[technicalValue="true"] {{ font-family: "Cascadia Code", "Consolas", "SFMono-Regular", monospace; font-size: {d['font_metadata']}px; font-weight: 400; }}
QLabel#StudioSelectChevron {{ color: {c['text.muted']}; background: transparent; }}
QFrame#StudioSelectPopup {{ background: {c['surface.panel']}; border: 1px solid {c['border.normal']}; border-radius: {r_popup}px; }}
QListWidget#StudioSelectList {{ background: {c['surface.panel']}; border: none; padding: 0; outline: none; }}
QListWidget#StudioSelectList QWidget {{ background: {c['surface.panel']}; }}
QListWidget#StudioSelectList::item {{ min-height: {d['row']}px; padding: {d['space_micro']}px {d['space_normal']}px; border-radius: {r_control}px; }}
QListWidget#StudioSelectList::item:hover {{ background: {c['surface.hover']}; }}
QListWidget#StudioSelectList::item:selected {{ background: {c['surface.selected']}; color: {c['accent.primary']}; }}
QSpinBox#StudioNumericInput {{ padding: 0 10px; border-radius: {r_control}px; }}
QPushButton#StudioSegment {{ border-radius: 0px; margin: 0px; border-right-width: 0px; }}
QPushButton#StudioSegment[segmentPosition="first"] {{ border-top-left-radius: {r_control}px; border-bottom-left-radius: {r_control}px; }}
QPushButton#StudioSegment[segmentPosition="last"] {{ border-top-right-radius: {r_control}px; border-bottom-right-radius: {r_control}px; border-right-width: 1px; }}
QPushButton#StudioSegment[segmentPosition="only"] {{ border-radius: {r_control}px; border-right-width: 1px; }}
QPushButton#StudioSegment {{ min-height: {d['control']}px; padding: 0 {d['pad']}px; color: {c['text.secondary']}; font-weight: 500; }}
QPushButton#StudioSegment:checked {{ background: {c['surface.selected']}; color: {c['text.primary']}; border-color: {c['border.normal']}; }}
QPushButton#StudioSegment[hoverVisible="true"] {{ background: {c['surface.hover']}; color: {c['text.primary']}; }}
QPushButton#StudioSegment:checked[hoverVisible="true"] {{ background: {c['accent.soft']}; color: {c['text.primary']}; }}
QPushButton#StudioSegment[keyboardFocusVisible="true"]:focus {{ border-color: {c['border.focus']}; }}
QPushButton#StudioSegment:disabled {{ color: {c['text.disabled']}; background: transparent; }}

QLineEdit, QSpinBox, QComboBox {{
    min-height: {d['control']}px; background: {c['surface.toolbar']}; border: 1px solid {c['border.subtle']};
    border-radius: {r_control}px; padding: 0 8px; color: {c['text.primary']}; selection-background-color: {c['accent.primary']};
}}
/* Focus changes color only; width stays 1px so geometry never jumps. */
QLineEdit:focus, QSpinBox:focus, QComboBox:focus {{ border: 1px solid {c['border.focus']}; background: {c['surface.panel']}; }}
QListWidget, QListView, QPlainTextEdit {{
    background: {c['surface.toolbar']}; border: 1px solid {c['border.subtle']}; border-radius: {r_panel}px;
    padding: 4px; color: {c['text.primary']};
}}
QListWidget::item {{ min-height: {d['row']}px; padding: {d['space_micro']}px {d['space_normal']}px; border-radius: {r_control}px; }}
QListWidget::item:hover {{ background: {c['surface.hover']}; }}
QListWidget::item:selected {{ background: {c['surface.selected']}; color: {c['accent.primary']}; }}
QCheckBox {{ spacing: {d['space_compact']}px; color: {c['text.secondary']}; }}
QTabWidget::pane {{ border: none; background: transparent; }}
QTabBar::tab {{ min-height: 28px; padding: 5px 10px; margin-right: 2px; border-radius: {r_control}px; color: {c['text.secondary']}; }}
QTabBar::tab:hover {{ background: {c['surface.hover']}; }}
QTabBar::tab:selected {{ background: {c['surface.selected']}; color: {c['accent.primary']}; font-weight: 600; }}
QSplitter::handle {{ background: transparent; width: 8px; height: 8px; }}

QWidget#PreferencesRoot {{ background: {c['app.background']}; color: {c['text.primary']}; }}
QLabel#SettingsSaveStatus {{ color: {c['text.muted']}; font-size: {d['font_metadata']}px; padding: 4px 8px; }}
QLabel#SettingsSaveStatus[saveState="saving"] {{ color: {c['accent.primary']}; }}
QLabel#SettingsSaveStatus[saveState="saved"] {{ color: {c['status.success']}; }}
QLabel#SettingsSaveStatus[saveState="failed"] {{ color: {c['status.error']}; }}
QLineEdit#SettingsSearch {{ background: {c['surface.panel']}; border-color: {c['border.subtle']}; }}
QLineEdit#SettingsSearch[searchMiss="true"] {{ border-color: {c['status.error']}; }}
QLineEdit[validationState="error"] {{ border-color: {c['status.error']}; }}
QListWidget#PreferencesNavigation {{ background: transparent; border: none; border-radius: 0; padding: 2px; outline: none; }}
QListWidget#PreferencesNavigation::item {{ min-height: 34px; max-height: 36px; padding: 0 10px; border-radius: {r_control}px; border-left: 2px solid transparent; color: {c['text.secondary']}; }}
QListWidget#PreferencesNavigation::item:hover {{ background: {c['surface.hover']}; color: {c['text.primary']}; }}
QListWidget#PreferencesNavigation::item:selected {{ background: {c['surface.selected']}; color: {c['text.primary']}; border-left: 2px solid {c['accent.primary']}; font-weight: 600; }}
QFrame#PreferencesDangerCard {{ background: {c['surface.panel']}; border: 1px solid {c['status.error']}; border-radius: {r_panel}px; }}
QWidget#PreferencesSection {{ background: transparent; border: none; }}
QFrame#PreferencesSectionDivider, QFrame#SettingRowDivider {{ background: {c['border.subtle']}; min-height: 1px; max-height: 1px; border: none; }}
QLabel#SettingsFieldHelp {{ color: {c['text.muted']}; font-size: {d['font_metadata']}px; }}
QLabel#SettingsSectionTitle {{ color: {c['text.primary']}; font-weight: 600; }}
QLabel#SettingsSectionHelp {{ color: {c['text.muted']}; font-size: {d['font_metadata']}px; }}
QLabel#SettingRowLabel {{ color: {c['text.primary']}; font-weight: 500; }}
QLabel#SettingsFooterProduct {{ color: {c['text.secondary']}; font-weight: 600; padding-left: 10px; }}
QLabel#SettingsFooterVersion {{ color: {c['text.muted']}; font-size: {d['font_metadata']}px; padding: 0 0 6px 10px; }}
QWidget#SettingRow, QWidget#SettingRowContent {{ background: transparent; }}

QWidget#SettingsField {{ background: transparent; }}
QLabel#SearchMatch {{ background: {c['accent.soft']}; color: {c['text.primary']}; border-radius: {r_control}px; }}
QStackedWidget#PreferencesStack, QScrollArea#PreferencesScroll, QWidget#PreferencesViewport, QWidget#PreferencesPage, QWidget#PreferencesContent {{
    background: {c['app.background']}; color: {c['text.primary']};
}}

QScrollArea {{ border: none; background: transparent; }}
QScrollBar:vertical {{ width: 10px; background: transparent; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {c['border.normal']}; min-height: 28px; border-radius: {r_menu}px; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QMenuBar {{ background: {c['app.background']}; color: {c['text.primary']}; }}
QMenuBar::item:selected {{ background: {c['surface.hover']}; border-radius: {r_menu}px; }}
QMenu {{ background: {c['surface.panel']}; color: {c['text.primary']}; border: 1px solid {c['border.subtle']}; padding: {d['space_tight']}px; }}
QMenu::item {{ min-height: {d['row']}px; padding: 0 {d['space_section']}px 0 {d['space_group']}px; border-radius: {r_menu}px; }}
QMenu::item:selected {{ background: {c['surface.selected']}; color: {c['accent.primary']}; }}
QStatusBar {{ background: {c['app.background']}; color: {c['text.secondary']}; }}

QWidget#EditorCommandBar, QWidget#PixelCommandBar {{ background: {c['app.background']}; border-bottom: 1px solid {c['border.subtle']}; }}
QWidget#CommandBarLeft, QWidget#CommandBarCenter, QWidget#CommandBarRight {{ background: transparent; }}
QFrame#ProfessionalPanel {{ background: {c['surface.panel']}; border: 1px solid {c['border.subtle']}; border-radius: {r_panel}px; }}
QFrame#CanvasWorkspace {{ background: {c['surface.canvas']}; border: 1px solid {c['border.normal']}; border-radius: {r_panel}px; }}
QFrame#CanvasWorkspace[canvasFocus="true"] {{ border-color: {c['border.focus']}; }}
QWidget#CanvasViewport {{ background: {c['surface.canvas']}; }}
QWidget#InspectorRoot, QWidget#WorkspaceRail {{ background: {c['surface.toolbar']}; }}
QWidget#ToolRail {{ background: {c['surface.toolbar']}; border-right: 1px solid {c['border.subtle']}; }}
QFrame#SectionDivider {{ background: {c['border.subtle']}; min-height: 1px; max-height: 1px; border: none; }}
QLabel#ErrorText {{ color: {c['status.error']}; font-size: {d['font_metadata']}px; }}
QLabel#ErrorSummary {{ color: {c['status.error']}; }}
QLabel#EmptyStateGuidance {{ padding-top: {d['space_tight']}px; }}
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
