from __future__ import annotations

from enum import Enum


class PopupInteractionState(str, Enum):
    CLOSED = 'closed'
    OPENING = 'opening'
    OPEN = 'open'
    CLOSING = 'closing'
    COMMIT_PENDING = 'commit_pending'
    DISABLED = 'disabled'


class CloseReason(str, Enum):
    ANCHOR_TOGGLE = 'anchor_toggle'
    ITEM_COMMIT = 'item_commit'
    ESCAPE = 'escape'
    OUTSIDE_CLICK = 'outside_click'
    OTHER_POPUP_OPEN = 'other_popup_open'
    OWNER_HIDDEN = 'owner_hidden'
    TAB_SWITCH = 'tab_switch'
    WINDOW_DEACTIVATE = 'window_deactivate'
    THEME_CHANGE = 'theme_change'
    LANGUAGE_CHANGE = 'language_change'
    DPI_CHANGE = 'dpi_change'
    PROGRAMMATIC = 'programmatic'
    DISABLED = 'disabled'


class PopupStateMachine:
    """Qt-independent select popup interaction state.

    The state machine deliberately tracks a one-shot suppressed anchor click.
    Qt.Popup may auto-close on the mouse press that lands on the anchor; the
    button's later clicked signal must not immediately reopen the popup.
    """

    def __init__(self) -> None:
        self.state = PopupInteractionState.CLOSED
        self.close_reason: CloseReason | None = None
        self._suppress_anchor_click = False

    def anchor_press(self) -> str:
        if self.state is PopupInteractionState.DISABLED:
            return 'none'
        if self.state in (PopupInteractionState.OPEN, PopupInteractionState.OPENING, PopupInteractionState.COMMIT_PENDING):
            self.state = PopupInteractionState.CLOSING
            self.close_reason = CloseReason.ANCHOR_TOGGLE
            return 'close'
        if self.state is PopupInteractionState.CLOSING:
            return 'none'
        self.state = PopupInteractionState.OPENING
        self.close_reason = None
        return 'open'

    def opened(self) -> None:
        if self.state is not PopupInteractionState.DISABLED:
            self.state = PopupInteractionState.OPEN
            self.close_reason = None

    def begin_commit(self) -> None:
        if self.state is not PopupInteractionState.DISABLED:
            self.state = PopupInteractionState.COMMIT_PENDING
            self.close_reason = CloseReason.ITEM_COMMIT

    def closed(self, reason: CloseReason, *, owner_anchor: bool = False) -> None:
        self.state = PopupInteractionState.CLOSED
        self.close_reason = reason
        if reason is CloseReason.ANCHOR_TOGGLE or (reason is CloseReason.OUTSIDE_CLICK and owner_anchor):
            self._suppress_anchor_click = True

    @property
    def anchor_suppressed(self) -> bool:
        return bool(self._suppress_anchor_click)

    def consume_anchor_click(self) -> bool:
        """Return whether the current physical anchor gesture is suppressed.

        Suppression is deliberately *not* cleared here.  Native Qt.Popup can
        close on mouse press while QAbstractButton emits clicked on release;
        clearing at the first callback creates a close-then-reopen race.
        The release boundary owns the reset.
        """
        return bool(self._suppress_anchor_click)

    def release_anchor_suppression(self) -> None:
        self._suppress_anchor_click = False

    def clear_anchor_suppression(self) -> None:
        # Backward-compatible alias for non-pointer callers/tests.
        self.release_anchor_suppression()

    def set_enabled(self, enabled: bool) -> None:
        if enabled:
            if self.state is PopupInteractionState.DISABLED:
                self.state = PopupInteractionState.CLOSED
            return
        self.state = PopupInteractionState.DISABLED
        self.close_reason = CloseReason.DISABLED
        self._suppress_anchor_click = False
