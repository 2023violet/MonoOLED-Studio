"""Measure the Rust desktop app against the spec §5 interactive budgets.

Runs ``monooled-studio --bench`` in a real window (preferences redirected to a
temporary directory), then reads the process's private memory while it idles.
Windows only for the memory probe; elsewhere memory is reported as null.

Usage: python tools/RUN_DESKTOP_BENCH.py [--exe target/release/monooled-studio.exe] [--runs 3]
"""
from __future__ import annotations

import argparse
import ctypes
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
BUDGETS = {'cold_start_ms': 1000.0, 'stroke_p95_ms': 8.0, 'theme_switch_p95_ms': 50.0,
           'max_handler_ms': 16.0, 'idle_private_mb': 80.0}
# Reported for transparency; not a spec budget (includes the vsync wait).
INFO = ('stroke_free_running_p95_ms', 'cold_start_from_main_ms')


def private_mb(pid: int) -> float | None:
    if sys.platform != 'win32':
        return None

    class Counters(ctypes.Structure):
        _fields_ = [('cb', ctypes.c_ulong), ('PageFaultCount', ctypes.c_ulong),
                    ('PeakWorkingSetSize', ctypes.c_size_t), ('WorkingSetSize', ctypes.c_size_t),
                    ('QuotaPeakPagedPoolUsage', ctypes.c_size_t), ('QuotaPagedPoolUsage', ctypes.c_size_t),
                    ('QuotaPeakNonPagedPoolUsage', ctypes.c_size_t), ('QuotaNonPagedPoolUsage', ctypes.c_size_t),
                    ('PagefileUsage', ctypes.c_size_t), ('PeakPagefileUsage', ctypes.c_size_t),
                    ('PrivateUsage', ctypes.c_size_t)]

    handle = ctypes.windll.kernel32.OpenProcess(0x1000 | 0x0010, False, pid)
    if not handle:
        return None
    counters = Counters()
    counters.cb = ctypes.sizeof(Counters)
    ok = ctypes.windll.psapi.GetProcessMemoryInfo(handle, ctypes.byref(counters), counters.cb)
    ctypes.windll.kernel32.CloseHandle(handle)
    return counters.PrivateUsage / (1024 * 1024) if ok else None


def run_once(exe: Path, project: Path, scratch: Path, index: int) -> dict:
    out = scratch / f'bench_{index}.json'
    out.unlink(missing_ok=True)
    env = dict(os.environ, APPDATA=str(scratch), LOCALAPPDATA=str(scratch), XDG_CONFIG_HOME=str(scratch))
    # Cold start counts from here, like the V1 baseline probe (MONO_T0; tools/MEASURE_V1_BASELINE.py at v1-final).
    env['MONO_T0'] = repr(time.time())
    proc = subprocess.Popen([str(exe), str(project), '--bench', str(out)], env=env)
    memory = None
    deadline = time.monotonic() + 120
    while proc.poll() is None and time.monotonic() < deadline:
        if out.exists() and memory is None:
            time.sleep(1.5)  # idle period inside the app's 3 s grace window
            memory = private_mb(proc.pid)
        time.sleep(0.1)
    if proc.poll() is None:
        proc.kill()
        raise RuntimeError('bench did not finish')
    result = json.loads(out.read_text(encoding='utf-8'))
    result['idle_private_mb'] = memory
    return result


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--exe', default=str(ROOT / 'target' / 'release' / ('monooled-studio.exe' if sys.platform == 'win32' else 'monooled-studio')))
    ap.add_argument('--project', default=str(ROOT / 'test_assets' / 'projects' / 'curing_lite' / 'project.oled.json'))
    ap.add_argument('--runs', type=int, default=3)
    args = ap.parse_args()
    with tempfile.TemporaryDirectory(prefix='mono-bench-') as tmp:
        runs = [run_once(Path(args.exe), Path(args.project), Path(tmp), i) for i in range(args.runs)]
    summary = {}
    for key, budget in BUDGETS.items():
        values = [r[key] for r in runs if r.get(key) is not None]
        worst = max(values) if values else None
        summary[key] = {'runs': values, 'worst': worst, 'budget': budget,
                        'pass': None if worst is None else worst <= budget}
    for key in INFO:
        values = [r[key] for r in runs if r.get(key) is not None]
        summary[key] = {'runs': values, 'worst': max(values) if values else None}
    print(json.dumps({'runs': runs, 'summary': summary}, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
