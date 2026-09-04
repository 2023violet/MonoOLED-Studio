from font_pack import create_font_pack, rasterize_characters
from pathlib import Path
import pytest


def _font_path():
    for candidate in (Path('C:/Windows/Fonts/arial.ttf'), Path('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf')):
        if candidate.is_file():
            return candidate
    pytest.skip('no deterministic TrueType test font available')


def _lit_bounds(rows):
    points = [(x, y) for y, row in enumerate(rows) for x, value in enumerate(row) if value]
    return min(x for x, _ in points), max(x for x, _ in points)


def test_glyph_width_alignment_centers_each_glyph_while_font_set_uses_shared_box(tmp_path):
    individual = create_font_pack(tmp_path / 'individual', 'Individual', cell=(20, 24), baseline=18, advance=20)
    shared = create_font_pack(tmp_path / 'shared', 'Shared', cell=(20, 24), baseline=18, advance=20)
    font_path = _font_path()

    rasterize_characters(individual, 'IW', font_path=font_path, font_size=18, alignment='glyph_width')
    rasterize_characters(shared, 'IW', font_path=font_path, font_size=18, alignment='font_set')

    i_individual = _lit_bounds(individual.glyph('I').pixels)
    i_shared = _lit_bounds(shared.glyph('I').pixels)
    assert abs((i_individual[0] + i_individual[1]) - 19) <= 1
    assert i_shared != i_individual


def test_antialias_supersampling_still_produces_strict_binary_rows(tmp_path):
    pack = create_font_pack(tmp_path / 'font', 'AA', cell=(20, 24), baseline=18, advance=20)

    font_path = _font_path()
    rasterize_characters(pack, 'A', font_path=font_path, font_size=18, antialias_scale=4, threshold=128)

    assert {value for row in pack.glyph('A').pixels for value in row} <= {0, 1}
