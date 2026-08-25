#!/usr/bin/env python3
from __future__ import annotations

import hashlib, json, struct, sys
from pathlib import Path

ROOT=Path(__file__).resolve().parent
SUMS=ROOT/'SHA256SUMS.txt'
SIM=ROOT/'OLED模拟器'
VERSION='8.4.3'
RELEASE='Windows Release & Real-Qt GA Closure'
COMPAT_LAUNCHER_SHA='558c2115941aff959927dc6b29c6bd4ac5a746dc2c6854ea921efd2180615c87'


def fail(message:str)->int:
    print('FAIL: '+message,file=sys.stderr); return 1

def sha(path:Path)->str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main()->int:
    if not SUMS.is_file(): return fail('SHA256SUMS.txt not found')
    listed={}; failures=[]
    for line in SUMS.read_text(encoding='utf-8').splitlines():
        if not line.strip(): continue
        try: digest,rel=line.split('  ',1)
        except ValueError: return fail(f'malformed checksum line: {line!r}')
        if rel in listed: return fail(f'duplicate checksum path {rel}')
        listed[rel]=digest; p=ROOT/rel
        if not p.is_file(): failures.append(f'MISSING {rel}'); continue
        if sha(p)!=digest: failures.append(f'HASH {rel}')
    actual={p.relative_to(ROOT).as_posix() for p in ROOT.rglob('*') if p.is_file() and p!=SUMS and '__pycache__' not in p.parts and '.pytest_cache' not in p.parts and p.suffix!='.pyc'}
    if actual-set(listed): failures.append('UNMANAGED '+', '.join(sorted(actual-set(listed))[:8]))
    if set(listed)-actual: failures.append('CHECKSUM_ONLY '+', '.join(sorted(set(listed)-actual)[:8]))
    if failures:
        print('\n'.join(failures),file=sys.stderr); return fail(f'{len(failures)} delivery integrity issue(s)')

    version=(SIM/'VERSION').read_text(encoding='utf-8').strip()
    manifest=json.loads((ROOT/'DELIVERY_MANIFEST.json').read_text(encoding='utf-8'))
    if version!=VERSION: return fail(f'unexpected VERSION {version!r}')
    if manifest.get('product')!='MonoOLED Studio' or manifest.get('version')!=VERSION or manifest.get('primary_gui')!='PySide6 / Qt':
        return fail(f'manifest does not describe MonoOLED Studio {VERSION} Qt release')
    if manifest.get('release_name')!=RELEASE: return fail('unexpected V8.4.3 release name')

    if manifest.get('delivery_profile')!='source': return fail('V8.4.3 complete delivery must declare delivery_profile=source')

    frozen=json.loads((SIM/'reports/frozen_product_assets_v70.json').read_text(encoding='utf-8'))
    if frozen.get('count')!=464 or len(frozen.get('files',{}))!=464: return fail('frozen product asset manifest must contain 464 files')
    for rel,expected in frozen['files'].items():
        p=ROOT/rel
        if not p.is_file() or sha(p)!=expected: return fail(f'frozen V7.0 product asset drift: {rel}')
    golden=json.loads((SIM/'reports/frozen_golden_v70.json').read_text(encoding='utf-8'))
    gdir=SIM/'exports/clinical_14/golden'
    if golden.get('count')!=14 or golden.get('bytes_each')!=512: return fail('frozen Golden manifest invalid')
    for name,expected in golden['files'].items():
        p=gdir/name
        if not p.is_file() or p.stat().st_size!=512 or sha(p)!=expected: return fail(f'Golden drift: {name}')

    modules=(
        'preferences.py','preferences_qt.py','theme_system.py','runtime_settings.py','preference_delta.py','ui_metrics.py','system_theme.py',
        'ui_controls.py','popup_geometry.py','popup_state.py','qt_interaction.py','commands.py','project_workspace.py','autosave.py','asset_library.py',
        'selection_model.py','workspace_host.py','font_pack.py','font_lab_qt.py','automation_service.py','automation_qt.py','agent_bridge.py',
        'resource_cache.py','atomic_io.py','diagnostics.py','state_schema.py','automation_jobs.py')
    for rel in modules:
        if not (SIM/rel).is_file(): return fail(f'V8.4 module missing: {rel}')

    documents=('FINAL_VERIFICATION_REPORT.md','TEST_MATRIX_V843.md','WINDOWS_RELEASE_REAL_QT_GA_CLOSURE_V843.md','TEST_MATRIX_V842.md','AUTOMATION_RELIABILITY_GA_CLOSURE_V842.md','TEST_MATRIX_V841.md','AUTOMATION_STATE_MODEL_CLOSURE_V841.md','TEST_MATRIX_V84.md','FINAL_PROJECT_CODE_AI_CLOSURE_V84.md','CODE_AI_AUTOMATION_API_V1.md','AUTOMATION_API_V1.json','TEST_MATRIX_V83.md','RELIABILITY_PERFORMANCE_CLOSURE_V83.md','USER_GUIDE_CN.md')
    for rel in documents:
        if not (SIM/rel).is_file(): return fail(f'V8.4 release document missing: {rel}')

    gui=(SIM/'gui.py').read_text(encoding='utf-8')
    canvas=(SIM/'qt_canvas.py').read_text(encoding='utf-8')
    controls=(SIM/'ui_controls.py').read_text(encoding='utf-8')
    editor=(SIM/'editor_model.py').read_text(encoding='utf-8')
    automation=(SIM/'automation_qt.py').read_text(encoding='utf-8')
    system_theme=(SIM/'system_theme.py').read_text(encoding='utf-8')
    i18n=(SIM/'i18n.py').read_text(encoding='utf-8')
    launcher=(SIM/'windows_launcher.c').read_text(encoding='utf-8')
    for marker in ("APP_VERSION = '8.4.3'",'def run_startup_smoke(','--startup-smoke','CORE CHECK PASS','PreferenceDelta','editor_registry.apply_runtime_delta'):
        if marker not in gui: return fail(f'V8.4 GUI marker missing: {marker}')
    if canvas.count('def mouseReleaseEvent(')!=1: return fail('OLEDCanvas must contain exactly one mouseReleaseEvent implementation')
    if '_frame_image' not in canvas or 'drawImage' not in canvas: return fail('QImage framebuffer paint cache marker missing')
    for marker in ('self.popup = None','self.list = None','installEventFilter','def showPopup(','def hidePopup('):
        if marker not in controls: return fail(f'StudioSelect hardening marker missing: {marker}')
    for marker in ('RenderResources','def batch_set_geometry(','def batch_move('):
        if marker not in editor: return fail(f'EditorSession V8.3 marker missing: {marker}')
    if 'self.timer.start()' not in automation.split('def start(',1)[1]: return fail('Agent timer must start on demand')
    if '.join(' not in automation: return fail('Agent worker join marker missing')
    if 'lambda' in system_theme and 'colorSchemeChanged.connect' in system_theme: return fail('SystemThemeProvider must not connect application signal through capturing lambda')
    en_block=i18n[i18n.index('EN = {'):]
    if '"workspace.design": "设计"' in en_block or '"workspace.review": "评审"' in en_block: return fail('English workspace labels still contain Chinese text')
    for marker in ('startup_smoke_ok','.venv-runtime','MONOOLED_PYTHON','WaitForSingleObject'):
        if marker not in launcher: return fail(f'V8.3 launcher source marker missing: {marker}')

    attrs=ROOT/'.gitattributes'
    if not attrs.is_file(): return fail('.gitattributes missing')
    attr_text=attrs.read_text(encoding='utf-8')
    for marker in ('*.bat text eol=crlf','*.cmd text eol=crlf'):
        if marker not in attr_text: return fail(f'Windows EOL contract missing: {marker}')
    if not (ROOT/'pytest.ini').is_file(): return fail('pytest.ini repository-root import contract missing')
    scripts=sorted([*(ROOT/'Developer_Tools').glob('*.bat'),*(ROOT/'Developer_Tools').glob('*.cmd')])
    if not scripts: return fail('Windows command scripts missing')
    for path in scripts:
        raw=path.read_bytes(); crlf=raw.count(b'\r\n'); bare=raw.count(b'\n')-crlf
        if crlf<=0 or bare: return fail(f'Windows script must be CRLF-only: {path.relative_to(ROOT)} (CRLF={crlf}, LF-only={bare})')

    workflow=(ROOT/'.github/workflows/build-windows-exe.yml').read_text(encoding='utf-8')
    builder=(ROOT/'Developer_Tools/BUILD_WINDOWS_EXE.bat').read_text(encoding='utf-8')
    for marker in ('1.0','1.25','1.5','1.75','2.0','2.25','2.5','3.0','test_qt_v82_studio_select_state_machine.py','test_qt_v82_preferences_theme_surface.py','test_qt_v83_reliability.py'):
        if marker not in workflow or marker not in builder: return fail(f'Windows Real-Qt gate marker missing: {marker}')
    for marker in ('VERIFY_JUNIT_NO_SKIPS.py','--startup-smoke','VERIFY_V82_STRESS.py','VERIFY_V83_STRESS.py','VERIFY_V84_FINAL.py','VERIFY_V841_FINAL.py','VERIFY_V842_FINAL.py','VERIFY_V843_FINAL.py'):
        if marker not in builder: return fail(f'Windows V8.4 zero-skip/build marker missing: {marker}')
    for rel in ('Developer_Tools/VERIFY_V83_STRESS.py','Developer_Tools/VERIFY_V84_FINAL.py','Developer_Tools/VERIFY_V841_FINAL.py','Developer_Tools/VERIFY_V842_FINAL.py','Developer_Tools/VERIFY_V843_FINAL.py','Developer_Tools/BUILD_DELIVERY_V84.py','Developer_Tools/BUILD_DELIVERY_V841.py','Developer_Tools/BUILD_DELIVERY_V842.py','Developer_Tools/BUILD_DELIVERY_V843.py','Developer_Tools/RUN_WINDOWS_TEST_GROUPS.py','Developer_Tools/VERIFY_WINDOWS_RELEASE_TEXT.py','Developer_Tools/EXPORT_AUTOMATION_API_V1.py','Developer_Tools/VERIFY_JUNIT_NO_SKIPS.py','Developer_Tools/CREATE_RUNTIME_ENV.bat','Developer_Tools/RUN_MONOOLED_DIAGNOSTIC.bat'):
        if not (ROOT/rel).is_file(): return fail(f'V8.4 release tool missing: {rel}')

    automation_contract=json.loads((SIM/'AUTOMATION_API_V1.json').read_text(encoding='utf-8'))
    if automation_contract.get('api_version')!='1.2.0': return fail('Automation API contract version must be 1.2.0')
    automation_source=(SIM/'automation_service.py').read_text(encoding='utf-8')
    for marker in ('AUTOMATION_API_VERSION = \'1.2.0\'','project.open_screen','render.all_states','validate.all_states','pixel.create','export.code_ai_handoff','state.validate_schema','state.set_schema','state.validate','state.count','job.start','job.status','job.result','job.cancel'):
        if marker not in automation_source: return fail(f'Automation API 1.1 marker missing: {marker}')
    builder=(ROOT/'Developer_Tools/BUILD_WINDOWS_EXE.bat').read_text(encoding='utf-8')
    if 'test_qt_v84_project_automation.py' not in builder or 'VERIFY_V84_FINAL.py' not in builder or 'VERIFY_V841_FINAL.py' not in builder or 'VERIFY_V842_FINAL.py' not in builder or 'VERIFY_V843_FINAL.py' not in builder:
        return fail('Windows V8.4.3 historical/Real-Qt gate markers missing')
    if 'RUN_WINDOWS_TEST_GROUPS.py' not in builder or '--phase source' not in builder or '--phase qt' not in builder:
        return fail('Windows bounded test runner markers missing')
    if 'pytest "OLED模拟器\\tests" -q' in builder:
        return fail('monolithic Windows pytest invocation must not return')

    if (ROOT/'CuringLiteOLEDDesigner_SourceLauncher.exe').exists() or (ROOT/'CuringLiteOLEDDesigner_SourceLauncher-script.pyw').exists():
        return fail('broken legacy SourceLauncher must not be delivered')
    entry=ROOT/'MonoOLEDStudio.exe'
    if not entry.is_file(): return fail('MonoOLEDStudio.exe runtime-locator user entry missing')
    raw=entry.read_bytes()
    if sha(entry)!=COMPAT_LAUNCHER_SHA: return fail('bundled compatibility launcher binary drifted without Windows rebuild evidence')
    if raw[:2]!=b'MZ' or b'PE\x00\x00' not in raw[:2048]: return fail('MonoOLEDStudio.exe is not a PE Windows executable')
    for marker in (b'KERNEL32.dll',b'USER32.dll','MonoOLED Studio'.encode('utf-16le'),'OLED模拟器\\gui.py'.encode('utf-16le')):
        if marker not in raw: return fail(f'Windows launcher contract marker missing: {marker!r}')
    pe=struct.unpack_from('<I',raw,0x3C)[0]; sections=struct.unpack_from('<H',raw,pe+6)[0]; opt=struct.unpack_from('<H',raw,pe+20)[0]; table=pe+24+opt
    names=[raw[table+i*40:table+i*40+8].split(b'\0',1)[0].decode('ascii','ignore') for i in range(sections)]
    if '.rsrc' not in names: return fail('runtime-locator launcher icon resource section missing')
    if list(ROOT.glob('*.bat')) or (ROOT/'MonoOLEDStudio.spec').exists(): return fail('user root must not expose BAT/SPEC build files')

    print(f'PASS: delivery integrity verified for {len(listed)} managed file(s)')
    print('PASS: version=8.4.3, frozen product assets=464/464, Golden=14/14 x 512B')
    print('PASS: V8.2–V8.4.2 inheritance + CRLF-safe bounded Windows/Real-Qt GA release gates present')
    return 0

if __name__=='__main__': raise SystemExit(main())
