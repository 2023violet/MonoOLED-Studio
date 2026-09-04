from PIL import Image

from bitmap_raster import rasterize_image
from output_profiles import RasterProfile


def test_rgb_all_and_luma_have_distinct_explicit_semantics():
    image = Image.new('RGBA', (2, 1))
    image.putdata(((255, 0, 0, 255), (255, 255, 255, 255)))

    luma = rasterize_image(image, RasterProfile(threshold_mode='luma', luma_threshold=76))
    rgb = rasterize_image(image, RasterProfile(threshold_mode='rgb_all', red_threshold=255, green_threshold=255, blue_threshold=255))

    assert luma.rows == ((1, 1),)
    assert rgb.rows == ((0, 1),)


def test_transparent_pixels_remain_off_even_when_source_is_inverted():
    image = Image.new('RGBA', (2, 1))
    image.putdata(((255, 255, 255, 0), (0, 0, 0, 255)))

    bitmap = rasterize_image(image, RasterProfile(invert_source=True))

    assert bitmap.rows == ((0, 1),)
