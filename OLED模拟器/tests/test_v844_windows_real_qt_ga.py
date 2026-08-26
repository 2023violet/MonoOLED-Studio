from __future__ import annotations

import importlib.util
import hashlib
import io
import os
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
TOOLS = ROOT / 'Developer_Tools'


def _load_windows_runner():
    path = TOOLS / 'RUN_WINDOWS_TEST_GROUPS.py'
    spec = importlib.util.spec_from_file_location('windows_test_groups_v844', path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _load_delivery_builder():
    path = TOOLS / 'BUILD_DELIVERY_V844.py'
    spec = importlib.util.spec_from_file_location('delivery_builder_v844', path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_windows_runner_falls_back_to_escaped_text_on_cp936_console():
    runner = _load_windows_runner()
    raw = io.BytesIO()
    console = io.TextIOWrapper(raw, encoding='cp936', newline='')

    runner._write_console('ASCII 中文 ģ\n', stream=console)
    console.flush()

    rendered = raw.getvalue().decode('cp936')
    assert rendered == 'ASCII 中文 \\u0123\n'


def test_windows_runner_preserves_original_utf8_log_during_console_fallback(tmp_path, monkeypatch):
    runner = _load_windows_runner()
    raw = io.BytesIO()
    console = io.TextIOWrapper(raw, encoding='cp936', newline='')
    monkeypatch.setattr(runner.sys, 'stdout', console)
    log = tmp_path / 'unicode.log'
    child = "import os; os.write(1, 'ASCII 中文 ģ\\n'.encode('utf-8'))"

    rc = runner._run_process([sys.executable, '-c', child], env=os.environ.copy(), timeout=10, log=log)
    console.flush()

    assert rc == 0
    assert log.read_text(encoding='utf-8') == 'ASCII 中文 ģ\n'
    assert '\\u0123' in raw.getvalue().decode('cp936')


def test_windows_runner_uses_native_qpa_for_real_qt_on_windows():
    runner = _load_windows_runner()
    env = {}

    runner._configure_qt_environment(env, platform_name='nt')

    assert env['QT_QPA_PLATFORM'] == 'windows'


def test_windows_runner_preserves_explicit_qpa_override():
    runner = _load_windows_runner()
    env = {'QT_QPA_PLATFORM': 'minimal'}

    runner._configure_qt_environment(env, platform_name='nt')

    assert env['QT_QPA_PLATFORM'] == 'minimal'


def test_v844_release_identity_and_closure_artifacts_are_current():
    sim = ROOT / 'OLED模拟器'
    assert (sim / 'VERSION').read_text(encoding='utf-8').strip() == '8.4.4'
    assert "APP_VERSION = '8.4.4'" in (sim / 'gui.py').read_text(encoding='utf-8')
    assert (sim / 'WINDOWS_REAL_QT_GA_FINAL_CLOSURE_V844.md').is_file()
    assert (sim / 'TEST_MATRIX_V844.md').is_file()
    assert (TOOLS / 'VERIFY_V844_FINAL.py').is_file()
    assert (TOOLS / 'BUILD_DELIVERY_V844.py').is_file()


def test_runtime_sha_writer_emits_a_verified_ascii_checksum(tmp_path):
    builder = _load_delivery_builder()
    target = tmp_path / 'runtime.zip'
    target.write_bytes(b'runtime-zip-probe')

    digest = builder.write_sha256_file(target)

    expected = hashlib.sha256(target.read_bytes()).hexdigest()
    assert digest == expected
    assert target.with_suffix('.zip.sha256').read_bytes() == (
        f'{expected}  runtime.zip\n'.encode('ascii')
    )


def test_windows_builder_fails_through_python_owned_runtime_sha_generation():
    batch = (TOOLS / 'BUILD_WINDOWS_EXE.bat').read_text(encoding='utf-8')
    assert '--sha256-only "%ZIP%" || exit /b 2' in batch
    assert 'Get-FileHash' not in batch
