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
        'app.background': '#faf9f6', 'surface.panel': '#ffffff', 'surface.canvas': '#f3f3ef', 'surface.toolbar': '#fcfbf7',
        'surface.hover': '#f0eee8', 'surface.pressed': '#e6e3da', 'surface.selected': '#d9ece9',
        'text.primary': '#202a30', 'text.secondary': '#59656b', 'text.muted': '#657176', 'text.disabled': '#9aa5a6',
        'border.normal': '#dfe4e1', 'border.subtle': '#e9ede9', 'border.focus': '#176b75',
        'accent.primary': '#176b75', 'accent.hover': '#12565e', 'accent.soft': '#d9ece9', 'accent.on_primary': '#ffffff',
        'status.success': '#2f7d5c', 'status.warning': '#b8873a', 'status.error': '#b3402a',
        'status.neutral.background':'#f0efe9','status.neutral.foreground':'#59656b','status.accent.background':'#d9ece9','status.accent.foreground':'#12565e','status.success.background':'#e3f1e7','status.success.foreground':'#256b4a','status.warning.background':'#f5ecd9','status.warning.foreground':'#8a6529','status.error.background':'#f7e6e0','status.error.foreground':'#8f3522','popover.shadow':'#33000000','overlay.scrim':'#66000000',
        'canvas.grid': '#343438', 'canvas.guide': '#FF9F0A', 'canvas.selection': '#176b75',
    },
    'monooled-dark': {
        'app.background': '#13191c', 'surface.panel': '#1a2226', 'surface.canvas': '#10161a', 'surface.toolbar': '#202a2f',
        'surface.hover': '#232e33', 'surface.pressed': '#28343a', 'surface.selected': '#10393c',
        'text.primary': '#e7eceb', 'text.secondary': '#a5b0b3', 'text.muted': '#89979d', 'text.disabled': '#5f6b70',
        'border.normal': '#2c373c', 'border.subtle': '#263034', 'border.focus': '#12ccd8',
        'accent.primary': '#12ccd8', 'accent.hover': '#2ce2e8', 'accent.soft': '#0e3f44', 'accent.on_primary': '#000000',
        'status.success': '#5fc79a', 'status.warning': '#d3b26a', 'status.error': '#d86a52',
        'status.neutral.background':'#232e33','status.neutral.foreground':'#a5b0b3','status.accent.background':'#0e3f44','status.accent.foreground':'#7ce8ec','status.success.background':'#16402c','status.success.foreground':'#8ad9b4','status.warning.background':'#40351a','status.warning.foreground':'#e3c98c','status.error.background':'#45231c','status.error.foreground':'#eb9a85','popover.shadow':'#99000000','overlay.scrim':'#99000000',
        'canvas.grid': '#343438', 'canvas.guide': '#FFD60A', 'canvas.selection': '#12ccd8',
    },
    'one-dark-pro': {
        'app.background': '#13191c', 'surface.panel': '#1a2226', 'surface.canvas': '#10161a', 'surface.toolbar': '#202a2f',
        'surface.hover': '#232e33', 'surface.pressed': '#28343a', 'surface.selected': '#10393c',
        'text.primary': '#e7eceb', 'text.secondary': '#a5b0b3', 'text.muted': '#89979d', 'text.disabled': '#5f6b70',
        'border.normal': '#2c373c', 'border.subtle': '#263034', 'border.focus': '#12ccd8',
        'accent.primary': '#12ccd8', 'accent.hover': '#2ce2e8', 'accent.soft': '#0e3f44', 'accent.on_primary': '#000000',
        'status.success': '#5fc79a', 'status.warning': '#d3b26a', 'status.error': '#d86a52',
        'status.neutral.background':'#232e33','status.neutral.foreground':'#a5b0b3','status.accent.background':'#0e3f44','status.accent.foreground':'#7ce8ec','status.success.background':'#16402c','status.success.foreground':'#8ad9b4','status.warning.background':'#40351a','status.warning.foreground':'#e3c98c','status.error.background':'#45231c','status.error.foreground':'#eb9a85','popover.shadow':'#99000000','overlay.scrim':'#99000000',
        'canvas.grid': '#343438', 'canvas.guide': '#FFD60A', 'canvas.selection': '#12ccd8',
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
    """Resolve the single product appearance policy.

    ``name`` is retained only for backward API/file compatibility.  User-visible
    appearance is intentionally controlled by mode alone: Light is MonoOLED
    Light, Dark is the approved One Dark Pro surface, and System follows the OS.
    """
    _ = name
    mode = str(mode or 'system').strip().lower()
    if mode == 'light':
        return 'monooled-light'
    if mode == 'dark':
        return 'one-dark-pro'
    return 'one-dark-pro' if bool(system_dark) else 'monooled-light'
