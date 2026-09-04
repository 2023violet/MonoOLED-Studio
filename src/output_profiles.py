from __future__ import annotations

from dataclasses import asdict, dataclass, field
import re
from typing import Any

from bitmap_encoding import EncodingProfile


_PLACEHOLDERS = {'symbol', 'name', 'codepoint', 'width', 'height', 'byte_count', 'offset'}
_TEMPLATE_FIELDS = (
    'segment_prefix', 'segment_suffix', 'comment_prefix', 'comment_suffix',
    'data_prefix', 'data_suffix', 'line_prefix', 'line_suffix', 'line_end',
)


@dataclass(frozen=True)
class RasterProfile:
    alignment: str = 'glyph_width'
    threshold_mode: str = 'luma'
    luma_threshold: int = 128
    red_threshold: int = 255
    green_threshold: int = 255
    blue_threshold: int = 255
    invert_source: bool = False
    antialias_scale: int = 1
    offset_x: int = 0
    offset_y: int = 0

    def __post_init__(self) -> None:
        if self.alignment not in {'font_set', 'glyph_width'}:
            raise ValueError('alignment must be font_set or glyph_width')
        if self.threshold_mode not in {'luma', 'rgb_all'}:
            raise ValueError('threshold_mode must be luma or rgb_all')
        for name in ('luma_threshold', 'red_threshold', 'green_threshold', 'blue_threshold'):
            if not 0 <= int(getattr(self, name)) <= 255:
                raise ValueError(f'{name} must be between 0 and 255')
        if self.antialias_scale not in {1, 2, 4}:
            raise ValueError('antialias_scale must be 1, 2, or 4')


@dataclass(frozen=True)
class TextFormatProfile:
    container: str = 'text'
    radix: str = 'hex'
    uppercase: bool = True
    bytes_per_line: int = 16
    index_entries_per_line: int = 16
    index_mode: str = 'none'
    minimal_data: bool = False
    compact_spacing: bool = False
    segment_prefix: str = '#pragma once\n#include <stdint.h>\n\nstatic const uint8_t ${symbol}[] = {\n'
    segment_suffix: str = '};\n'
    comment_prefix: str = '    /* '
    comment_suffix: str = ' */\n'
    data_prefix: str = '0x'
    data_suffix: str = ','
    line_prefix: str = '    '
    line_suffix: str = ''
    line_end: str = '\n'

    def __post_init__(self) -> None:
        if self.container not in {'binary', 'text'}:
            raise ValueError('container must be binary or text')
        if self.radix not in {'hex', 'decimal'}:
            raise ValueError('radix must be hex or decimal')
        if self.index_mode not in {'none', 'inline', 'sidecar'}:
            raise ValueError('index_mode must be none, inline, or sidecar')
        for name in ('bytes_per_line', 'index_entries_per_line'):
            if not 1 <= int(getattr(self, name)) <= 256:
                raise ValueError(f'{name} must be between 1 and 256')
        for name in _TEMPLATE_FIELDS:
            value = getattr(self, name)
            if not isinstance(value, str):
                raise ValueError(f'{name} must be text')
            if len(value) > 1024:
                raise ValueError(f'{name} must not exceed 1024 characters')
            for placeholder in re.findall(r'\$\{([^}]+)\}', value):
                if placeholder not in _PLACEHOLDERS:
                    raise ValueError(f'unknown placeholder: {placeholder}')


@dataclass(frozen=True)
class OutputProfile:
    name: str = 'SSD1306 VLSB · C Header'
    raster: RasterProfile = field(default_factory=RasterProfile)
    encoding: EncodingProfile = field(default_factory=EncodingProfile)
    text: TextFormatProfile = field(default_factory=TextFormatProfile)

    @classmethod
    def default(cls) -> 'OutputProfile':
        return cls()

    def to_dict(self) -> dict[str, Any]:
        return {
            'name': self.name,
            'raster': asdict(self.raster),
            'encoding': self.encoding.to_dict(),
            'text': asdict(self.text),
        }


def normalize_profile(raw: OutputProfile | dict[str, Any]) -> OutputProfile:
    if isinstance(raw, OutputProfile):
        return raw
    if not isinstance(raw, dict):
        raise ValueError('output profile must be an object')
    name = str(raw.get('name', '')).strip()
    if not name or len(name) > 64:
        raise ValueError('profile name must contain 1 to 64 characters')
    return OutputProfile(
        name=name,
        raster=RasterProfile(**dict(raw.get('raster') or {})),
        encoding=EncodingProfile(**dict(raw.get('encoding') or {})),
        text=TextFormatProfile(**dict(raw.get('text') or {})),
    )


def _text(**changes) -> TextFormatProfile:
    values = asdict(TextFormatProfile())
    values.update(changes)
    return TextFormatProfile(**values)


def builtin_profiles() -> dict[str, OutputProfile]:
    default = OutputProfile.default()
    return {
        'ssd1306_vlsb_c': default,
        'row_msb_c51': OutputProfile(
            name='逐行 MSB · C51',
            encoding=EncodingProfile(bit_axis='horizontal', group_order='row_major', bit_order='msb_first'),
            text=_text(segment_prefix='const unsigned char code ${symbol}[] = {\n'),
        ),
        'raw_hex': OutputProfile(name='Raw Hex', text=_text(minimal_data=True)),
        'raw_decimal': OutputProfile(name='Raw Decimal', text=_text(radix='decimal', data_prefix='', minimal_data=True)),
        'legacy_pixel_c': OutputProfile(
            name='Legacy Pixel C Header',
            text=_text(
                bytes_per_line=12,
                segment_prefix='#define ${symbol}_WIDTH ${width}\n#define ${symbol}_HEIGHT ${height}\n#define ${symbol}_BYTES ${byte_count}\n\nstatic const unsigned char ${symbol}[] = {\n',
                comment_prefix='',
                comment_suffix='',
            ),
        ),
    }


_PROFILE_ID = re.compile(r'^[a-z0-9][a-z0-9_-]{0,63}$')


def validate_profile_id(profile_id: str) -> str:
    value = str(profile_id)
    if not _PROFILE_ID.fullmatch(value):
        raise ValueError('profile id must use lowercase ASCII letters, digits, underscore, or hyphen')
    return value
