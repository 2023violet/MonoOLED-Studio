#!/usr/bin/env python3
from __future__ import annotations

"""Capture V12.3.1 Settings visual evidence across boundary configurations.

This is a GA evidence gate, not a screenshot-only utility: each screenshot is
accepted only when the same live PreferencesView reports zero geometry
violations. Every Settings page is captured for each bounded pairwise case.
"""

import argparse
import json
import os
import shutil
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / 'src'
OUT = ROOT / '.artifacts' / 'windows_ga' / 'settings_v1231_golden'

CASES = (
    ('1.0','zh_CN','light','compact','90%',720,560),
    ('1.25','en_US','dark','comfortable','100%',760,600),
    ('1.5','zh_CN','system','spacious','110%',900,620),
    ('1.75','en_US','light','compact','125%',980,680),
    ('2.0','zh_CN','dark','comfortable','150%',1180,720),
    ('2.25','en_US','system','spacious','90%',1440,900),
    ('2.5','zh_CN','dark','spacious','150%',760,680),
    ('3.0','en_US','light','comfortable','125%',900,720),
)


def _encode(case) -> str:
    return '|'.join(map(str, case))


def _decode(text: str):
    scale, language, theme, density, ui_scale, width, height = text.split('|')
    return scale, language, theme, density, ui_scale, int(width), int(height)


def _child(case_text: str, output: Path) -> int:
    sys.path.insert(0, str(SRC))
    try:
        from PySide6.QtWidgets import QApplication
        from i18n import Translator
        from preferences import PreferencesStore, default_preferences
        from preferences_qt import PreferencesWindow
        from qt_theme import build_stylesheet
        from runtime_settings import RuntimeSettings
    except Exception as exc:
        print(f'FAIL: Real-Qt import failed: {exc}', file=sys.stderr)
        return 2

    scale, language, theme, density, ui_scale, width, height = _decode(case_text)
    prefs = default_preferences()
    prefs['language'] = language
    prefs['appearance']['theme_mode'] = theme
    prefs['appearance']['density'] = density
    prefs['appearance']['ui_scale'] = ui_scale
    store = PreferencesStore(Path(os.environ['LOCALAPPDATA']) / 'MonoOLEDStudio' / 'preferences.json', prefs)
    store.save()
    runtime = RuntimeSettings.from_preferences(store)
    app = QApplication.instance() or QApplication([])
    app.setStyle('Fusion')
    app.setStyleSheet(build_stylesheet('monooled-dark' if theme == 'dark' else 'monooled-light', density, runtime.ui_scale))
    window = PreferencesWindow(store, Translator(language))
    window.resize(width, height)
    window.show()
    window.apply_runtime_settings(runtime)
    for _ in range(8): app.processEvents(); window.view.stabilize_layout()

    output.mkdir(parents=True, exist_ok=True)
    stem = f'{language}_{theme}_{density}_{ui_scale.replace("%","p")}_{scale.replace(".","p")}x_{width}x{height}'
    reports=[]
    failed=False
    for page in range(window.view.nav.count()):
        window.view.nav.setCurrentRow(page)
        for _ in range(4): app.processEvents(); window.view.stabilize_layout()
        issues=window.view.layout_violations()
        png=output/f'{stem}_page{page:02d}.png'
        captured=window.grab().save(str(png))
        reports.append({'page':page,'label':window.view.nav.item(page).text(),'screenshot':png.name,'captured':bool(captured),'violations':issues})
        if issues or not captured: failed=True
    (output/f'{stem}_layout.json').write_text(json.dumps({'case':case_text,'pages':reports},ensure_ascii=False,indent=2),encoding='utf-8')
    window.close(); app.processEvents()
    if failed:
        print(f'FAIL {case_text}: '+repr([r for r in reports if r['violations'] or not r['captured']]))
        return 1
    print(f'PASS {case_text}: {len(reports)} pages')
    return 0


def main() -> int:
    ap=argparse.ArgumentParser(); ap.add_argument('--child'); ap.add_argument('--output',default=str(OUT)); args=ap.parse_args()
    out=Path(args.output).resolve()
    if args.child: return _child(args.child,out)
    if os.name!='nt':
        print('SKIP: Settings golden capture requires Windows Real-Qt.')
        return 0
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True, exist_ok=True)
    failures=[]
    for case in CASES:
        text=_encode(case); scale=case[0]
        with tempfile.TemporaryDirectory(prefix='monooled-settings-v1231-') as td:
            env=os.environ.copy(); env['LOCALAPPDATA']=td; env['QT_SCALE_FACTOR']=scale; env['QT_AUTO_SCREEN_SCALE_FACTOR']='0'; env['MONOOLED_REDUCED_MOTION']='1'
            proc=subprocess.run([sys.executable,str(Path(__file__).resolve()),'--child',text,'--output',str(out)],cwd=ROOT,env=env,check=False,timeout=240)
            if proc.returncode: failures.append(text)
    print(f'V12.3.1 Settings visual evidence: {len(CASES)-len(failures)} PASS / {len(failures)} FAIL')
    if failures:
        print('Failed cases: '+', '.join(failures), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
