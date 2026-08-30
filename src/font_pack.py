from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import json
from io import BytesIO
from PIL import Image
from atomic_io import atomic_write_bytes, atomic_write_json
from builtin_oled_font import (
    BUILTIN_5X7,
    DEFAULT_CHARACTERS,
    builtin_glyph_rows,
    recommended_advance,
    recommended_baseline,
    supports_builtin_5x7,
)


def _flattened_image_data(image):
    getter = getattr(image, 'get_flattened_data', None)
    return getter() if callable(getter) else image.getdata()


@dataclass(frozen=True)
class GlyphMetrics:
    bearing_x: int = 0
    bearing_y: int = 0
    advance: int = 0


@dataclass
class Glyph:
    char: str
    pixels: list[list[int]]
    metrics: GlyphMetrics


class FontPack:
    SCHEMA = 1

    @staticmethod
    def validate_metrics(*, cell: tuple[int, int], baseline: int, advance: int) -> tuple[tuple[int, int], int, int]:
        try:
            w, h = tuple(map(int, cell))
        except Exception as exc:
            raise ValueError('font cell must contain width and height') from exc
        if w <= 0 or h <= 0:
            raise ValueError('font cell dimensions must be positive')
        baseline = int(baseline)
        advance = int(advance)
        if not 0 <= baseline < h:
            raise ValueError(f'font baseline must be inside cell height 0..{h-1}')
        if advance <= 0:
            raise ValueError('font advance must be greater than 0')
        return (w, h), baseline, advance

    def __init__(self, root: str | Path, name: str, *, cell: tuple[int, int], baseline: int, advance: int):
        cell, baseline, advance = self.validate_metrics(cell=cell, baseline=baseline, advance=advance)
        self.root = Path(root)
        self.name = str(name)
        self.cell = cell
        self.baseline = baseline
        self.advance = advance
        self._glyphs = {}

    def set_metrics(self, *, baseline: int | None = None, advance: int | None = None):
        advance_was_explicit = advance is not None
        cell, baseline, advance = self.validate_metrics(
            cell=self.cell,
            baseline=self.baseline if baseline is None else baseline,
            advance=self.advance if advance is None else advance,
        )
        self.cell = cell
        self.baseline = baseline
        self.advance = advance
        if advance_was_explicit:
            for ch, glyph in tuple(self._glyphs.items()):
                self._glyphs[ch] = Glyph(
                    glyph.char,
                    glyph.pixels,
                    GlyphMetrics(glyph.metrics.bearing_x, glyph.metrics.bearing_y, advance),
                )
        return self.baseline, self.advance

    @property
    def manifest_path(self):
        return self.root / 'fontpack.json'

    def set_glyph(self, char, pixels, metrics: GlyphMetrics | None = None):
        if len(char) != 1:
            raise ValueError('glyph key must be one Unicode character')
        w, h = self.cell
        rows = [[1 if v else 0 for v in row] for row in pixels]
        if len(rows) != h or any(len(row) != w for row in rows):
            raise ValueError('glyph dimensions do not match font cell')
        resolved_metrics = metrics or GlyphMetrics(0, 0, self.advance)
        if int(resolved_metrics.advance) <= 0:
            raise ValueError('glyph advance must be greater than 0')
        resolved_metrics = GlyphMetrics(
            int(resolved_metrics.bearing_x),
            int(resolved_metrics.bearing_y),
            int(resolved_metrics.advance),
        )
        self._glyphs[char] = Glyph(char, rows, resolved_metrics)

    def glyph(self, char):
        return self._glyphs[char]

    def characters(self):
        return tuple(self._glyphs)

    def compose_text(self, text: str, *, tracking: int = 0) -> list[list[int]]:
        """Compose exact stored glyph pixels into one monochrome bitmap."""
        text = str(text)
        if not text:
            return [[] for _ in range(self.cell[1])]
        missing = [ch for ch in text if ch not in self._glyphs]
        if missing:
            raise KeyError(f'missing glyphs: {missing}')
        starts = []
        cursor = 0
        right = 0
        for i, ch in enumerate(text):
            glyph = self._glyphs[ch]
            start = cursor + glyph.metrics.bearing_x
            starts.append((start, glyph))
            right = max(right, start + self.cell[0])
            cursor += glyph.metrics.advance + (int(tracking) if i < len(text) - 1 else 0)
        left = min(0, min(start for start, _ in starts))
        width = max(0, right - left)
        rows = [[0 for _ in range(width)] for __ in range(self.cell[1])]
        for start, glyph in starts:
            x0 = start - left
            y0 = glyph.metrics.bearing_y
            for gy, row in enumerate(glyph.pixels):
                ty = gy + y0
                if not 0 <= ty < len(rows):
                    continue
                for gx, value in enumerate(row):
                    tx = x0 + gx
                    if value and 0 <= tx < width:
                        rows[ty][tx] = 1
        return rows

    def save(self, *, changed_chars=None):
        """Persist the pack, optionally rewriting only changed glyph PNG assets.

        The manifest is committed exactly once per save.  Existing unchanged
        PNGs are left untouched, which is important for Font Lab updates where
        only a subset of a large pack changed.
        """
        self.set_metrics()
        self.root.mkdir(parents=True, exist_ok=True)
        gd = self.root / 'glyphs'
        gd.mkdir(exist_ok=True)
        manifest = {
            'schema': self.SCHEMA,
            'name': self.name,
            'cell': {'w': self.cell[0], 'h': self.cell[1]},
            'baseline': self.baseline,
            'advance': self.advance,
            'glyphs': {},
        }
        expected_assets = {f'U+{ord(ch):04X}.png' for ch in self._glyphs}
        for stale in gd.glob('U+*.png'):
            if stale.name not in expected_assets:
                stale.unlink(missing_ok=True)

        if changed_chars is None:
            changed = set(self._glyphs)
        else:
            changed = {str(ch) for ch in changed_chars if str(ch) in self._glyphs}

        for ch, g in self._glyphs.items():
            fn = f'U+{ord(ch):04X}.png'
            asset = gd / fn
            if ch in changed or not asset.is_file():
                img = Image.new('1', self.cell, 0)
                img.putdata([255 if value else 0 for row in g.pixels for value in row])
                buf = BytesIO()
                img.save(buf, format='PNG', optimize=False)
                atomic_write_bytes(asset, buf.getvalue())
            manifest['glyphs'][ch] = {
                'asset': f'glyphs/{fn}',
                'bearing_x': g.metrics.bearing_x,
                'bearing_y': g.metrics.bearing_y,
                'advance': g.metrics.advance,
            }
        atomic_write_json(self.manifest_path, manifest)
        return self.manifest_path

    @classmethod
    def load(cls, root):
        root = Path(root).resolve()
        data = json.loads((root / 'fontpack.json').read_text(encoding='utf-8'))
        if int(data.get('schema', cls.SCHEMA)) != cls.SCHEMA:
            raise ValueError(f'unsupported font pack schema: {data.get("schema")}')
        pack = cls(
            root,
            data['name'],
            cell=(data['cell']['w'], data['cell']['h']),
            baseline=data.get('baseline', data['cell']['h'] - 1),
            advance=data.get('advance', data['cell']['w']),
        )
        for ch, meta in data.get('glyphs', {}).items():
            asset = (root / str(meta['asset'])).resolve()
            try:
                asset.relative_to(root)
            except ValueError as exc:
                raise ValueError('glyph asset must stay inside font pack') from exc
            if not asset.is_file():
                raise ValueError(f'missing glyph asset: {meta["asset"]}')
            with Image.open(asset) as im:
                img = im.convert('1')
                width, height = img.size
                flat = [1 if value else 0 for value in _flattened_image_data(img)]
            rows = [flat[y * width:(y + 1) * width] for y in range(height)]
            pack.set_glyph(
                ch,
                rows,
                GlyphMetrics(
                    int(meta.get('bearing_x', 0)),
                    int(meta.get('bearing_y', 0)),
                    int(meta.get('advance', pack.advance)),
                ),
            )
        return pack


