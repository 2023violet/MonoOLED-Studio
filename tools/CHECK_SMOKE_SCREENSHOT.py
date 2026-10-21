"""Sanity-check desktop smoke screenshots from CI (G5 install tests).

A PNG passes when it is at least 1000x600 and actually shows a UI: not one
flat colour, enough distinct colours, and a share of high-contrast "ink"
pixels (text, outlines, the OLED canvas). This catches blank, black or
crashed windows. It cannot prove every glyph rendered: the Linux CJK font is
covered by installing the .deb in a clean container (its Depends must pull a
CJK font), and the screenshots are kept as artifacts for human review.

Usage: python tools/CHECK_SMOKE_SCREENSHOT.py smoke/*.png
"""
from __future__ import annotations

from collections import Counter
import struct
import sys
import zlib

MIN_SIZE = (1000, 600)
MAX_DOMINANT_SHARE = 0.90
MIN_COLOURS = 32
MIN_INK_SHARE = 0.005
INK_CONTRAST = 80


def decode_png(data: bytes) -> tuple[int, int, list[tuple[int, int, int]]]:
    if data[:8] != b'\x89PNG\r\n\x1a\n':
        raise ValueError('not a PNG')
    pos, idat = 8, b''
    width = height = channels = 0
    while pos < len(data):
        length, kind = struct.unpack('>I4s', data[pos:pos + 8])
        body = data[pos + 8:pos + 8 + length]
        pos += 12 + length
        if kind == b'IHDR':
            width, height, depth, colour, _, _, interlace = struct.unpack('>IIBBBBB', body)
            if depth != 8 or interlace or colour not in (2, 6):
                raise ValueError(f'unsupported PNG (depth {depth}, colour {colour}, interlace {interlace})')
            channels = 3 if colour == 2 else 4
        elif kind == b'IDAT':
            idat += body
        elif kind == b'IEND':
            break
    raw = zlib.decompress(idat)
    stride = width * channels
    prev = bytearray(stride)
    pixels: list[tuple[int, int, int]] = []
    for y in range(height):
        start = y * (stride + 1)
        kind, line = raw[start], bytearray(raw[start + 1:start + 1 + stride])
        for i in range(stride):
            a = line[i - channels] if i >= channels else 0
            b = prev[i]
            c = prev[i - channels] if i >= channels else 0
            if kind == 1:
                line[i] = (line[i] + a) & 0xFF
            elif kind == 2:
                line[i] = (line[i] + b) & 0xFF
            elif kind == 3:
                line[i] = (line[i] + (a + b) // 2) & 0xFF
            elif kind == 4:
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                line[i] = (line[i] + (a if pa <= pb and pa <= pc else b if pb <= pc else c)) & 0xFF
        pixels.extend(tuple(line[x:x + 3]) for x in range(0, stride, channels))
        prev = line
    return width, height, pixels


def check(path: str) -> list[str]:
    width, height, pixels = decode_png(open(path, 'rb').read())
    problems = []
    if width < MIN_SIZE[0] or height < MIN_SIZE[1]:
        problems.append(f'window too small: {width}x{height}')
    counts = Counter(pixels)
    dominant, dominant_count = counts.most_common(1)[0]
    share = dominant_count / len(pixels)
    lum = sum(dominant) / 3
    ink = sum(n for colour, n in counts.items() if abs(sum(colour) / 3 - lum) > INK_CONTRAST) / len(pixels)
    print(f'{path}: {width}x{height}, {len(counts)} colours, dominant {share:.1%}, ink {ink:.2%}')
    if share > MAX_DOMINANT_SHARE:
        problems.append(f'mostly one colour ({share:.1%})')
    if len(counts) < MIN_COLOURS:
        problems.append(f'only {len(counts)} colours')
    if ink < MIN_INK_SHARE:
        problems.append(f'almost no text or outlines ({ink:.2%})')
    return problems


def main(paths: list[str]) -> int:
    if not paths:
        print('no screenshots given', file=sys.stderr)
        return 2
    failed = False
    for path in paths:
        for problem in check(path):
            print(f'FAIL {path}: {problem}', file=sys.stderr)
            failed = True
    return 1 if failed else 0


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))
