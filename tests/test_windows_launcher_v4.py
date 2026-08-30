from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


def test_source_delivery_rejects_obsolete_top_level_windows_launcher():
    assert not (ROOT/'MonoOLEDStudio.exe').exists()
    manifest=(ROOT/'DELIVERY_MANIFEST.json').read_text(encoding='utf-8')
    assert 'obsolete-root-exe-forbidden' in manifest


def test_windows_builder_produces_self_contained_pyinstaller_executable():
    builder=(ROOT/'tools/BUILD_WINDOWS_GA.bat').read_text(encoding='utf-8')
    spec=(ROOT/'tools/MonoOLEDStudio.spec').read_text(encoding='utf-8')
    assert 'PyInstaller' in builder
    assert 'dist\\MonoOLEDStudio\\MonoOLEDStudio.exe' in builder
    assert "ROOT / 'src' / 'gui.py'" in spec
    assert "name='MonoOLEDStudio'" in spec


def test_windows_release_requires_native_real_qt_v12_gate_before_packaging():
    builder=(ROOT/'tools/BUILD_WINDOWS_GA.bat').read_text(encoding='utf-8')
    assert 'VERIFY_V120_GENERIC_PRODUCT_CLOSURE.py' in builder
    assert '--phase qt' in builder
    assert 'VERIFY_JUNIT_NO_SKIPS.py' in builder
    assert builder.index('VERIFY_V120_GENERIC_PRODUCT_CLOSURE.py') < builder.index('PyInstaller')
