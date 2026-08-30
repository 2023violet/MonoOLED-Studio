from pathlib import Path
import json
import sys
import time

SIM = Path(__file__).resolve().parents[1] / 'src'
sys.path.insert(0, str(SIM))

from autosave import AutoSaveManager


def test_autosave_snapshot_and_recovery_candidate(tmp_path):
    scene_path = tmp_path / 'scenes' / 'main.json'; scene_path.parent.mkdir()
    scene_path.write_text('{"canvas":{"w":128,"h":32},"states":{},"elements":[],"timeline":[]}', encoding='utf-8')
    scene = {'_path': str(scene_path), '_root': str(tmp_path), 'canvas': {'w': 128, 'h': 32}, 'states': {}, 'elements': [], 'timeline': []}
    manager = AutoSaveManager(scene, keep=3)
    snap = manager.snapshot(reason='timer')
    assert snap.exists()
    payload = json.loads(snap.read_text(encoding='utf-8'))
    assert payload['_autosave']['reason'] == 'timer'
    assert manager.latest_recovery() == snap


def test_autosave_prunes_old_snapshots(tmp_path):
    scene_path = tmp_path / 'scene.json'; scene_path.write_text('{}', encoding='utf-8')
    scene = {'_path': str(scene_path), '_root': str(tmp_path), 'canvas': {'w': 128, 'h': 32}, 'states': {}, 'elements': [], 'timeline': []}
    manager = AutoSaveManager(scene, keep=2)
    for i in range(4):
        scene['marker'] = i
        manager.snapshot(reason=f't{i}')
        time.sleep(0.002)
    assert len(manager.snapshots()) == 2
