from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / 'tools'
WORKFLOW = ROOT / '.github' / 'workflows' / 'release-windows.yml'


def _text(path: Path) -> str:
    return path.read_text(encoding='utf-8')


def _load_runtime_zip_tool():
    path = TOOLS / 'BUILD_WINDOWS_RUNTIME_ZIP.py'
    spec = importlib.util.spec_from_file_location('runtime_zip_v1237', path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _load_tag_tool():
    path = TOOLS / 'VERIFY_RELEASE_TAG.py'
    spec = importlib.util.spec_from_file_location('release_tag_v1237', path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_manual_release_checkout_is_bound_to_requested_tag_ref():
    workflow = _text(WORKFLOW)
    assert "ref: ${{ github.event_name == 'push' && github.ref || inputs.tag }}" in workflow
    assert 'fetch-depth: 0' in workflow


def test_release_gate_requires_head_to_equal_tag_commit():
    workflow = _text(WORKFLOW)
    assert 'VERIFY_RELEASE_TAG.py "%RELEASE_TAG%" --require-git-head' in workflow


def test_release_tag_verifier_detects_head_tag_commit_mismatch(tmp_path):
    subprocess.run(['git', 'init', '-q', str(tmp_path)], check=True)
    subprocess.run(['git', '-C', str(tmp_path), 'config', 'user.email', 'test@example.com'], check=True)
    subprocess.run(['git', '-C', str(tmp_path), 'config', 'user.name', 'Test'], check=True)
    (tmp_path / 'a.txt').write_text('one', encoding='utf-8')
    subprocess.run(['git', '-C', str(tmp_path), 'add', '.'], check=True)
    subprocess.run(['git', '-C', str(tmp_path), 'commit', '-qm', 'one'], check=True)
    subprocess.run(['git', '-C', str(tmp_path), 'tag', 'v1.2.3'], check=True)

    tool = _load_tag_tool()
    ok, *_ = tool.verify_git_head_matches_tag(tmp_path, 'v1.2.3')
    assert ok is True

    (tmp_path / 'a.txt').write_text('two', encoding='utf-8')
    subprocess.run(['git', '-C', str(tmp_path), 'commit', '-qam', 'two'], check=True)
    ok, head, tagged = tool.verify_git_head_matches_tag(tmp_path, 'v1.2.3')
    assert ok is False
    assert head != tagged


def test_ga_builder_clears_previous_evidence_before_certification():
    batch = _text(TOOLS / 'BUILD_WINDOWS_GA.bat')
    assert 'if exist ".artifacts\\windows_ga" rmdir /s /q ".artifacts\\windows_ga"' in batch
    assert 'mkdir ".artifacts\\windows_ga"' in batch


def test_settings_visual_capture_resets_output_directory_before_matrix():
    capture = _text(TOOLS / 'CAPTURE_V1231_SETTINGS_GOLDENS.py')
    assert 'shutil.rmtree(out)' in capture
    assert 'out.mkdir(parents=True, exist_ok=True)' in capture


def test_runtime_pyinstaller_bundle_does_not_ship_test_fixtures():
    spec = _text(TOOLS / 'MonoOLEDStudio.spec')
    assert "add_tree('test_assets'" not in spec


def test_runtime_zip_builder_is_deterministic_safe_and_has_provenance(tmp_path):
    tool = _load_runtime_zip_tool()
    app = tmp_path / 'app'
    (app / 'src').mkdir(parents=True)
    (app / 'MonoOLEDStudio.exe').write_bytes(b'MZ-probe')
    (app / 'src' / 'VERSION').write_text('12.3.7\n', encoding='utf-8')
    (app / 'nested').mkdir()
    (app / 'nested' / 'payload.bin').write_bytes(b'payload')

    a = tmp_path / 'a.zip'
    b = tmp_path / 'b.zip'
    tool.build_runtime_zip(app, a, version='12.3.7', git_commit='abc123')
    tool.build_runtime_zip(app, b, version='12.3.7', git_commit='abc123')
    assert a.read_bytes() == b.read_bytes()

    report = tool.verify_runtime_zip(a, expected_version='12.3.7')
    assert report['files'] == 4
    assert report['exe'] == 'MonoOLEDStudio.exe'
    with zipfile.ZipFile(a) as zf:
        info = json.loads(zf.read('BUILD_INFO.json'))
        assert info['version'] == '12.3.7'
        assert info['release_tag'] == 'v12.3.7'
        assert info['git_commit'] == 'abc123'
        assert 'test_assets/' not in '\n'.join(zf.namelist())


def test_runtime_zip_verifier_rejects_unsafe_or_missing_executable(tmp_path):
    tool = _load_runtime_zip_tool()
    bad = tmp_path / 'bad.zip'
    with zipfile.ZipFile(bad, 'w') as zf:
        zf.writestr('../escape.txt', 'bad')
        zf.writestr('BUILD_INFO.json', json.dumps({'version': '12.3.7'}))
    try:
        tool.verify_runtime_zip(bad, expected_version='12.3.7')
    except RuntimeError as exc:
        assert 'unsafe' in str(exc).lower() or 'executable' in str(exc).lower()
    else:
        raise AssertionError('unsafe runtime ZIP was accepted')


def test_ga_builder_verifies_extracted_release_package_with_real_exe_smokes():
    batch = _text(TOOLS / 'BUILD_WINDOWS_GA.bat')
    assert 'BUILD_WINDOWS_RUNTIME_ZIP.py' in batch
    assert 'Compress-Archive' not in batch
    assert '--extract-to ".artifacts\\windows_ga\\release_extract"' in batch
    assert 'release_extract\\MonoOLEDStudio.exe' in batch
    assert 'PACKAGED_APP' in batch
    assert '"%PACKAGED_APP%" --check' in batch
    assert '"%PACKAGED_APP%" --startup-smoke' in batch
    assert '"%PACKAGED_APP%" --settings-smoke' in batch


def test_publisher_reverifies_zip_and_checksum_before_upload():
    publisher = _text(TOOLS / 'PUBLISH_GITHUB_RELEASE.ps1')
    assert 'BUILD_WINDOWS_RUNTIME_ZIP.py' in publisher
    assert '--verify' in publisher
    assert '--checksum' in publisher
    assert 'gh release create' in publisher
    assert 'gh release download' in publisher


def test_release_workflow_preserves_ga_evidence_even_when_certification_fails():
    workflow = _text(WORKFLOW)
    block = workflow.split('- name: Preserve Windows GA evidence', 1)[1].split('- name: Publish GitHub Release', 1)[0]
    assert 'if: always()' in block
    assert 'if-no-files-found: warn' in block


def test_windows_qt_runner_isolates_user_state_per_process(tmp_path):
    path = TOOLS / 'RUN_WINDOWS_TEST_GROUPS.py'
    spec = importlib.util.spec_from_file_location('windows_runner_v1237', path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    base = {'LOCALAPPDATA': 'shared', 'APPDATA': 'shared-roaming', 'KEEP': '1'}
    isolated = module.isolated_user_state_env(base, tmp_path / 'case-a')
    assert isolated['LOCALAPPDATA'] == str((tmp_path / 'case-a').resolve())
    assert isolated['APPDATA'] == str((tmp_path / 'case-a' / 'Roaming').resolve())
    assert isolated['KEEP'] == '1'
    assert base['LOCALAPPDATA'] == 'shared'


def test_runtime_zip_build_failure_preserves_previous_known_good_zip(tmp_path):
    tool = _load_runtime_zip_tool()
    app = tmp_path / 'app'
    app.mkdir()
    (app / 'MonoOLEDStudio.exe').write_bytes(b'MZ-probe')
    # Reserved entry would collide with builder-owned provenance.
    (app / 'BUILD_INFO.json').write_text('{}', encoding='utf-8')
    target = tmp_path / 'runtime.zip'
    target.write_bytes(b'KNOWN-GOOD-ZIP')
    try:
        tool.build_runtime_zip(app, target, version='12.3.7', git_commit='abc123')
    except RuntimeError:
        pass
    else:
        raise AssertionError('reserved BUILD_INFO.json collision was accepted')
    assert target.read_bytes() == b'KNOWN-GOOD-ZIP'


def test_ga_builder_relies_on_atomic_runtime_replace_instead_of_deleting_old_zip_first():
    batch = _text(TOOLS / 'BUILD_WINDOWS_GA.bat')
    assert 'if exist "%ZIP%" del /q "%ZIP%"' not in batch
    assert 'if exist "%ZIP%.sha256" del /q "%ZIP%.sha256"' not in batch


def test_runtime_zip_verifier_can_bind_build_info_to_expected_git_commit(tmp_path):
    tool = _load_runtime_zip_tool()
    app = tmp_path / 'app'
    app.mkdir()
    (app / 'MonoOLEDStudio.exe').write_bytes(b'MZ-probe')
    target = tmp_path / 'runtime.zip'
    tool.build_runtime_zip(app, target, version='12.3.7', git_commit='abc123')
    ok = tool.verify_runtime_zip(target, expected_version='12.3.7', expected_git_commit='abc123')
    assert ok['git_commit'] == 'abc123'
    try:
        tool.verify_runtime_zip(target, expected_version='12.3.7', expected_git_commit='different')
    except RuntimeError as exc:
        assert 'commit' in str(exc).lower()
    else:
        raise AssertionError('runtime ZIP with wrong build commit was accepted')


def test_ga_and_publisher_bind_runtime_provenance_to_current_git_commit():
    batch = _text(TOOLS / 'BUILD_WINDOWS_GA.bat')
    publisher = _text(TOOLS / 'PUBLISH_GITHUB_RELEASE.ps1')
    assert '--expected-git-commit "%GIT_COMMIT%"' in batch
    assert 'VERIFY_RELEASE_TAG.py' in publisher and '--require-git-head' in publisher
    assert '--expected-git-commit $GitCommit' in publisher


def test_publisher_treats_existing_release_assets_as_immutable():
    publisher = _text(TOOLS / 'PUBLISH_GITHUB_RELEASE.ps1')
    assert 'gh release download' in publisher
    assert '--clobber' not in publisher
    assert 'Refusing to replace existing release assets' in publisher
    assert 'Existing release assets are identical' in publisher
    assert 'ReadAllText' in publisher
