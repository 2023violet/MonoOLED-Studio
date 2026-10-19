"""Encoding matrix and FrameBuffer VLSB cases."""
from __future__ import annotations

from itertools import product
from pathlib import Path

from .common import byte_result, case, rows_to_strings

from bitmap_encoding import EncodingProfile, MonoBitmap, encode_bitmap
from framebuffer import FrameBuffer

NAME = 'encoding'
SOURCES = ('src/bitmap_encoding.py', 'src/framebuffer.py')

SIZES = ((1, 1), (7, 1), (8, 8), (10, 7), (13, 17), (128, 32), (128, 64), (256, 128))
AXES = ('horizontal', 'vertical')
ORDERS = ('row_major', 'column_major')
BIT_ORDERS = ('lsb_first', 'msb_first')
POLARITIES = ('one_is_lit', 'zero_is_lit')


def pattern(width: int, height: int) -> list[list[int]]:
    return [[1 if ((x * 7 + y * 13 + x * y) % 5) < 2 else 0 for x in range(width)] for y in range(height)]


def _trace(encoded, index: int) -> dict:
    step = encoded.trace_step(index)
    return {
        'index': step.index,
        'value': step.value,
        'coordinates': [list(item) if item is not None else None for item in step.coordinates],
        'source_bits': list(step.source_bits),
    }


def _encoding_cases() -> list[dict]:
    cases = []
    for (width, height), axis, order, bit_order, polarity in product(SIZES, AXES, ORDERS, BIT_ORDERS, POLARITIES):
        rows = pattern(width, height)
        profile = EncodingProfile(bit_axis=axis, group_order=order, bit_order=bit_order, polarity=polarity)
        encoded = encode_bitmap(MonoBitmap.from_rows(rows), profile)
        count = encoded.byte_count
        samples = sorted({0, count // 2, count - 1})
        cases.append(case(
            f'enc-{width}x{height}-{axis}-{order}-{bit_order}-{polarity}', 'encoding', 'strict',
            {'rows': rows_to_strings(rows), 'profile': profile.to_dict()},
            {**byte_result(encoded.data), 'padded_size': list(encoded.padded_size),
             'trace': [_trace(encoded, index) for index in samples]},
        ))
    return cases


def _framebuffer_cases() -> list[dict]:
    specs = {
        'fb-128x32-pixels-and-mask': (128, 32, [(0, 0), (127, 31), (64, 8), (5, 17)],
                                      [{'origin': [10, 3], 'rows': ['10101', '01110', '11111']},
                                       {'origin': [125, 30], 'rows': ['111', '111', '111']}]),
        'fb-128x64-empty': (128, 64, [], []),
        'fb-16x8-negative-origin-mask': (16, 8, [(15, 7)], [{'origin': [-2, -1], 'rows': ['1111', '1111', '1111']}]),
    }
    cases = []
    for case_id, (width, height, pixels, masks) in specs.items():
        fb = FrameBuffer(width, height)
        for x, y in pixels:
            fb.set_pixel(x, y)
        for mask in masks:
            fb.or_mask([[1 if ch == '1' else 0 for ch in row] for row in mask['rows']], *mask['origin'])
        cases.append(case(
            case_id, 'framebuffer', 'strict',
            {'width': width, 'height': height, 'set_pixels': [list(item) for item in pixels], 'masks': masks},
            {**byte_result(fb.to_vlsb()), 'rows': rows_to_strings(fb.to_rows())},
        ))
    try:
        FrameBuffer(8, 7).to_vlsb()
    except ValueError as exc:
        cases.append(case('fb-8x7-vlsb-rejects-partial-page', 'framebuffer', 'strict',
                          {'width': 8, 'height': 7, 'set_pixels': [], 'masks': []},
                          {'error': type(exc).__name__, 'message': str(exc)}))
    return cases


def build(work: Path) -> list[dict]:
    return _encoding_cases() + _framebuffer_cases()
