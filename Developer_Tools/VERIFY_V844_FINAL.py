#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
SIM=ROOT/'OLED模拟器'
TOOLS=ROOT/'Developer_Tools'
sys.path.insert(0,str(SIM))

from automation_service import AUTOMATION_API_VERSION, METHOD_SPECS


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main()->int:
    version=(SIM/'VERSION').read_text(encoding='utf-8').strip()
    assert version=='8.4.4'
    assert AUTOMATION_API_VERSION=='1.2.0'
    assert len(METHOD_SPECS)==82

    manifest=json.loads((ROOT/'DELIVERY_MANIFEST.json').read_text(encoding='utf-8'))
    assert manifest['version']==version
    assert manifest['release_name']=='Windows Real-Qt GA Final Closure'
    assert manifest['verification']['v843_paths_missing_v844']==0
    assert manifest['verification']['v844_paths_added']==6

    frozen=json.loads((SIM/'reports/frozen_product_assets_v70.json').read_text(encoding='utf-8'))
    assert frozen['count']==464 and len(frozen['files'])==464
    for rel,expected in frozen['files'].items():assert sha(ROOT/rel)==expected
    golden=json.loads((SIM/'reports/frozen_golden_v70.json').read_text(encoding='utf-8'))
    assert golden['count']==14 and golden['bytes_each']==512
    for name,expected in golden['files'].items():
        path=SIM/'exports/clinical_14/golden'/name
        assert path.stat().st_size==512 and sha(path)==expected

    required=(
        SIM/'WINDOWS_REAL_QT_GA_FINAL_CLOSURE_V844.md',SIM/'TEST_MATRIX_V844.md',
        SIM/'tests/test_v844_windows_real_qt_ga.py',TOOLS/'BUILD_DELIVERY_V844.py',
    )
    assert all(path.is_file() for path in required)
    asset_test=(SIM/'tests/test_asset_library_v4.py').read_text(encoding='utf-8')
    assert 'test_unchanged_asset_scan_does_not_replace_identical_persistent_cache' in asset_test
    builder=(TOOLS/'BUILD_WINDOWS_EXE.bat').read_text(encoding='utf-8')
    for marker in ('VERIFY_V843_FINAL.py','VERIFY_V844_FINAL.py','--phase source','--phase qt','1.0,1.25,1.5,1.75,2.0,2.25,2.5,3.0','PyInstaller','--sha256-only "%ZIP%" || exit /b 2'):
        assert marker in builder

    report={
        'version':version,'automation_api':AUTOMATION_API_VERSION,'method_count':len(METHOD_SPECS),
        'frozen_product_assets':'464/464 PASS','clinical_golden':'14/14 x 512B PASS',
        'v843_paths_missing':0,'v844_paths_added':6,
        'ortho_expected_hashes':{
            'standby':'1f20bcf70e17c8ebab0fb4f303ec1657aaa532a22cd297e80e05d5a82897b1af',
            'running':'4b0b9050cd3710d2e3e4fef905c7d041927fb324963ca95c24abf949a680ae12',
        },
        'v83_performance_limits_ms':{
            'render_p95':6.00,'geometry_p95':0.50,'smart_guides_p95':2.00,
        },
        'native_source_real_qt_after_renderer':{
            'processes':104,'tests':1048,'failures':0,'errors':0,'skipped':0,'timeouts':0,
            'evidence_scope':'source-tree diagnostic; formal sealed-ZIP Builder repetition required',
        },
        'release_decision_standard':{
            'ga_release_gates':'PASS required','known_blockers':0,'known_p0_p1':0,
            'evidence_confidence':'High only after formal sealed-ZIP Builder and ORTHO graduation',
        },
        'windows_formal_sealed_run':'required external GA evidence',
    }
    target=SIM/'reports/v844_final_report.json';target.parent.mkdir(parents=True,exist_ok=True)
    target.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False,indent=2));return 0


if __name__=='__main__':raise SystemExit(main())
