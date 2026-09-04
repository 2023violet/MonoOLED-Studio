from __future__ import annotations

from dataclasses import dataclass
import re

from bitmap_encoding import EncodedOutput
from output_profiles import TextFormatProfile


@dataclass(frozen=True)
class OutputItem:
    name: str
    encoded: EncodedOutput
    codepoint: int | None = None
    width: int | None = None
    height: int | None = None
    bearing_x: int = 0
    bearing_y: int = 0
    advance: int = 0


@dataclass(frozen=True)
class IndexEntry:
    codepoint: int
    offset: int
    byte_length: int
    width: int
    height: int
    bearing_x: int
    bearing_y: int
    advance: int


@dataclass(frozen=True)
class FormattedOutput:
    data: bytes
    text: str
    preview_text: str
    preview_truncated: bool
    index: tuple[IndexEntry, ...]
    sidecar_text: str = ''


def sanitize_symbol(value: str) -> str:
    symbol = re.sub(r'[^A-Za-z0-9_]+', '_', str(value)).strip('_') or 'oled_bitmap'
    if symbol[0].isdigit():
        symbol = 'bitmap_' + symbol
    return symbol


def _expand(template: str, values: dict[str, object]) -> str:
    return re.sub(r'\$\{([^}]+)\}', lambda match: str(values[match.group(1)]), template)


def _number(value: int, profile: TextFormatProfile) -> str:
    if profile.radix == 'decimal':
        return str(value)
    digits = f'{value:02X}' if profile.uppercase else f'{value:02x}'
    return digits


def _data_lines(data: bytes, profile: TextFormatProfile, *, minimal: bool) -> str:
    separator = '' if profile.compact_spacing else ' '
    prefix = '' if minimal else profile.line_prefix
    suffix = '' if minimal else profile.line_suffix
    ending = '\n' if minimal else profile.line_end
    lines = []
    for start in range(0, len(data), profile.bytes_per_line):
        tokens = [profile.data_prefix + _number(value, profile) + profile.data_suffix for value in data[start:start + profile.bytes_per_line]]
        lines.append(prefix + separator.join(tokens) + suffix + ending)
    return ''.join(lines)


def _index_text(entries: tuple[IndexEntry, ...], symbol: str, entries_per_line: int) -> str:
    if not entries:
        return ''
    records = [
        f'{{ 0x{entry.codepoint:08X}, {entry.offset}, {entry.byte_length}, {entry.width}, {entry.height}, {entry.bearing_x}, {entry.bearing_y}, {entry.advance} }},'
        for entry in entries
    ]
    rows = ''.join('    ' + ' '.join(records[start:start + entries_per_line]) + '\n' for start in range(0, len(records), entries_per_line))
    return (
        '\ntypedef struct { uint32_t codepoint, offset, byte_length; uint16_t width, height; int16_t bearing_x, bearing_y; uint16_t advance; } MonoGlyphIndex;\n'
        f'static const MonoGlyphIndex {symbol}_index[] = {{\n{rows}}};\n'
    )


def _preview(text: str, limit: int) -> tuple[str, bool]:
    raw = text.encode('utf-8')
    if len(raw) <= limit:
        return text, False
    return raw[:max(0, int(limit))].decode('utf-8', errors='ignore'), True


def format_output(items: list[OutputItem], profile: TextFormatProfile, *, symbol: str, preview_limit: int = 256 * 1024) -> FormattedOutput:
    if not items:
        raise ValueError('output requires at least one item')
    symbol = sanitize_symbol(symbol)
    data = b''.join(item.encoded.data for item in items)
    entries = []
    offset = 0
    for item in items:
        if item.codepoint is not None:
            entries.append(IndexEntry(
                int(item.codepoint), offset, len(item.encoded.data),
                int(item.width if item.width is not None else item.encoded.width),
                int(item.height if item.height is not None else item.encoded.height),
                int(item.bearing_x), int(item.bearing_y), int(item.advance),
            ))
        offset += len(item.encoded.data)
    index = tuple(entries)

    if profile.container == 'binary':
        return FormattedOutput(data, '', '', False, index)

    common = {
        'symbol': symbol, 'name': items[0].name,
        'codepoint': '' if items[0].codepoint is None else items[0].codepoint,
        'width': items[0].encoded.width, 'height': items[0].encoded.height,
        'byte_count': len(data), 'offset': 0,
    }
    if profile.minimal_data:
        text = _data_lines(data, profile, minimal=True)
    else:
        chunks = [_expand(profile.segment_prefix, common)]
        running_offset = 0
        for item in items:
            values = dict(common)
            values.update(
                name=item.name,
                codepoint='' if item.codepoint is None else item.codepoint,
                width=item.encoded.width,
                height=item.encoded.height,
                byte_count=len(item.encoded.data),
                offset=running_offset,
            )
            if profile.comment_prefix or profile.comment_suffix:
                chunks.append(_expand(profile.comment_prefix, values) + str(values['name']) + _expand(profile.comment_suffix, values))
            chunks.append(_data_lines(item.encoded.data, profile, minimal=False))
            running_offset += len(item.encoded.data)
        chunks.append(_expand(profile.segment_suffix, common))
        text = ''.join(chunks)
    index_text = _index_text(index, symbol, profile.index_entries_per_line) if profile.index_mode != 'none' else ''
    sidecar = index_text if profile.index_mode == 'sidecar' else ''
    if profile.index_mode == 'inline':
        text += index_text
    preview_text, truncated = _preview(text, preview_limit)
    return FormattedOutput(data, text, preview_text, truncated, index, sidecar)
