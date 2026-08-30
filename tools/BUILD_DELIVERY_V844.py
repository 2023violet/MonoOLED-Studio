#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path, PurePosixPath
import zipfile

ROOT=Path(__file__).resolve().parents[1]
TRANSIENT={'.pytest_cache','__pycache__','.git','.venv','.venv-build','build','dist','release'}


def include(path: Path) -> bool:
    rel=path.relative_to(ROOT)
    if any(part in TRANSIENT for part in rel.parts):return False
    if path.suffix in {'.pyc','.pyo'}:return False
    if len(rel.parts)>=3 and rel.parts[0]=='src' and rel.parts[1]=='reports':
        if rel.parts[2].startswith('linux_') or rel.parts[2] in {'windows_ga','windows_qt'}:
            return False
    return path.is_file()


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_sha256_file(target: Path) -> str:
    target=Path(target).resolve()
    if not target.is_file():raise FileNotFoundError(target)
    digest=sha(target);sidecar=target.with_suffix(target.suffix+'.sha256')
    expected=f'{digest}  {target.name}\n'.encode('ascii')
    sidecar.write_bytes(expected)
    if sidecar.read_bytes()!=expected or sha(target)!=digest:
        raise RuntimeError(f'SHA-256 sidecar verification failed: {sidecar}')
    return digest


def managed_files() -> list[Path]:
    return sorted((p for p in ROOT.rglob('*') if include(p) and p.name!='SHA256SUMS.txt'),key=lambda p:p.relative_to(ROOT).as_posix())


def normalize_windows_scripts() -> int:
    count=0
    for path in sorted([*ROOT.rglob('*.bat'),*ROOT.rglob('*.cmd')]):
        if not include(path):continue
        raw=path.read_bytes().replace(b'\r\n',b'\n').replace(b'\r',b'\n')
        normalized=raw.replace(b'\n',b'\r\n')
        if not normalized.endswith(b'\r\n'):normalized+=b'\r\n'
        path.write_bytes(normalized);count+=1
    return count


def write_sums() -> int:
    normalize_windows_scripts()
    files=managed_files();lines=[f'{sha(p)}  {p.relative_to(ROOT).as_posix()}' for p in files]
    (ROOT/'SHA256SUMS.txt').write_text('\n'.join(lines)+'\n',encoding='utf-8',newline='\n')
    return len(files)


def build_zip(target: Path) -> tuple[int,str,int]:
    write_sums()
    files=sorted((p for p in ROOT.rglob('*') if include(p)),key=lambda p:p.relative_to(ROOT).as_posix())
    target.parent.mkdir(parents=True,exist_ok=True)
    if target.exists():target.unlink()
    with zipfile.ZipFile(target,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as zf:
        for path in files:
            rel=path.relative_to(ROOT).as_posix()
            info=zipfile.ZipInfo(rel,date_time=(1980,1,1,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED;info.external_attr=0o100644<<16
            zf.writestr(info,path.read_bytes())
    with zipfile.ZipFile(target,'r') as zf:
        infos=zf.infolist();names=[i.filename for i in infos]
        if len(names)!=len(set(names)):raise RuntimeError('duplicate ZIP entries')
        for info in infos:
            posix=PurePosixPath(info.filename)
            if posix.is_absolute() or '..' in posix.parts:raise RuntimeError(f'unsafe ZIP path: {info.filename}')
            if any(ord(ch)>127 for ch in info.filename) and not (info.flag_bits&0x800):raise RuntimeError(f'non-UTF8 ZIP filename flag: {info.filename}')
        nonascii=sum(any(ord(ch)>127 for ch in i.filename) for i in infos)
    digest=write_sha256_file(target)
    return len(files),digest,nonascii


def main()->int:
    default=ROOT.parent/'MonoOLED_Studio_v8.4.4_Windows_Real_Qt_GA_Final_Closure_Complete_Delivery_2026-08-24.zip'
    parser=argparse.ArgumentParser();parser.add_argument('output',nargs='?',default=str(default));parser.add_argument('--sha256-only');args=parser.parse_args()
    if args.sha256_only:
        target=Path(args.sha256_only).resolve();digest=write_sha256_file(target)
        print(f'SHA256 {digest}');print(target.with_suffix(target.suffix+'.sha256'));return 0
    target=Path(args.output).resolve();count,digest,nonascii=build_zip(target)
    print(f'PASS: ZIP entries={count}, managed files={count-1}, non-ASCII UTF-8 entries={nonascii}')
    print(f'PASS: SHA256 {digest}')
    print(target);return 0


if __name__=='__main__':raise SystemExit(main())
