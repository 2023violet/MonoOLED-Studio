#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def _git_commit(root: Path, ref: str) -> str:
    proc = subprocess.run(
        ['git', '-C', str(root), 'rev-parse', ref],
        text=True, capture_output=True, check=False,
    )
    if proc.returncode:
        raise RuntimeError(proc.stderr.strip() or f'git rev-parse failed for {ref!r}')
    return proc.stdout.strip().lower()


def verify_git_head_matches_tag(root: Path, tag: str) -> tuple[bool, str, str]:
    root = Path(root).resolve()
    head = _git_commit(root, 'HEAD^{commit}')
    tagged = _git_commit(root, f'{tag}^{{commit}}')
    return head == tagged, head, tagged


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('tag', nargs='?', default=os.environ.get('GITHUB_REF_NAME', ''))
    parser.add_argument('--require-git-head', action='store_true')
    args = parser.parse_args(argv)

    version = (ROOT / 'src' / 'VERSION').read_text(encoding='utf-8').strip()
    tag = args.tag.strip()
    expected = f'v{version}'
    if not re.fullmatch(r'v\d+\.\d+\.\d+', tag):
        print(f'[FAIL] release tag must be vMAJOR.MINOR.PATCH, got {tag!r}', file=sys.stderr)
        return 2
    if tag != expected:
        print(f'[FAIL] tag/version mismatch: tag={tag!r}, expected={expected!r}', file=sys.stderr)
        return 2
    if args.require_git_head:
        try:
            ok, head, tagged = verify_git_head_matches_tag(ROOT, tag)
        except Exception as exc:
            print(f'[FAIL] cannot verify git release identity: {exc}', file=sys.stderr)
            return 2
        if not ok:
            print(f'[FAIL] checked-out HEAD does not match {tag}: HEAD={head} tag={tagged}', file=sys.stderr)
            return 2
        print(f'[PASS] git HEAD is exactly {tag} commit: {head}')
    print(f'[PASS] release tag matches src/VERSION: {tag}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
