#!/usr/bin/env python3
from __future__ import annotations

"""Windows Real-Qt visual gate for Micro Interaction Signature V10.3."""

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]
SIM=ROOT/'src'
OUT=SIM/'reports'/'windows_micro_signature_v103'


def _child(output: Path) -> int:
    sys.path.insert(0,str(SIM))
    try:
        from PySide6.QtCore import QPoint, Qt
        from PySide6.QtTest import QTest
        from PySide6.QtWidgets import QApplication
        from gui import OLEDDesignerWindow
        from pixel_studio import PixelDocument
        from pixel_studio_qt import PixelCanvas
        from qt_theme import build_stylesheet, build_theme_palette
        from ui_controls import StudioSelect
    except Exception as exc:
        print(f'FAIL: Real-Qt imports unavailable: {exc}',file=sys.stderr); return 2

    app=QApplication.instance() or QApplication([])
    app.setPalette(build_theme_palette('monooled-dark')); app.setStyleSheet(build_stylesheet('monooled-dark'))
    output.mkdir(parents=True,exist_ok=True)
    results={}
    main=None; pixel=None; combo=None
    try:
        main=OLEDDesignerWindow('main_scene'); main.resize(1440,900); main.show(); app.processEvents()
        element=next(e for e in main.scene['elements'] if all(k in e for k in ('x','y')) and not e.get('locked'))
        eid=str(element['id']); main._set_selection([eid],source='api',primary=eid); app.processEvents()
        dot_size=(main.document_dirty_dot.width(),main.document_dirty_dot.height())
        x0=main.session.geometry(eid).x; main.session.set_geometry(eid,x=x0+1); main.refresh_all(keep_selection=True); app.processEvents()
        if not main.document_dirty_dot.is_active(): raise AssertionError('dirty dot not active after edit')
        if not main.geom_labels['x'].is_marked(): raise AssertionError('Inspector X modified dot not active')
        if (main.document_dirty_dot.width(),main.document_dirty_dot.height())!=dot_size: raise AssertionError('dirty dot slot shifted geometry')
        main.grab().save(str(output/'01_main_dirty_modified.png'))
        results['dirty_modified']=True

        pixel=PixelCanvas(PixelDocument(8,8)); pixel.theme_name='monooled-dark'; pixel.zoom=20; pixel._sync_size(); pixel.show(); app.processEvents()
        before=[row[:] for row in pixel.document.pixels]; QTest.mouseMove(pixel,QPoint(50,70)); app.processEvents()
        if pixel._hover_pixel!=(2,3): raise AssertionError(f'pixel hover mismatch: {pixel._hover_pixel}')
        if pixel.document.pixels!=before: raise AssertionError('pixel hover mutated document')
        pixel.grab().save(str(output/'02_pixel_hover.png')); results['pixel_hover']=True

        combo=StudioSelect(); combo.addItems(['Compact','Comfortable','Spacious']); combo.setCurrentIndex(1); combo.resize(220,34); combo.show(); combo.showPopup(); app.processEvents()
        combo.popup.grab().save(str(output/'03_popup_selected_dot.png')); results['popup_selected_dot']=True

        # The dedicated test module covers Canvas Primary Corner + Snap Anchor raster.
        proc=subprocess.run([sys.executable,'-m','pytest',str(SIM/'tests'/'test_qt_micro_signature_v103.py'),'-q'],cwd=ROOT,check=False)
        if proc.returncode!=0: raise AssertionError(f'test_qt_micro_signature_v103.py rc={proc.returncode}')
        results['real_qt_suite']=True
        (output/'micro_signature_v103.json').write_text(json.dumps(results,indent=2),encoding='utf-8')
        print('PASS: Micro Interaction Signature V10.3 Real-Qt raster/state gate')
        return 0
    except Exception as exc:
        print(f'FAIL: {exc}',file=sys.stderr); return 1
    finally:
        if main is not None: main.session.document.dirty=False; main.close()
        if pixel is not None: pixel.close()
        if combo is not None: combo.hidePopup(); combo.close()
        app.processEvents()


def main() -> int:
    if os.name!='nt':
        print('SKIP: Micro Interaction Signature V10.3 Real-Qt gate must run on Windows.')
        return 0
    with tempfile.TemporaryDirectory(prefix='monooled-v103-') as td:
        env=os.environ.copy(); env['LOCALAPPDATA']=td; env['QT_QPA_PLATFORM']='windows'
        return subprocess.run([sys.executable,str(Path(__file__).resolve()),'--child',str(OUT)],cwd=ROOT,env=env,check=False).returncode


if __name__=='__main__':
    if len(sys.argv)>=3 and sys.argv[1]=='--child': raise SystemExit(_child(Path(sys.argv[2]).resolve()))
    raise SystemExit(main())
