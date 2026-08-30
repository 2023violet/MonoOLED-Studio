from __future__ import annotations

from pathlib import Path
import re

_VERSION_RE = re.compile(r'^\d+\.\d+\.\d+$')


def load_version() -> str:
    version = Path(__file__).with_name('VERSION').read_text(encoding='utf-8').strip()
    if not _VERSION_RE.fullmatch(version):
        raise RuntimeError(f'invalid MonoOLED Studio version: {version!r}')
    return version


APP_VERSION = load_version()
