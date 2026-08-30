#!/usr/bin/env python3
from __future__ import annotations

"""Capture the V10 UI Craft Windows Real-Qt visual verification matrix.

Run on Windows from the repository root after rebuilding/activating the Qt
runtime.  The matrix is deliberately bounded rather than a full Cartesian
product: every required DPI, locale, appearance mode, density, and target
window size is exercised while keeping the release gate practical.

Each case captures main.png, preferences.png and pixel_studio.png plus a JSON
layout report.  A focused Main screenshot is also captured to make keyboard
focus treatment reviewable without changing geometry.
"""

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]
SIM=ROOT/'src'
OUT=SIM/'reports'/'windows_v10_ui_craft_golden'
DPI=('1.0','1.25','1.5','1.75','2.0')
LANG=('zh_CN','en_US')
MODES=('system','light','dark')
DENSITIES=('compact','comfortable','spacious')
WINDOWS=((1280,720),(1440,900),(1920,1080))

# Bounded coverage: all values on every axis appear at least once, with the
# standard 1440x900 comfortable pair captured in both languages and modes.
CASES=(
    ('1.0','zh_CN','light','comfortable',(1280,720)),
    ('1.0','en_US','dark','comfortable',(1440,900)),
    ('1.25','zh_CN','dark','compact',(1440,900)),
    ('1.25','en_US','light','spacious',(1920,1080)),
    ('1.5','zh_CN','light','comfortable',(1440,900)),
    ('1.5','en_US','dark','comfortable',(1920,1080)),
    ('1.75','zh_CN','dark','spacious',(1280,720)),
    ('1.75','en_US','light','compact',(1440,900)),
    ('2.0','zh_CN','light','compact',(1920,1080)),
    ('2.0','en_US','dark','spacious',(1280,720)),
    ('1.0','en_US','light','comfortable',(1440,900)),
    ('1.0','zh_CN','dark','comfortable',(1440,900)),
    ('1.0','zh_CN','system','comfortable',(1440,900)),
    ('1.25','en_US','system','comfortable',(1280,720)),
)


def _parse_case(case: str):
    scale,lang,mode,density,size=case.split('|')
    width,height=(int(v) for v in size.lower().split('x',1))
    return scale,lang,mode,density,width,height


def _repolish(widget) -> None:
    widget.style().unpolish(widget); widget.style().polish(widget); widget.update()


