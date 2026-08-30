from pathlib import Path

SIM = Path(__file__).resolve().parents[1] / 'src'
GUI = SIM / 'gui.py'
CANVAS = SIM / 'qt_canvas.py'
ROOT = SIM.parent


def test_gui_uses_live_geometry_updates_and_auto_zoom():
    text = GUI.read_text(encoding='utf-8')
    assert 'valueChanged.connect' in text
    assert "'Auto'" in text or 'zoom.auto' in text
    assert 'set_canvas_size' in text
    assert 'CANVAS_PRESETS' in text
    assert 'canvas_preset_combo' in text
    assert 'spin.setRange(-512, 512)' not in text


def test_qt_canvas_does_not_hardcode_128x32_pixel_bounds():
    text = CANVAS.read_text(encoding='utf-8')
    assert 'range(129)' not in text
    assert 'range(33)' not in text
    assert 'x < 128' not in text
    assert 'y < 32' not in text


def test_broken_source_launcher_is_not_part_of_v3_delivery():
    assert not (ROOT / 'CuringLiteOLEDDesigner_SourceLauncher.exe').exists()


def test_windows_builder_requires_layout_smoke_after_exe_build():
    script = (ROOT / 'tools' / 'BUILD_WINDOWS_GA.bat').read_text(encoding='utf-8')
    assert '--layout-smoke' in script
