from __future__ import annotations

import json
from pathlib import Path


def _repo_root() -> Path:
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / 'README.md').is_file() and (parent / 'DELIVERY_README.md').is_file():
            return parent
    raise RuntimeError('repository root not found')


REPO = _repo_root()
SRC = REPO / 'src' if (REPO / 'src').is_dir() else REPO / 'OLED模拟器'
TOOLS = REPO / 'tools' if (REPO / 'tools').is_dir() else REPO / 'Developer_Tools'


def test_v12_repository_layout_is_ascii_and_legacy_roots_removed():
    for name in ('src', 'tests', 'tools', 'test_assets', 'docs', '.github'):
        assert (REPO / name).is_dir(), name
    for name in ('OLED模拟器', 'Developer_Tools', 'Curing_Lite光固化机产品 - UI设计初稿', 'scenes'):
        assert not (REPO / name).exists(), name
    non_ascii = [p.relative_to(REPO).as_posix() for p in REPO.rglob('*') if any(ord(ch) > 127 for ch in p.relative_to(REPO).as_posix())]
    assert non_ascii == []


def test_default_scene_is_generic_product_neutral_and_schema_compliant():
    scene = json.loads((SRC / 'scenes' / 'main_scene.json').read_text(encoding='utf-8'))
    assert scene['canvas']['w'] == 128 and scene['canvas']['h'] == 32
    assert scene['storage']['layout'].upper().startswith('VLSB')
    assert scene.get('states') == {}
    assert scene.get('timeline') == []
    payload = json.dumps(scene, ensure_ascii=False).lower()
    for forbidden in ('curing', 'battery', 'countdown', 'normal', 'turbo', 'ortho', 'clinical'):
        assert forbidden not in payload


def test_global_run_menu_is_removed_and_timeline_stays_explicit_capability_only():
    gui = (SRC / 'gui.py').read_text(encoding='utf-8')
    capabilities = (SRC / 'preview_capabilities.py').read_text(encoding='utf-8')
    assert "self._menus['run']" not in gui
    assert "'run':'menu.run'" not in gui.replace(' ', '')
    assert "'timeline' in declared" in capabilities
    assert "preview.get('capabilities')" in capabilities


def test_preferences_content_is_centered_and_responsive_to_760px():
    prefs = (SRC / 'preferences_qt.py').read_text(encoding='utf-8')
    assert 'content_max_width = 760' in prefs
    assert 'setMaximumWidth(self.content_max_width)' in prefs
    assert 'Qt.AlignHCenter|Qt.AlignTop' in prefs.replace(' ', '')
    assert 'setMaximumWidth(720)' not in prefs


def test_builder_spec_and_v12_gate_follow_current_source_layout():
    builder = (TOOLS / 'BUILD_WINDOWS_GA.bat').read_text(encoding='utf-8')
    spec = (TOOLS / 'MonoOLEDStudio.spec').read_text(encoding='utf-8')
    gate = TOOLS / 'VERIFY_V120_GENERIC_PRODUCT_CLOSURE.py'
    delivery = TOOLS / 'BUILD_DELIVERY_V120.py'
    for marker in ('requirements-build.txt', 'requirements-dev.txt', 'tests', 'src\\gui.py', 'VERIFY_V120_GENERIC_PRODUCT_CLOSURE.py', 'BUILD_WINDOWS_RUNTIME_ZIP.py'):
        assert marker in builder
    assert "ROOT / 'src' / 'gui.py'" in spec
    assert "'src/scenes'" in spec and "'docs'" in spec
    assert "add_tree('test_assets'" not in spec
    assert gate.is_file()
    assert delivery.is_file()


def test_v12_docs_are_current_only_without_transition_archives():
    docs = REPO / 'docs'
    assert docs.is_dir()
    assert not (docs / 'archive').exists()
    assert not (docs / 'releases').exists()
    assert not (docs / 'design').exists()
    assert not (docs / 'superpowers').exists()
    names = {p.name for p in docs.iterdir() if p.is_file()}
    required = {'README.md', 'USER_GUIDE_CN.md', 'USER_GUIDE_EN.md', 'SCENE_SCHEMA.md', 'AUTOMATION_API_V1.md', 'DESIGN_SYSTEM.md', 'V12_GENERIC_PRODUCT_CLOSURE.md'}
    assert required <= names


def test_v12_package_contract_rejects_obsolete_root_launcher():
    assert not (REPO / 'MonoOLEDStudio.exe').exists()
    verifier = (REPO / 'VERIFY_PACKAGE.py').read_text(encoding='utf-8')
    assert 'V12' in verifier
    assert 'MonoOLEDStudio.exe' in verifier and 'obsolete' in verifier.lower()
    assert "ROOT / 'src'" in verifier
    assert "ROOT / 'tests'" in verifier
    assert "ROOT / 'tools'" in verifier


def test_frozen_asset_manifest_uses_ascii_migrated_paths_and_keeps_464_hashes():
    manifest = REPO / 'test_assets' / 'manifests' / 'frozen_product_assets_v70.json'
    data = json.loads(manifest.read_text(encoding='utf-8'))
    assert data['count'] == 464
    assert len(data['files']) == 464
    assert all(rel.startswith('test_assets/projects/curing_lite/') for rel in data['files'])
    assert all(rel.isascii() for rel in data['files'])
    assert all((REPO / rel).is_file() for rel in data['files'])
