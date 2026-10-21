//! Framebuffer -> Slint image (1 image pixel per OLED pixel; the UI scales it
//! with `image-rendering: pixelated`, so zoom never re-renders pixels).
//!
//! Pixel Studio display colours (V1 output workbench "显示" group) and the
//! per-pixel outline overlay also live here.

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
    image_with_colors(width, height, pixels, LIT, OFF)
}

/// Image of `pixels` with explicit lit / off colours.
pub fn image_with_colors(
    width: usize,
    height: usize,
    pixels: &[u8],
    lit: Rgba8Pixel,
    off: Rgba8Pixel,
) -> Image {
    let mut buffer = SharedPixelBuffer::<Rgba8Pixel>::new(width as u32, height as u32);
    for (slot, value) in buffer.make_mut_slice().iter_mut().zip(pixels) {
        *slot = if *value != 0 { lit } else { off };
    }
    Image::from_rgba8(buffer)
}

/// V1 display defaults (`_reset_display`).
pub const DEFAULT_BACKGROUND: &str = "#000000";
pub const DEFAULT_GRID: &str = "#495028";
pub const DEFAULT_FILL: &str = "#FFFFFF";
pub const DEFAULT_BORDER: &str = "#FFFF00";

/// `#RGB`, `#RRGGBB` or `#AARRGGBB` (the hex forms Qt's `QColor` accepts).
pub fn parse_color(text: &str) -> Option<Rgba8Pixel> {
    let hex = text.trim().strip_prefix('#')?;
    if !hex.chars().all(|c| c.is_ascii_hexdigit()) {
        return None;
    }
    let byte = |s: &str| u8::from_str_radix(s, 16).ok();
    let (a, r, g, b) = match hex.len() {
        3 => {
            let d = |i: usize| byte(&hex[i..=i].repeat(2));
            (Some(255), d(0), d(1), d(2))
        }
        6 => (
            Some(255),
            byte(&hex[0..2]),
            byte(&hex[2..4]),
            byte(&hex[4..6]),
        ),
        8 => (
            byte(&hex[0..2]),
            byte(&hex[2..4]),
            byte(&hex[4..6]),
            byte(&hex[6..8]),
        ),
        _ => return None,
    };
    Some(Rgba8Pixel {
        r: r?,
        g: g?,
        b: b?,
        a: a?,
    })
}

pub fn slint_color(pixel: Rgba8Pixel) -> slint::Color {
    slint::Color::from_argb_u8(pixel.a, pixel.r, pixel.g, pixel.b)
}

/// The visible cell window of the Pixel canvas and its zoom (logical px per cell).
#[derive(Debug, Clone, Copy, Default, PartialEq, Eq)]
pub struct Viewport {
    pub x0: usize,
    pub y0: usize,
    pub cols: usize,
    pub rows: usize,
    pub zoom: usize,
}

/// Largest overlay the UI asks for (a 4K viewport at 1x); larger requests are clamped.
const MAX_OVERLAY_PIXELS: usize = 3840 * 2160;

/// V1 `paintEvent` pixel border: a 1 px outline around every lit pixel of the
/// visible window, as an image `(cols * zoom + 1) x (rows * zoom + 1)` placed at
/// cell `(x0, y0)`. None when nothing is visible.
pub fn border_overlay(
    width: usize,
    height: usize,
    pixels: &[u8],
    view: Viewport,
    color: Rgba8Pixel,
) -> Option<Image> {
    let z = view.zoom;
    let x1 = (view.x0 + view.cols).min(width);
    let y1 = (view.y0 + view.rows).min(height);
    if z == 0 || view.x0 >= x1 || view.y0 >= y1 {
        return None;
    }
    let (cols, rows) = (x1 - view.x0, y1 - view.y0);
    let (w, h) = (cols * z + 1, rows * z + 1);
    if w * h > MAX_OVERLAY_PIXELS {
        return None;
    }
    let mut buffer = SharedPixelBuffer::<Rgba8Pixel>::new(w as u32, h as u32);
    let out = buffer.make_mut_slice();
    for cy in 0..rows {
        let row = &pixels[(view.y0 + cy) * width..];
        for cx in 0..cols {
            if row[view.x0 + cx] == 0 {
                continue;
            }
            let (left, top) = (cx * z, cy * z);
            for x in left..=left + z {
                out[top * w + x] = color;
                out[(top + z) * w + x] = color;
            }
            for y in top..=top + z {
                out[y * w + left] = color;
                out[y * w + left + z] = color;
            }
        }
    }
    Some(Image::from_rgba8(buffer))
}

#[cfg(test)]
mod tests {
    #![allow(clippy::unwrap_used)]
    use super::*;

    #[test]
    fn parses_the_hex_forms_qt_accepts() {
        assert_eq!(
            parse_color("#FFFF00").unwrap(),
            Rgba8Pixel {
                r: 255,
                g: 255,
                b: 0,
                a: 255
            }
        );
        assert_eq!(
            parse_color("#0f0").unwrap(),
            Rgba8Pixel {
                r: 0,
                g: 255,
                b: 0,
                a: 255
            }
        );
        assert_eq!(
            parse_color("#80102030").unwrap(),
            Rgba8Pixel {
                r: 16,
                g: 32,
                b: 48,
                a: 128
            }
        );
        for bad in ["", "FFFF00", "#GGGGGG", "#12345", "#ﾌﾌﾌ"] {
            assert!(parse_color(bad).is_none(), "{bad}");
        }
    }

    #[test]
    fn overlay_outlines_each_lit_pixel_in_the_window() {
        // 3x2 document, lit pixels at (1,0) and (2,1); window = whole document at zoom 4.
        let pixels = [0, 1, 0, 0, 0, 1];
        let view = Viewport {
            x0: 0,
            y0: 0,
            cols: 3,
            rows: 2,
            zoom: 4,
        };
        let image = border_overlay(3, 2, &pixels, view, LIT).unwrap();
        let buffer = image.to_rgba8().unwrap();
        assert_eq!((buffer.width(), buffer.height()), (13, 9));
        let at = |x: usize, y: usize| buffer.as_slice()[y * 13 + x].a;
        assert_eq!(at(4, 0), 255); // top-left corner of (1,0)
        assert_eq!(at(8, 4), 255); // shared corner with (2,1)
        assert_eq!(at(6, 2), 0); // inside a lit pixel: not filled
        assert_eq!(at(1, 1), 0); // off pixel
        assert_eq!(at(12, 8), 255); // bottom-right of (2,1)
        // A window that starts at (2,1) only sees that pixel.
        let view = Viewport {
            x0: 2,
            y0: 1,
            cols: 5,
            rows: 5,
            zoom: 2,
        };
        let buffer = border_overlay(3, 2, &pixels, view, LIT)
            .unwrap()
            .to_rgba8()
            .unwrap();
        assert_eq!((buffer.width(), buffer.height()), (3, 3));
        assert!(border_overlay(3, 2, &pixels, Viewport { zoom: 0, ..view }, LIT).is_none());
    }
}
