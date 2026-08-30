from __future__ import annotations

import ctypes
import os
from typing import Mapping

from theme_system import get_theme, is_dark_theme

# Windows 11 DWM attributes. Calls are best-effort because older Windows builds
# may reject individual attributes while preserving normal native window chrome.
_DWMWA_USE_IMMERSIVE_DARK_MODE = 20
_DWMWA_BORDER_COLOR = 34
_DWMWA_CAPTION_COLOR = 35
_DWMWA_TEXT_COLOR = 36


def _colorref(value: str) -> int:
    text=str(value or '#000000').lstrip('#')
    if len(text) != 6:
        text='000000'
    r,g,b=(int(text[i:i+2],16) for i in (0,2,4))
    return r | (g << 8) | (b << 16)


def apply_windows_chrome(window, theme_name: str, tokens: Mapping[str, str] | None = None) -> bool:
    """Match the native Windows caption to the active theme without frameless chrome.

    Returns True when at least one DWM attribute call succeeds. On non-Windows,
    unsupported Windows versions, or invalid/native handles this is a no-op.
    """
    if os.name != 'nt' or window is None:
        return False
    try:
        hwnd=ctypes.c_void_p(int(window.winId()))
        dwm=ctypes.windll.dwmapi.DwmSetWindowAttribute
        palette=dict(tokens or get_theme(theme_name))
        values=(
            (_DWMWA_USE_IMMERSIVE_DARK_MODE, ctypes.c_int(1 if is_dark_theme(theme_name) else 0)),
            (_DWMWA_BORDER_COLOR, ctypes.c_uint(_colorref(palette.get('border.normal','#3B4048')))),
            (_DWMWA_CAPTION_COLOR, ctypes.c_uint(_colorref(palette.get('surface.toolbar','#252931')))),
            (_DWMWA_TEXT_COLOR, ctypes.c_uint(_colorref(palette.get('text.primary','#ABB2BF')))),
        )
        applied=False
        for attribute,value in values:
            try:
                result=dwm(hwnd, ctypes.c_uint(attribute), ctypes.byref(value), ctypes.sizeof(value))
                applied = applied or result == 0
            except (OSError, AttributeError, TypeError, ValueError):
                continue
        return applied
    except (OSError, AttributeError, TypeError, ValueError):
        return False
