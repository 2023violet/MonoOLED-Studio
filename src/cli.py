#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
import sys
import time

from asset_library import AssetLibrary
from batch_validate import validate_matrix, write_matrix_report
from c_export import write_c_header
from design_rules import check_design_rules
from evidence import frame_evidence
from exporter import ExportBlockedError, export_scene
from handoff import build_handoff_package
from export_matrix import build_export_states, select_export_states
from project_workspace import ProjectWorkspace
from render import render_scene
from runtime import SceneRuntime
from scene import init_state, load_scene, scene_root
from session_log import SessionLogger
from validate import has_blockers, validate_scene


def _load_for_args(args):
    project_path = getattr(args, 'project', '') or ''
    if project_path:
        project = ProjectWorkspace.load(project_path)
        scene = load_scene(project.screen_path(project.active_screen), project_root=project.root)
        scene['_project_path'] = str(project.path)
        scene['_asset_dirs'] = list(project.asset_dirs)
        scene['_design_rules'] = dict(project.data.get('design_rules') or {})
        return project, scene
    return None, load_scene(getattr(args, 'scene', 'main_scene'))


def _state_from_args(scene: dict, args) -> dict:
    state = init_state(scene)
    for key in ('mode', 'phase', 'seconds', 'battery'):
        value = getattr(args, key, None)
        if value is not None and key in state:
            state[key] = value
    return state


def _print_findings(findings) -> None:
    for finding in findings:
        suffix = f' [{finding.element_id}]' if finding.element_id else ''
        print(f'{finding.severity} {finding.code}{suffix}: {finding.message}')


def cmd_validate(args) -> int:
    _project, scene = _load_for_args(args)
    state = _state_from_args(scene, args)
    findings = list(validate_scene(scene, state)) + check_design_rules(scene, scene.get('_design_rules') or {})
    blocking = sum(1 for f in findings if f.severity in {'ERROR', 'BLOCKER'})
    _print_findings(findings)
    print(f"{'PASS' if not blocking else 'FAIL'}: {blocking} blocking finding(s), {len(findings)} total")
    return 1 if blocking else 0


def cmd_export(args) -> int:
    _project, scene = _load_for_args(args)
    tokens = [t for t in args.states.split(',') if t.strip()] if args.states else ['all']
    try:
        states = select_export_states(
            scene,
            tokens,
            integer_policy=args.integer_policy,
            max_cases=args.max_cases,
            allow_large_matrix=args.allow_large_matrix,
        )
        summary = export_scene(scene, Path(args.output), states)
    except (ExportBlockedError, ValueError) as exc:
        print(f'FAIL: {exc}', file=sys.stderr)
        return 2
    print(f'PASS: exported {summary.frame_count} frame(s) to {summary.output_dir}')
    for name, digest in sorted(summary.frame_hashes.items()):
        print(f'  {name}: {digest}')
    return 0


def cmd_simulate(args) -> int:
    _project, scene = _load_for_args(args)
    log_path = Path(args.log)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    logger = SessionLogger(log_path)
    try:
        runtime = SceneRuntime(scene, logger=logger)
        for key in ('mode', 'phase', 'seconds', 'battery'):
            value = getattr(args, key, None)
            if value is not None and key in runtime.state:
                runtime.set_state(key, value)

        def emit_frame():
            result = render_scene(scene, runtime.state)
            payload = frame_evidence(result, runtime.state, elapsed=runtime.elapsed, project_root=scene_root(scene))
            logger.log('FRAME', **payload)
            state=runtime.state
            fields=' '.join(f'{k}={state[k]}' for k in ('mode','phase','seconds','battery') if k in state)
            print(f"t={runtime.elapsed:04d} {fields} sha256={payload['sha256']}")

        emit_frame()
        for _ in range(args.steps):
            if args.interval > 0:
                time.sleep(args.interval)
            runtime.step(1)
            emit_frame()
        logger.write_markdown(log_path.with_suffix('.md'))
    finally:
        logger.close()
    print(f'PASS: session log -> {log_path}')
    return 0


def cmd_batch_validate(args) -> int:
    _project, scene = _load_for_args(args)
    matrix = list(build_export_states(
        scene,
        integer_policy=args.integer_policy,
        max_cases=args.max_cases,
        allow_large_matrix=args.allow_large_matrix,
    ).values())
    summary = validate_matrix(scene, matrix)
    target = write_matrix_report(summary, args.output)
    rules = check_design_rules(scene, scene.get('_design_rules') or {})
    if rules:
        with Path(target).open('a', encoding='utf-8') as fp:
            fp.write('\n## Project Design Rules\n\n')
            for f in rules:
                fp.write(f'- **{f.severity}/{f.code}**: {f.message}\n')
    rule_blockers = sum(1 for f in rules if f.severity in {'ERROR', 'BLOCKER'})
    blockers = summary.blockers + rule_blockers
    print(f"{'PASS' if not blockers else 'FAIL'}: {summary.cases} cases, {summary.findings + len(rules)} findings, {blockers} blockers -> {target}")
    return 1 if blockers else 0


