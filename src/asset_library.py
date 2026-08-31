from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
from pathlib import Path
import json
import os
import shutil

from assets import AssetFormatError, load_bitmap
from project_workspace import resolve_under_root
from atomic_io import unique_temp_path

IMAGE_SUFFIXES = {'.png', '.bmp'}
CACHE_SCHEMA_VERSION = 2


@dataclass(frozen=True)
class AssetEntry:
    rel_path: str
    width: int
    height: int
    sha256: str
    source_mode: str
    source_polarity: str
    inverted: bool
    valid: bool = True
    error: str = ''


@dataclass(frozen=True)
class AssetHealth:
    duplicates: tuple[tuple[str, ...], ...]
    unused: tuple[str, ...]
    invalid: tuple[tuple[str, str], ...]


class AssetLibrary:
    def __init__(self, project_root: str | Path, asset_dirs=('assets',), *, cache_budget_mb: int = 512):
        self.root = Path(project_root).resolve()
        self.asset_dirs = tuple(str(v) for v in asset_dirs)
        # Reject ambiguous external roots. External assets must be imported into
        # the project explicitly so project packages remain portable.
        for rel_dir in self.asset_dirs:
            resolve_under_root(self.root, rel_dir, label='asset directory')
        self.cache_budget_mb = max(32, min(4096, int(cache_budget_mb)))
        self._entries: list[AssetEntry] = []
        self._cache: dict[Path, tuple[int, int, str, AssetEntry]] = {}
        self._cache_path = self.root / '.oled' / 'asset_cache_v1.json'
        self._load_persistent_cache()

    @property
    def _cache_entry_limit(self) -> int:
        # Metadata-only cache. This establishes a deterministic upper bound and
        # gives the user-facing cache budget a real runtime consumer.
        return max(64, (self.cache_budget_mb * 1024 * 1024) // 512)

    def set_cache_budget_mb(self, value: int) -> None:
        self.cache_budget_mb = max(32, min(4096, int(value)))
        self._trim_cache()

    def clear_cache(self) -> None:
        self._cache.clear()
        self._entries.clear()
        try:
            self._cache_path.unlink(missing_ok=True)
        except OSError:
            pass

    def _trim_cache(self) -> None:
        excess = len(self._cache) - self._cache_entry_limit
        if excess > 0:
            for path in tuple(self._cache)[:excess]:
                self._cache.pop(path, None)

    def _load_persistent_cache(self) -> None:
        try:
            payload = json.loads(self._cache_path.read_text(encoding='utf-8'))
        except (OSError, ValueError, TypeError):
            return
        if not isinstance(payload, dict) or payload.get('schema_version') != CACHE_SCHEMA_VERSION:
            return
        entries = payload.get('entries') or {}
        if not isinstance(entries, dict):
            return
        for rel, raw in entries.items():
            try:
                path = resolve_under_root(self.root, rel, label='asset cache path')
                entry = AssetEntry(**raw['entry'])
                raw_hash = str(raw['content_sha256'])
                self._cache[path] = (int(raw['mtime_ns']), int(raw['size']), raw_hash, entry)
            except (KeyError, TypeError, ValueError):
                continue
        self._trim_cache()

    def _save_persistent_cache(self) -> None:
        self._trim_cache()
        payload = {'schema_version': CACHE_SCHEMA_VERSION, 'entries': {}}
        for path, (mtime_ns, size, raw_hash, entry) in self._cache.items():
            try:
                rel = path.relative_to(self.root).as_posix()
            except ValueError:
                continue
            payload['entries'][rel] = {
                'mtime_ns': mtime_ns, 'size': size, 'content_sha256': raw_hash,
                'entry': asdict(entry),
            }
        try:
            serialized = json.dumps(payload, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
            if self._cache_path.exists() and self._cache_path.read_bytes() == serialized:
                return
            self._cache_path.parent.mkdir(parents=True, exist_ok=True)
            temp = unique_temp_path(self._cache_path)
            with temp.open('wb') as fp:
                fp.write(serialized)
                fp.flush(); os.fsync(fp.fileno())
            os.replace(temp, self._cache_path)
        except OSError:
            pass
        finally:
            try:
                temp.unlink(missing_ok=True)
            except (UnboundLocalError, OSError):
                pass

    def _entry(self, path: Path) -> AssetEntry:
        resolved = path.resolve()
        rel = resolved.relative_to(self.root).as_posix()
        try:
            asset = load_bitmap(path)
            pixel_bytes = bytes(v for row in asset.pixels for v in row)
            canonical_hash = sha256(asset.width.to_bytes(4, 'little') + asset.height.to_bytes(4, 'little') + pixel_bytes).hexdigest()
            return AssetEntry(rel, asset.width, asset.height, canonical_hash, asset.source_mode, asset.source_polarity, asset.inverted)
        except (AssetFormatError, OSError, ValueError) as exc:
            raw_hash = sha256(path.read_bytes()).hexdigest() if path.exists() else ''
            return AssetEntry(rel, 0, 0, raw_hash, '', '', False, False, str(exc))

    def scan(self) -> list[AssetEntry]:
        entries: list[AssetEntry] = []
        seen: set[Path] = set()
        for rel_dir in self.asset_dirs:
            base = resolve_under_root(self.root, rel_dir, label='asset directory')
            if not base.exists() or not base.is_dir():
                continue
            for path in sorted(base.rglob('*'), key=lambda p: p.as_posix().lower()):
                if path.suffix.lower() not in IMAGE_SUFFIXES:
                    continue
                try:
                    if not path.is_file():
                        continue
                    resolved = path.resolve()
                    # A junction/symlink under an allowed directory can still point
                    # outside the project. Treat that one entry as unsafe instead of
                    # taking down the entire live asset scan.
                    resolved.relative_to(self.root)
                    stat = resolved.stat()
                    cached = self._cache.get(resolved)
                    # Persistent cache correctness is content-addressed. Metadata such
                    # as mtime+size is only advisory: tools can rewrite a bitmap while
                    # preserving both values, so skipping the content hash would make
                    # stale pixels look current. We still avoid the expensive bitmap
                    # decode whenever the raw content hash matches the cached entry.
                    content_hash = sha256(resolved.read_bytes()).hexdigest()
                except (OSError, ValueError):
                    # External editors, git operations, and atomic replace workflows
                    # can remove/replace an asset while this scan is in flight. Skip
                    # the transient/unsafe entry and keep the rest of the library live.
                    continue
                seen.add(resolved)
                fingerprint = (stat.st_mtime_ns, stat.st_size, content_hash)
                if cached is not None and cached[2] == content_hash:
                    entry = cached[3]
                else:
                    entry = self._entry(resolved)
                self._cache[resolved] = (fingerprint[0], fingerprint[1], fingerprint[2], entry)
                entries.append(entry)
        for stale in tuple(self._cache):
            if stale not in seen:
                self._cache.pop(stale, None)
        self._entries = entries
        self._save_persistent_cache()
        return list(entries)

    @property
    def entries(self) -> tuple[AssetEntry, ...]:
        return tuple(self._entries or self.scan())

    def search(self, query: str = '') -> list[AssetEntry]:
        q = query.strip().casefold()
        values = list(self.entries)
        if not q:
            return values
        return [entry for entry in values if q in entry.rel_path.casefold()]

    def import_asset(self, source: str | Path, *, target_dir: str = 'assets/imported') -> AssetEntry:
        source = Path(source).resolve()
        if not source.exists() or not source.is_file():
            raise FileNotFoundError(source)
        if source.suffix.lower() not in IMAGE_SUFFIXES:
            raise ValueError(f'unsupported image type: {source.suffix}')
        # Validate before copying so invalid source never pollutes the project.
        load_bitmap(source)
        target_root = resolve_under_root(self.root, target_dir, label='asset import target')
        target_root.mkdir(parents=True, exist_ok=True)
        target = target_root / source.name
        # Filename is sourced from a Path.name and therefore cannot itself traverse.
        target = resolve_under_root(self.root, target.relative_to(self.root), label='asset import file')
        source_hash = sha256(source.read_bytes()).hexdigest()
        if target.exists() and sha256(target.read_bytes()).hexdigest() != source_hash:
            target = target_root / f'{source.stem}_{source_hash[:8]}{source.suffix.lower()}'
        if not target.exists():
            shutil.copy2(source, target)
        entry = self._entry(target)
        self.scan()
        return entry

    def health_report(self, *, used_paths: set[str] | None = None) -> AssetHealth:
        used = {str(Path(p).as_posix()) for p in (used_paths or set())}
        entries = list(self.entries)
        by_hash: dict[str, list[str]] = {}
        invalid: list[tuple[str, str]] = []
        for entry in entries:
            if entry.valid:
                by_hash.setdefault(entry.sha256, []).append(entry.rel_path)
            else:
                invalid.append((entry.rel_path, entry.error))
        duplicates = tuple(tuple(paths) for paths in sorted(by_hash.values(), key=lambda p: p[0]) if len(paths) > 1)
        unused = tuple(sorted(entry.rel_path for entry in entries if entry.rel_path not in used))
        return AssetHealth(duplicates, unused, tuple(sorted(invalid)))
