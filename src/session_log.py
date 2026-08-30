from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
from typing import Callable

from atomic_io import unique_temp_path


class SessionLogger:
    def __init__(self, path: str | Path, callback: Callable[[dict], None] | None = None):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._fp = self.path.open('a', encoding='utf-8', newline='\n')
        self._callback = callback
        self._seq = self._existing_count()
        self._degraded = False
        self._last_error = ''

    @property
    def degraded(self) -> bool:
        return self._degraded

    @property
    def last_error(self) -> str:
        return self._last_error

    def _existing_count(self) -> int:
        try:
            count = 0
            highest = 0
            with self.path.open('r', encoding='utf-8') as fp:
                for raw in fp:
                    if not raw.strip():
                        continue
                    count += 1
                    try:
                        item = json.loads(raw)
                        highest = max(highest, int(item.get('seq', count)))
                    except (json.JSONDecodeError, TypeError, ValueError):
                        highest = max(highest, count)
            return highest
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
        try:
            self._fp.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + '\n')
            self._fp.flush()
        except (OSError, ValueError) as exc:
            # Session evidence is important, but it is not allowed to make a
            # successful editor mutation fail after the fact. Expose the
            # degraded state for diagnostics while preserving the main flow.
            self._degraded = True
            self._last_error = str(exc)
        if self._callback is not None:
            try:
                self._callback(dict(record))
            except Exception:
                # The callback is a non-authoritative UI mirror. Logging must
                # remain durable even if that presentation hook is unavailable.
                pass
        return record

    def write_markdown(self, path: str | Path) -> None:
        out = Path(path)
        out.parent.mkdir(parents=True, exist_ok=True)
        temp = unique_temp_path(out)
        try:
            with self.path.open('r', encoding='utf-8') as source, temp.open('w', encoding='utf-8', newline='\n') as target:
                target.write('# OLED UI Session Log\n\n')
                for line_no, raw in enumerate(source, start=1):
                    raw = raw.rstrip('\r\n')
                    if not raw.strip():
                        continue
                    try:
                        item = json.loads(raw)
                    except (json.JSONDecodeError, TypeError, ValueError):
                        target.write(f'- ⚠ skipped corrupt JSONL record at line {line_no}\n')
                        continue
                    core = f"- `{item.get('ts','')}` **{item.get('event','')}** seq={item.get('seq')}"
                    payload = {k: v for k, v in item.items() if k not in {'ts', 'seq', 'event'}}
                    if payload:
                        core += ' — ' + ', '.join(f"{k}={v!r}" for k, v in payload.items())
                    target.write(core + '\n')
                target.flush()
                os.fsync(target.fileno())
            os.replace(temp, out)
        finally:
            try:
                temp.unlink(missing_ok=True)
            except OSError:
                pass

    def close(self) -> None:
        if not self._fp.closed:
            try:
                self._fp.flush()
            except (OSError, ValueError) as exc:
                self._degraded = True
                self._last_error = str(exc)
            try:
                self._fp.close()
            except OSError as exc:
                self._degraded = True
                self._last_error = str(exc)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()
