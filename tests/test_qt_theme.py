import sys
from pathlib import Path

import pytest

pytest.importorskip('PySide6')

SIM = Path(__file__).resolve().parents[1] / 'src'
sys.path.insert(0, str(SIM))

from qt_theme import COLORS, METRICS, build_stylesheet
from theme_system import REQUIRED_TOKENS, get_theme, resolve_theme_name
from ui_metrics import build_ui_metrics


def test_professional_editor_theme_matches_ui_craft_contract():
    assert COLORS['app_bg'].upper() == '#FAF9F6'
    assert COLORS['text'].upper() == '#202A30'
    assert METRICS['grid'] == 8
    assert METRICS['gap'] == 20
    assert COLORS['text_muted'].upper() == '#657176'
    assert COLORS['text_secondary'].upper() == '#59656B'
    metrics=build_ui_metrics('comfortable',1.0)
    assert metrics['radius_panel']==12
    assert metrics['radius_control']==8
    assert metrics['radius_pill']==16
    assert metrics['radius_menu'] == 8


def test_runtime_dark_theme_uses_approved_tokens_without_rerouting():
    approved = get_theme('monooled-dark')
    runtime = get_theme('one-dark-pro')
    assert resolve_theme_name('', 'dark') == 'one-dark-pro'
    assert resolve_theme_name('', 'system', system_dark=True) == 'one-dark-pro'
    assert resolve_theme_name('', 'light') == 'monooled-light'
    assert {token: runtime[token] for token in REQUIRED_TOKENS} == {
        token: approved[token] for token in REQUIRED_TOKENS
    }


def test_stylesheet_contains_interactive_states_and_accessible_structure():
    css = build_stylesheet()
    assert '#faf9f6' in css
    assert '#202a30' in css
    assert 'QPushButton[hoverVisible="true"]' in css
    assert 'QPushButton[pressedVisible="true"]' in css
    assert 'QPushButton:disabled' in css
    assert 'QFrame#ProfessionalPanel' in css
    assert 'QFrame#CanvasWorkspace' in css
    assert 'border: 1px solid' in css


def _relative_luminance(hex_color: str) -> float:
    raw = hex_color.lstrip('#')
    values = [int(raw[i:i+2], 16) / 255.0 for i in (0, 2, 4)]
    linear = [v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4 for v in values]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def _contrast(a: str, b: str) -> float:
    hi, lo = sorted((_relative_luminance(a), _relative_luminance(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def test_primary_text_colors_meet_wcag_aa_on_panels():
    assert _contrast(COLORS['text'], COLORS['card']) >= 4.5
    assert _contrast(COLORS['text_secondary'], COLORS['card']) >= 4.5
    assert _contrast(COLORS['accent'], COLORS['card']) >= 4.5
