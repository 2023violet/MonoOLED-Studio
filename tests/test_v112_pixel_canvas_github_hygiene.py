import importlib.util
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SIM = ROOT / 'src'


def test_pixel_canvas_defaults_to_oled_truth_and_keeps_display_colors_out_of_encoding():
    source = (SIM / 'pixel_studio_qt.py').read_text(encoding='utf-8')
    assert "t['canvas.background']" not in source
    assert "PIXEL_OFF_COLOR = '#000000'" in source
    assert "PIXEL_ON_COLOR = '#FFFFFF'" in source
    assert 'self.background_color=PIXEL_OFF_COLOR' in source
    assert 'self.fill_color=PIXEL_ON_COLOR' in source
    assert 'pix.fill(QColor(self.background_color))' in source
    assert 'painter.setBrush(QColor(self.fill_color))' in source
    assert 'to_vlsb' not in source[source.index('def _base_pixmap'):source.index('def _stroke_bounds')]


def test_github_root_markdown_is_curated():
    root_markdown = sorted(p.name for p in ROOT.glob('*.md'))
    # Allow the core docs plus standard open-source support files; reject
    # stray/placeholder markdown at the repository root.
    assert root_markdown == ['CONTRIBUTING.md', 'DELIVERY_README.md', 'README.md', 'SECURITY.md']


def test_github_documentation_is_classified():
    docs = ROOT / 'docs'
    required = {
        'README.md', 'USER_GUIDE_CN.md', 'USER_GUIDE_EN.md', 'SCENE_SCHEMA.md',
        'AUTOMATION_API_V1.md', 'DESIGN_SYSTEM.md', 'ENGINEERING_HISTORY.md', 'WINDOWS_BUILD.md',
        'OUTPUT_WORKBENCH.md',
    }
    assert required <= {p.name for p in docs.iterdir() if p.is_file()}
    for legacy in ('design', 'releases', 'archive'):
        assert not (docs / legacy).exists()

def _load_source_builder():
    path = ROOT / 'tools' / 'BUILD_DELIVERY_V120.py'
    spec = importlib.util.spec_from_file_location('source_builder', path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_runtime_artifacts_are_excluded_from_release_payload():
    builder = _load_source_builder()
    runtime_file = ROOT / '.oled' / 'asset_cache_v1.json'
    runtime_file.parent.mkdir(exist_ok=True)
    runtime_file.write_text('{}', encoding='utf-8')

    packaged = {
        path.relative_to(ROOT).as_posix()
        for path in builder.managed_files()
    }

    assert '.oled/asset_cache_v1.json' not in packaged


def test_generic_source_delivery_entrypoint_writes_checksum(tmp_path):
    artifact = tmp_path / 'source.zip'
    artifact.write_bytes(b'source-payload')
    result = subprocess.run(
        [sys.executable, str(ROOT / 'tools' / 'BUILD_SOURCE_DELIVERY.py'),
         '--sha256-only', str(artifact)],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert artifact.with_suffix('.zip.sha256').read_text(encoding='ascii').endswith('  source.zip\n')


def test_gitignore_covers_runtime_build_and_python_noise():
    text = (ROOT / '.gitignore').read_text(encoding='utf-8')
    for marker in (
        '__pycache__/', '.pytest_cache/', '.oled/', '.oled/logs/', '.oled/autosave/',
        '.oled/asset_cache_v1.json', '.oled/fonts/', 'build/', 'dist/', '.venv/'
    ):
        assert marker in text


def test_v112_windows_gate_and_release_binding_exist():
    gate = ROOT / 'tools' / 'VERIFY_V112_PIXEL_GITHUB_RELEASE.py'
    qt_test = ROOT / 'tests' / 'test_qt_v112_pixel_canvas_release.py'
    assert gate.is_file()
    assert qt_test.is_file()
    builder = (ROOT / 'tools' / 'BUILD_WINDOWS_GA.bat').read_text(encoding='utf-8')
    assert 'VERIFY_V112_PIXEL_GITHUB_RELEASE.py' in builder
    assert 'VERIFY_V120_GENERIC_PRODUCT_CLOSURE.py' in builder

def test_package_verifier_enforces_v112_hygiene_contract():
    source = (ROOT / 'VERIFY_PACKAGE.py').read_text(encoding='utf-8')
    pixel = (SIM / 'pixel_studio_qt.py').read_text(encoding='utf-8')
    assert "PIXEL_OFF_COLOR = '#000000'" in pixel
    assert "PIXEL_ON_COLOR = '#FFFFFF'" in pixel
    for marker in ('CURRENT_DOCS', 'OBSOLETE_ROOTS', 'MonoOLEDStudio.exe', 'test_assets', "'.git' not in p.parts"):
        assert marker in source
