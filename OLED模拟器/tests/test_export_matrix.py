import sys
from pathlib import Path

import pytest

SIM = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SIM))

from export_matrix import build_export_states, select_export_states
from batch_validate import validate_matrix
from scene import load_scene


def _generic_scene():
    return {
        "states": {
            "page": {"type": "enum", "values": ["HOME", "SETTINGS"], "init": "HOME"},
            "channel": {"type": "int", "min": 1, "max": 4, "init": 2},
            "level": {"type": "int", "values": [0, 25, 50, 75, 100], "init": 50},
            "alarm": {"type": "enum", "values": ["OFF", "ON"], "init": "OFF"},
        },
    }


def test_build_export_states_preserves_schema_order_and_generates_80_cases():
    states = build_export_states(_generic_scene())

    assert len(states) == 80
    names = list(states)
    assert names[0] == "case_0000__page-HOME__channel-1__level-0__alarm-OFF"
    assert names[-1] == "case_0079__page-SETTINGS__channel-4__level-100__alarm-ON"
    assert states[names[0]] == {
        "page": "HOME",
        "channel": 1,
        "level": 0,
        "alarm": "OFF",
    }


def test_build_export_states_filters_relation_violations():
    scene = _generic_scene()
    scene["state_relations"] = [{"left": "channel", "operator": "<", "right": "level"}]

    states = build_export_states(scene)

    assert states
    assert all(state["channel"] < state["level"] for state in states.values())


def test_empty_schema_emits_one_empty_case():
    assert build_export_states({"states": {}}) == {"case_0000": {}}


def test_invalid_schema_fails_closed_without_curing_fallback():
    scene = {"states": {"mode": {"type": "string", "init": "NORMAL"}}}

    with pytest.raises(ValueError, match="invalid state schema"):
        build_export_states(scene)


def test_integer_policies_are_forwarded_to_matrix_generation():
    scene = {"states": {"level": {"type": "int", "min": 0, "max": 20, "init": 10}}}

    representative = build_export_states(scene, integer_policy="representative")
    boundaries = build_export_states(scene, integer_policy="boundaries")
    full = build_export_states(scene, integer_policy="full")

    assert list(representative.values()) != list(full.values())
    assert len(boundaries) == 3
    assert len(full) == 21


def test_matrix_size_limit_rejects_without_truncating():
    with pytest.raises(ValueError, match="max_cases=2"):
        build_export_states(_generic_scene(), max_cases=2)


def test_select_export_states_accepts_case_names_and_numeric_indexes():
    scene = _generic_scene()
    all_states = build_export_states(scene)
    first, second = list(all_states)[:2]

    selected = select_export_states(scene, ["0", second])

    assert list(selected) == [first, second]
    assert selected[first] == all_states[first]


def test_select_export_states_reports_unknown_case_without_guessing():
    with pytest.raises(ValueError, match="available cases=80"):
        select_export_states(_generic_scene(), ["normal_standby"])


def test_case_names_are_safe_for_enum_values_with_path_characters():
    scene = {"states": {"page": {"type": "enum", "values": ["A/B", ".."], "init": "A/B"}}}

    states = build_export_states(scene)
    names = list(states)

    assert names[0] == "case_0000__page-A_B"
    assert "/" not in names[0]
    assert ".." not in names[1]


def test_curing_representative_matrix_has_560_cases_without_blockers():
    scene = load_scene()

    states = build_export_states(scene, integer_policy="representative", max_cases=5000)
    summary = validate_matrix(scene, list(states.values()))

    assert len(states) == 560
    assert summary.blockers == 0
