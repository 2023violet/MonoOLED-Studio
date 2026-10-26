//! Framebuffer -> Slint image (1 image pixel per OLED pixel; the UI scales it
//! with `image-rendering: pixelated`, so zoom never re-renders pixels).
//!
//! Pixel Studio display colours (V1 output workbench "显示" group) and the
//! per-pixel border outline also live here.

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

/// RGBA colours for a 0/1 pixel buffer (1 = `lit`).
pub fn rgba_pixels(pixels: &[u8], lit: Rgba8Pixel, off: Rgba8Pixel) -> Vec<Rgba8Pixel> {
    pixels
        .iter()
        .map(|value| if *value != 0 { lit } else { off })
        .collect()
}

/// Image of `pixels` with explicit lit / off colours.
pub fn image_with_colors(
    width: usize,
    height: usize,
    pixels: &[u8],
    lit: Rgba8Pixel,
    off: Rgba8Pixel,
) -> Image {
    let colors = rgba_pixels(pixels, lit, off);
    let mut buffer = SharedPixelBuffer::<Rgba8Pixel>::new(width as u32, height as u32);
    let slice = buffer.make_mut_slice();
    let count = slice.len().min(colors.len());
    slice[..count].copy_from_slice(&colors[..count]);
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

/// One straight piece of the pixel-border outline, in cells: from `(x, y)`
/// along x (`vertical == false`) or y for `len` cells.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct BorderRun {
    pub x: usize,
    pub y: usize,
    pub len: usize,
    pub vertical: bool,
}

/// V1 `paintEvent` pixel border (every lit pixel stroked as a 1 px rect) as
/// merged edge runs: a grid edge is drawn when a lit pixel lies on either side.
pub fn border_runs(width: usize, height: usize, pixels: &[u8]) -> Vec<BorderRun> {
    let lit = |x: usize, y: usize| x < width && y < height && pixels[y * width + x] != 0;
    let mut runs = Vec::new();
    let mut scan = |count: usize, along: usize, vertical: bool, edge: &dyn Fn(usize) -> bool| {
        let mut start = None;
        for i in 0..=count {
            match (start, i < count && edge(i)) {
                (None, true) => start = Some(i),
                (Some(s), false) => {
                    let (x, y) = if vertical { (along, s) } else { (s, along) };
                    runs.push(BorderRun {
                        x,
                        y,
                        len: i - s,
                        vertical,
                    });
                    start = None;
                }
                _ => {}
            }
        }
    };
    for y in 0..=height {
        scan(width, y, false, &|x| lit(x, y) || (y > 0 && lit(x, y - 1)));
    }
    for x in 0..=width {
        scan(height, x, true, &|y| lit(x, y) || (x > 0 && lit(x - 1, y)));
    }
    runs
}

/// Visible cell window of the Pixel canvas (UI-reported; the outline is only
/// built for it, like V1 painting only the exposed region).
#[derive(Debug, Clone, Copy, Default, PartialEq, Eq)]
pub struct CellWindow {
    pub x0: usize,
    pub y0: usize,
    pub x1: usize,
    pub y1: usize,
}

/// `runs` clipped to `window` (cells `x0..x1`, `y0..y1`; edges on `x1`/`y1` kept).
pub fn clip_runs(runs: &[BorderRun], window: CellWindow) -> Vec<BorderRun> {
    runs.iter()
        .filter_map(|r| {
            let (fixed, lo, hi, start, end) = if r.vertical {
                (r.x, window.y0, window.y1, r.y, r.y + r.len)
            } else {
                (r.y, window.x0, window.x1, r.x, r.x + r.len)
            };
            let (fixed_lo, fixed_hi) = if r.vertical {
                (window.x0, window.x1)
            } else {
                (window.y0, window.y1)
            };
            if fixed < fixed_lo || fixed > fixed_hi {
                return None;
            }
            let (start, end) = (start.max(lo), end.min(hi));
            (start < end).then(|| {
                let (x, y) = if r.vertical {
                    (r.x, start)
                } else {
                    (start, r.y)
                };
                BorderRun {
                    x,
                    y,
                    len: end - start,
                    vertical: r.vertical,
                }
            })
        })
        .collect()
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
    fn border_runs_merge_edges_next_to_lit_pixels() {
        // 3x2 document, lit pixels at (1,0) and (2,1).
        let pixels = [0, 1, 0, 0, 0, 1];
        let runs = border_runs(3, 2, &pixels);
        let h = |x, y, len| BorderRun {
            x,
            y,
            len,
            vertical: false,
        };
        let v = |x, y, len| BorderRun {
            x,
            y,
            len,
            vertical: true,
        };
        assert_eq!(
            runs,
            vec![
                h(1, 0, 1), // top of (1,0)
                h(1, 1, 2), // bottom of (1,0) + top of (2,1), merged
                h(2, 2, 1), // bottom of (2,1)
                v(1, 0, 1),
                v(2, 0, 2), // right of (1,0) + left of (2,1), merged
                v(3, 1, 1),
            ]
        );
        // A fully lit canvas is one run per grid line; a dark one has none.
        assert_eq!(border_runs(4, 3, &[1; 12]).len(), 4 + 5);
        assert!(border_runs(4, 3, &[0; 12]).is_empty());
        let window = CellWindow {
            x0: 2,
            y0: 1,
            x1: 3,
            y1: 2,
        };
        assert_eq!(
            clip_runs(&runs, window),
            vec![h(2, 1, 1), h(2, 2, 1), v(2, 1, 1), v(3, 1, 1)]
        );
    }
}
