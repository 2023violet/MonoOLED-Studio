from __future__ import annotations

import json
import sys
from pathlib import Path

SIM = Path(__file__).resolve().parents[1] / 'src'
sys.path.insert(0, str(SIM))

from commands import CommandRegistry
from preferences import PreferencesStore, default_preferences

# Mirrors the corruption found on a real user machine: nested dicts written
# where flat command ids belong, plus literal 'None' strings from a historical
# str(None) writer.
JUNK_SHORTCUTS_FILE = {
    'schema_version': 1,
    'language': 'en_US',
    'shortcuts': {
        'preferences.open': 'Ctrl+,',
        'designer.undo': 'None',
        'pixel.pencil': {'x': 1},
        'designer.redo': 'Ctrl+Y',
        'preferences': {'open': 'None'},
        'workspace': {'canvas_only': 'None'},
        'project': {'save': 'None'},
        'designer': {'undo': 'None', 'redo': 'None'},
        'pixel': {'pencil': 'None', 'select': 'None', 'fill': 'None'},
        'some.future.key': 'Ctrl+X',
    },
}


def _defaults() -> dict[str, str]:
    return default_preferences()['shortcuts']


def test_corrupt_shortcut_section_is_cleaned_on_load(tmp_path):
    target = tmp_path / 'preferences.json'
    target.write_text(json.dumps(JUNK_SHORTCUTS_FILE), encoding='utf-8')
    store = PreferencesStore.load(target)
    shortcuts = store.data['shortcuts']

    # nested dicts and unknown keys are dropped (closed command namespace)
    assert 'preferences' not in shortcuts
    assert 'workspace' not in shortcuts
    assert 'project' not in shortcuts
    assert 'designer' not in shortcuts
    assert 'pixel' not in shortcuts
    assert 'some.future.key' not in shortcuts

    # only known commands with flat string values remain
    assert set(shortcuts) == set(_defaults())
    assert all(isinstance(value, str) for value in shortcuts.values())

    # junked values fall back to the default binding; valid customs survive
    assert shortcuts['designer.undo'] == _defaults()['designer.undo']
    assert shortcuts['pixel.pencil'] == _defaults()['pixel.pencil']
    assert shortcuts['preferences.open'] == 'Ctrl+,'
    assert shortcuts['designer.redo'] == 'Ctrl+Y'


def test_shortcut_cleanup_is_idempotent_across_save_load(tmp_path):
    target = tmp_path / 'preferences.json'
    target.write_text(json.dumps(JUNK_SHORTCUTS_FILE), encoding='utf-8')
    store = PreferencesStore.load(target)
    store.save()
    again = PreferencesStore.load(target)
    assert again.data['shortcuts'] == store.data['shortcuts']


def test_setting_junk_shortcut_value_resets_to_default(tmp_path):
    store = PreferencesStore(tmp_path / 'preferences.json', default_preferences())
    store.set('shortcuts.designer.undo', 'None')
    assert store.get('shortcuts.designer.undo') == _defaults()['designer.undo']


def test_ui_dotted_round_trip_stays_flat_and_survives_reload(tmp_path):
    """The preferences UI writes dotted command ids; they must round-trip as
    flat section keys instead of regenerating nested-dict corruption."""
    target = tmp_path / 'preferences.json'
    store = PreferencesStore(target, default_preferences())
    store.set('shortcuts.designer.undo', 'Ctrl+Shift+Z')

    assert store.get('shortcuts.designer.undo') == 'Ctrl+Shift+Z'
    reloaded = PreferencesStore.load(target)
    assert reloaded.get('shortcuts.designer.undo') == 'Ctrl+Shift+Z'
    assert 'designer' not in reloaded.data['shortcuts']


def test_best_effort_rejects_non_string_bindings():
    registry = CommandRegistry()
    for command_id, shortcut in _defaults().items():
        registry.register(command_id, shortcut=shortcut)

    accepted, rejected = registry.apply_bindings_best_effort({'pixel.pencil': {'x': 1}})

    assert accepted == {}
    assert 'pixel.pencil' in rejected
    assert registry.shortcut('pixel.pencil') == _defaults()['pixel.pencil']


def test_cleared_binding_remains_a_valid_choice():
    registry = CommandRegistry()
    for command_id, shortcut in _defaults().items():
        registry.register(command_id, shortcut=shortcut)

    accepted, rejected = registry.apply_bindings_best_effort({'pixel.fill': ''})

    assert accepted == {'pixel.fill': ''}
    assert rejected == {}
    assert registry.shortcut('pixel.fill') == ''
