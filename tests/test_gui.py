import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

SIM = Path(__file__).resolve().parents[1] / 'src'
GUI = SIM / 'gui.py'


def test_primary_gui_is_pyside6_and_not_tkinter():
    text = GUI.read_text(encoding='utf-8')
    assert 'from PySide6' in text
    assert 'import tkinter' not in text
    assert 'OLEDDesignerWindow' in text
    assert 'build_adaptive_stylesheet' in text
    assert 'build_theme_palette' in text


def test_gui_check_mode_reports_dependency_or_validates_core():
    result = subprocess.run([sys.executable, str(GUI), '--check'], text=True, capture_output=True)
    if importlib.util.find_spec('PySide6') is None:
        assert result.returncode == 2
        assert 'PySide6 is not installed' in result.stderr
    else:
        assert result.returncode == 0, result.stdout + result.stderr
        assert 'CORE CHECK PASS' in result.stdout
        assert '128x32' in result.stdout
        assert 'PySide6=' in result.stdout


def test_gui_window_smoke_can_create_and_close_under_xvfb_when_pyside_available():
    if importlib.util.find_spec('PySide6') is None:
        pytest.skip('PySide6 not available in this Linux execution environment')
    import shutil
    if shutil.which('xvfb-run') is None:
        pytest.skip('xvfb-run not available')
    result = subprocess.run(
        ['xvfb-run', '-a', sys.executable, str(GUI), '--smoke-ms', '200'],
        text=True, capture_output=True, timeout=15,
    )
    assert result.returncode == 0, result.stdout + result.stderr
