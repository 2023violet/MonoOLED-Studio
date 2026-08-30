from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any


def unique_temp_path(path: str | Path) -> Path:
    """Create a unique closed temporary sibling suitable for atomic replace."""
    target=Path(path); target.parent.mkdir(parents=True,exist_ok=True)
    fd,name=tempfile.mkstemp(prefix=f'.{target.name}.',suffix='.tmp',dir=target.parent)
    os.close(fd)
    return Path(name)


def atomic_write_bytes(path: str | Path, data: bytes) -> Path:
    target=Path(path); target.parent.mkdir(parents=True,exist_ok=True); tmp=unique_temp_path(target)
    try:
        with tmp.open('wb') as fp:
            fp.write(data); fp.flush(); os.fsync(fp.fileno())
        os.replace(tmp,target)
    finally:
        if tmp.exists(): tmp.unlink(missing_ok=True)
    return target


def atomic_write_text(path: str | Path, text: str, *, encoding: str='utf-8') -> Path:
    return atomic_write_bytes(path, str(text).encode(encoding))


def atomic_write_json(path: str | Path, data: Any, *, sort_keys: bool=False) -> Path:
    return atomic_write_text(path,json.dumps(data,ensure_ascii=False,indent=2,sort_keys=sort_keys)+'\n')
