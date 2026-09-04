from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Sequence


_BIT_AXES = {'horizontal', 'vertical'}
_GROUP_ORDERS = {'row_major', 'column_major'}
_BIT_ORDERS = {'msb_first', 'lsb_first'}
_POLARITIES = {'one_is_lit', 'zero_is_lit'}


@dataclass(frozen=True)
class MonoBitmap:
    width: int
    height: int
    rows: tuple[tuple[int, ...], ...]

    @classmethod
    def from_rows(cls, rows: Iterable[Iterable[int]]) -> 'MonoBitmap':
        normalized = tuple(tuple(int(value) for value in row) for row in rows)
        if not normalized or not normalized[0]:
            raise ValueError('monochrome bitmap must not be empty')
        width = len(normalized[0])
        if any(len(row) != width for row in normalized):
            raise ValueError('monochrome bitmap rows must have equal width')
        if any(value not in (0, 1) for row in normalized for value in row):
            raise ValueError('monochrome bitmap values must be 0 or 1')
        return cls(width, len(normalized), normalized)


@dataclass(frozen=True)
class EncodingProfile:
    bit_axis: str = 'vertical'
    group_order: str = 'row_major'
    bit_order: str = 'lsb_first'
    polarity: str = 'one_is_lit'

    def __post_init__(self) -> None:
        for name, value, allowed in (
            ('bit_axis', self.bit_axis, _BIT_AXES),
            ('group_order', self.group_order, _GROUP_ORDERS),
            ('bit_order', self.bit_order, _BIT_ORDERS),
            ('polarity', self.polarity, _POLARITIES),
        ):
            if value not in allowed:
                raise ValueError(f'{name} must be one of {sorted(allowed)}')

    def to_dict(self) -> dict[str, str]:
        return {
            'bit_axis': self.bit_axis,
            'group_order': self.group_order,
            'bit_order': self.bit_order,
            'polarity': self.polarity,
        }


@dataclass(frozen=True)
class TraceStep:
    index: int
    value: int
    coordinates: tuple[tuple[int, int] | None, ...]
    source_bits: tuple[int, ...]


@dataclass(frozen=True)
class EncodedOutput:
    data: bytes
    width: int
    height: int
    padded_size: tuple[int, int]
    _steps: tuple[TraceStep, ...] = field(repr=False)

    @property
    def byte_count(self) -> int:
        return len(self.data)

    def trace_step(self, index: int) -> TraceStep:
        return self._steps[index]


def _groups(bitmap: MonoBitmap, profile: EncodingProfile):
    if profile.bit_axis == 'horizontal':
        blocks = (bitmap.width + 7) // 8
        if profile.group_order == 'row_major':
            for y in range(bitmap.height):
                for block in range(blocks):
                    yield tuple((block * 8 + bit, y) if block * 8 + bit < bitmap.width else None for bit in range(8))
        else:
            for block in range(blocks):
                for y in range(bitmap.height):
                    yield tuple((block * 8 + bit, y) if block * 8 + bit < bitmap.width else None for bit in range(8))
        return

    blocks = (bitmap.height + 7) // 8
    if profile.group_order == 'column_major':
        for x in range(bitmap.width):
            for block in range(blocks):
                yield tuple((x, block * 8 + bit) if block * 8 + bit < bitmap.height else None for bit in range(8))
    else:
        for block in range(blocks):
            for x in range(bitmap.width):
                yield tuple((x, block * 8 + bit) if block * 8 + bit < bitmap.height else None for bit in range(8))


def encode_bitmap(bitmap: MonoBitmap, profile: EncodingProfile | None = None) -> EncodedOutput:
    profile = profile or EncodingProfile()
    output = bytearray()
    steps = []
    for index, coordinates in enumerate(_groups(bitmap, profile)):
        source_bits = tuple(bitmap.rows[coordinate[1]][coordinate[0]] if coordinate is not None else 0 for coordinate in coordinates)
        value = 0
        for position, source_bit in enumerate(source_bits):
            encoded_bit = source_bit if profile.polarity == 'one_is_lit' else 1 - source_bit
            shift = 7 - position if profile.bit_order == 'msb_first' else position
            value |= encoded_bit << shift
        output.append(value)
        steps.append(TraceStep(index, value, coordinates, source_bits))
    padded = (
        ((bitmap.width + 7) // 8 * 8, bitmap.height)
        if profile.bit_axis == 'horizontal'
        else (bitmap.width, (bitmap.height + 7) // 8 * 8)
    )
    return EncodedOutput(bytes(output), bitmap.width, bitmap.height, padded, tuple(steps))


def bitmap_from_framebuffer(framebuffer) -> MonoBitmap:
    return MonoBitmap.from_rows(framebuffer.to_rows())


def bitmap_from_pixel_document(document) -> MonoBitmap:
    return MonoBitmap.from_rows(document.pixels)
