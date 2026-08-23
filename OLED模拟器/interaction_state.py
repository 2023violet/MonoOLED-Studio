from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class FocusOrigin(str, Enum):
    NONE = 'none'
    MOUSE = 'mouse'
    KEYBOARD = 'keyboard'


@dataclass
class ControlInteraction:
    """Pure interaction-state model used by tests and Qt control adapters.

    Selected, hover, pressed and keyboard focus are deliberately independent.
    Disabled is authoritative: a disabled control can never retain hover/press/
    visible keyboard-focus state.
    """

    selected: bool = False
    hovered: bool = False
    pressed: bool = False
    enabled: bool = True
    focus_origin: FocusOrigin = FocusOrigin.NONE
    has_focus: bool = False

    def mouse_enter(self) -> None:
        if self.enabled:
            self.hovered = True

    def mouse_leave(self) -> None:
        self.hovered = False
        self.pressed = False

    def mouse_press(self) -> None:
        if not self.enabled:
            return
        self.focus_origin = FocusOrigin.MOUSE
        self.pressed = True

    def mouse_release(self) -> None:
        self.pressed = False

    def keyboard_focus(self, focused: bool = True) -> None:
        self.has_focus = bool(focused)
        if focused and self.enabled:
            self.focus_origin = FocusOrigin.KEYBOARD
        elif not focused:
            self.focus_origin = FocusOrigin.NONE

    def mouse_focus(self, focused: bool = True) -> None:
        self.has_focus = bool(focused)
        if focused and self.enabled:
            self.focus_origin = FocusOrigin.MOUSE
        elif not focused:
            self.focus_origin = FocusOrigin.NONE

    def set_selected(self, selected: bool) -> None:
        self.selected = bool(selected) if self.enabled else False

    def set_enabled(self, enabled: bool) -> None:
        self.enabled = bool(enabled)
        if not self.enabled:
            self.hovered = False
            self.pressed = False
            self.has_focus = False
            self.focus_origin = FocusOrigin.NONE

    @property
    def keyboard_focus_visible(self) -> bool:
        return self.enabled and self.has_focus and self.focus_origin == FocusOrigin.KEYBOARD

    @property
    def visual_state(self) -> str:
        if not self.enabled:
            return 'disabled'
        if self.pressed:
            return 'pressed'
        if self.selected and self.hovered:
            return 'selected_hover'
        if self.selected:
            return 'selected'
        if self.hovered:
            return 'hover'
        return 'normal'
