#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import tempfile
import zipfile

FIXED_TIME = (1980, 1, 1, 0, 0, 0)
FORBIDDEN_PREFIXES = ('test_assets/', 'tests/', '.git/', '.venv', 'build/', 'release/')


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def _safe_name(name: str) -> None:
    rel = PurePosixPath(name)
    if not name or rel.is_absolute() or '..' in rel.parts or '\\' in name:
        raise RuntimeError(f'unsafe runtime ZIP path: {name!r}')
    if not name.isascii():
        raise RuntimeError(f'non-ASCII runtime ZIP path: {name!r}')


def _atomic_write(path: Path, payload: bytes) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f'.{path.name}.', suffix='.tmp', dir=path.parent)
    temp = Path(temp_name)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
    except Exception:
        temp.unlink(missing_ok=True)
        raise


def _write_checksum(target: Path) -> Path:
    digest = _sha256(target)
    sidecar = target.with_suffix(target.suffix + '.sha256')
    _atomic_write(sidecar, f'{digest}  {target.name}\n'.encode('ascii'))
    return sidecar


def _build_info(version: str, git_commit: str) -> bytes:
    payload = {
        'product': 'MonoOLED Studio',
        'version': version,
        'release_tag': f'v{version}',
        'git_commit': git_commit or 'unavailable',
        'distribution': 'Windows x64 onedir',
        'format': 1,
    }
    return (json.dumps(payload, sort_keys=True, indent=2) + '\n').encode('utf-8')


def _app_files(app_dir: Path) -> list[Path]:
    app_dir = Path(app_dir).resolve()
    if not (app_dir / 'MonoOLEDStudio.exe').is_file():
        raise RuntimeError(f'missing runtime executable: {app_dir / "MonoOLEDStudio.exe"}')
    files = []
    for path in app_dir.rglob('*'):
        if path.is_symlink():
            raise RuntimeError(f'runtime bundle may not contain symlinks: {path}')
        if path.is_file():
            rel = path.relative_to(app_dir).as_posix()
            _safe_name(rel)
            if rel == 'BUILD_INFO.json':
                raise RuntimeError('BUILD_INFO.json is reserved for builder-owned provenance')
            if any(rel == prefix.rstrip('/') or rel.startswith(prefix) for prefix in FORBIDDEN_PREFIXES):
                raise RuntimeError(f'developer/test artifact forbidden in runtime bundle: {rel}')
            files.append(path)
    return sorted(files, key=lambda p: p.relative_to(app_dir).as_posix())


