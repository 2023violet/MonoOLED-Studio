from support import load_curing_scene
import json
import sys
from pathlib import Path

from PIL import Image

SIM = Path(__file__).resolve().parents[1] / 'src'
sys.path.insert(0, str(SIM))

from scene import load_scene, init_state
from exporter import export_scene


def test_export_scene_emits_contract_golden_preview_manifest_and_reports(tmp_path):
    scene = load_curing_scene()
    base = init_state(scene)
    states = {
        'normal_standby': {**base, 'mode': 'NORMAL', 'phase': 'standby', 'seconds': 10, 'battery': 4},
        'normal_running': {**base, 'mode': 'NORMAL', 'phase': 'running', 'seconds': 9, 'battery': 4},
    }

    summary = export_scene(scene, tmp_path, states)

    expected = [
        tmp_path / 'UI_SPEC.md',
        tmp_path / 'ui_contract.json',
        tmp_path / 'asset_manifest.json',
        tmp_path / 'validation_report.md',
        tmp_path / 'reference' / 'normal_standby.png',
        tmp_path / 'reference' / 'normal_running.png',
        tmp_path / 'golden' / 'normal_standby.bin',
        tmp_path / 'golden' / 'normal_running.bin',
    ]
    assert all(p.exists() for p in expected)
    assert len((tmp_path / 'golden' / 'normal_standby.bin').read_bytes()) == 512
    assert Image.open(tmp_path / 'reference' / 'normal_standby.png').size == (128, 32)

    contract = json.loads((tmp_path / 'ui_contract.json').read_text(encoding='utf-8'))
    assert contract['coordinate_contract']['bounds'] == '[x, x+w) × [y, y+h)'
    assert contract['frames']['normal_running']['state']['phase'] == 'running'
    assert len(contract['frames']['normal_running']['golden_sha256']) == 64

    manifest = json.loads((tmp_path / 'asset_manifest.json').read_text(encoding='utf-8'))
    paths = {item['path'] for item in manifest['assets']}
    assert 'assets/clinical_ui/running.png' in paths
    assert all(not p.startswith('/mnt/') for p in paths)
    bitmap_entries = [item for item in manifest['assets'] if item.get('kind') == 'bitmap']
    assert bitmap_entries
    assert all('source_polarity' in item for item in bitmap_entries)
    assert any(item.get('inverted_for_oled') is True for item in bitmap_entries)

    spec = (tmp_path / 'UI_SPEC.md').read_text(encoding='utf-8')
    assert '## NORMAL_RUNNING' in spec
    assert '| running_icon | image | 94 | 19 | 24 | 12 |' in spec
    assert summary.frame_count == 2


def test_export_is_deterministic_for_same_input(tmp_path):
    scene = load_curing_scene()
    base = init_state(scene)
    states = {'normal_standby': {**base, 'mode': 'NORMAL', 'phase': 'standby', 'seconds': 10}}
    a = export_scene(scene, tmp_path / 'a', states)
    b = export_scene(scene, tmp_path / 'b', states)
    assert a.frame_hashes == b.frame_hashes
    assert (tmp_path / 'a' / 'ui_contract.json').read_bytes() == (tmp_path / 'b' / 'ui_contract.json').read_bytes()
    assert (tmp_path / 'a' / 'UI_SPEC.md').read_bytes() == (tmp_path / 'b' / 'UI_SPEC.md').read_bytes()
