from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    'rust_golden_verifier', ROOT / 'tools' / 'VERIFY_RUST_GOLDENS.py')
verifier = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(verifier)
DOCUMENT = json.loads(verifier.DEFAULT_FIXTURE.read_text(encoding='utf-8'))


@pytest.mark.parametrize('case', DOCUMENT['cases'], ids=lambda case: case['id'])
def test_python_reference_matches_frozen_expected(case):
    assert verifier.reference_result(case) == case['expected']


def test_checker_detects_corrupted_expected_and_does_not_rewrite(tmp_path):
    payload = json.loads(verifier.DEFAULT_FIXTURE.read_text(encoding='utf-8'))
    payload['cases'][0]['expected']['hex'] = '00'
    target = tmp_path / 'corrupt.json'
    target.write_text(json.dumps(payload), encoding='utf-8')
    before = target.read_bytes()
    result = subprocess.run(
        [sys.executable, str(ROOT / 'tools' / 'VERIFY_RUST_GOLDENS.py'),
         '--fixture', str(target)], capture_output=True, text=True)
    assert result.returncode == 1
    assert 'MISMATCH ' + payload['cases'][0]['id'] in result.stdout
    assert target.read_bytes() == before


def test_json_semantics_ignore_layout_but_preserve_values_and_array_order():
    a = json.loads('{"b": [1, 2], "a": "OLED"}')
    b = json.loads('{\r\n  "a": "OLED",\r\n  "b": [1,2]\r\n}')
    assert verifier.canonical_json(a) == verifier.canonical_json(b)
    assert verifier.canonical_json(a) != verifier.canonical_json(
        {'a': 'OLED', 'b': [2, 1]})


def test_independent_pixel_font_and_padding_anchors():
    cases = {case['id']: case for case in DOCUMENT['cases']}
    font = cases['builtin-5x7']['expected']
    assert font['glyphs']['A']['rows'] == [
        '01110', '10001', '10001', '11111',
        '10001', '10001', '10001', '00000']
    assert font['baseline'] == 6 and font['advance'] == 6
    assert cases['polarity-padding']['expected']['hex'] == '5f'
    fb = bytes.fromhex(cases['framebuffer-boundary']['expected']['hex'])
    assert fb[0] == 0x01 and fb[3] == 0x80 and fb[7] == 0x80
    project = cases['legacy-project']['expected']
    assert project['read_preserved_bytes'] is True
    assert 'output_workbench' not in project['saved_manifest']
