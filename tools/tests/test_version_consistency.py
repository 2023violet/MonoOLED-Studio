from __future__ import annotations

from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[2]


def workspace_version() -> str:
    text = (ROOT / 'Cargo.toml').read_text(encoding='utf-8')
    block = re.search(r'\[workspace\.package\](.*?)(?:\n\[|\Z)', text, re.DOTALL)
    assert block, 'Cargo.toml has no [workspace.package] section'
    version = re.search(r'version\s*=\s*"([^"]+)"', block.group(1))
    assert version, 'workspace version is missing'
    return version.group(1)


def test_slint_default_version_matches_cargo():
    version = workspace_version()
    text = (ROOT / 'apps' / 'mono-desktop' / 'ui' / 'main.slint').read_text(encoding='utf-8')
    slint = re.search(r'version:\s*"([^"]+)"', text)
    assert slint, 'AppModel has no default version'
    assert slint.group(1) == version


def test_current_state_records_product_version():
    version = workspace_version()
    text = (ROOT / '.ai' / 'CURRENT_STATE.md').read_text(encoding='utf-8')
    assert f'- Product version: {version} ' in text


def test_changelog_documents_product_version():
    version = workspace_version()
    text = (ROOT / 'CHANGELOG.md').read_text(encoding='utf-8')
    assert re.search(rf'^## {re.escape(version)} - \d{{4}}-\d{{2}}-\d{{2}}$', text, re.MULTILINE)
