from __future__ import annotations

import pytest

from bitmap_encoding import EncodingProfile, MonoBitmap, encode_bitmap


ROWS = (
    (1, 0, 1, 0, 0, 0, 0, 0, 1, 0),
    (0, 1, 0, 0, 0, 0, 0, 0, 0, 1),
    (0, 0, 0, 0, 1, 0, 0, 0, 0, 0),
    (0, 0, 0, 0, 0, 0, 0, 1, 0, 0),
    (0, 0, 0, 1, 0, 0, 0, 0, 0, 0),
    (0, 0, 0, 0, 0, 1, 0, 0, 0, 0),
    (1, 0, 0, 0, 0, 0, 1, 0, 0, 0),
    (0, 0, 1, 0, 0, 0, 0, 0, 0, 0),
    (0, 1, 0, 0, 0, 0, 0, 0, 1, 0),
    (0, 0, 0, 0, 1, 0, 0, 0, 0, 1),
)


@pytest.mark.parametrize(
    ('bit_axis', 'group_order', 'expected'),
    [
        ('horizontal', 'row_major', bytes.fromhex('A0 80 40 40 08 00 01 00 10 00 04 00 82 00 20 00 40 80 08 40')),
        ('horizontal', 'column_major', bytes.fromhex('A0 40 08 01 10 04 82 20 40 08 80 40 00 00 00 00 00 00 80 40')),
        ('vertical', 'column_major', bytes.fromhex('82 00 40 80 81 00 08 00 20 40 04 00 02 00 10 00 80 80 40 40')),
        ('vertical', 'row_major', bytes.fromhex('82 40 81 08 20 04 02 10 80 40 00 80 00 00 40 00 00 00 80 40')),
    ],
)
def test_four_extraction_modes_have_independent_literal_goldens(bit_axis, group_order, expected):
    result = encode_bitmap(
        MonoBitmap.from_rows(ROWS),
        EncodingProfile(bit_axis=bit_axis, group_order=group_order, bit_order='msb_first'),
    )

    assert result.data == expected
    assert result.padded_size == (16, 10) if bit_axis == 'horizontal' else (10, 16)
    assert result.byte_count == 20


@pytest.mark.parametrize(
    ('bit_axis', 'group_order', 'expected'),
    [
        ('horizontal', 'row_major', bytes.fromhex('05 01 02 02 10 00 80 00 08 00 20 00 41 00 04 00 02 01 10 02')),
        ('horizontal', 'column_major', bytes.fromhex('05 02 10 80 08 20 41 04 02 10 01 02 00 00 00 00 00 00 01 02')),
        ('vertical', 'column_major', bytes.fromhex('41 00 02 01 81 00 10 00 04 02 20 00 40 00 08 00 01 01 02 02')),
        ('vertical', 'row_major', bytes.fromhex('41 02 81 10 04 20 40 08 01 02 00 01 00 00 02 00 00 00 01 02')),
    ],
)
def test_lsb_first_places_first_sample_in_bit_zero(bit_axis, group_order, expected):
    profile = EncodingProfile(bit_axis=bit_axis, group_order=group_order, bit_order='lsb_first')
    assert encode_bitmap(MonoBitmap.from_rows(ROWS), profile).data == expected


def test_zero_is_lit_inverts_pixels_and_padded_off_bits():
    bitmap = MonoBitmap.from_rows(((1, 0, 1),))
    profile = EncodingProfile(bit_axis='horizontal', group_order='row_major', bit_order='msb_first', polarity='zero_is_lit')
    result = encode_bitmap(bitmap, profile)

    assert result.data == bytes((0x5F,))
    assert result.trace_step(0).coordinates == ((0, 0), (1, 0), (2, 0), None, None, None, None, None)
    assert result.trace_step(0).source_bits == (1, 0, 1, 0, 0, 0, 0, 0)


@pytest.mark.parametrize(
    'rows',
    [(), ((1, 0), (1,)), ((0, 2),)],
)
def test_monobitmap_rejects_empty_ragged_or_non_binary_rows(rows):
    with pytest.raises(ValueError):
        MonoBitmap.from_rows(rows)
