#!/usr/bin/env python3
from __future__ import annotations
import sys
from pathlib import Path
import xml.etree.ElementTree as ET


def main(argv=None):
    args=list(sys.argv[1:] if argv is None else argv)
    if not args: print('usage: VERIFY_JUNIT_NO_SKIPS.py <junit.xml>',file=sys.stderr); return 2
    root=ET.parse(Path(args[0])).getroot(); suites=[root] if root.tag=='testsuite' else list(root.findall('.//testsuite'))
    skipped=sum(int(s.attrib.get('skipped','0') or 0) for s in suites)
    failures=sum(int(s.attrib.get('failures','0') or 0)+int(s.attrib.get('errors','0') or 0) for s in suites)
    tests=sum(int(s.attrib.get('tests','0') or 0) for s in suites)
    if failures or skipped:
        print(f'REAL-QT GATE FAIL: tests={tests} failures/errors={failures} skipped={skipped}',file=sys.stderr); return 3
    print(f'REAL-QT GATE PASS: tests={tests} failures/errors=0 skipped=0'); return 0

if __name__=='__main__':raise SystemExit(main())
