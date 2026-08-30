from support import load_curing_scene
import sys
from pathlib import Path

SIM = Path(__file__).resolve().parents[1] / 'src'
sys.path.insert(0, str(SIM))

from presets import clinical_states
from scene import load_scene


def test_clinical_states_are_derived_from_scene_enums_and_overrides():
    states = clinical_states(load_curing_scene(), seconds=10, battery=3)
    assert len(states) == 14
    assert states['normal_standby']['mode'] == 'NORMAL'
    assert states['normal_standby']['phase'] == 'standby'
    assert states['check_running']['seconds'] == 10
    assert states['check_running']['battery'] == 3
