from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil


class AutoSaveManager:
    def __init__(self, scene: dict, *, keep: int = 10):
        self.scene = scene
        self.keep = max(1, int(keep))
        root = Path(scene.get('_root') or Path(scene['_path']).parent).resolve()
        stem = Path(scene['_path']).stem
        self.directory = root / '.oled' / 'autosave' / stem

    def set_keep(self, keep: int) -> None:
        self.keep = max(1, int(keep))
        snaps = self.snapshots()
        for old in snaps[:-self.keep]:
            old.unlink(missing_ok=True)

    def snapshots(self) -> list[Path]:
        if not self.directory.exists():
            return []
        return sorted(self.directory.glob('*.autosave.json'), key=lambda p: p.name)

    @staticmethod
    def _validate_snapshot_payload(payload) -> dict:
        if not isinstance(payload, dict):
            raise ValueError('autosave snapshot must contain a JSON object')
        canvas = payload.get('canvas')
        if not isinstance(canvas, dict):
            raise ValueError('autosave snapshot missing canvas')
        try:
            width = int(canvas.get('w', 0)); height = int(canvas.get('h', 0))
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError('autosave snapshot has invalid canvas') from exc
        if width <= 0 or height <= 0 or height % 8:
            raise ValueError('autosave snapshot has invalid canvas dimensions')
        if not isinstance(payload.get('elements', []), list):
            raise ValueError('autosave snapshot elements must be a list')
        if not isinstance(payload.get('states', {}), dict):
            raise ValueError('autosave snapshot states must be an object')
        if not isinstance(payload.get('timeline', []), list):
            raise ValueError('autosave snapshot timeline must be a list')
        return payload

    def snapshot(self, *, reason: str = 'timer') -> Path:
        self.directory.mkdir(parents=True, exist_ok=True)
        now = datetime.now(timezone.utc)
        stamp = now.strftime('%Y%m%dT%H%M%S_%fZ')
        target = self.directory / f'{stamp}.autosave.json'
        payload = {k: v for k, v in self.scene.items() if not str(k).startswith('_')}
        payload['_autosave'] = {
            'reason': reason,
            'source': str(Path(self.scene['_path']).resolve()),
            'created_utc': now.isoformat(),
        }
        temp = target.with_name(target.name + '.tmp')
        try:
            with temp.open('w', encoding='utf-8', newline='\n') as fp:
                json.dump(payload, fp, ensure_ascii=False, indent=2)
                fp.write('\n')
                fp.flush(); os.fsync(fp.fileno())
            os.replace(temp, target)
        finally:
            temp.unlink(missing_ok=True)
        snaps = self.snapshots()
        for old in snaps[:-self.keep]:
            old.unlink(missing_ok=True)
        return target

    def _quarantine(self, path: Path, reason: str = 'invalid') -> None:
        try:
            qdir = self.directory / 'quarantine'
            qdir.mkdir(parents=True, exist_ok=True)
            target = qdir / f'{path.name}.{reason}'
            n = 1
            while target.exists():
                target = qdir / f'{path.name}.{reason}.{n}'
                n += 1
            shutil.move(str(path), str(target))
        except OSError:
            # Recovery must remain fail-safe even when quarantine itself cannot write.
            pass

    def _latest_valid(self) -> Path | None:
        for candidate in reversed(self.snapshots()):
            try:
                self.load_snapshot(candidate)
                return candidate
            except (OSError, UnicodeError, json.JSONDecodeError, ValueError, TypeError):
                self._quarantine(candidate)
        return None

    def recovery_candidate(self) -> Path | None:
        """Return the newest valid autosave only when it is newer than disk."""
        latest = self._latest_valid()
        if latest is None:
            return None
        source = Path(self.scene['_path'])
        if not source.exists():
            return latest
        return latest if latest.stat().st_mtime_ns > source.stat().st_mtime_ns else None

    def latest_recovery(self) -> Path | None:
        """Return the newest *valid* recovery point, skipping corrupt snapshots."""
        return self._latest_valid()

    @classmethod
    def load_snapshot(cls, path: str | Path) -> dict:
        payload = json.loads(Path(path).read_text(encoding='utf-8'))
        cls._validate_snapshot_payload(payload)
        payload = dict(payload)
        payload.pop('_autosave', None)
        return payload
