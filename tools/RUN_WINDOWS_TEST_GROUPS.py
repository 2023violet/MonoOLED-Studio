#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import tempfile
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
SIM = ROOT / 'src'
TESTS = ROOT / 'tests'
DEFAULT_SCALES = ('1.0','1.25','1.5','1.75','2.0','2.25','2.5','3.0')


def _write_console(text: str, stream=None) -> None:
    target = stream if stream is not None else sys.stdout
    try:
        target.write(text)
    except UnicodeEncodeError:
        encoding = getattr(target, 'encoding', None) or 'utf-8'
        safe = text.encode(encoding, errors='backslashreplace').decode(encoding)
        target.write(safe)


def _configure_qt_environment(env: dict[str, str], *, platform_name: str = os.name) -> None:
    if platform_name == 'nt':
        env.setdefault('QT_QPA_PLATFORM', 'windows')


def isolated_user_state_env(env: dict[str, str], root: Path) -> dict[str, str]:
    """Return an env copy whose persistent user state is unique to one GA process."""
    root = Path(root).resolve()
    roaming = root / 'Roaming'
    root.mkdir(parents=True, exist_ok=True)
    roaming.mkdir(parents=True, exist_ok=True)
    out = env.copy()
    out['LOCALAPPDATA'] = str(root)
    out['APPDATA'] = str(roaming)
    return out


def test_inventory() -> tuple[list[Path], list[Path]]:
    all_tests = sorted(TESTS.glob('test_*.py'))
    qt_tests = sorted(TESTS.glob('test_qt_*.py'))
    qt_set = set(qt_tests)
    source = [p for p in all_tests if p not in qt_set]
    return source, qt_tests


def chunks(items: list[Path], size: int) -> list[list[Path]]:
    size = max(1, int(size))
    return [items[i:i+size] for i in range(0, len(items), size)]


def _junit_counts(path: Path) -> dict[str, int]:
    root = ET.parse(path).getroot()
    nodes = [root] if root.tag == 'testsuite' else list(root.findall('.//testsuite'))
    if not nodes:
        return {'tests':0,'failures':0,'errors':0,'skipped':0}
    # pytest's root testsuites contains aggregate child suite; sum leaf suites only.
    leaves = [n for n in nodes if not list(n.findall('testsuite'))]
    nodes = leaves or nodes
    out = {'tests':0,'failures':0,'errors':0,'skipped':0}
    for node in nodes:
        for key in out:
            out[key] += int(float(node.attrib.get(key, '0') or 0))
    return out


def _kill_process_tree(proc: subprocess.Popen) -> None:
    if os.name == 'nt':
        subprocess.run(
            ['taskkill', '/PID', str(proc.pid), '/T', '/F'],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False,
        )
    else:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass


def _run_process(cmd: list[str], *, env: dict[str,str], timeout: int, log: Path) -> int:
    log.parent.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    timed_out = False
    # Write child output directly to the log file. Do not use PIPE: a test can
    # spawn a descendant that inherits stdout after pytest exits, and waiting
    # for pipe EOF would make the GA runner itself appear hung.
    with log.open('w', encoding='utf-8', newline='\n') as stream:
        popen_kwargs = dict(cwd=ROOT, env=env, stdout=stream, stderr=subprocess.STDOUT)
        if os.name == 'nt':
            popen_kwargs['creationflags'] = getattr(subprocess, 'CREATE_NEW_PROCESS_GROUP', 0)
        else:
            popen_kwargs['start_new_session'] = True
        proc = subprocess.Popen(cmd, **popen_kwargs)
        try:
            proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            _kill_process_tree(proc)
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)
        stream.flush()
    elapsed = time.monotonic() - started
    output = log.read_text(encoding='utf-8', errors='replace') if log.exists() else ''
    if output:
        _write_console(output if output.endswith('\n') else output+'\n')
    try:
        shown_log=log.relative_to(ROOT)
    except ValueError:
        shown_log=log
    print(f'[GROUP] elapsed={elapsed:.1f}s log={shown_log}')
    if timed_out:
        print(f'[TIMEOUT] exceeded {timeout}s: {" ".join(cmd)}', file=sys.stderr)
        return 124
    return int(proc.returncode or 0)


def _pytest_group(python: str, files: list[Path], *, report_dir: Path, tag: str, timeout: int, env: dict[str,str], no_skips: bool) -> int:
    xml = report_dir / f'{tag}.xml'
    log = report_dir / f'{tag}.log'
    rels = [p.relative_to(ROOT).as_posix() for p in files]
    cmd = [python, '-m', 'pytest', *rels, '-q', f'--junitxml={xml.as_posix()}']
    print(f'\n=== {tag}: {len(files)} module(s), timeout={timeout}s ===')
    rc = _run_process(cmd, env=env, timeout=timeout, log=log)
    if rc:
        return rc
    counts = _junit_counts(xml)
    print(f'[JUNIT] {tag}: {counts}')
    if counts['failures'] or counts['errors']:
        return 2
    if no_skips and counts['skipped']:
        print(f'[FAIL] {tag}: Real-Qt gate forbids {counts["skipped"]} skipped test(s)', file=sys.stderr)
        return 3
    if no_skips:
        verify = ROOT / 'tools' / 'VERIFY_JUNIT_NO_SKIPS.py'
        rc = _run_process([python, str(verify), str(xml)], env=env, timeout=60, log=report_dir/f'{tag}_no_skips.log')
        if rc:
            return rc
    return 0


