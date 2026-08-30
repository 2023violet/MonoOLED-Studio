from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
SIM = ROOT / 'src'
TOOLS = ROOT / 'tools'


def _bare_lf_count(raw: bytes) -> int:
    return raw.count(b'\n') - raw.count(b'\r\n')


def test_windows_command_scripts_are_real_crlf_files():
    scripts = sorted([*TOOLS.glob('*.bat'), *TOOLS.glob('*.cmd')])
    assert scripts, 'expected Windows command scripts'
    for path in scripts:
        raw = path.read_bytes()
        assert raw.count(b'\r\n') > 0, f'{path.name} has no CRLF records'
        assert _bare_lf_count(raw) == 0, f'{path.name} contains LF-only records'


def test_source_package_declares_git_eol_contract_for_windows_scripts():
    attrs = (ROOT / '.gitattributes').read_text(encoding='utf-8')
    assert '*.bat text eol=crlf' in attrs
    assert '*.cmd text eol=crlf' in attrs


def test_windows_ga_builder_uses_bounded_group_runner_instead_of_monolithic_pytest():
    builder = (TOOLS / 'BUILD_WINDOWS_GA.bat').read_text(encoding='utf-8')
    assert 'RUN_WINDOWS_TEST_GROUPS.py' in builder
    assert 'pytest "src\\tests" -q' not in builder
    assert '--phase source' in builder
    assert '--phase qt' in builder


def test_windows_group_runner_and_release_text_gate_exist():
    assert (TOOLS / 'RUN_WINDOWS_TEST_GROUPS.py').is_file()
    assert (TOOLS / 'VERIFY_WINDOWS_RELEASE_TEXT.py').is_file()


def test_pytest_selected_automation_module_collects_from_repo_root_without_pythonpath():
    env = os.environ.copy()
    env.pop('PYTHONPATH', None)
    result = subprocess.run(
        [sys.executable, '-m', 'pytest', 'tests/test_automation_reliability_v842.py', '--collect-only', '-q'],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert 'test_transaction_commit_marks_unsaved_scene_dirty' in result.stdout


def test_v843_release_identity_and_tools_are_present():
    version=(SIM/'VERSION').read_text(encoding='utf-8').strip()
    assert tuple(map(int,version.split('.'))) >= (8,4,3)
    gui = (SIM / 'gui.py').read_text(encoding='utf-8')
    assert 'APP_VERSION = load_version()' in gui
    assert (TOOLS / 'VERIFY_V843_FINAL.py').is_file()
    assert (TOOLS / 'BUILD_DELIVERY_V843.py').is_file()
    assert (TOOLS / 'VERIFY_V120_GENERIC_PRODUCT_CLOSURE.py').is_file()

def test_windows_group_runner_accepts_absolute_external_report_dir(tmp_path):
    result = subprocess.run(
        [
            sys.executable, str(TOOLS / 'RUN_WINDOWS_TEST_GROUPS.py'),
            '--phase', 'source', '--match', 'test_automation_reliability_v842.py',
            '--source-group-size', '1', '--group-timeout', '120',
            '--report-dir', str(tmp_path / 'reports'),
        ],
        cwd=ROOT, text=True, capture_output=True, timeout=180,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert (tmp_path / 'reports' / 'source_01.xml').is_file()
    assert (tmp_path / 'reports' / 'source_01.log').is_file()


def test_windows_group_runner_timeout_kills_descendant_process_tree(tmp_path):
    probe = r"""
import importlib.util, os, pathlib, subprocess, sys
root=pathlib.Path(sys.argv[1])
spec=importlib.util.spec_from_file_location('runner', root/'tools'/'RUN_WINDOWS_TEST_GROUPS.py')
mod=importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
child_code="import time; time.sleep(30)"
parent_code="import subprocess,sys,time; subprocess.Popen([sys.executable,'-c',%r]); time.sleep(30)" % child_code
rc=mod._run_process([sys.executable,'-c',parent_code], env=os.environ.copy(), timeout=1, log=pathlib.Path(sys.argv[2]))
print('RC',rc)
raise SystemExit(0 if rc==124 else 7)
"""
    try:
        result = subprocess.run(
            [sys.executable, '-c', probe, str(ROOT), str(tmp_path/'timeout.log')],
            cwd=ROOT, text=True, capture_output=True, timeout=6,
        )
    except subprocess.TimeoutExpired as exc:
        raise AssertionError('runner timeout did not terminate descendant process tree') from exc
    assert result.returncode == 0, result.stdout + result.stderr
    assert 'RC 124' in result.stdout


def test_windows_group_runner_does_not_wait_for_orphan_stdout_pipe(tmp_path):
    probe = r"""
import importlib.util, os, pathlib, subprocess, sys
root=pathlib.Path(sys.argv[1])
spec=importlib.util.spec_from_file_location('runner', root/'tools'/'RUN_WINDOWS_TEST_GROUPS.py')
mod=importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
parent_code="import subprocess,sys; subprocess.Popen([sys.executable,'-c','import time; time.sleep(30)'])"
rc=mod._run_process([sys.executable,'-c',parent_code], env=os.environ.copy(), timeout=5, log=pathlib.Path(sys.argv[2]))
print('RC',rc)
raise SystemExit(rc)
"""
    try:
        result = subprocess.run(
            [sys.executable, '-c', probe, str(ROOT), str(tmp_path/'orphan.log')],
            cwd=ROOT, text=True, capture_output=True, timeout=6,
        )
    except subprocess.TimeoutExpired as exc:
        raise AssertionError('runner waited for descendant-owned stdout after pytest parent exited') from exc
    assert result.returncode == 0, result.stdout + result.stderr
    assert 'RC 0' in result.stdout