def cmd_handoff(args) -> int:
    _project, scene = _load_for_args(args)
    tokens = [t for t in args.states.split(',') if t.strip()] if args.states else ['all']
    try:
        states = select_export_states(
            scene,
            tokens,
            integer_policy=args.integer_policy,
            max_cases=args.max_cases,
            allow_large_matrix=args.allow_large_matrix,
        )
        summary = build_handoff_package(
            scene,
            args.output,
            states=states,
            integer_policy=args.integer_policy,
        )
    except (ExportBlockedError, ValueError) as exc:
        print(f'FAIL: {exc}', file=sys.stderr)
        return 2
    print(f'PASS: handoff {summary.frame_count} frame(s) -> {args.output}')
    return 0


def cmd_asset_audit(args) -> int:
    project, scene = _load_for_args(args)
    root = scene_root(scene)
    dirs = project.asset_dirs if project else tuple(scene.get('_asset_dirs') or ['assets'])
    lib = AssetLibrary(root, dirs)
    entries = lib.scan()
    health = lib.health_report()
    print(f'Assets: {len(entries)}')
    print(f'Duplicate groups: {len(health.duplicates)}')
    print(f'Unused (without state usage input): {len(health.unused)}')
    print(f'Invalid: {len(health.invalid)}')
    for path, error in health.invalid:
        print(f'INVALID {path}: {error}')
    return 1 if health.invalid else 0


def cmd_c_header(args) -> int:
    _project, scene = _load_for_args(args)
    state = _state_from_args(scene, args)
    result = render_scene(scene, state)
    target = write_c_header(result.framebuffer, args.output, name=args.name)
    print(f'PASS: C header -> {target}')
    return 0


def _add_source(parser) -> None:
    parser.add_argument('--scene', default='main_scene')
    parser.add_argument('--project', default='', help='optional project.oled.json; takes precedence over --scene')


def _add_state(parser) -> None:
    parser.add_argument('--mode')
    parser.add_argument('--phase')
    parser.add_argument('--seconds', type=int)
    parser.add_argument('--battery', type=int)


def _add_matrix(parser) -> None:
    parser.add_argument('--states', default='all')
    parser.add_argument('--integer-policy', choices=('representative', 'boundaries', 'full'), default='representative')
    parser.add_argument('--max-cases', type=int, default=5000)
    parser.add_argument('--allow-large-matrix', action='store_true')


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description='MonoOLED Studio canonical CLI')
    sub = parser.add_subparsers(dest='command', required=True)

    validate = sub.add_parser('validate', help='validate the current scene/state')
    _add_source(validate); _add_state(validate); validate.set_defaults(func=cmd_validate)

    export = sub.add_parser('export', help='export one or more states')
    _add_source(export)
    _add_matrix(export)
    export.add_argument('--output', default=str(Path(__file__).resolve().parent / 'exports' / 'latest'))
    export.set_defaults(func=cmd_export)

    simulate = sub.add_parser('simulate', help='run UI-state timeline and stream JSONL evidence')
    _add_source(simulate); _add_state(simulate)
    simulate.add_argument('--steps', type=int, default=10)
    simulate.add_argument('--interval', type=float, default=1.0)
    simulate.add_argument('--log', default=str(Path(__file__).resolve().parent / 'logs' / 'session.jsonl'))
    simulate.set_defaults(func=cmd_simulate)

    batch = sub.add_parser('batch-validate', help='validate a state combination matrix')
    _add_source(batch)
    batch.add_argument('--integer-policy', choices=('boundaries', 'full'), default='boundaries')
    batch.add_argument('--max-cases', type=int, default=5000)
    batch.add_argument('--allow-large-matrix', action='store_true')
    batch.add_argument('--output', default=str(Path(__file__).resolve().parent / 'reports' / 'batch_validation.md'))
    batch.set_defaults(func=cmd_batch_validate)

    handoff = sub.add_parser('handoff', help='build deterministic Code AI handoff ZIP')
    _add_source(handoff)
    _add_matrix(handoff)
    handoff.add_argument('--output', default=str(Path(__file__).resolve().parent / 'exports' / 'OLED_Code_AI_Handoff.zip'))
    handoff.set_defaults(func=cmd_handoff)

    audit = sub.add_parser('asset-audit', help='scan project asset health')
    _add_source(audit); audit.set_defaults(func=cmd_asset_audit)

    cheader = sub.add_parser('c-header', help='export current canonical framebuffer as C header')
    _add_source(cheader); _add_state(cheader)
    cheader.add_argument('--output', required=True); cheader.add_argument('--name', default='oled_frame')
    cheader.set_defaults(func=cmd_c_header)
    return parser


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except (KeyError, ValueError, OSError) as exc:
        print(f'ERROR: {exc}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
