from __future__ import annotations

from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))

import golden_corpus  # noqa: E402
from golden_corpus import common  # noqa: E402
from golden_corpus.common import Category  # noqa: E402
import EXPORT_GOLDEN_CORPUS as exporter  # noqa: E402


def _build(name: str):
    category = next(item for item in golden_corpus.CATEGORIES if item.name == name)
    import tempfile
    with tempfile.TemporaryDirectory(prefix='mono-golden-test-') as work:
        return {item['id']: item for item in category.build(Path(work))}


def test_case_rejects_unknown_level():
    with pytest.raises(ValueError):
        common.case('x', 'k', 'loose', {}, {})


def test_generate_is_deterministic(tmp_path, monkeypatch):
    monkeypatch.setattr(golden_corpus, 'CATEGORIES', [
        Category('demo', lambda work: [common.case('b', 'demo', 'strict', {}, {'v': 1}),
                                       common.case('a', 'demo', 'semantic', {}, {'v': 2})], ('src/framebuffer.py',)),
    ])
    first = exporter.generate(tmp_path / 'a')
    second = exporter.generate(tmp_path / 'b')
    assert first == second
    for path in (tmp_path / 'a').iterdir():
        data = path.read_bytes()
        assert data == (tmp_path / 'b' / path.name).read_bytes()
        assert b'\r\n' not in data
    assert first['categories']['demo']['levels'] == {'strict': 1, 'semantic': 1}


def test_check_reports_changed_case_ids(tmp_path, monkeypatch):
    def demo(value):
        return [Category('demo', lambda work: [common.case('one', 'demo', 'strict', {}, {'v': value})], ('src/framebuffer.py',))]

    monkeypatch.setattr(golden_corpus, 'CATEGORIES', demo(2))
    exporter.generate(tmp_path / 'd')
    assert exporter.check(tmp_path / 'd') == []
    monkeypatch.setattr(golden_corpus, 'CATEGORIES', demo(3))
    assert exporter.check(tmp_path / 'd') == ['demo:one']


def test_replace_root_only_substitutes_project_root(tmp_path):
    value = {'path': str(tmp_path / 'exports' / 'a.h'), 'other': 'C:/unrelated'}
    replaced = common.replace_root(value, tmp_path)
    assert replaced['path'].startswith(common.PROJECT_ROOT_TOKEN)
    assert replaced['other'] == 'C:/unrelated'
