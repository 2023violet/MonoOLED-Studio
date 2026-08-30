#!/usr/bin/env python3
from __future__ import annotations
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
TOOLS=ROOT/'tools'


def main()->int:
    scripts=sorted([*TOOLS.glob('*.bat'),*TOOLS.glob('*.cmd')])
    if not scripts:
        print('FAIL: no .bat/.cmd scripts found',file=sys.stderr); return 2
    bad=[]
    for path in scripts:
        raw=path.read_bytes()
        crlf=raw.count(b'\r\n'); bare=raw.count(b'\n')-crlf
        if crlf<=0 or bare:
            bad.append(f'{path.relative_to(ROOT)}: CRLF={crlf} LF-only={bare}')
    attrs=ROOT/'.gitattributes'
    if not attrs.is_file(): bad.append('.gitattributes missing')
    else:
        text=attrs.read_text(encoding='utf-8')
        for marker in ('*.bat text eol=crlf','*.cmd text eol=crlf'):
            if marker not in text: bad.append(f'.gitattributes missing {marker!r}')
    if bad:
        print('FAIL: Windows release text contract',file=sys.stderr)
        print('\n'.join(bad),file=sys.stderr); return 1
    print(f'PASS: Windows command scripts CRLF-clean ({len(scripts)} file(s), 0 LF-only records)')
    return 0

if __name__=='__main__': raise SystemExit(main())