def recommended_font_size(cell: tuple[int, int]) -> int:
    """Return a conservative preferred TrueType size for an OLED cell."""
    width, height = map(int, cell)
    if width <= 0 or height <= 0:
        raise ValueError('font cell dimensions must be positive')
    return max(4, min(height, int(round(height * 0.9))))


def create_font_pack(root, name, *, cell=(5, 8), baseline=None, advance=None):
    resolved_baseline = recommended_baseline(cell) if baseline is None else int(baseline)
    resolved_advance = recommended_advance(cell) if advance is None else int(advance)
    return FontPack(root, name, cell=cell, baseline=resolved_baseline, advance=resolved_advance)


def _load_truetype(font_path: str | Path | None, size: int):
    from PIL import ImageFont
    if font_path:
        return ImageFont.truetype(str(font_path), size=int(size))
    try:
        return ImageFont.truetype('DejaVuSans.ttf', size=int(size))
    except OSError:
        return ImageFont.load_default()


def _fit_sample(characters: str) -> list[str]:
    chars = list(dict.fromkeys(str(characters)))
    # Representative ascender/descender/wide glyphs are kept first; cap work
    # for very large Unicode batches so fitting cannot dominate generation.
    sample = []
    for ch in 'MWAgjpQ0/':
        if ch in chars and ch not in sample:
            sample.append(ch)
    for ch in chars:
        if ch not in sample:
            sample.append(ch)
        if len(sample) >= 64:
            break
    return sample


