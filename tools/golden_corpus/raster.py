"""Colour image to strict 0/1 rasterization cases.

Source pixels are stored as raw RGBA bytes so the Rust side does not depend
on any image codec to reproduce the input.
"""
from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

from PIL import Image

from .common import byte_result, case, rows_to_strings

from bitmap_encoding import encode_bitmap
from bitmap_raster import rasterize_image
from output_profiles import RasterProfile

NAME = 'raster'
SOURCES = ('src/bitmap_raster.py', 'src/output_profiles.py', 'src/bitmap_encoding.py')


def _gradient(x: int, y: int) -> tuple[int, int, int, int]:
    return (x * 255 // 63, y * 255 // 31, (x + y) * 255 // 94, 255)


def _checker(x: int, y: int) -> tuple[int, int, int, int]:
    alpha = (0, 128, 255)[(x + y) % 3]
    return (200, 200, 200, alpha) if (x // 2 + y // 2) % 2 else (20, 240, 20, alpha)


def _bars(x: int, y: int) -> tuple[int, int, int, int]:
    return ((255, 0, 0, 255), (0, 255, 0, 255), (0, 0, 255, 255), (255, 255, 255, 255))[x // 10]


SOURCES_IMAGES = {
    'gradient_64x32': (64, 32, _gradient),
    'checker_alpha_17x9': (17, 9, _checker),
    'rgb_bars_40x10': (40, 10, _bars),
}


def _image(width: int, height: int, fn) -> Image.Image:
    image = Image.new('RGBA', (width, height))
    image.putdata([fn(x, y) for y in range(height) for x in range(width)])
    return image


def _profiles() -> dict[str, RasterProfile]:
    return {
        'luma-1': RasterProfile(luma_threshold=1),
        'luma-128': RasterProfile(),
        'luma-255': RasterProfile(luma_threshold=255),
        'luma-128-invert': RasterProfile(invert_source=True),
        'rgb_all-128': RasterProfile(threshold_mode='rgb_all', red_threshold=128, green_threshold=128, blue_threshold=128),
        'rgb_all-red-only': RasterProfile(threshold_mode='rgb_all', red_threshold=200, green_threshold=0, blue_threshold=0),
    }


def _result(bitmap) -> dict:
    return {'rows': rows_to_strings(bitmap.rows), 'vlsb': byte_result(encode_bitmap(bitmap).data)}


def build(work: Path) -> list[dict]:
    cases = []
    for name, (width, height, fn) in SOURCES_IMAGES.items():
        image = _image(width, height, fn)
        source = {'width': width, 'height': height, 'rgba': byte_result(image.tobytes())}
        for label, profile in _profiles().items():
            cases.append(case(f'raster-{name}-{label}', 'raster', 'strict',
                              {'source': source, 'profile': asdict(profile), 'output_size': None},
                              _result(rasterize_image(image, profile))))
        for scale in (1, 2, 4):
            profile = RasterProfile(antialias_scale=scale)
            cases.append(case(f'raster-{name}-resize-32x16-aa{scale}', 'raster', 'strict',
                              {'source': source, 'profile': asdict(profile), 'output_size': [32, 16]},
                              _result(rasterize_image(image, profile, output_size=(32, 16))),
                              note='Pillow LANCZOS resample; may downgrade to semantic at G1 with recorded reason'))
    return cases
