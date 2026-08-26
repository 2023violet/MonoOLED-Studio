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


def _write_generic_scene(path: Path) -> Path:
    path.write_text(
        __import__('json').dumps({
            'schema_version': 1,
            'product': 'Generic CLI fixture',
            'canvas': {'w': 16, 'h': 8, 'preview_scale': 4},
            'storage': {'layout': 'VLSB', 'polarity': '1 = lit', 'bytes_per_frame': 16},
            'states': {
                'page': {'type': 'enum', 'values': ['HOME', 'SETTINGS'], 'init': 'HOME'},
                'channel': {'type': 'int', 'min': 1, 'max': 2, 'init': 1},
            },
            'elements': [],
            'timeline': [],
        }),
        encoding='utf-8',
    )
    return path


def test_export_command_accepts_generic_case_index(tmp_path):
    scene = _write_generic_scene(tmp_path / 'generic.json')
    result = run_cli(
        'export',
        '--scene', str(scene),
        '--states', '0',
        '--output', str(tmp_path),
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert (tmp_path / 'golden' / 'case_0000__page-HOME__channel-1.bin').exists()
    assert '1 frame(s)' in result.stdout


def test_export_command_rejects_legacy_clinical_case_name(tmp_path):
    scene = _write_generic_scene(tmp_path / 'generic.json')
    result = run_cli(
        'export',
        '--scene', str(scene),
        '--states', 'normal_standby',
        '--output', str(tmp_path / 'export'),
    )

    assert result.returncode == 2
    assert 'available cases=4' in result.stderr


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
