from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]

def main() -> int:
    required=[ROOT/'src/gui.py',ROOT/'tests/test_qt_v120_generic_product_closure.py',ROOT/'test_assets',ROOT/'docs']
    missing=[str(p) for p in required if not p.exists()]
    if missing:
        print('[FAIL] V12 required paths missing:', *missing, sep='\n  '); return 2
    if os.name != 'nt':
        print('[SKIP] V12 Real-Qt Windows gate requires native Windows; source contract remains testable cross-platform.')
        return 0
    env=os.environ.copy(); env['QT_QPA_PLATFORM']='windows'
    cmd=[sys.executable,'-m','pytest','-q','tests/test_qt_v120_generic_product_closure.py']
    print('[V12 Real-Qt]', ' '.join(cmd))
    return subprocess.call(cmd,cwd=ROOT,env=env)

if __name__=='__main__': raise SystemExit(main())
