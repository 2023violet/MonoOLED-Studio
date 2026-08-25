import sys
from pathlib import Path

SIM = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SIM))

from runtime import SceneRuntime
from scene import load_scene
from session_log import SessionLogger


def test_runtime_applies_timeline_without_off_by_one_and_stops_at_zero(tmp_path):
    scene = load_scene()
    logger = SessionLogger(tmp_path / 'runtime.jsonl')
    rt = SceneRuntime(scene, logger=logger)

    assert rt.elapsed == 0
    assert rt.state['phase'] == 'standby'
    assert rt.state['seconds'] == 300
    assert rt.state['battery'] == 4

    rt.step(5)
    assert rt.elapsed == 5
    assert rt.state['phase'] == 'running'
    assert rt.state['seconds'] == 300  # first decrement occurs one second after entering running

    rt.step(1)
    assert rt.elapsed == 6
    assert rt.state['seconds'] == 299

    rt.step(299)
    assert rt.elapsed == 305
    assert rt.state['seconds'] == 0
    assert rt.state['phase'] == 'standby'

    rt.step(1)
    assert rt.state['seconds'] == 0
    logger.close()


def test_manual_state_change_is_clamped_and_logged(tmp_path):
    scene = load_scene()
    log_path = tmp_path / 'runtime.jsonl'
    logger = SessionLogger(log_path)
    rt = SceneRuntime(scene, logger=logger)
    rt.set_state('seconds', 5000)
    assert rt.state['seconds'] == 999
    logger.close()
    text = log_path.read_text(encoding='utf-8')
    assert '"event": "STATE"' in text
    assert '"name": "seconds"' in text
    assert '"after": 999' in text
    assert '"source": "manual"' in text
