from __future__ import annotations

from copy import deepcopy

REQUIRED_TOKENS = (
    'app.background', 'surface.panel', 'surface.canvas', 'surface.toolbar',
    'surface.hover', 'surface.pressed', 'surface.selected',
    'text.primary', 'text.secondary', 'text.muted', 'text.disabled',
    'border.normal', 'border.subtle', 'border.focus',
    'accent.primary', 'accent.hover', 'accent.soft', 'accent.on_primary',
    'status.success', 'status.warning', 'status.error',
    'status.neutral.background','status.neutral.foreground',
    'status.accent.background','status.accent.foreground',
    'status.success.background','status.success.foreground',
    'status.warning.background','status.warning.foreground',
    'status.error.background','status.error.foreground',
    'popover.shadow','overlay.scrim',
    'canvas.grid', 'canvas.guide', 'canvas.selection',
)

_THEMES = {
    'monooled-light': {
        'app.background': '#F5F5F7', 'surface.panel': '#FFFFFF', 'surface.canvas': '#FFFFFF', 'surface.toolbar': '#F8F8FA',
        'surface.hover': '#ECECF1', 'surface.pressed': '#E1E1E8', 'surface.selected': '#DCEBFA',
        'text.primary': '#1D1D1F', 'text.secondary': '#5E5E63', 'text.muted': '#6E6E73', 'text.disabled': '#AEAEB2',
        'border.normal': '#D2D2D7', 'border.subtle': '#E5E5EA', 'border.focus': '#0A84FF',
        'accent.primary': '#0071E3', 'accent.hover': '#147CE5', 'accent.soft': '#DCEBFA', 'accent.on_primary': '#FFFFFF',
        'status.success': '#248A3D', 'status.warning': '#B35C00', 'status.error': '#D70015',
        'status.neutral.background':'#F2F2F7','status.neutral.foreground':'#5E5E63','status.accent.background':'#DCEBFA','status.accent.foreground':'#0066CC','status.success.background':'#EAF8EE','status.success.foreground':'#1D6F31','status.warning.background':'#FFF4E5','status.warning.foreground':'#8A4600','status.error.background':'#FDEBEC','status.error.foreground':'#B00012','popover.shadow':'#33000000','overlay.scrim':'#66000000',
        'canvas.grid': '#343438', 'canvas.guide': '#FF9F0A', 'canvas.selection': '#0A84FF',
    },
    'monooled-dark': {
        'app.background': '#151517', 'surface.panel': '#1E1E21', 'surface.canvas': '#171719', 'surface.toolbar': '#232326',
        'surface.hover': '#2B2B30', 'surface.pressed': '#34343A', 'surface.selected': '#173A5E',
        'text.primary': '#F5F5F7', 'text.secondary': '#C7C7CC', 'text.muted': '#98989D', 'text.disabled': '#636366',
        'border.normal': '#3A3A3F', 'border.subtle': '#2D2D31', 'border.focus': '#64D2FF',
        'accent.primary': '#409CFF', 'accent.hover': '#64B5FF', 'accent.soft': '#173A5E', 'accent.on_primary': '#000000',
        'status.success': '#30D158', 'status.warning': '#FF9F0A', 'status.error': '#FF453A',
        'status.neutral.background':'#2B2B30','status.neutral.foreground':'#C7C7CC','status.accent.background':'#173A5E','status.accent.foreground':'#8CC8FF','status.success.background':'#143D24','status.success.foreground':'#65E580','status.warning.background':'#4A2D08','status.warning.foreground':'#FFC45C','status.error.background':'#4A1C1A','status.error.foreground':'#FF8A84','popover.shadow':'#99000000','overlay.scrim':'#99000000',
        'canvas.grid': '#343438', 'canvas.guide': '#FFD60A', 'canvas.selection': '#64D2FF',
    },
    'one-dark-pro': {
        'app.background': '#21252B', 'surface.panel': '#282C34', 'surface.canvas': '#1E2227', 'surface.toolbar': '#252931',
        'surface.hover': '#333842', 'surface.pressed': '#3A404B', 'surface.selected': '#2C4058',
        'text.primary': '#ABB2BF', 'text.secondary': '#9DA5B4', 'text.muted': '#9DA5B4', 'text.disabled': '#5C6370',
        'border.normal': '#3B4048', 'border.subtle': '#30343B', 'border.focus': '#61AFEF',
        'accent.primary': '#61AFEF', 'accent.hover': '#7CC1F7', 'accent.soft': '#2C4058', 'accent.on_primary': '#000000',
        'status.success': '#98C379', 'status.warning': '#E5C07B', 'status.error': '#E06C75',
        'status.neutral.background':'#333842','status.neutral.foreground':'#C8CFDA','status.accent.background':'#2C4058','status.accent.foreground':'#8BC8F3','status.success.background':'#31402D','status.success.foreground':'#B2D89C','status.warning.background':'#493E28','status.warning.foreground':'#F3D391','status.error.background':'#4A3036','status.error.foreground':'#F199A1','popover.shadow':'#88000000','overlay.scrim':'#88000000',
        'canvas.grid': '#3A3F47', 'canvas.guide': '#E5C07B', 'canvas.selection': '#61AFEF',
    },
    'high-contrast': {
        'app.background': '#000000', 'surface.panel': '#000000', 'surface.canvas': '#000000', 'surface.toolbar': '#000000',
        'surface.hover': '#202020', 'surface.pressed': '#303030', 'surface.selected': '#002A55',
        'text.primary': '#FFFFFF', 'text.secondary': '#FFFFFF', 'text.muted': '#D8D8D8', 'text.disabled': '#888888',
        'border.normal': '#FFFFFF', 'border.subtle': '#A0A0A0', 'border.focus': '#00D8FF',
        'accent.primary': '#00A8FF', 'accent.hover': '#00D8FF', 'accent.soft': '#002A55', 'accent.on_primary': '#000000',
        'status.success': '#00FF6A', 'status.warning': '#FFD400', 'status.error': '#FF3B30',
        'status.neutral.background':'#000000','status.neutral.foreground':'#FFFFFF','status.accent.background':'#002A55','status.accent.foreground':'#FFFFFF','status.success.background':'#003A18','status.success.foreground':'#FFFFFF','status.warning.background':'#4A3D00','status.warning.foreground':'#FFFFFF','status.error.background':'#4A0000','status.error.foreground':'#FFFFFF','popover.shadow':'#FF000000','overlay.scrim':'#CC000000',
        'canvas.grid': '#505050', 'canvas.guide': '#FFD400', 'canvas.selection': '#00D8FF',
    },
}

THEME_NAMES = tuple(_THEMES)


def get_theme(name: str) -> dict[str, str]:
    key = str(name or '').strip().lower()
    if key not in _THEMES:
        key = 'monooled-light'
    result = deepcopy(_THEMES[key])
    missing = [token for token in REQUIRED_TOKENS if token not in result]
    if missing:
        raise KeyError(f'theme {key} missing semantic tokens: {missing}')
    return result


def is_dark_theme(name: str) -> bool:
    return str(name).lower() in {'monooled-dark', 'one-dark-pro', 'high-contrast'}


def resolve_theme_name(name: str, mode: str = 'system', *, system_dark: bool = False) -> str:
    requested = str(name or 'monooled-light').strip().lower()
    if requested not in _THEMES:
        requested = 'monooled-light'
    mode = str(mode or 'system').strip().lower()
    if mode == 'light':
        return 'monooled-light'
    if mode == 'dark':
        return requested if requested in {'one-dark-pro', 'high-contrast'} else 'monooled-dark'
    if mode != 'system':
        mode = 'system'
    if requested in {'one-dark-pro', 'high-contrast'}:
        return requested
    return 'monooled-dark' if system_dark else 'monooled-light'