def _child(case: str, output: Path) -> int:
    sys.path.insert(0,str(SIM))
    try:
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import QApplication
        from gui import OLEDDesignerWindow, _apply_application_theme
        from preferences import PreferencesStore, default_preferences
        from preferences_qt import PreferencesWindow
        from pixel_studio_qt import PixelStudioWindow
        from runtime_settings import RuntimeSettings
        from theme_system import resolve_theme_name
        from i18n import Translator
    except Exception as exc:
        print(f'FAIL: PySide6/Studio import unavailable: {exc}',file=sys.stderr); return 2

    scale,lang,mode,density,width,height=_parse_case(case)
    temp=Path(os.environ['LOCALAPPDATA'])/'MonoOLEDStudio'/'preferences.json'
    prefs=default_preferences()
    prefs['language']=lang
    prefs['appearance']['theme_mode']=mode
    prefs['appearance']['color_theme']='high-contrast' if mode=='system' else ('monooled-dark' if mode=='dark' else 'monooled-light')
    prefs['appearance']['density']=density
    prefs['appearance']['ui_scale']='100%'
    store=PreferencesStore(temp,prefs); store.save()

    app=QApplication.instance() or QApplication([])
    runtime=RuntimeSettings.from_preferences(store)
    theme=resolve_theme_name(runtime.color_theme,runtime.theme_mode,system_dark=False)
    _apply_application_theme(app,theme,runtime.density,runtime.ui_scale)

    main=OLEDDesignerWindow(str(ROOT/'test_assets/projects/curing_lite/project.oled.json'),language=lang)
    main.resize(width,height); main.show()
    expected_theme=resolve_theme_name(runtime.color_theme,runtime.theme_mode,system_dark=main.system_theme.is_dark())
    if main._resolved_theme != expected_theme:
        print(f'FAIL {case}: resolved theme {main._resolved_theme!r} != {expected_theme!r}',file=sys.stderr); return 1
    pref=PreferencesWindow(store,Translator(lang),parent=main)
    pref.resize(980,680); pref.show()
    pixel=PixelStudioWindow(language=lang,parent=None,preferences=store,project_root=ROOT)
    pixel.resize(min(width,1440),min(height,900)); pixel.show()
    for _ in range(10): app.processEvents()

    output.mkdir(parents=True,exist_ok=True)
    stem=f'{lang}_{mode}_{density}_{scale.replace(".","p")}x_{width}x{height}'
    # Stable suffixes are intentional: release review tooling searches these.
    main_png=output/f'{stem}_main.png'
    preferences_png=output/f'{stem}_preferences.png'
    pixel_png=output/f'{stem}_pixel_studio.png'
    ok_main=main.grab().save(str(main_png))
    ok_pref=pref.grab().save(str(preferences_png))
    ok_pixel=pixel.grab().save(str(pixel_png))

    # Capture a focused state to audit the fixed-width canvas focus treatment.
    main.canvas.setFocus(Qt.OtherFocusReason)
    main.canvas_card.setProperty('canvasFocus',True); _repolish(main.canvas_card)
    for _ in range(2): app.processEvents()
    ok_focus=main.grab().save(str(output/f'{stem}_main_focus.png'))

    violations={
        'main':main.layout_violations(),
        'preferences':pref.layout_violations(),
        'pixel_studio':pixel.layout_violations(),
    }
    (output/f'{stem}_layout.json').write_text(json.dumps({
        'case':case,'dpi':scale,'language':lang,'mode':mode,'density':density,
        'window':[width,height],'screenshots':{
            'main':main_png.name,'preferences':preferences_png.name,'pixel_studio':pixel_png.name,
        },'violations':violations,
    },ensure_ascii=False,indent=2),encoding='utf-8')

    pixel.close(); pref.close(); main.close(); app.processEvents()
    screenshots_ok=ok_main and ok_pref and ok_pixel and ok_focus
    all_violations=[f'{surface}:{item}' for surface,items in violations.items() for item in items]
    if not screenshots_ok or all_violations:
        print(f'FAIL {case}: screenshots={screenshots_ok}, violations={all_violations}'); return 1
    print(f'PASS {case}'); return 0


def _case_text(item) -> str:
    scale,lang,mode,density,(width,height)=item
    return f'{scale}|{lang}|{mode}|{density}|{width}x{height}'


def main() -> int:
    ap=argparse.ArgumentParser()
    ap.add_argument('--child')
    ap.add_argument('--output',default=str(OUT))
    args=ap.parse_args(); out=Path(args.output).resolve()
    if args.child:return _child(args.child,out)
    if os.name!='nt':
        print('SKIP: Windows Real-Qt visual capture must run on Windows.'); return 0

    failures=[]
    for item in CASES:
        case=_case_text(item); scale=item[0]
        with tempfile.TemporaryDirectory(prefix='monooled-v10-') as td:
            env=os.environ.copy(); env['LOCALAPPDATA']=td; env['QT_SCALE_FACTOR']=scale
            env['QT_AUTO_SCREEN_SCALE_FACTOR']='0'; env['MONOOLED_REDUCED_MOTION']='1'
            proc=subprocess.run(
                [sys.executable,str(Path(__file__).resolve()),'--child',case,'--output',str(out)],
                cwd=ROOT,env=env,check=False,
            )
            if proc.returncode:failures.append(case)
    print(f'V10 UI Craft visual matrix: {len(CASES)-len(failures)} PASS / {len(failures)} FAIL')
    if failures:
        print('Failed cases: '+', '.join(failures)); return 1
    return 0

if __name__=='__main__':raise SystemExit(main())
