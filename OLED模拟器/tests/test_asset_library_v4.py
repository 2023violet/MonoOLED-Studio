from pathlib import Path
import sys
from PIL import Image

SIM = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SIM))

from asset_library import AssetLibrary


def _img(path: Path, size=(4, 4), invert=False):
    path.parent.mkdir(parents=True, exist_ok=True)
    image = Image.new('1', size, 255 if invert else 0)
    image.putpixel((1, 1), 0 if invert else 255)
    image.save(path)


def test_asset_library_scans_searches_and_detects_duplicates(tmp_path):
    root = tmp_path / 'p'; root.mkdir()
    _img(root / 'assets' / 'icons' / 'run.png')
    _img(root / 'assets' / 'icons' / 'run_copy.png')
    _img(root / 'assets' / 'battery' / 'battery.png', size=(5, 7))
    lib = AssetLibrary(root, ['assets'])
    assets = lib.scan()
    assert len(assets) == 3
    assert [a.rel_path for a in lib.search('battery')] == ['assets/battery/battery.png']
    health = lib.health_report(used_paths={'assets/icons/run.png'})
    assert len(health.duplicates) == 1
    assert 'assets/battery/battery.png' in health.unused
    assert 'assets/icons/run_copy.png' in health.unused


def test_asset_library_imports_external_resource_portably(tmp_path):
    root = tmp_path / 'project'; root.mkdir()
    external = tmp_path / 'external' / 'new icon.png'
    _img(external, size=(6, 8))
    lib = AssetLibrary(root, ['assets'])
    imported = lib.import_asset(external)
    assert imported.rel_path.startswith('assets/imported/')
    assert (root / imported.rel_path).exists()
    assert (imported.width, imported.height) == (6, 8)


def test_unchanged_asset_scan_does_not_replace_identical_persistent_cache(tmp_path, monkeypatch):
    root = tmp_path / 'project'; root.mkdir()
    bitmap = root / 'assets' / 'icon.png'
    _img(bitmap)
    lib = AssetLibrary(root, ['assets'])
    lib.scan()

    replacements = []
    original_replace = __import__('asset_library').os.replace
    monkeypatch.setattr(
        'asset_library.os.replace',
        lambda source, target: (replacements.append((source, target)), original_replace(source, target))[1],
    )

    lib.scan()

    assert replacements == []

    _img(bitmap, invert=True)
    lib.scan()
    assert len(replacements) == 1
