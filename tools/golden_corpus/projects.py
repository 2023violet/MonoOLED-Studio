"""Project manifest persistence, round-trip and path-safety cases."""
from __future__ import annotations

import json
from pathlib import Path
import shutil

from .common import ROOT, byte_result, case, replace_root

from output_profiles import builtin_profiles, validate_profile_id
from project_workspace import (
    ExternalProjectModificationError,
    InvalidProjectPath,
    ProjectWorkspace,
    create_project,
    resolve_under_root,
    validate_screen_id,
)

NAME = 'projects'
SOURCES = ('src/project_workspace.py', 'src/output_profiles.py', 'src/atomic_io.py')

CURING_LITE = ROOT / 'test_assets' / 'projects' / 'curing_lite'


def _snapshot(root: Path) -> dict:
    return {path.relative_to(root).as_posix(): byte_result(path.read_bytes())
            for path in sorted(root.rglob('*')) if path.is_file() and path.suffix == '.json'}


def _error(exc: Exception, root: Path) -> dict:
    return {'error': type(exc).__name__, 'message': replace_root(str(exc), root)}


def _profiles_summary(project: ProjectWorkspace) -> dict:
    active, profiles = project.get_output_profiles()
    return {'active': active, 'profiles': {key: value.to_dict() for key, value in profiles.items()}}


def _roundtrip_cases(work: Path) -> list[dict]:
    cases = []
    copy = work / 'curing_lite'
    shutil.copytree(CURING_LITE, copy)
    manifest = copy / 'project.oled.json'
    before = manifest.read_bytes()
    project = ProjectWorkspace.load(manifest)
    loaded = {
        'name': project.name,
        'active_screen': project.active_screen,
        'screens': [screen.__dict__ for screen in project.screens],
        'asset_dirs': list(project.asset_dirs),
        'output': _profiles_summary(project),
        'manifest_unchanged_after_open': manifest.read_bytes() == before,
    }
    cases.append(case('project-curing_lite-open', 'project_open', 'strict',
                      {'project': 'test_assets/projects/curing_lite/project.oled.json'},
                      {'source': byte_result(before), 'loaded': loaded}))
    project.save()
    cases.append(case('project-curing_lite-save', 'project_save', 'strict',
                      {'project': 'test_assets/projects/curing_lite/project.oled.json', 'operation': 'open then save without edits'},
                      {'saved': byte_result(manifest.read_bytes())}))
    return cases


def _create_cases(work: Path) -> list[dict]:
    cases = []
    root = work / 'golden'
    project = create_project(root, name='Golden', canvas=(128, 32))
    cases.append(case('project-create-golden-128x32', 'project_create', 'strict',
                      {'name': 'Golden', 'canvas': [128, 32]}, {'files': _snapshot(root)}))

    steps = [
        ('upsert-profile', lambda: project.upsert_output_profile('my_row', builtin_profiles()['row_msb_c51'], activate=True)),
        ('set-active-profile', lambda: project.set_active_output_profile('ssd1306_vlsb_c')),
        ('delete-profile', lambda: project.delete_output_profile('my_row')),
        ('add-screen', lambda: project.add_screen('status', label='Status', canvas=(128, 64))),
        ('duplicate-screen', lambda: project.duplicate_screen('status', new_id='status_copy', label='Copy')),
        ('rename-screen', lambda: project.rename_screen('status_copy', new_id='renamed', label='Renamed')),
        ('remove-screen', lambda: project.remove_screen('renamed')),
    ]
    for label, action in steps:
        action()
        project.save()
        cases.append(case(f'project-op-{label}', 'project_operation', 'strict',
                          {'base': 'project-create-golden-128x32', 'operations_through': label},
                          {'files': _snapshot(root), 'output': _profiles_summary(project)}))

    manifest = root / 'project.oled.json'
    manifest.write_bytes(manifest.read_bytes().replace(b'"Golden"', b'"Edited"'))
    try:
        project.save()
    except ExternalProjectModificationError as exc:
        cases.append(case('project-save-rejects-external-modification', 'project_operation', 'strict',
                          {'base': 'project-op-remove-screen', 'external_edit': 'name Golden -> Edited'}, _error(exc, root)))
    try:
        project.add_screen('STATUS')
    except (ValueError, InvalidProjectPath) as exc:
        cases.append(case('project-add-screen-rejects-case-collision', 'project_operation', 'strict',
                          {'existing': 'status', 'new': 'STATUS'}, _error(exc, root)))
    return cases


def _legacy_cases(work: Path) -> list[dict]:
    root = work / 'legacy'
    create_project(root, name='Legacy', canvas=(128, 32))
    manifest = root / 'project.oled.json'
    data = json.loads(manifest.read_text(encoding='utf-8'))
    data.pop('output_workbench')
    manifest.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8', newline='\n')
    before = manifest.read_bytes()
    project = ProjectWorkspace.load(manifest)
    summary = _profiles_summary(project)
    return [case('project-legacy-open-no-output-workbench', 'project_open', 'strict',
                 {'source': byte_result(before)},
                 {'rewritten': manifest.read_bytes() != before, 'output': summary})]


def _rejection_cases(work: Path) -> list[dict]:
    root = work / 'reject'
    root.mkdir()
    cases = []
    for label, member in (('parent', '../escape.json'), ('absolute', str(work / 'abs.json')), ('nested-parent', 'a/../../b.json')):
        try:
            resolve_under_root(root, member)
            outcome = {'accepted': True}
        except InvalidProjectPath as exc:
            outcome = _error(exc, work)
        cases.append(case(f'path-reject-{label}', 'path_safety', 'strict',
                          {'member': replace_root(member, work)}, outcome))
    for label, value in (('empty', ''), ('dot', '.'), ('leading-space', ' a'), ('trailing-dot', 'a.'),
                         ('slash', 'a/b'), ('colon', 'a:b'), ('reserved', 'CON'), ('reserved-ext', 'con.json'),
                         ('too-long', 'x' * 97), ('ok-uppercase', 'Main')):
        try:
            outcome = {'accepted': validate_screen_id(value)}
        except InvalidProjectPath as exc:
            outcome = _error(exc, work)
        cases.append(case(f'screen-id-{label}', 'path_safety', 'strict', {'screen_id': value}, outcome))
    for label, value in (('uppercase', 'Bad-ID'), ('too-long', 'a' * 65), ('ok', 'my_row-1')):
        try:
            outcome = {'accepted': validate_profile_id(value)}
        except ValueError as exc:
            outcome = _error(exc, work)
        cases.append(case(f'profile-id-{label}', 'path_safety', 'strict', {'profile_id': value}, outcome))
    return cases


def build(work: Path) -> list[dict]:
    return _roundtrip_cases(work) + _create_cases(work) + _legacy_cases(work) + _rejection_cases(work)