def recommended_truetype_layout(
    font_path: str | Path | None,
    cell: tuple[int, int],
    characters: str,
    preferred_size: int,
) -> tuple[int, int]:
    """Return a fitted TrueType size and a centered shared baseline.

    The family is measured as one batch.  We center the union of representative
    glyph ink inside the cell, then every glyph is rendered against that same
    baseline.  This avoids the per-glyph vertical centering that made letters
    appear to jump up and down in earlier Font Lab builds.
    """
    width, height = map(int, cell)
    preferred_size = int(preferred_size)
    if width <= 0 or height <= 0 or preferred_size <= 0:
        raise ValueError('font dimensions and preferred size must be positive')
    sample = _fit_sample(characters)
    if not sample:
        return max(4, preferred_size), recommended_baseline((width, height))

    lower = 4
    fallback = (lower, recommended_baseline((width, height)))
    for size in range(max(lower, preferred_size), lower - 1, -1):
        font = _load_truetype(font_path, size)
        boxes = []
        for ch in sample:
            try:
                boxes.append(font.getbbox(ch, anchor='ls'))
            except TypeError:
                boxes.append(font.getbbox(ch))
        max_width = max((right - left) for left, top, right, bottom in boxes)
        top = min(box[1] for box in boxes)
        bottom = max(box[3] for box in boxes)
        ink_height = bottom - top
        if max_width > width or ink_height > height:
            continue
        y0 = max(0, (height - ink_height) // 2)
        baseline = y0 - top
        baseline = max(0, min(height - 1, baseline))
        if baseline + top >= 0 and baseline + bottom <= height:
            return size, baseline
        fallback = (size, baseline)
    return fallback


def fit_font_size_for_cell(
    font_path: str | Path | None,
    cell: tuple[int, int],
    baseline: int,
    characters: str,
    preferred_size: int,
) -> int:
    """Fit one TrueType size to a cell while preserving one shared baseline."""
    width, height = map(int, cell)
    preferred_size = int(preferred_size)
    baseline = int(baseline)
    if width <= 0 or height <= 0 or preferred_size <= 0:
        raise ValueError('font dimensions and preferred size must be positive')
    if not 0 <= baseline < height:
        raise ValueError('font baseline must be inside cell height')
    sample = _fit_sample(characters)
    if not sample:
        return max(4, preferred_size)

    lower = 4
    for size in range(max(lower, preferred_size), lower - 1, -1):
        font = _load_truetype(font_path, size)
        fits = True
        for ch in sample:
            try:
                left, top, right, bottom = font.getbbox(ch, anchor='ls')
            except TypeError:
                left, top, right, bottom = font.getbbox(ch)
            if right - left > width:
                fits = False
                break
            if baseline + top < 0 or baseline + bottom > height:
                fits = False
                break
        if fits:
            return size
    return lower


def rasterize_characters(
    pack: FontPack,
    characters: str,
    *,
    font_path: str | Path | None = None,
    font_size: int = 12,
    threshold: int = 128,
    offset: tuple[int, int] = (0, 0),
    weight: str = 'normal',
    progress=None,
) -> int:
    """Rasterize unique characters into an existing FontPack deterministically.

    If the user has not selected a font file and the entire requested character
    set is covered by the built-in OLED family, the canonical bitmap font is
    used.  Imported fonts are auto-fitted once for the batch and still share the
    pack baseline; individual glyphs are never vertically centered.
    """
    from PIL import ImageDraw

    font_size = int(font_size)
    threshold = int(threshold)
    if font_size <= 0:
        raise ValueError('font_size must be greater than 0')
    if not 0 <= threshold <= 255:
        raise ValueError('threshold must be between 0 and 255')
    try:
        ox, oy = offset
    except Exception as exc:
        raise ValueError('offset must contain exactly x and y') from exc
    if isinstance(offset, (list, tuple)) and len(offset) != 2:
        raise ValueError('offset must contain exactly x and y')
    ox, oy = int(ox), int(oy)
    pack.set_metrics()
    chars = list(dict.fromkeys(str(characters)))
    if not chars:
        return 0

    w, h = pack.cell
    total = len(chars)
    use_builtin = (
        not font_path
        and (ox, oy) == (0, 0)
        and supports_builtin_5x7(pack.cell)
        and all(ch in BUILTIN_5X7 for ch in chars)
    )
    if use_builtin:
        for index, ch in enumerate(chars, 1):
            rows = builtin_glyph_rows(ch, pack.cell, baseline=pack.baseline)
            pack.set_glyph(ch, rows, GlyphMetrics(0, 0, pack.advance))
            if progress is not None:
                progress(index, total)
        pack.save(changed_chars=chars)
        return len(chars)

    fitted_size = fit_font_size_for_cell(font_path, pack.cell, pack.baseline + oy, ''.join(chars), font_size)
    font = _load_truetype(font_path, fitted_size)
    threshold_table = [0 if value < threshold else 255 for value in range(256)]
    for index, ch in enumerate(chars, 1):
        img = Image.new('L', (w, h), 0)
        draw = ImageDraw.Draw(img)
        bbox = draw.textbbox((0, 0), ch, font=font, anchor='ls')
        tw = bbox[2] - bbox[0]
        x = (w - tw) // 2 - bbox[0] + ox
        y = pack.baseline + oy
        draw.text((x, y), ch, font=font, fill=255, anchor='ls')
        mask = img.point(threshold_table, mode='1')
        flat = [1 if value else 0 for value in _flattened_image_data(mask)]
        rows = [flat[row * w:(row + 1) * w] for row in range(h)]
        pack.set_glyph(ch, rows, GlyphMetrics(0, 0, pack.advance))
        if progress is not None:
            progress(index, total)
    pack.save(changed_chars=chars)
    return len(chars)
