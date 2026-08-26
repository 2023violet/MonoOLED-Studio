from __future__ import annotations

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

    def __init__(self):
        self._bitmaps: dict[Path, tuple[str, BitmapAsset]] = {}
        self._fonts: dict[Path, tuple[str, dict]] = {}
        self._fontpacks: dict[Path, tuple[str, FontPack]] = {}
        self.stats = CacheStats()

    @staticmethod
    def _digest(raw: bytes) -> str:
        return sha256(raw).hexdigest()

    def _bitmap_resolved(self, path: Path) -> BitmapAsset:
        p = Path(path); raw = p.read_bytes(); digest = self._digest(raw)
        cached = self._bitmaps.get(p)
        if cached and cached[0] == digest:
            self.stats.bitmap_hits += 1
            return cached[1]
        asset = decode_bitmap_bytes(p, raw)
        self._bitmaps[p] = (digest, asset); self.stats.bitmap_misses += 1
        return asset

    def bitmap(self, path: str | Path) -> BitmapAsset:
        return self._bitmap_resolved(Path(path).resolve())

    def _mode_font_resolved(self, path: Path):
        p = Path(path); raw = p.read_bytes(); digest = self._digest(raw)
        cached = self._fonts.get(p)
        if cached and cached[0] == digest:
            self.stats.font_hits += 1
            return cached[1]
        # load_mode_font parses the authoritative format; the second read occurs
        # only on cache miss/content change, never on ordinary render hits.
        font = load_mode_font(p)
        self._fonts[p] = (digest, font); self.stats.font_misses += 1
        return font

    def mode_font(self, path: str | Path):
        return self._mode_font_resolved(Path(path).resolve())

    def font_pack(self, root: str | Path) -> FontPack:
        root = Path(root).resolve(); manifest = root / 'fontpack.json'
        manifest_raw = manifest.read_bytes(); data = json.loads(manifest_raw.decode('utf-8'))
        h = sha256(); h.update(manifest_raw)
        # Content fingerprint includes every declared glyph, not timestamps.
        for ch, meta in sorted(data.get('glyphs', {}).items(), key=lambda kv: kv[0]):
            p = (root / meta['asset']).resolve(); h.update(ch.encode('utf-8')); h.update(p.read_bytes())
        digest = h.hexdigest(); cached = self._fontpacks.get(root)
        if cached and cached[0] == digest:
            self.stats.fontpack_hits += 1
            return cached[1]
        pack = FontPack.load(root)
        self._fontpacks[root] = (digest, pack); self.stats.fontpack_misses += 1
        return pack

    def invalidate(self, path: str | Path | None = None) -> None:
        if path is None:
            self._bitmaps.clear(); self._fonts.clear(); self._fontpacks.clear(); return
        p = Path(path).resolve()
        self._bitmaps.pop(p, None); self._fonts.pop(p, None)
        for root in list(self._fontpacks):
            try:
                if p == root or p.is_relative_to(root): self._fontpacks.pop(root, None)
            except AttributeError:  # pragma: no cover - Python <3.9 compatibility
                try: p.relative_to(root); self._fontpacks.pop(root, None)
                except ValueError: pass