def build_runtime_zip(app_dir: Path, target: Path, *, version: str, git_commit: str = '') -> dict[str, object]:
    app_dir = Path(app_dir).resolve()
    target = Path(target).resolve()
    files = _app_files(app_dir)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f'.{target.name}.', suffix='.tmp', dir=target.parent)
    os.close(fd)
    temp = Path(temp_name)
    try:
        with zipfile.ZipFile(temp, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
            for path in files:
                rel = path.relative_to(app_dir).as_posix()
                info = zipfile.ZipInfo(rel, date_time=FIXED_TIME)
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o100644 << 16
                archive.writestr(info, path.read_bytes())
            info = zipfile.ZipInfo('BUILD_INFO.json', date_time=FIXED_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, _build_info(version, git_commit))
        # Validate the complete candidate before replacing any known-good release ZIP.
        report = verify_runtime_zip(temp, expected_version=version, expected_git_commit=git_commit or 'unavailable')
        os.replace(temp, target)
    except Exception:
        temp.unlink(missing_ok=True)
        raise
    sidecar = _write_checksum(target)
    report['sha256'] = _sha256(target)
    report['checksum'] = sidecar.name
    return report


def _verify_checksum(zip_path: Path, checksum: Path) -> None:
    raw = Path(checksum).read_text(encoding='ascii').strip().split()
    if len(raw) != 2:
        raise RuntimeError(f'invalid checksum sidecar: {checksum}')
    expected, filename = raw
    if filename != zip_path.name:
        raise RuntimeError(f'checksum filename mismatch: {filename!r} != {zip_path.name!r}')
    actual = _sha256(zip_path)
    if actual != expected:
        raise RuntimeError(f'checksum mismatch: expected={expected} actual={actual}')


def verify_runtime_zip(zip_path: Path, *, expected_version: str, checksum: Path | None = None, expected_git_commit: str | None = None) -> dict[str, object]:
    zip_path = Path(zip_path).resolve()
    if not zip_path.is_file():
        raise FileNotFoundError(zip_path)
    if checksum is not None:
        _verify_checksum(zip_path, Path(checksum).resolve())
    with zipfile.ZipFile(zip_path, 'r') as archive:
        infos = archive.infolist()
        names = [item.filename for item in infos]
        if len(names) != len(set(names)):
            raise RuntimeError('duplicate runtime ZIP entries')
        for name in names:
            _safe_name(name)
            if any(name == prefix.rstrip('/') or name.startswith(prefix) for prefix in FORBIDDEN_PREFIXES):
                raise RuntimeError(f'developer/test artifact forbidden in runtime ZIP: {name}')
        if 'MonoOLEDStudio.exe' not in names:
            raise RuntimeError('runtime ZIP missing MonoOLEDStudio.exe')
        if 'BUILD_INFO.json' not in names:
            raise RuntimeError('runtime ZIP missing BUILD_INFO.json')
        try:
            build_info = json.loads(archive.read('BUILD_INFO.json').decode('utf-8'))
        except Exception as exc:
            raise RuntimeError(f'invalid BUILD_INFO.json: {exc}') from exc
        if build_info.get('version') != expected_version:
            raise RuntimeError(
                f'runtime ZIP version mismatch: {build_info.get("version")!r} != {expected_version!r}'
            )
        if build_info.get('release_tag') != f'v{expected_version}':
            raise RuntimeError('runtime ZIP release tag mismatch')
        git_commit = str(build_info.get('git_commit') or '')
        if expected_git_commit is not None and git_commit.lower() != expected_git_commit.lower():
            raise RuntimeError(
                f'runtime ZIP git commit mismatch: {git_commit!r} != {expected_git_commit!r}'
            )
    return {'files': len(names), 'exe': 'MonoOLEDStudio.exe', 'version': expected_version, 'git_commit': git_commit}


def extract_runtime_zip(zip_path: Path, destination: Path, *, expected_version: str, checksum: Path | None = None, expected_git_commit: str | None = None) -> dict[str, object]:
    report = verify_runtime_zip(zip_path, expected_version=expected_version, checksum=checksum, expected_git_commit=expected_git_commit)
    destination = Path(destination).resolve()
    if destination.exists():
        shutil.rmtree(destination)
    destination.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(Path(zip_path).resolve(), 'r') as archive:
        for item in archive.infolist():
            _safe_name(item.filename)
            target = (destination / PurePosixPath(item.filename)).resolve()
            try:
                target.relative_to(destination)
            except ValueError as exc:
                raise RuntimeError(f'unsafe extraction path: {item.filename}') from exc
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(item, 'r') as source, target.open('wb') as sink:
                shutil.copyfileobj(source, sink)
    if not (destination / 'MonoOLEDStudio.exe').is_file():
        raise RuntimeError('extracted runtime missing MonoOLEDStudio.exe')
    report['extracted_to'] = str(destination)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description='Build/verify deterministic MonoOLED Studio Windows runtime ZIP.')
    parser.add_argument('--app-dir')
    parser.add_argument('--output')
    parser.add_argument('--version')
    parser.add_argument('--git-commit', default='unavailable')
    parser.add_argument('--verify')
    parser.add_argument('--expected-version')
    parser.add_argument('--checksum')
    parser.add_argument('--extract-to')
    parser.add_argument('--expected-git-commit')
    args = parser.parse_args()

    if args.verify:
        version = args.expected_version or args.version
        if not version:
            parser.error('--expected-version is required with --verify')
        checksum = Path(args.checksum) if args.checksum else None
        if args.extract_to:
            report = extract_runtime_zip(Path(args.verify), Path(args.extract_to), expected_version=version, checksum=checksum, expected_git_commit=args.expected_git_commit)
        else:
            report = verify_runtime_zip(Path(args.verify), expected_version=version, checksum=checksum, expected_git_commit=args.expected_git_commit)
        print('PASS: runtime ZIP verified ' + json.dumps(report, sort_keys=True))
        return 0

    if not (args.app_dir and args.output and args.version):
        parser.error('--app-dir, --output and --version are required to build')
    report = build_runtime_zip(Path(args.app_dir), Path(args.output), version=args.version, git_commit=args.git_commit)
    print('PASS: runtime ZIP built ' + json.dumps(report, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
