import sys
from pathlib import Path

import pytest

pytest.importorskip('PySide6')

SIM = Path(__file__).resolve().parents[1] / 'src'
sys.path.insert(0, str(SIM))

from qt_theme import COLORS, METRICS, build_stylesheet
from ui_metrics import build_ui_metrics


def test_professional_editor_theme_matches_ui_craft_contract():
    assert COLORS['app_bg'].upper() == '#F4F5F7'
    assert COLORS['text'].upper() == '#1D1D1F'
    assert METRICS['grid'] == 8
    assert METRICS['gap'] == 20
    assert COLORS['text_muted'].upper() == '#86868B'
    assert COLORS['text_secondary'].upper() == '#6E6E73'
    metrics=build_ui_metrics('comfortable',1.0)
    assert metrics['radius_panel']==8
    assert metrics['radius_control']==6
    assert metrics['radius_pill']==10
    assert metrics['radius_menu'] in (4,5,6)


def test_stylesheet_contains_interactive_states_and_accessible_structure():
    css = build_stylesheet()
    assert '#F4F5F7' in css
    assert '#1D1D1F' in css
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
