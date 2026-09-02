#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path, PurePosixPath
import zipfile

ROOT = Path(__file__).resolve().parents[1]
TRANSIENT = {
    '.git', '.oled', '.pytest_cache', '.venv', '.venv-build', '.artifacts',
    '__pycache__', 'build', 'dist', 'release', '.mypy_cache', '.ruff_cache',
}


def include(path: Path) -> bool:
    rel = path.relative_to(ROOT)
    if any(part in TRANSIENT for part in rel.parts):
        return False
    if path.suffix in {'.pyc', '.pyo'}:
        return False
    return path.is_file()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def write_sha256_file(target: Path) -> str:
    target = Path(target).resolve()
    if not target.is_file():
        raise FileNotFoundError(target)
    digest = sha256(target)
    sidecar = target.with_suffix(target.suffix + '.sha256')
    payload = f'{digest}  {target.name}\n'.encode('ascii')
    sidecar.write_bytes(payload)
    if sidecar.read_bytes() != payload or sha256(target) != digest:
        raise RuntimeError(f'SHA-256 sidecar verification failed: {sidecar}')
    return digest


def normalize_windows_scripts() -> int:
    count = 0
    for path in sorted([*ROOT.rglob('*.bat'), *ROOT.rglob('*.cmd')]):
        if not include(path):
            continue
        raw = path.read_bytes().replace(b'\r\n', b'\n').replace(b'\r', b'\n')
        normalized = raw.replace(b'\n', b'\r\n')
        if not normalized.endswith(b'\r\n'):
            normalized += b'\r\n'
        path.write_bytes(normalized)
        count += 1
    return count


def managed_files() -> list[Path]:
    return sorted(
        (path for path in ROOT.rglob('*') if include(path) and path.name != 'SHA256SUMS.txt'),
        key=lambda path: path.relative_to(ROOT).as_posix(),
    )


def write_sums() -> int:
    normalize_windows_scripts()
    files = managed_files()
    lines = []
    for path in files:
        rel = path.relative_to(ROOT).as_posix()
        if not rel.isascii():
            raise RuntimeError(f'non-ASCII source release path: {rel}')
        lines.append(f'{sha256(path)}  {rel}')
    (ROOT / 'SHA256SUMS.txt').write_text('\n'.join(lines) + '\n', encoding='utf-8', newline='\n')
    return len(files)


def build_zip(target: Path) -> tuple[int, str]:
    write_sums()
    files = sorted(
        (path for path in ROOT.rglob('*') if include(path)),
        key=lambda path: path.relative_to(ROOT).as_posix(),
    )
    target = Path(target).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        target.unlink()
    with zipfile.ZipFile(target, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in files:
            rel = path.relative_to(ROOT).as_posix()
            if not rel.isascii():
                raise RuntimeError(f'non-ASCII source ZIP path: {rel}')
            info = zipfile.ZipInfo(rel, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, path.read_bytes())
    with zipfile.ZipFile(target, 'r') as archive:
        infos = archive.infolist()
        names = [item.filename for item in infos]
        if len(names) != len(set(names)):
            raise RuntimeError('duplicate ZIP entries')
        for item in infos:
            rel = PurePosixPath(item.filename)
            if rel.is_absolute() or '..' in rel.parts:
                raise RuntimeError(f'unsafe ZIP path: {item.filename}')
            if not item.filename.isascii():
                raise RuntimeError(f'non-ASCII source ZIP path: {item.filename}')
    return len(files), write_sha256_file(target)


def main() -> int:
    version = (ROOT / 'src' / 'VERSION').read_text(encoding='utf-8').strip()
    default = ROOT.parent / f'MonoOLED-Studio-v{version}-Release-Ready-Source.zip'
    parser = argparse.ArgumentParser()
    parser.add_argument('output', nargs='?', default=str(default))
    parser.add_argument('--sha256-only')
    args = parser.parse_args()
    if args.sha256_only:
        target = Path(args.sha256_only).resolve()
        digest = write_sha256_file(target)
        print(f'SHA256 {digest}')
        print(target.with_suffix(target.suffix + '.sha256'))
        return 0
    target = Path(args.output).resolve()
    count, digest = build_zip(target)
    print(f'PASS: source ZIP entries={count}, non-ASCII paths=0')
    print(f'PASS: SHA256 {digest}')
    print(target)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
