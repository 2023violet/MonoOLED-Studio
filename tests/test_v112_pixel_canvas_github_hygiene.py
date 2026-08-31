from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SIM = ROOT / 'src'


def test_pixel_canvas_uses_oled_black_white_truth_not_theme_surface():
    source = (SIM / 'pixel_studio_qt.py').read_text(encoding='utf-8')
    assert "t['canvas.background']" not in source
    assert "PIXEL_OFF_COLOR = '#000000'" in source
    assert "PIXEL_ON_COLOR = '#FFFFFF'" in source
    assert 'pix.fill(QColor(PIXEL_OFF_COLOR))' in source
    assert 'painter.setBrush(QColor(PIXEL_ON_COLOR))' in source


def test_github_root_markdown_is_curated():
    root_markdown = sorted(p.name for p in ROOT.glob('*.md'))
    # Allow the core docs plus standard open-source support files; reject
    # stray/placeholder markdown at the repository root.
    assert root_markdown == ['CONTRIBUTING.md', 'DELIVERY_README.md', 'README.md', 'SECURITY.md']


def test_github_documentation_is_classified():
    docs = ROOT / 'docs'
    required = {
        'README.md', 'USER_GUIDE_CN.md', 'USER_GUIDE_EN.md', 'SCENE_SCHEMA.md',
        'AUTOMATION_API_V1.md', 'DESIGN_SYSTEM.md', 'V12_GENERIC_PRODUCT_CLOSURE.md', 'WINDOWS_BUILD.md',
    }
    assert required <= {p.name for p in docs.iterdir() if p.is_file()}
    for legacy in ('design', 'releases', 'archive'):
        assert not (docs / legacy).exists()

def test_runtime_artifacts_are_not_part_of_clean_release_tree():
    forbidden = [
        ROOT / '.oled' / 'asset_cache_v1.json',
        ROOT / '.oled' / 'logs',
        ROOT / '.oled' / 'autosave',
    ]
    assert not [str(path.relative_to(ROOT)) for path in forbidden if path.exists()]


def test_gitignore_covers_runtime_build_and_python_noise():
    text = (ROOT / '.gitignore').read_text(encoding='utf-8')
    for marker in (
        '__pycache__/', '.pytest_cache/', '.oled/logs/', '.oled/autosave/',
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

