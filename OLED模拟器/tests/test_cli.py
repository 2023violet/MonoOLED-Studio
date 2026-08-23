import subprocess
import sys
from pathlib import Path

SIM = Path(__file__).resolve().parents[1]
CLI = SIM / 'cli.py'


def run_cli(*args):
    return subprocess.run([sys.executable, str(CLI), *args], text=True, capture_output=True)


def test_validate_command_reports_pass():
    result = run_cli('validate')
    assert result.returncode == 0, result.stdout + result.stderr
    assert 'PASS' in result.stdout
    assert '0 blocking' in result.stdout


def test_export_command_accepts_named_clinical_states(tmp_path):
    result = run_cli(
        'export',
        '--states', 'normal_standby,normal_running',
        '--seconds', '10',
        '--output', str(tmp_path),
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert (tmp_path / 'golden' / 'normal_standby.bin').exists()
    assert (tmp_path / 'golden' / 'normal_running.bin').exists()
    assert '2 frame(s)' in result.stdout


def test_simulate_command_runs_timeline_and_writes_realtime_jsonl(tmp_path):
    log = tmp_path / 'session.jsonl'
    result = run_cli('simulate', '--steps', '6', '--interval', '0', '--log', str(log))
    assert result.returncode == 0, result.stdout + result.stderr
    assert 't=0005' in result.stdout
    assert 'phase=running' in result.stdout
    assert 't=0006' in result.stdout
    assert 'seconds=299' in result.stdout
    text = log.read_text(encoding='utf-8')
    assert '"event": "FRAME"' in text
    assert '"event": "STATE"' in text
