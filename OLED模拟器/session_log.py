from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Callable


class SessionLogger:
    def __init__(self, path: str | Path, callback: Callable[[dict], None] | None = None):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._fp = self.path.open('a', encoding='utf-8', newline='\n')
        self._callback = callback
        self._seq = self._existing_count()

    def _existing_count(self) -> int:
        try:
            return sum(1 for line in self.path.read_text(encoding='utf-8').splitlines() if line.strip())
        except FileNotFoundError:
            return 0

    def log(self, event: str, **payload) -> dict:
        self._seq += 1
        record = {
            'ts': datetime.now(timezone.utc).isoformat(timespec='milliseconds'),
            'seq': self._seq,
            'event': str(event),
            **payload,
        }
        self._fp.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + '\n')
        self._fp.flush()
        if self._callback is not None:
            self._callback(dict(record))
        return record

    def write_markdown(self, path: str | Path) -> None:
        out = Path(path)
        lines = ['# OLED UI Session Log', '']
        for raw in self.path.read_text(encoding='utf-8').splitlines():
            if not raw.strip():
                continue
            item = json.loads(raw)
            core = f"- `{item.get('ts','')}` **{item.get('event','')}** seq={item.get('seq')}"
            payload = {k: v for k, v in item.items() if k not in {'ts', 'seq', 'event'}}
            if payload:
                core += ' — ' + ', '.join(f"{k}={v!r}" for k, v in payload.items())
            lines.append(core)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text('\n'.join(lines).rstrip() + '\n', encoding='utf-8')

    def close(self) -> None:
        if not self._fp.closed:
            self._fp.flush()
            self._fp.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()
