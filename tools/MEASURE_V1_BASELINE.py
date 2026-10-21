"""Measure Python V1 against the same spec §5 metrics as the Rust V2 tools (G5).

* core: 256x128 encode + format p95, 50-screen firmware export, 50-screen
  evidence-package export (V1 `exporter.export_scene`), the same workloads as
  ``mono bench``;
* GUI: cold start (process launch -> first paint of the main window) and idle
  private memory, like ``tools/RUN_DESKTOP_BENCH.py``.

V1 code is imported unchanged; the GUI run uses a temporary project copy and
temporary preference directories.

Usage: python tools/MEASURE_V1_BASELINE.py [--runs 3]
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / 'src'
PROJECT = ROOT / 'test_assets' / 'projects' / 'curing_lite'

GUI_PROBE = r'''
import json, os, sys, time
sys.path.insert(0, os.environ['MONO_V1_SRC'])
t0 = float(os.environ['MONO_T0'])
from PySide6.QtCore import QObject, QEvent, QTimer
from PySide6.QtWidgets import QApplication
import gui
state = {'done': False}
class Probe(QObject):
    def eventFilter(self, obj, event):
        if not state['done'] and event.type() == QEvent.Paint and getattr(obj, 'isWindow', lambda: False)() and obj.isVisible():
            state['done'] = True
            first = (time.time() - t0) * 1000.0
            QTimer.singleShot(0, lambda: print(json.dumps({'cold_start_ms': first, 'pid': os.getpid()}), flush=True))
            QTimer.singleShot(3000, QApplication.instance().quit)
        return False
_orig_exec = QApplication.exec
def _exec(*_args):
    app = QApplication.instance()
    probe = Probe(app)
    app.installEventFilter(probe)
    return _orig_exec()
QApplication.exec = _exec
sys.argv = ['gui.py', '--project', os.environ['MONO_V1_PROJECT']]
raise SystemExit(gui.main())
'''


def private_mb(pid: int) -> float | None:
    sys.path.insert(0, str(ROOT / 'tools'))
    from RUN_DESKTOP_BENCH import private_mb as probe  # noqa: E402
    return probe(pid)


def core_bench() -> dict:
    sys.path.insert(0, str(SRC))
    from bitmap_encoding import MonoBitmap, bitmap_from_framebuffer, encode_bitmap
    from output_formatter import OutputItem, format_output
    from output_profiles import builtin_profiles
    from atomic_io import atomic_write_bytes
    from exporter import export_scene
    from project_workspace import ProjectWorkspace
    from render import render_scene
    from scene import init_state, load_scene

    profile = builtin_profiles()['ssd1306_vlsb_c']
    rows = [[1 if (x * 7 + y * 3) % 5 == 0 else 0 for x in range(256)] for y in range(128)]
    bitmap = MonoBitmap.from_rows(rows)
    samples = []
    for _ in range(200):
        t = time.perf_counter()
        encoded = encode_bitmap(bitmap, profile.encoding)
        format_output([OutputItem(name='bench', encoded=encoded)], profile.text, symbol='bench')
        samples.append((time.perf_counter() - t) * 1000.0)
    samples.sort()
    p95 = samples[round((len(samples) - 1) * 0.95)]

    project = ProjectWorkspace.load(PROJECT / 'project.oled.json')
    scene = load_scene(project.screen_path(project.active_screen), project_root=project.root)
    state = init_state(scene)
    work = Path(tempfile.mkdtemp(prefix='mono-v1-bench-'))
    try:
        t = time.perf_counter()
        for index in range(50):
            frame = render_scene(scene, dict(state)).framebuffer
            encoded = encode_bitmap(bitmap_from_framebuffer(frame), profile.encoding)
            formatted = format_output([OutputItem(name=f'screen_{index:02}', encoded=encoded)], profile.text, symbol='screen')
            atomic_write_bytes(work / 'firmware' / f'screen_{index:02}.h', formatted.text.encode('utf-8'))
        firmware = (time.perf_counter() - t) * 1000.0
        t = time.perf_counter()
        for index in range(50):
            export_scene(scene, work / 'evidence' / f'screen_{index:02}', {'current': dict(state)})
        evidence = (time.perf_counter() - t) * 1000.0
    finally:
        shutil.rmtree(work, ignore_errors=True)
    return {'encode_format_256x128_p95_ms': p95, 'firmware_export_total_ms': firmware, 'evidence_export_total_ms': evidence}


def gui_run(index: int) -> dict:
    with tempfile.TemporaryDirectory(prefix='mono-v1-gui-') as tmp:
        project = Path(tmp) / 'project'
        shutil.copytree(PROJECT, project)
        env = dict(os.environ, APPDATA=tmp, LOCALAPPDATA=tmp, XDG_CONFIG_HOME=tmp,
                   MONO_V1_SRC=str(SRC), MONO_V1_PROJECT=str(project / 'project.oled.json'))
        env['MONO_T0'] = repr(time.time())
        proc = subprocess.Popen([sys.executable, '-c', GUI_PROBE], env=env, stdout=subprocess.PIPE, text=True)
        line = proc.stdout.readline()
        time.sleep(1.5)
        # venv launchers start the real interpreter as a child: probe its own pid.
        pid = json.loads(line).get('pid', proc.pid) if line.strip() else proc.pid
        memory = private_mb(pid)
        try:
            proc.wait(timeout=30)
        except subprocess.TimeoutExpired:
            proc.kill()
        result = json.loads(line) if line.strip() else {'cold_start_ms': None}
        result.pop('pid', None)
        result['idle_private_mb'] = memory
        return result


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--runs', type=int, default=3)
    args = ap.parse_args()
    runs = [gui_run(i) for i in range(args.runs)]
    report = {'core': core_bench(), 'gui_runs': runs}
    print(json.dumps(report, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
