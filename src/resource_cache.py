from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path

from assets import BitmapAsset, decode_bitmap_bytes, load_mode_font
from font_pack import FontPack


@dataclass
class CacheStats:
    bitmap_hits: int = 0
    bitmap_misses: int = 0
    font_hits: int = 0
    font_misses: int = 0
    fontpack_hits: int = 0
    fontpack_misses: int = 0


class RenderResources:
    """Content-safe decode cache for interactive rendering.

    Files are hashed from their current bytes before a cached decoded object is
    reused.  That deliberately handles the same-size/same-mtime mutation case
    that a stat-only cache cannot detect, while avoiding Pillow/header parsing
    on every interactive render.
    """

    def __init__(self, *, bitmap_limit: int = 256, font_limit: int = 32, fontpack_limit: int = 32):
        self.bitmap_limit = max(1, int(bitmap_limit))
        self.font_limit = max(1, int(font_limit))
        self.fontpack_limit = max(1, int(fontpack_limit))
        self._bitmaps: OrderedDict[Path, tuple[str, BitmapAsset]] = OrderedDict()
        self._fonts: OrderedDict[Path, tuple[str, dict]] = OrderedDict()
        self._fontpacks: OrderedDict[Path, tuple[str, FontPack]] = OrderedDict()
        # Manifest digest -> precomputed glyph fingerprint payload. The glyph
        # bytes are hashed once per manifest change, not on every render hit, so
        # the hot path never re-reads glyph files while staying content-addressed.
        self._fontpack_fingerprints: dict[Path, tuple[str, bytes]] = {}
        self.stats = CacheStats()

    @staticmethod
    def _remember(cache, key, value, limit: int):
        cache[key] = value
        cache.move_to_end(key)
        while len(cache) > limit:
            cache.popitem(last=False)


    @staticmethod
    def _digest(raw: bytes) -> str:
        return sha256(raw).hexdigest()

    def _bitmap_resolved(self, path: Path) -> BitmapAsset:
        p = Path(path); raw = p.read_bytes(); digest = self._digest(raw)
        cached = self._bitmaps.get(p)
        if cached and cached[0] == digest:
            self._bitmaps.move_to_end(p)
            self.stats.bitmap_hits += 1
            return cached[1]
        asset = decode_bitmap_bytes(p, raw)
        self._remember(self._bitmaps, p, (digest, asset), self.bitmap_limit); self.stats.bitmap_misses += 1
        return asset

    def bitmap(self, path: str | Path) -> BitmapAsset:
        return self._bitmap_resolved(Path(path).resolve())

    def _mode_font_resolved(self, path: Path):
        p = Path(path); raw = p.read_bytes(); digest = self._digest(raw)
        cached = self._fonts.get(p)
        if cached and cached[0] == digest:
            self._fonts.move_to_end(p)
            self.stats.font_hits += 1
            return cached[1]
        # load_mode_font parses the authoritative format; the second read occurs
        # only on cache miss/content change, never on ordinary render hits.
        font = load_mode_font(p)
        self._remember(self._fonts, p, (digest, font), self.font_limit); self.stats.font_misses += 1
        return font

    def mode_font(self, path: str | Path):
        return self._mode_font_resolved(Path(path).resolve())

    def font_pack(self, root: str | Path) -> FontPack:
        root = Path(root).resolve(); manifest = root / 'fontpack.json'
        manifest_raw = manifest.read_bytes(); manifest_digest = self._digest(manifest_raw)
        mf = self._fontpack_fingerprints.get(root)
        if mf is None or mf[0] != manifest_digest:
            data = json.loads(manifest_raw.decode('utf-8'))
            payload = bytearray(manifest_raw)
            for ch, meta in sorted(data.get('glyphs', {}).items(), key=lambda kv: kv[0]):
                p = (root / str(meta['asset'])).resolve()
                try:
                    p.relative_to(root)
                except ValueError as exc:
                    raise ValueError('glyph asset must stay inside font pack') from exc
                payload += ch.encode('utf-8')
                # Hash each glyph once per manifest change; ordinary render hits
                # reuse the cached payload and never re-read glyph files.
                payload += self._digest(p.read_bytes()).encode('utf-8')
            self._fontpack_fingerprints[root] = (manifest_digest, bytes(payload))
            mf = self._fontpack_fingerprints[root]
        h = sha256(); h.update(mf[1])
        digest = h.hexdigest(); cached = self._fontpacks.get(root)
        if cached and cached[0] == digest:
            self._fontpacks.move_to_end(root)
            self.stats.fontpack_hits += 1
            return cached[1]
        pack = FontPack.load(root)
        self._remember(self._fontpacks, root, (digest, pack), self.fontpack_limit); self.stats.fontpack_misses += 1
        return pack

    def invalidate(self, path: str | Path | None = None) -> None:
        if path is None:
            self._bitmaps.clear(); self._fonts.clear(); self._fontpacks.clear(); self._fontpack_fingerprints.clear(); return
        p = Path(path).resolve()
        self._bitmaps.pop(p, None); self._fonts.pop(p, None)
        for root in list(self._fontpacks):
            try:
                if p == root or p.is_relative_to(root): self._fontpacks.pop(root, None); self._fontpack_fingerprints.pop(root, None)
            except AttributeError:  # pragma: no cover - Python <3.9 compatibility
                try: p.relative_to(root); self._fontpacks.pop(root, None); self._fontpack_fingerprints.pop(root, None)
                except ValueError: pass
