from __future__ import annotations

from bitmap_encoding import EncodingProfile, MonoBitmap, encode_bitmap
from output_formatter import OutputItem, format_output
from output_profiles import TextFormatProfile
from output_profiles import builtin_profiles
from pixel_studio import PixelDocument


def _encoded():
    return encode_bitmap(
        MonoBitmap.from_rows(((1, 0, 1, 0, 0, 0, 0, 1),)),
        EncodingProfile(bit_axis='horizontal', group_order='row_major', bit_order='msb_first'),
    )


def test_custom_text_format_applies_literal_fields_in_defined_order():
    profile = TextFormatProfile(
        radix='hex', uppercase=True, bytes_per_line=1,
        segment_prefix='BEGIN ${symbol}\n', segment_suffix='END ${byte_count}\n',
        comment_prefix='/* ', comment_suffix=' */\n', data_prefix='0x', data_suffix=',',
        line_prefix='{', line_suffix='}', line_end=';\n',
    )
    text = format_output([OutputItem('logo', _encoded())], profile, symbol='demo-logo').text

    assert text == 'BEGIN demo_logo\n/* logo */\n{0xA1,};\nEND 1\n'


def test_decimal_compact_output_respects_bytes_per_line():
    encoded = encode_bitmap(
        MonoBitmap.from_rows(((1,) * 24,)),
        EncodingProfile(bit_axis='horizontal', group_order='row_major', bit_order='msb_first'),
    )
    profile = TextFormatProfile(radix='decimal', data_prefix='', bytes_per_line=2, compact_spacing=True, minimal_data=True)

    assert format_output([OutputItem('row', encoded)], profile, symbol='row').text == '255,255,\n255,\n'


def test_font_index_offsets_match_flattened_data_and_character_order():
    first = OutputItem('A', _encoded(), codepoint=65, width=8, height=1, advance=6)
    second = OutputItem('中', _encoded(), codepoint=0x4E2D, width=8, height=1, advance=8)
    profile = TextFormatProfile(index_mode='inline')
    result = format_output([first, second], profile, symbol='font')

    assert result.data == bytes((0xA1, 0xA1))
    assert [(row.codepoint, row.offset, row.byte_length) for row in result.index] == [(65, 0, 1), (0x4E2D, 1, 1)]
    assert '{ 0x00000041, 0, 1, 8, 1, 0, 0, 6 }' in result.text
    assert '{ 0x00004E2D, 1, 1, 8, 1, 0, 0, 8 }' in result.text


def test_font_index_respects_entries_per_line():
    items = [OutputItem(chr(65 + i), _encoded(), codepoint=65 + i) for i in range(3)]
    profile = TextFormatProfile(index_mode='sidecar', index_entries_per_line=2)

    result = format_output(items, profile, symbol='font')
    record_lines = [line for line in result.sidecar_text.splitlines() if line.startswith('    {')]

    assert len(record_lines) == 2
    assert record_lines[0].count('{') == 2


def test_preview_truncates_text_without_changing_full_payload():
    profile = TextFormatProfile(minimal_data=True)
    result = format_output([OutputItem('logo', _encoded())], profile, symbol='logo', preview_limit=4)

    assert result.preview_truncated is True
    assert len(result.preview_text.encode('utf-8')) <= 4
    assert result.text == '0xA1,\n'


def test_legacy_pixel_template_matches_existing_header_for_compatible_symbol():
    document = PixelDocument(8, 8)
    document.pencil(0, 0, 1)
    encoded = encode_bitmap(MonoBitmap.from_rows(document.pixels))

    result = format_output(
        [OutputItem('LOGO', encoded)],
        builtin_profiles()['legacy_pixel_c'].text,
        symbol='LOGO',
    )

    assert result.text == document.to_c_header('LOGO')
