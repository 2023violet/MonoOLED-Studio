#!/usr/bin/env python3
from __future__ import annotations

"""V12.3.1 Settings reliability gate for real Windows Qt.

Runs the embedded Settings boundary matrix and a 500-cycle state-machine soak.
The normal Real-Qt inventory additionally executes the dedicated Qt module at
all mandatory QT_SCALE_FACTOR values.
"""

import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
GUI = ROOT / 'src' / 'gui.py'


def _run(*args: str, timeout: int) -> int:
    env = os.environ.copy()
    env.setdefault('MONOOLED_REDUCED_MOTION', '1')
    proc = subprocess.run([sys.executable, str(GUI), *args], cwd=ROOT, env=env, timeout=timeout, check=False)
    return int(proc.returncode)


def main() -> int:
    if os.name != 'nt':
        print('SKIP: V12.3.1 Settings reliability gate requires Windows Real-Qt.')
        return 0
    if _run('--settings-smoke', timeout=180):
        print('FAIL: Settings boundary smoke failed.', file=sys.stderr)
        return 2
    if _run('--settings-soak', '--settings-soak-cycles', '500', timeout=600):
        print('FAIL: Settings 500-cycle soak failed.', file=sys.stderr)
        return 2
    print('PASS: V12.3.1 Settings reliability smoke + 500-cycle soak')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
