from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from io import BytesIO
import re

from PIL import Image


@dataclass(frozen=True)
class BitmapAsset:
    path: Path
    width: int
    height: int
    pixels: tuple[tuple[int, ...], ...]
    sha256: str
    source_mode: str
    source_polarity: str
    inverted: bool


class AssetFormatError(ValueError):
    pass


def _binary_rgba_pixel(r: int, g: int, b: int, a: int, *, path: Path, xy: tuple[int, int]) -> int:
    if a not in (0, 255):
        raise AssetFormatError(f"{path}: partial alpha {a} at {xy}")
    if a == 0:
        return 0
    if (r, g, b) == (0, 0, 0):
        return 0
    if (r, g, b) == (255, 255, 255):
        return 1
    raise AssetFormatError(f"{path}: non-binary RGB {(r, g, b)} at {xy}")


def _detect_source_polarity(rgba, *, path: Path) -> tuple[str, bool]:
    """Detect bitmap source polarity without changing the production pixel contract.

    Transparent assets use alpha as background. Fully opaque assets are classified by
    their border: a white-dominant border means the source is a conventional
    black-on-white design asset and must be inverted for an OLED black background.
    """
    width, height = rgba.size
    pixels = [rgba.getpixel((x, y)) for y in range(height) for x in range(width)]
    for index, (r, g, b, a) in enumerate(pixels):
        if a not in (0, 255):
            x, y = index % width, index // width
            raise AssetFormatError(f"{path}: partial alpha {a} at {(x, y)}")
        if a and (r, g, b) not in {(0, 0, 0), (255, 255, 255)}:
            x, y = index % width, index // width
            raise AssetFormatError(f"{path}: non-binary RGB {(r, g, b)} at {(x, y)}")

    if any(a == 0 for _, _, _, a in pixels):
        return "transparent", False

    border: list[tuple[int, int, int, int]] = []
    if width and height:
        for x in range(width):
            border.append(rgba.getpixel((x, 0)))
            if height > 1:
                border.append(rgba.getpixel((x, height - 1)))
        for y in range(1, max(1, height - 1)):
            border.append(rgba.getpixel((0, y)))
            if width > 1:
                border.append(rgba.getpixel((width - 1, y)))

    white_border = sum(1 for r, g, b, _ in border if (r, g, b) == (255, 255, 255))
    black_border = sum(1 for r, g, b, _ in border if (r, g, b) == (0, 0, 0))
    black_total = sum(1 for r, g, b, _ in pixels if (r, g, b) == (0, 0, 0))
    white_total = len(pixels) - black_total

    if black_total and (white_border > black_border or (white_border == black_border and white_total > black_total)):
        return "black_on_white", True
    return "white_on_black", False


def decode_bitmap_bytes(path: str | Path, raw: bytes) -> BitmapAsset:
    """Decode an already-read bitmap without a second filesystem read."""
    path = Path(path)
    with Image.open(BytesIO(raw)) as image:
        source_mode = image.mode
        rgba = image.convert("RGBA")
        source_polarity, inverted = _detect_source_polarity(rgba, path=path)
        rows: list[tuple[int, ...]] = []
        for y in range(rgba.height):
            row = []
            for x in range(rgba.width):
                value = _binary_rgba_pixel(*rgba.getpixel((x, y)), path=path, xy=(x, y))
                if inverted:
                    value = 1 - value
                row.append(value)
            rows.append(tuple(row))
        return BitmapAsset(
            path=path, width=rgba.width, height=rgba.height, pixels=tuple(rows),
            sha256=sha256(raw).hexdigest(), source_mode=source_mode,
            source_polarity=source_polarity, inverted=inverted,
        )


def load_bitmap(path: str | Path) -> BitmapAsset:
    path = Path(path)
    return decode_bitmap_bytes(path, path.read_bytes())


_ROW_RE = re.compile(r"\{([^{}]+)\}\s*,?\s*/\*\s*([A-Z])\s*\*/")
_HEX_RE = re.compile(r"0[xX][0-9A-Fa-f]+|\d+")


def load_mode_font(header_path: str | Path) -> dict[str, list[list[int]]]:
    """Decode the approved 26×5 clinical 5×7 font (column-major, bit0=top)."""
    header_path = Path(header_path)
    text = header_path.read_text(encoding="utf-8")
    glyphs: dict[str, list[list[int]]] = {}
    for body, letter in _ROW_RE.findall(text):
        cols = [int(token, 0) & 0xFF for token in _HEX_RE.findall(body)]
        if len(cols) != 5:
            continue
        glyphs[letter] = [[(cols[x] >> y) & 1 for x in range(5)] for y in range(7)]
    if set(glyphs) != set("ABCDEFGHIJKLMNOPQRSTUVWXYZ"):
        missing = "".join(sorted(set("ABCDEFGHIJKLMNOPQRSTUVWXYZ") - set(glyphs)))
        raise AssetFormatError(f"{header_path}: expected A-Z 5x7 font; missing={missing or 'unknown'}")
    return glyphs
