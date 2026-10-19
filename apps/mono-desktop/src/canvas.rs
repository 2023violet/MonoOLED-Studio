//! Framebuffer -> Slint image (1 image pixel per OLED pixel; the UI scales it
//! with `image-rendering: pixelated`, so zoom never re-renders pixels).

use slint::{Image, Rgba8Pixel, SharedPixelBuffer};

pub const LIT: Rgba8Pixel = Rgba8Pixel {
    r: 255,
    g: 255,
    b: 255,
    a: 255,
};
pub const OFF: Rgba8Pixel = Rgba8Pixel {
    r: 0,
    g: 0,
    b: 0,
    a: 255,
};

/// Image of `pixels` (row-major 0/1), lit pixels white on black.
pub fn image_from_pixels(width: usize, height: usize, pixels: &[u8]) -> Image {
    let mut buffer = SharedPixelBuffer::<Rgba8Pixel>::new(width as u32, height as u32);
    for (slot, value) in buffer.make_mut_slice().iter_mut().zip(pixels) {
        *slot = if *value != 0 { LIT } else { OFF };
    }
    Image::from_rgba8(buffer)
}
