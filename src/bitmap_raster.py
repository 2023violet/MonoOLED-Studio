from __future__ import annotations

from PIL import Image

from bitmap_encoding import MonoBitmap
from output_profiles import RasterProfile


def rasterize_image(image: Image.Image, profile: RasterProfile | None = None, *, output_size=None) -> MonoBitmap:
    """Convert color source pixels to strict 0/1 values with stable integer rules."""
    profile = profile or RasterProfile()
    rgba = image.convert('RGBA')
    if output_size is not None:
        width, height = map(int, output_size)
        if width <= 0 or height <= 0:
            raise ValueError('output_size must be positive')
        scale = profile.antialias_scale
        intermediate = (width * scale, height * scale)
        rgba = rgba.resize(intermediate, Image.Resampling.LANCZOS)
        if scale > 1:
            rgba = rgba.resize((width, height), Image.Resampling.LANCZOS)
    width, height = rgba.size
    if width <= 0 or height <= 0:
        raise ValueError('image must not be empty')
    rows = []
    pixels = rgba.load()
    for y in range(height):
        row = []
        for x in range(width):
            red, green, blue, alpha = pixels[x, y]
            if alpha == 0:
                row.append(0)
                continue
            if profile.threshold_mode == 'rgb_all':
                lit = red >= profile.red_threshold and green >= profile.green_threshold and blue >= profile.blue_threshold
            else:
                luma = (299 * red + 587 * green + 114 * blue + 500) // 1000
                lit = luma >= profile.luma_threshold
            value = 1 if lit else 0
            row.append(1 - value if profile.invert_source else value)
        rows.append(row)
    return MonoBitmap.from_rows(rows)
