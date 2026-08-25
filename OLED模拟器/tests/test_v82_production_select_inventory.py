from pathlib import Path
import re

SIM=Path(__file__).resolve().parents[1]


def test_all_production_select_factories_route_to_studio_select():
    gui=(SIM/'gui.py').read_text(encoding='utf-8')
    prefs=(SIM/'preferences_qt.py').read_text(encoding='utf-8')
    pixel=(SIM/'pixel_studio_qt.py').read_text(encoding='utf-8')
    assert 'QComboBox = StudioSelect' in gui
    assert 'QComboBox = StudioSelect' in prefs
    assert len(re.findall(r'QComboBox\(\)',gui))==7
    assert len(re.findall(r'QComboBox\(\)',prefs))==10
    assert len(re.findall(r'StudioSelect\(\)',pixel))==3
    assert 7+10+3==20


def test_v82_select_foundation_has_explicit_state_and_opaque_surface_contract():
    controls=(SIM/'ui_controls.py').read_text(encoding='utf-8')
    theme=(SIM/'qt_theme.py').read_text(encoding='utf-8')
    for marker in ('PopupStateMachine','CloseReason.ANCHOR_TOGGLE','def showPopup(','def hidePopup(','content_popup_width','setMask('):
        assert marker in controls
    assert 'WA_TranslucentBackground, True' not in controls
    assert "QListWidget#StudioSelectList {{ background: {c['surface.panel']}" in theme


def test_preferences_pages_have_explicit_theme_surfaces():
    prefs=(SIM/'preferences_qt.py').read_text(encoding='utf-8')
    theme=(SIM/'qt_theme.py').read_text(encoding='utf-8')
    for name in ('PreferencesRoot','PreferencesPage','PreferencesViewport','PreferencesNavigation','PreferencesStack'):
        assert name in prefs
    for name in ('PreferencesRoot','PreferencesPage','PreferencesViewport'):
        assert name in theme
