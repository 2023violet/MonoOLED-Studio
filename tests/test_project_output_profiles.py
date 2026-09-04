from __future__ import annotations

import json

import pytest

from output_profiles import OutputProfile
from project_workspace import ExternalProjectModificationError, ProjectWorkspace, create_project


def test_new_project_contains_portable_default_output_profile(tmp_path):
    project = create_project(tmp_path / 'demo', name='Demo')

    payload = json.loads(project.path.read_text(encoding='utf-8'))
    workbench = payload['output_workbench']
    assert workbench['schema'] == 1
    assert workbench['active_profile'] == 'ssd1306_vlsb_c'
    assert workbench['profiles']['ssd1306_vlsb_c']['encoding'] == {
        'bit_axis': 'vertical', 'group_order': 'row_major',
        'bit_order': 'lsb_first', 'polarity': 'one_is_lit',
    }


def test_old_project_gets_read_only_default_without_rewriting_manifest(tmp_path):
    project = create_project(tmp_path / 'old', name='Old')
    payload = json.loads(project.path.read_text(encoding='utf-8'))
    payload.pop('output_workbench')
    project.path.write_text(json.dumps(payload), encoding='utf-8')
    before = project.path.read_bytes()

    loaded = ProjectWorkspace.load(project.path)
    active, profiles = loaded.get_output_profiles()

    assert active == 'ssd1306_vlsb_c'
    assert profiles[active].name == 'SSD1306 VLSB · C Header'
    assert project.path.read_bytes() == before


def test_profile_mutations_are_atomic_and_round_trip(tmp_path):
    project = create_project(tmp_path / 'demo', name='Demo')
    raw = OutputProfile.default().to_dict()
    raw['name'] = 'My C51'
    raw['encoding']['bit_axis'] = 'horizontal'
    raw['encoding']['group_order'] = 'row_major'
    raw['encoding']['bit_order'] = 'msb_first'

    project.upsert_output_profile('my_c51', raw, activate=True)
    loaded = ProjectWorkspace.load(project.path)
    active, profiles = loaded.get_output_profiles()

    assert active == 'my_c51'
    assert profiles['my_c51'].encoding.bit_axis == 'horizontal'
    assert profiles['my_c51'].encoding.bit_order == 'msb_first'


def test_invalid_profile_does_not_change_memory_or_disk(tmp_path):
    project = create_project(tmp_path / 'demo', name='Demo')
    before_data = json.loads(json.dumps(project.data))
    before_disk = project.path.read_bytes()
    raw = OutputProfile.default().to_dict()
    raw['encoding']['bit_axis'] = 'diagonal'

    with pytest.raises(ValueError, match='bit_axis'):
        project.upsert_output_profile('broken', raw)

    assert project.data == before_data
    assert project.path.read_bytes() == before_disk


def test_external_manifest_change_blocks_profile_write(tmp_path):
    project = create_project(tmp_path / 'demo', name='Demo')
    project.path.write_text(project.path.read_text(encoding='utf-8') + ' ', encoding='utf-8')

    with pytest.raises(ExternalProjectModificationError):
        project.set_active_output_profile('ssd1306_vlsb_c')
