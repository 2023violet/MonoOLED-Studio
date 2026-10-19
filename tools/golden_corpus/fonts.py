"""Font Pack persistence (strict) and TrueType glyph generation (semantic).

Glyph PNG bytes depend on the PNG encoder, so glyphs are compared by decoded
rows; `fontpack.json` is compared byte-for-byte.
"""
from __future__ import annotations

from pathlib import Path

from .common import ROOT, byte_result, case, rows_to_strings

from builtin_oled_font import DEFAULT_CHARACTERS
from font_pack import FontPack, GlyphMetrics, create_font_pack, rasterize_characters

NAME = 'fonts'
SOURCES = ('src/font_pack.py', 'src/builtin_oled_font.py', 'src/font_generator.py', 'src/atomic_io.py')

DEJAVU = ROOT / 'test_assets' / 'fonts' / 'DejaVuSans.ttf'
ASCII = ''.join(chr(code) for code in range(0x20, 0x7F))


def _glyphs(pack: FontPack) -> dict:
    return {
        f'U+{ord(ch):04X}': {
            'rows': rows_to_strings(pack.glyph(ch).pixels),
            'bearing_x': pack.glyph(ch).metrics.bearing_x,
            'bearing_y': pack.glyph(ch).metrics.bearing_y,
            'advance': pack.glyph(ch).metrics.advance,
        }
        for ch in sorted(pack.characters())
    }


def _persisted(pack: FontPack) -> dict:
    loaded = FontPack.load(pack.root)
    return {
        'cell': list(pack.cell), 'baseline': pack.baseline, 'advance': pack.advance,
        'manifest': byte_result(pack.manifest_path.read_bytes()),
        'glyph_assets': sorted(path.name for path in (pack.root / 'glyphs').glob('*.png')),
        'glyphs': _glyphs(pack),
        'reload_matches': _glyphs(loaded) == _glyphs(pack),
    }


def _strict_cases(work: Path) -> list[dict]:
    cases = []
    for cell in ((5, 8), (6, 10)):
        pack = create_font_pack(work / f'builtin_{cell[0]}x{cell[1]}', 'Builtin', cell=cell)
        rasterize_characters(pack, DEFAULT_CHARACTERS)
        cases.append(case(f'fontpack-builtin-{cell[0]}x{cell[1]}-roundtrip', 'font_pack', 'strict',
                          {'cell': list(cell), 'characters': DEFAULT_CHARACTERS, 'font_path': None},
                          _persisted(pack)))
    pack = create_font_pack(work / 'manual', 'Manual 中文', cell=(8, 8), baseline=6, advance=9)
    pack.set_glyph('中', [[1 if x in (3, 4) or y in (2, 5) else 0 for x in range(8)] for y in range(8)], GlyphMetrics(0, 0, 9))
    pack.set_glyph('A', [[1 if (x + y) % 3 == 0 else 0 for x in range(8)] for y in range(8)], GlyphMetrics(1, -1, 7))
    pack.save()
    cases.append(case('fontpack-manual-8x8-cjk-roundtrip', 'font_pack', 'strict',
                      {'name': 'Manual 中文', 'cell': [8, 8], 'baseline': 6, 'advance': 9,
                       'glyphs': {'U+4E2D': 'bars', 'U+0041': 'diagonal (x+y)%3==0, metrics 1,-1,7'}},
                      _persisted(pack)))
    return cases


def _semantic_cases(work: Path) -> list[dict]:
    cases = []
    variants = []
    for cell in ((5, 8), (8, 16), (12, 24)):
        for scale in (1, 4):
            variants.append((f'fontgen-dejavu-{cell[0]}x{cell[1]}-aa{scale}', cell, {'antialias_scale': scale}))
    variants.append(('fontgen-dejavu-8x16-font_set', (8, 16), {'alignment': 'font_set'}))
    variants.append(('fontgen-dejavu-8x16-bold', (8, 16), {'weight': 'bold'}))
    for case_id, cell, options in variants:
        pack = create_font_pack(work / case_id, 'DejaVu', cell=cell)
        rasterize_characters(pack, ASCII, font_path=DEJAVU, font_size=max(4, round(cell[1] * 0.9)), **options)
        cases.append(case(case_id, 'font_generate', 'semantic',
                          {'font': 'test_assets/fonts/DejaVuSans.ttf', 'cell': list(cell), 'characters': ASCII,
                           'font_size': max(4, round(cell[1] * 0.9)), 'threshold': 128, **options},
                          {'cell': list(pack.cell), 'baseline': pack.baseline, 'advance': pack.advance, 'glyphs': _glyphs(pack)},
                          note='semantic: glyph metrics must match exactly; pixel diff threshold set at G1'))
    return cases


def build(work: Path) -> list[dict]:
    return _strict_cases(work) + _semantic_cases(work)
