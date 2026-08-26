#!/usr/bin/env python3
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
SIM=ROOT/'OLED模拟器'
TOOLS=ROOT/'Developer_Tools'
sys.path.insert(0,str(SIM))

from automation_service import AUTOMATION_API_VERSION, METHOD_SPECS


def run(cmd:list[str], *, env=None, timeout=60)->subprocess.CompletedProcess:
    return subprocess.run(cmd,cwd=ROOT,env=env,text=True,capture_output=True,timeout=timeout)


def main()->int:
    version=(SIM/'VERSION').read_text(encoding='utf-8').strip()
    assert version in {'8.4.3','8.4.4'}
    assert AUTOMATION_API_VERSION=='1.2.0'
    assert len(METHOD_SPECS)==82
    contract=json.loads((SIM/'AUTOMATION_API_V1.json').read_text(encoding='utf-8'))
    assert contract['api_version']==AUTOMATION_API_VERSION
    assert set(contract['methods'])==set(METHOD_SPECS)

    manifest=json.loads((ROOT/'DELIVERY_MANIFEST.json').read_text(encoding='utf-8'))
    assert manifest['version']==version
    if version=='8.4.3':
        assert manifest['release_name']=='Windows Release & Real-Qt GA Closure'
    assert manifest['delivery_profile']=='source'

    text_gate=run([sys.executable,str(TOOLS/'VERIFY_WINDOWS_RELEASE_TEXT.py')])
    assert text_gate.returncode==0, text_gate.stdout+text_gate.stderr

    attrs=(ROOT/'.gitattributes').read_text(encoding='utf-8')
    assert '*.bat text eol=crlf' in attrs and '*.cmd text eol=crlf' in attrs
    assert (ROOT/'pytest.ini').is_file()

    # Prove selected Automation modules collect from a fresh package root with no external PYTHONPATH.
    env=os.environ.copy(); env.pop('PYTHONPATH',None); env['PYTHONDONTWRITEBYTECODE']='1'
    collect=run([sys.executable,'-m','pytest','OLED模拟器/tests/test_automation_reliability_v842.py','--collect-only','-q'],env=env,timeout=60)
    assert collect.returncode==0, collect.stdout+collect.stderr
    assert 'test_transaction_commit_marks_unsaved_scene_dirty' in collect.stdout

    runner=TOOLS/'RUN_WINDOWS_TEST_GROUPS.py'
    listing=run([sys.executable,str(runner),'--phase','source','--list-only'],timeout=60)
    assert listing.returncode==0, listing.stdout+listing.stderr
    assert 'source_modules=' in listing.stdout and 'qt_modules=' in listing.stdout
    assert 'test_qt_v84_project_automation.py' in listing.stdout

    builder=(TOOLS/'BUILD_WINDOWS_EXE.bat').read_text(encoding='utf-8')
    assert 'RUN_WINDOWS_TEST_GROUPS.py' in builder
    assert '--phase source' in builder and '--phase qt' in builder
    assert 'pytest "OLED模拟器\\tests" -q' not in builder
    for marker in ('1.0','1.25','1.5','1.75','2.0','2.25','2.5','3.0','VERIFY_JUNIT_NO_SKIPS.py','VERIFY_V843_FINAL.py'):
        assert marker in builder

    report={
        'version':version,
        'automation_api':AUTOMATION_API_VERSION,
        'method_count':len(METHOD_SPECS),
        'windows_command_text':'PASS',
        'root_pytest_import':'PASS',
        'bounded_source_runner':'PASS',
        'isolated_real_qt_runner':'PRESENT / native Windows execution required',
    }
    target=SIM/'reports/v843_final_report.json'; target.parent.mkdir(parents=True,exist_ok=True)
    target.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False,indent=2))
    return 0

if __name__=='__main__': raise SystemExit(main())
