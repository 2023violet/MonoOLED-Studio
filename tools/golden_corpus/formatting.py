"""Text/binary formatting, preview truncation and legacy C header cases."""
from __future__ import annotations

from dataclasses import asdict, replace
from pathlib import Path

from .common import byte_result, case, digest_result, rows_to_strings, text_result
from .encoding import pattern

from bitmap_encoding import MonoBitmap, encode_bitmap
from c_export import framebuffer_to_c_header
from framebuffer import FrameBuffer
from output_formatter import OutputItem, format_output
from output_profiles import builtin_profiles

NAME = 'formatting'
SOURCES = ('src/output_formatter.py', 'src/output_profiles.py', 'src/c_export.py', 'src/bitmap_encoding.py')


def _item_specs() -> dict[str, list[dict]]:
    return {
        'single': [{'name': 'logo', 'rows': pattern(32, 16)}],
        'glyphs': [
            {'name': 'A', 'rows': pattern(5, 8), 'codepoint': 0x41, 'width': 5, 'height': 8, 'bearing_x': 0, 'bearing_y': 7, 'advance': 6},
            {'name': 'B', 'rows': pattern(6, 8), 'codepoint': 0x42, 'width': 6, 'height': 8, 'bearing_x': 1, 'bearing_y': 7, 'advance': 7},
            {'name': '中', 'rows': pattern(12, 12), 'codepoint': 0x4E2D, 'width': 12, 'height': 12, 'bearing_x': 0, 'bearing_y': 10, 'advance': 12},
        ],
    }


def _items(specs: list[dict], encoding) -> list[OutputItem]:
    items = []
    for spec in specs:
        encoded = encode_bitmap(MonoBitmap.from_rows(spec['rows']), encoding)
        items.append(OutputItem(
            spec['name'], encoded, spec.get('codepoint'), spec.get('width'), spec.get('height'),
            spec.get('bearing_x', 0), spec.get('bearing_y', 0), spec.get('advance', 0),
        ))
    return items


def _input(specs: list[dict], profile, symbol: str, preview_limit: int) -> dict:
    return {
        'items': [{**{k: v for k, v in spec.items() if k != 'rows'}, 'rows': rows_to_strings(spec['rows'])} for spec in specs],
        'encoding': profile.encoding.to_dict(),
        'text': asdict(profile.text),
        'symbol': symbol,
        'preview_limit': preview_limit,
    }


def _expected(result) -> dict:
    return {
        'data': byte_result(result.data),
        'text': text_result(result.text),
        'preview_text': text_result(result.preview_text),
        'preview_truncated': result.preview_truncated,
        'index': [asdict(entry) for entry in result.index],
        'sidecar_text': text_result(result.sidecar_text),
    }


def _variants(text):
    return {
        'base': text,
        'hex-lower': replace(text, uppercase=False),
        'decimal': replace(text, radix='decimal', data_prefix=''),
        'index-inline': replace(text, index_mode='inline'),
        'index-sidecar': replace(text, index_mode='sidecar'),
        'minimal': replace(text, minimal_data=True),
        'compact': replace(text, compact_spacing=True, bytes_per_line=7),
        'binary': replace(text, container='binary'),
    }


def _profile_cases() -> list[dict]:
    cases = []
    for profile_id, profile in builtin_profiles().items():
        for items_name, specs in _item_specs().items():
            for variant, text in _variants(profile.text).items():
                configured = replace(profile, text=text)
                result = format_output(_items(specs, configured.encoding), configured.text, symbol=f'{items_name}_data')
                cases.append(case(f'fmt-{profile_id}-{items_name}-{variant}', 'format', 'strict',
                                  _input(specs, configured, f'{items_name}_data', 256 * 1024), _expected(result)))
    profile = builtin_profiles()['ssd1306_vlsb_c']
    for case_id, symbol in (('fmt-symbol-empty', ''), ('fmt-symbol-leading-digit', '9 bad-name'), ('fmt-symbol-cjk', '图标')):
        specs = _item_specs()['single']
        result = format_output(_items(specs, profile.encoding), profile.text, symbol=symbol)
        cases.append(case(case_id, 'format', 'strict', _input(specs, profile, symbol, 256 * 1024), _expected(result)))
    return cases


def _preview_cases() -> list[dict]:
    profile = builtin_profiles()['ssd1306_vlsb_c']
    big = [{'name': f'frame_{index}', 'rows': pattern(256, 128)} for index in range(12)]
    items = _items(big, profile.encoding)
    full = format_output(items, profile.text, symbol='big').text
    length = len(full.encode('utf-8'))
    assert length > 256 * 1024, length
    cases = []
    for case_id, limit in (('preview-limit-default-over', 256 * 1024), ('preview-limit-exact', length),
                           ('preview-limit-over-by-one', length - 1), ('preview-small-limit', 64)):
        result = format_output(items, profile.text, symbol='big', preview_limit=limit)
        spec = _input(big, profile, 'big', limit)
        spec['items'] = [{'name': item['name'], 'pattern': 'golden_corpus.encoding.pattern(256, 128)', 'rows_sha256': digest_result(''.join(item['rows']).encode())['sha256']} for item in spec['items']]
        expected = _expected(result)
        cases.append(case(case_id, 'format', 'strict', spec, expected))
    cjk = _item_specs()['glyphs']
    for limit in (40, 41, 42):
        result = format_output(_items(cjk, profile.encoding), profile.text, symbol='cjk', preview_limit=limit)
        cases.append(case(f'preview-utf8-split-{limit}', 'format', 'strict', _input(cjk, profile, 'cjk', limit), _expected(result)))
    return cases


def _legacy_header_cases() -> list[dict]:
    cases = []
    for width, height in ((128, 32), (13, 16)):
        fb = FrameBuffer(width, height)
        rows = pattern(width, height)
        for y, row in enumerate(rows):
            for x, value in enumerate(row):
                if value:
                    fb.set_pixel(x, y)
        for name in ('oled_frame', '9 bad-name'):
            text = framebuffer_to_c_header(fb, name)
            label = 'oled_frame' if name == 'oled_frame' else 'bad_name'
            cases.append(case(f'legacy-c-header-{width}x{height}-{label}', 'legacy_c_header', 'strict',
                              {'width': width, 'height': height, 'rows': rows_to_strings(rows), 'name': name},
                              {'text': text_result(text, inline_limit=1 << 20)}))
    return cases


def build(work: Path) -> list[dict]:
    return _profile_cases() + _preview_cases() + _legacy_header_cases()