def run_source(args, env: dict[str,str], report_dir: Path) -> int:
    source, _ = test_inventory()
    if args.match:
        source = [p for p in source if args.match in p.name]
    if not source:
        print('[FAIL] no source tests selected', file=sys.stderr); return 2
    groups = chunks(source, args.source_group_size)
    print(f'[SOURCE] modules={len(source)} groups={len(groups)} group_size={args.source_group_size}')
    for idx, group in enumerate(groups, 1):
        rc = _pytest_group(args.python, group, report_dir=report_dir, tag=f'source_{idx:02d}', timeout=args.group_timeout, env=env, no_skips=False)
        if rc:
            return rc
    return 0


def run_qt(args, env: dict[str,str], report_dir: Path) -> int:
    _, qt = test_inventory()
    if args.match:
        qt = [p for p in qt if args.match in p.name]
    if not qt:
        print('[FAIL] no Real-Qt tests selected', file=sys.stderr); return 2
    scales = tuple(s.strip() for s in args.scales.split(',') if s.strip())
    if not scales:
        print('[FAIL] no QT scales selected', file=sys.stderr); return 2
    print(f'[REAL-QT] modules={len(qt)} scales={scales}; each module is an isolated process')
    for scale in scales:
        scale_env = env.copy(); scale_env['QT_SCALE_FACTOR'] = scale
        scale_tag = scale.replace('.', '_')
        for path in qt:
            tag = f'qt_{scale_tag}_{path.stem}'
            with tempfile.TemporaryDirectory(prefix=f'monooled-ga-{tag}-') as td:
                case_env = isolated_user_state_env(scale_env, Path(td))
                rc = _pytest_group(args.python, [path], report_dir=report_dir, tag=tag, timeout=args.qt_timeout, env=case_env, no_skips=True)
            if rc:
                return rc
        if args.qt_smokes:
            for smoke_name, smoke_args in (
                ('startup', ['--startup-smoke']),
                ('layout', ['--layout-smoke']),
                ('settings', ['--settings-smoke']),
                ('font', ['--font-smoke']),
            ):
                tag=f'qt_{scale_tag}_{smoke_name}_smoke'
                with tempfile.TemporaryDirectory(prefix=f'monooled-ga-{tag}-') as td:
                    case_env = isolated_user_state_env(scale_env, Path(td))
                    rc=_run_process([args.python, str(SIM/'gui.py'), *smoke_args], env=case_env, timeout=args.qt_timeout, log=report_dir/f'{tag}.log')
                if rc:
                    return rc
    return 0


def main() -> int:
    parser=argparse.ArgumentParser(description='Bounded Windows GA pytest runner; isolates source groups and every Real-Qt module.')
    parser.add_argument('--phase', choices=('source','qt'), required=True)
    parser.add_argument('--python', default=sys.executable)
    parser.add_argument('--report-dir', default=str(SIM/'reports/windows_ga'))
    parser.add_argument('--source-group-size', type=int, default=8)
    parser.add_argument('--group-timeout', type=int, default=300)
    parser.add_argument('--qt-timeout', type=int, default=300)
    parser.add_argument('--scales', default=','.join(DEFAULT_SCALES))
    parser.add_argument('--match', default='')
    parser.add_argument('--qt-smokes', action='store_true', default=True)
    parser.add_argument('--list-only', action='store_true')
    args=parser.parse_args()

    source, qt = test_inventory()
    if args.list_only:
        print(f'source_modules={len(source)}')
        for p in source: print('SOURCE', p.name)
        print(f'qt_modules={len(qt)}')
        for p in qt: print('QT', p.name)
        return 0

    report_dir=Path(args.report_dir)
    if not report_dir.is_absolute(): report_dir=ROOT/report_dir
    report_dir.mkdir(parents=True, exist_ok=True)
    env=os.environ.copy()
    sim=str(SIM)
    existing=env.get('PYTHONPATH','')
    env['PYTHONPATH']=sim+(os.pathsep+existing if existing else '')
    env['PYTHONDONTWRITEBYTECODE']='1'
    env.setdefault('QT_LOGGING_RULES','qt.qpa.*=false')
    _configure_qt_environment(env)
    if args.phase=='source': return run_source(args,env,report_dir)
    return run_qt(args,env,report_dir)

if __name__=='__main__':
    raise SystemExit(main())
