import sys
from pathlib import Path

SIM = Path(__file__).resolve().parents[1]
ROOT = SIM.parent
sys.path.insert(0, str(SIM))

from assets import load_bitmap, load_mode_font


def test_load_mode_icon_as_strict_binary_bitmap():
    asset = load_bitmap(ROOT / 'Curing_Lite光固化机产品 - UI设计初稿' / 'normal.png')
    assert (asset.width, asset.height) == (24, 12)
    assert asset.source_mode == 'RGBA'
    assert {v for row in asset.pixels for v in row} <= {0, 1}
    assert len(asset.sha256) == 64


def test_load_battery_asset_preserves_native_size():
    asset = load_bitmap(ROOT / '电池图标 - 字宽11字高28' / '11-28电池图标4.png')
    assert (asset.width, asset.height) == (11, 28)
    assert sum(sum(row) for row in asset.pixels) > 0


def test_mode_font_decodes_column_major_bit0_top():
    font = load_mode_font(ROOT / 'Curing_Lite光固化机产品 - UI设计初稿' / 'english_5x7_v2' / 'cl_font_mode_en_5x7_v2.h')
    assert set(font) == set('ABCDEFGHIJKLMNOPQRSTUVWXYZ')
    assert font['A'][0] == [0, 1, 1, 1, 0]
    assert font['A'][1] == [1, 0, 0, 0, 1]
    assert len(font['W']) == 7
    assert len(font['W'][0]) == 5


def test_load_bitmap_auto_inverts_opaque_black_on_white_assets(tmp_path):
    from PIL import Image
    p = tmp_path / 'black_on_white.png'
    image = Image.new('RGBA', (5, 5), (255, 255, 255, 255))
    image.putpixel((2, 2), (0, 0, 0, 255))
    image.save(p)

    asset = load_bitmap(p)

    assert asset.pixels[0][0] == 0
    assert asset.pixels[2][2] == 1
    assert asset.source_polarity == 'black_on_white'
    assert asset.inverted is True


def test_load_bitmap_preserves_opaque_white_on_black_assets(tmp_path):
    from PIL import Image
    p = tmp_path / 'white_on_black.png'
    image = Image.new('RGBA', (5, 5), (0, 0, 0, 255))
    image.putpixel((2, 2), (255, 255, 255, 255))
    image.save(p)

    asset = load_bitmap(p)

    assert asset.pixels[0][0] == 0
    assert asset.pixels[2][2] == 1
    assert asset.source_polarity == 'white_on_black'
    assert asset.inverted is False


def test_load_bitmap_transparent_background_is_always_off(tmp_path):
    from PIL import Image
    p = tmp_path / 'transparent.png'
    image = Image.new('RGBA', (5, 5), (0, 0, 0, 0))
    image.putpixel((2, 2), (255, 255, 255, 255))
    image.save(p)

    asset = load_bitmap(p)

    assert asset.pixels[0][0] == 0
    assert asset.pixels[2][2] == 1
    assert asset.source_polarity == 'transparent'
    assert asset.inverted is False


def test_existing_curing_lite_assets_normalize_white_background_to_off_pixels():
    digit = load_bitmap(ROOT / '数字 - 字宽13字高27' / '13-27数字0.png')
    icon = load_bitmap(ROOT / 'Curing_Lite光固化机产品 - UI设计初稿' / 'normal.png')
    battery = load_bitmap(ROOT / '电池图标 - 字宽11字高28' / '11-28电池图标4.png')

    assert digit.pixels[0][0] == 0
    assert icon.pixels[0][0] == 0
    assert battery.pixels[0][0] == 0
    assert digit.source_polarity == 'black_on_white'
    assert icon.source_polarity == 'black_on_white'
    assert battery.source_polarity == 'black_on_white'
