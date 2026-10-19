"""Generator for the frozen synthetic golden-corpus inputs in fixtures/golden/inputs/.

Already run once; its outputs are committed and treated as frozen inputs.
Usage: python tools/MAKE_GOLDEN_INPUTS.py <repo root>
"""
from __future__ import annotations

import json
from pathlib import Path
import shutil
import sys

ROOT = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(ROOT / 'src'))

from PIL import Image  # noqa: E402

from builtin_oled_font import DEFAULT_CHARACTERS  # noqa: E402
from font_pack import create_font_pack, rasterize_characters  # noqa: E402

INPUTS = ROOT / 'fixtures' / 'golden' / 'inputs'
BUILTIN = INPUTS / 'builtin'
SYN = INPUTS / 'synthetic'


def png(path: Path, mode: str, size, pixels) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    image = Image.new(mode, size)
    image.putdata(pixels)
    image.save(path, format='PNG', optimize=False)


def main() -> None:
    # V1 builtin scenes, kept so the corpus stays self-contained after V1 removal.
    for name in ('main_scene.json', 'example_placeholder.json', 'generic_mark.png'):
        target = BUILTIN / 'src' / 'scenes' / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / 'src' / 'scenes' / name, target)

    assets = SYN / 'assets'
    # Transparent white-on-transparent mark (RGBA), 6x4.
    png(assets / 'mark_rgba.png', 'RGBA', (6, 4),
        [(255, 255, 255, 255) if (x + y) % 2 == 0 else (0, 0, 0, 0) for y in range(4) for x in range(6)])
    # Opaque black-on-white (RGB) -> V1 inverts it for OLED.
    png(assets / 'ink_rgb.png', 'RGB', (8, 5),
        [(0, 0, 0) if x in (1, 6) or y == 2 else (255, 255, 255) for y in range(5) for x in range(8)])
    # 1-bit source mode.
    png(assets / 'bits_1.png', '1', (5, 3), [255 if (x * y) % 2 else 0 for y in range(3) for x in range(5)])
    # Grayscale with a non-binary value -> AssetFormatError.
    png(assets / 'bad_gray.png', 'L', (3, 3), [0, 128, 255, 0, 0, 0, 255, 255, 255])
    # Partial alpha -> AssetFormatError.
    png(assets / 'bad_alpha.png', 'RGBA', (2, 2), [(255, 255, 255, 255), (255, 255, 255, 100), (0, 0, 0, 0), (0, 0, 0, 0)])
    for n in range(3):
        png(assets / 'seq' / f'level_{n}.png', 'RGBA', (4, 6),
            [(255, 255, 255, 255) if y >= 6 - 2 * n - 1 else (0, 0, 0, 0) for y in range(6) for x in range(4)])
    for d in '0123456789':
        value = int(d)
        png(assets / 'digits' / f'd_{d}.png', 'RGBA', (3, 5),
            [(255, 255, 255, 255) if ((x + 3 * y + value) % 4) == 0 else (0, 0, 0, 0) for y in range(5) for x in range(3)])
    shutil.copyfile(ROOT / 'test_assets/projects/curing_lite/assets/clinical_ui/english_5x7_v2/cl_font_mode_en_5x7_v2.h',
                    assets / 'mode_font_5x7.h')

    pack = create_font_pack(SYN / 'fonts' / 'builtin_5x8', 'Synthetic Builtin', cell=(5, 8))
    rasterize_characters(pack, DEFAULT_CHARACTERS)

    base = {'schema_version': 1, 'product': 'Synthetic', 'canvas': {'w': 64, 'h': 32, 'preview_scale': 4},
            'storage': {'layout': 'VLSB column-page (SSD1306)', 'bytes_per_frame': 256, 'polarity': '1 = lit'},
            'timeline': [], 'zones': []}
    full = dict(base)
    full['states'] = {
        'level': {'type': 'int', 'min': 0, 'max': 2, 'init': 1},
        'count': {'type': 'int', 'values': [3, 42, 107], 'init': 3},
        'mode': {'type': 'enum', 'values': ['AB', 'CAB'], 'init': 'AB'},
        'show': {'type': 'enum', 'values': ['yes', 'no'], 'init': 'yes'},
    }
    full['state_relations'] = [{'left': 'level', 'operator': '<=', 'right': 'level'}]
    full['elements'] = [
        {'id': 'mark', 'type': 'image', 'asset': 'assets/mark_rgba.png', 'x': -2, 'y': 0},
        {'id': 'ink', 'type': 'image', 'asset': 'assets/ink_rgb.png', 'x': 10, 'y': 0, 'w': 9, 'blend': 'or', 'resize_policy': 'native_only'},
        {'id': 'bits', 'type': 'image', 'asset': 'assets/bits_1.png', 'x': 62, 'y': 30},
        {'id': 'level_bar', 'type': 'image_seq', 'dir': 'assets/seq', 'pattern': 'level_{n}.png', 'bind': 'level', 'x': 20, 'y': 0},
        {'id': 'counter', 'type': 'digits', 'dir': 'assets/digits', 'pattern': 'd_{d}.png', 'bind': 'count',
         'digit_w': 3, 'digit_h': 5, 'tracking': 1, 'min_digits': 3, 'pad_char': '0', 'x': 26, 'y': 0},
        {'id': 'label_left', 'type': 'text', 'text': '{mode}', 'font_header': 'assets/mode_font_5x7.h',
         'zone': {'x': 0, 'y': 8, 'w': 30, 'h': 7}, 'align': 'left'},
        {'id': 'label_center', 'type': 'text', 'text': 'x{mode}', 'font_header': 'assets/mode_font_5x7.h', 'cell_w': 5, 'cell_h': 7,
         'advance': 7, 'zone': {'x': 30, 'y': 8, 'w': 34, 'h': 7}, 'align': 'center'},
        {'id': 'label_right', 'type': 'text', 'text': 'ok', 'font_header': 'assets/mode_font_5x7.h',
         'zone': {'x': 0, 'y': 16, 'w': 64, 'h': 7}, 'align': 'right', 'y': 17},
        {'id': 'label_xy', 'type': 'text', 'text': '', 'font_header': 'assets/mode_font_5x7.h', 'x': 1, 'y': 1},
        {'id': 'pack_text', 'type': 'bitmap_text', 'text': 'A1/{mode}', 'font_pack': 'fonts/builtin_5x8', 'x': 0, 'y': 24},
        {'id': 'future', 'type': 'placeholder', 'x': 40, 'y': 24, 'w': 20, 'h': 6, 'label': 'FUTURE'},
        {'id': 'future_default_label', 'type': 'placeholder', 'x': 1, 'y': 1, 'w': 2, 'h': 2},
        {'id': 'only_when_shown', 'type': 'image', 'asset': 'assets/mark_rgba.png', 'x': 50, 'y': 0, 'visible_when': {'show': 'yes'}},
        {'id': 'hidden', 'type': 'image', 'asset': 'assets/missing.png', 'hidden': True, 'zone': {'x': 3, 'y': 4, 'w': 5, 'h': 6}},
        {'id': 'lower_var', 'type': 'image', 'asset': 'assets/{show}_never.png', 'var_lower': True, 'x': 0, 'y': 0, 'visible_when': {'show': 'never'}},
    ]
    (SYN / 'scenes').mkdir(parents=True, exist_ok=True)

    def write(name, scene):
        (SYN / 'scenes' / name).write_text(json.dumps(scene, ensure_ascii=False, indent=2) + '\n', encoding='utf-8', newline='\n')

    write('full.json', full)

    def single(element, states=None):
        scene = dict(base)
        scene['states'] = states or {}
        scene['elements'] = [element]
        return scene

    write('err_missing_glyph.json', single({'id': 't', 'type': 'text', 'text': 'A1', 'font_header': 'assets/mode_font_5x7.h', 'x': 0, 'y': 0}))
    write('err_bad_align.json', single({'id': 't', 'type': 'text', 'text': 'A', 'font_header': 'assets/mode_font_5x7.h',
                                        'zone': {'x': 0, 'y': 0, 'w': 10, 'h': 7}, 'align': 'justify'}))
    write('err_unknown_type.json', single({'id': 'u', 'type': 'sprite', 'x': 0, 'y': 0}))
    write('err_partial_alpha.json', single({'id': 'a', 'type': 'image', 'asset': 'assets/bad_alpha.png', 'x': 0, 'y': 0}))
    write('err_non_binary.json', single({'id': 'g', 'type': 'image', 'asset': 'assets/bad_gray.png', 'x': 0, 'y': 0}))
    write('err_missing_pack_glyph.json', single({'id': 'p', 'type': 'bitmap_text', 'text': 'a', 'font_pack': 'fonts/builtin_5x8', 'x': 0, 'y': 0}))
    write('err_missing_asset.json', single({'id': 'm', 'type': 'image', 'asset': 'assets/missing.png', 'x': 0, 'y': 0}))
    write('err_bad_schema.json', single({'id': 'm', 'type': 'placeholder', 'x': 0, 'y': 0, 'w': 1, 'h': 1},
                                        {'n': {'type': 'int', 'min': 3, 'max': 1, 'init': 0}}))


if __name__ == '__main__':
    main()
