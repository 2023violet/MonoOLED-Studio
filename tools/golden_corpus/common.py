"""Shared helpers for the V1 golden corpus used by the Rust rewrite."""
from __future__ import annotations

from collections import namedtuple
from hashlib import sha256
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / 'src'
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

LEVELS = ('strict', 'semantic')
PROJECT_ROOT_TOKEN = '${PROJECT_ROOT}'
_PATH_AFTER_TOKEN = re.compile(re.escape(PROJECT_ROOT_TOKEN) + r'''[^\s'"<>|*?:,;)\]}]*''')

Category = namedtuple('Category', 'name build sources')


def canonical_json(value) -> bytes:
    text = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)
    return text.encode('utf-8') + b'\n'


def byte_result(data: bytes) -> dict:
    data = bytes(data)
    return {'hex': data.hex(), 'byte_count': len(data), 'sha256': sha256(data).hexdigest()}


def digest_result(data: bytes) -> dict:
    """Byte summary without the payload, for large outputs."""
    data = bytes(data)
    return {'byte_count': len(data), 'sha256': sha256(data).hexdigest()}


def rows_to_strings(rows) -> list[str]:
    return [''.join('1' if bit else '0' for bit in row) for row in rows]


def strings_to_rows(rows: list[str]) -> list[list[int]]:
    return [[1 if ch == '1' else 0 for ch in row] for row in rows]


def text_result(text: str, inline_limit: int = 4096) -> dict:
    encoded = text.encode('utf-8')
    if len(encoded) <= inline_limit:
        return {'text': text, **digest_result(encoded)}
    return digest_result(encoded)


def replace_root(value, root: Path):
    """Replace the absolute temporary project root with PROJECT_ROOT_TOKEN, nothing else."""
    variants = set()
    for base in (str(root), str(Path(root).resolve())):
        # Plain, POSIX-style, and repr()-escaped spellings (OSError messages use repr).
        variants.update({base, base.replace('\\', '/'), base.replace('\\', '\\\\')})
    if isinstance(value, str):
        for variant in sorted(variants, key=len, reverse=True):
            value = value.replace(variant, PROJECT_ROOT_TOKEN)
        # Only the path that follows the token is made platform-neutral.
        return _PATH_AFTER_TOKEN.sub(lambda m: re.sub(r'\\+', '/', m.group(0)), value)
    if isinstance(value, list | tuple):
        return [replace_root(item, root) for item in value]
    if isinstance(value, dict):
        return {key: replace_root(item, root) for key, item in value.items()}
    return value


def case(id: str, kind: str, level: str, input: dict, expected: dict, note: str | None = None) -> dict:
    if level not in LEVELS:
        raise ValueError(f'level must be one of {LEVELS}: {level!r}')
    if not id or not id.isascii():
        raise ValueError(f'case id must be non-empty ASCII: {id!r}')
    payload = {'id': id, 'kind': kind, 'level': level, 'input': input, 'expected': expected}
    if note:
        payload['note'] = note
    return payload
