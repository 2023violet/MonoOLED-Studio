from pathlib import Path
import sys

SIM = Path(__file__).resolve().parents[1] / 'src'
sys.path.insert(0, str(SIM))

from state_preview import build_state_editor_specs, coerce_editor_value, format_state_label


GENERIC_SCHEMA = {
    'variables': {
        'page': {'type': 'enum', 'values': ['HOME', 'SETTINGS'], 'init': 'HOME'},
        'channel': {'type': 'int', 'min': 1, 'max': 4, 'init': 2},
        'level': {'type': 'int', 'values': [0, 25, 50, 75, 100], 'init': 50},
        'alarm': {'type': 'enum', 'values': ['OFF', 'ON'], 'init': 'OFF'},
    },
    'relations': [],
}


def test_schema_fields_preserve_order_and_map_editor_kinds():
    result = build_state_editor_specs(GENERIC_SCHEMA)

    assert result.valid is True
    assert [field.name for field in result.fields] == ['page', 'channel', 'level', 'alarm']
    assert [field.editor_kind for field in result.fields] == [
        'combo', 'spin', 'combo', 'combo'
    ]
    assert [field.initial for field in result.fields] == ['HOME', 2, 50, 'OFF']


def test_schema_field_labels_are_generic_and_not_curing_fallbacks():
    result = build_state_editor_specs(GENERIC_SCHEMA)

    assert format_state_label('current_cycle') == 'Current Cycle'
    assert {field.label for field in result.fields} == {
        'Page', 'Channel', 'Level', 'Alarm'
    }
    assert not hasattr(result, 'mode_combo')


def test_editor_values_preserve_types_and_reject_invalid_values():
    result = build_state_editor_specs(GENERIC_SCHEMA)
    by_name = {field.name: field for field in result.fields}

    assert coerce_editor_value(by_name['channel'], 4) == (True, 4)
    assert coerce_editor_value(by_name['level'], 75) == (True, 75)
    assert coerce_editor_value(by_name['page'], 'SETTINGS') == (True, 'SETTINGS')
    assert coerce_editor_value(by_name['channel'], 99) == (False, None)
    assert coerce_editor_value(by_name['level'], 60) == (False, None)
    assert coerce_editor_value(by_name['page'], 'UNKNOWN') == (False, None)


def test_empty_schema_is_valid_but_has_no_editors():
    result = build_state_editor_specs({'variables': {}, 'relations': []})

    assert result.valid is True
    assert result.fields == ()
    assert result.errors == ()


def test_invalid_schema_fails_closed_without_editor_specs():
    result = build_state_editor_specs({
        'variables': {
            'level': {'type': 'int', 'min': 10, 'max': 1, 'init': 3},
        },
    })

    assert result.valid is False
    assert result.fields == ()
    assert result.errors
