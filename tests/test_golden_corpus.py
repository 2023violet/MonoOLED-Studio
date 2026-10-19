from __future__ import annotations

import json
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


def test_encoding_cases_cover_padding_sizes():
    cases = _build('encoding')
    assert 'enc-1x1-vertical-row_major-lsb_first-one_is_lit' in cases
    assert 'enc-13x17-horizontal-column_major-msb_first-zero_is_lit' in cases
    assert sum(1 for item in cases.values() if item['kind'] == 'encoding') >= 128
    assert cases['fb-8x7-vlsb-rejects-partial-page']['expected']['error'] == 'ValueError'


def test_preview_boundary_cases_present():
    cases = _build('formatting')
    exact = cases['preview-limit-exact']['expected']
    over = cases['preview-limit-over-by-one']['expected']
    assert exact['preview_truncated'] is False
    assert over['preview_truncated'] is True
    assert exact['text'] == over['text']
    assert cases['preview-limit-default-over']['expected']['preview_truncated'] is True
    assert 'legacy-c-header-128x32-oled_frame' in cases
    assert any(case_id.startswith('fmt-legacy_pixel_c-') for case_id in cases)


def test_raster_cases_cover_threshold_and_resize():
    cases = _build('raster')
    assert 'raster-gradient_64x32-luma-128' in cases
    resized = cases['raster-gradient_64x32-resize-32x16-aa4']
    assert resized['input']['output_size'] == [32, 16]
    assert len(resized['expected']['rows']) == 16
    source = cases['raster-checker_alpha_17x9-luma-1']['input']['source']
    assert source['rgba']['byte_count'] == 17 * 9 * 4


def test_scene_cases_cover_builtin_and_project_frames():
    cases = _build('scenes')
    kinds = {element['type'] for item in cases.values() for element in item['expected'].get('resolved_elements', [])}
    assert {'image', 'image_seq', 'digits', 'text', 'bitmap_text', 'placeholder'} <= kinds
    errors = {item['expected']['error'] for item in cases.values() if 'error' in item['expected']}
    assert {'FileNotFoundError', 'ValueError', 'AssetFormatError'} <= errors
    assert any(case_id.startswith('scene-curing_lite_main-') for case_id in cases)
    assert any(case_id.startswith('scene-builtin_example_placeholder-') for case_id in cases)
    assert all(item['level'] == 'strict' for item in cases.values())
    blob = json.dumps(list(cases.values())[:50])
    assert ROOT.as_posix() not in blob and str(ROOT) not in blob


def test_legacy_project_open_is_byte_preserving():
    cases = _build('projects')
    assert cases['project-legacy-open-no-output-workbench']['expected']['rewritten'] is False
    assert cases['project-curing_lite-open']['expected']['loaded']['manifest_unchanged_after_open'] is True
    assert sum(1 for item in cases.values() if item['kind'] == 'path_safety') >= 8
    assert cases['project-save-rejects-external-modification']['expected']['error'] == 'ExternalProjectModificationError'


def test_handoff_cases_record_entries():
    cases = _build('handoff')
    entries = cases['handoff-builtin_main_scene-boundaries']['expected']['entries']
    names = {entry['name'] for entry in entries}
    assert 'ui_contract.json' in names and 'HANDOFF_README.md' in names
    assert any(entry['kind'] == 'png' for entry in entries)
    assert any(name.startswith('golden/') and name.endswith('.bin') for name in names)


def test_automation_sessions_cover_every_method_without_absolute_paths():
    from automation_service import METHOD_SPECS
    cases = _build('automation')
    methods = {step['request']['method'] for item in cases.values() for step in item['expected'].get('steps', [])}
    assert set(METHOD_SPECS) <= methods
    codes = {step['response'].get('error', {}).get('code') for item in cases.values() for step in item['expected'].get('steps', [])}
    assert {'STALE_REVISION', 'METHOD_OR_FIELD_NOT_FOUND', 'PERMISSION_DENIED', 'UNSAVED_CHANGES', 'TRANSACTION_ERROR', 'INVALID_REQUEST'} <= codes
    blob = json.dumps(list(cases.values()))
    assert ROOT.as_posix() not in blob and str(ROOT) not in blob
    assert '$doc' not in blob and '$builtin' not in blob
    assert 'pixel:assets/golden_icon.png' in blob and 'tx-1' in blob


def test_font_cases_split_strict_and_semantic():
    cases = _build('fonts')
    strict = cases['fontpack-builtin-5x8-roundtrip']
    assert strict['level'] == 'strict' and strict['expected']['reload_matches'] is True
    assert cases['fontpack-manual-8x8-cjk-roundtrip']['expected']['glyphs']['U+4E2D']
    generated = cases['fontgen-dejavu-8x16-aa1']
    assert generated['level'] == 'semantic'
    assert len(generated['expected']['glyphs']) == 95


def test_committed_corpus_matches_v1():
    assert exporter.check(ROOT / 'fixtures' / 'golden') == []


def _demo(name, value, sources=('src/framebuffer.py',)):
    return Category(name, lambda work: [common.case('one', name, 'strict', {}, {'v': value})], sources)


def test_check_reports_category_changes_blob_drift_and_bytes(tmp_path, monkeypatch):
    monkeypatch.setattr(golden_corpus, 'CATEGORIES', [_demo('demo', 1)])
    exporter.generate(tmp_path / 'g')
    monkeypatch.setattr(golden_corpus, 'CATEGORIES', [_demo('demo', 1), _demo('added', 1)])
    assert exporter.check(tmp_path / 'g') == ['added:*']
    monkeypatch.setattr(golden_corpus, 'CATEGORIES', [_demo('demo', 1, ('src/framebuffer.py', 'src/render.py'))])
    assert exporter.check(tmp_path / 'g') == ['reference:source_blobs:src/render.py']
    monkeypatch.setattr(golden_corpus, 'CATEGORIES', [_demo('demo', 1)])
    path = tmp_path / 'g' / 'demo.json'
    path.write_bytes(path.read_bytes().replace(b'\n', b'\r\n'))
    (tmp_path / 'g' / 'stray.json').write_text('{}', encoding='utf-8')
    assert exporter.check(tmp_path / 'g') == ['extra:stray.json', 'bytes:demo.json']


def test_check_detects_type_changes_hidden_by_python_equality(tmp_path, monkeypatch):
    monkeypatch.setattr(golden_corpus, 'CATEGORIES', [_demo('demo', 1)])
    exporter.generate(tmp_path / 'g')
    monkeypatch.setattr(golden_corpus, 'CATEGORIES', [_demo('demo', True)])
    assert exporter.check(tmp_path / 'g') == ['demo:one']
