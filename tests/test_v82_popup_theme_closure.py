from pathlib import Path

import pytest

from popup_geometry import content_popup_width
from popup_state import CloseReason, PopupInteractionState, PopupStateMachine

ROOT = Path(__file__).resolve().parents[1] / 'src'


def test_popup_state_machine_second_anchor_click_closes_without_reopen():
    sm = PopupStateMachine()
    assert sm.state is PopupInteractionState.CLOSED
    assert sm.anchor_press() == 'open'
    sm.opened()
    assert sm.state is PopupInteractionState.OPEN
    assert sm.anchor_press() == 'close'
    sm.closed(CloseReason.ANCHOR_TOGGLE)
    assert sm.state is PopupInteractionState.CLOSED
    # The click/release belonging to the same physical second press stays
    # suppressed until the real release boundary is observed.
    assert sm.consume_anchor_click() is True
    assert sm.state is PopupInteractionState.CLOSED
    assert sm.consume_anchor_click() is True
    sm.release_anchor_suppression()
    # The following independent click may open again.
    assert sm.consume_anchor_click() is False
    assert sm.anchor_press() == 'open'


def test_popup_outside_autoclose_on_anchor_is_suppressed_from_reopening():
    sm = PopupStateMachine()
    sm.anchor_press(); sm.opened()
    # Models Qt.Popup/native outside-close arriving before the anchor click callback.
    sm.closed(CloseReason.OUTSIDE_CLICK, owner_anchor=True)
    assert sm.consume_anchor_click() is True
    assert sm.state is PopupInteractionState.CLOSED


def test_popup_item_commit_does_not_poison_next_anchor_click():
    sm = PopupStateMachine()
    sm.anchor_press(); sm.opened()
    sm.begin_commit(); sm.closed(CloseReason.ITEM_COMMIT)
    assert sm.consume_anchor_click() is False
    assert sm.anchor_press() == 'open'


@pytest.mark.parametrize(
    'anchor, labels, expected_max',
    [
        (78, ['Off', '1 px', '2 px', '4 px', '8 px'], 120),
        (100, ['Auto', '1×', '2×', '4×', '8×', '12×'], 140),
        (180, ['Follow system', 'Light', 'Dark'], 260),
    ],
)
def test_content_popup_width_does_not_force_every_select_to_180(anchor, labels, expected_max):
    # Approximate text widths are injected so the sizing rule is Qt-independent/testable.
    widths = [len(x) * 8 for x in labels]
    result = content_popup_width(anchor, widths, horizontal_padding=34, minimum=72, maximum=320)
    assert result >= anchor
    assert result <= expected_max


def test_preferences_declares_semantic_root_page_and_viewport_surfaces():
    source = (ROOT / 'preferences_qt.py').read_text(encoding='utf-8')
    for name in ('PreferencesRoot', 'PreferencesPage', 'PreferencesViewport'):
        assert name in source


def test_theme_stylesheet_has_explicit_preferences_and_popup_surfaces():
    source = (ROOT / 'qt_theme.py').read_text(encoding='utf-8')
    for selector in ('QWidget#PreferencesRoot', 'QWidget#PreferencesPage', 'QWidget#PreferencesViewport', 'QFrame#StudioSelectPopup'):
        assert selector in source
    # The list surface must not be transparent: real screenshots showed bleed-through.
    assert 'QListWidget#StudioSelectList { background: transparent' not in source.replace('\n', ' ')


def test_studio_select_exposes_explicit_show_hide_api_and_no_fixed_180_width():
    source = (ROOT / 'ui_controls.py').read_text(encoding='utf-8')
    assert 'def showPopup(' in source
    assert 'def hidePopup(' in source
    assert 'def eventFilter(' in source
    assert 'QEvent.MouseButtonPress' in source
    assert 'width=max(self.width(), 180)' not in source
    assert 'width = max(self.width(), 180)' not in source


def test_v82_version_is_declared_in_preferences_and_manifest():
    prefs = (ROOT / 'preferences_qt.py').read_text(encoding='utf-8')
    version=(ROOT/'VERSION').read_text(encoding='utf-8').strip()
    assert 'Version {APP_VERSION}' in prefs
    import json
    manifest=json.loads((ROOT.parent / 'DELIVERY_MANIFEST.json').read_text(encoding='utf-8'))
    assert manifest['version']==version
