//! TrueType glyph generation for Font Packs (V1 `font_pack.rasterize_characters`).
//!
//! The built-in 5x7 path is exact. The TrueType path follows V1's algorithm
//! (batch size fitting, shared baseline, optional supersampling with LANCZOS,
//! threshold) on top of `ab_glyph`; the result is *semantically* equivalent to
//! V1's FreeType output (decision D6), not byte-identical.

use ab_glyph::{Font, FontArc, PxScale, ScaleFont, point};
use mono_core::font::{
    FontPack, GlyphMetrics, builtin_glyph_rows, has_builtin_glyph, supports_builtin_5x7,
};
use mono_core::profiles::Alignment;
use mono_core::raster::{RgbaImage, resize_lanczos};
use mono_core::{CoreError, CoreResult};

#[derive(Debug, Clone)]
pub struct GenerateOptions {
    pub font_size: i64,
    pub threshold: i64,
    pub offset: (i64, i64),
    pub alignment: Alignment,
    pub antialias_scale: i64,
}

impl Default for GenerateOptions {
    fn default() -> Self {
        Self {
            font_size: 12,
            threshold: 128,
            offset: (0, 0),
            alignment: Alignment::GlyphWidth,
            antialias_scale: 1,
        }
    }
}

pub fn load_font(bytes: Vec<u8>) -> CoreResult<FontArc> {
    FontArc::try_from_vec(bytes)
        .map_err(|e| CoreError::new("E-FONT-FILE", format!("cannot open font: {e}")))
}

/// FreeType `set_pixel_sizes(size)` equivalent: the em square is `size` pixels.
fn scale_for(font: &FontArc, size: f32) -> PxScale {
    let units = font.units_per_em().unwrap_or(1000.0);
    let factor = font.height_unscaled() / units;
    PxScale::from(size * factor)
}

/// Ink box relative to the left-baseline anchor, like Pillow `getbbox(anchor='ls')`.
fn ink_box(font: &FontArc, scale: PxScale, ch: char) -> (i64, i64, i64, i64) {
    let glyph = font
        .glyph_id(ch)
        .with_scale_and_position(scale, point(0.0, 0.0));
    let advance = font.as_scaled(scale).h_advance(font.glyph_id(ch));
    match font.outline_glyph(glyph) {
        Some(outlined) => {
            let b = outlined.px_bounds();
            (
                b.min.x.floor() as i64,
                b.min.y.floor() as i64,
                b.max.x.ceil() as i64,
                b.max.y.ceil() as i64,
            )
        }
        // Whitespace: Pillow reports the advance with an empty vertical extent at the baseline.
        None => (0, 0, advance.round() as i64, 0),
    }
}

fn fit_sample(chars: &[char]) -> Vec<char> {
    let mut sample: Vec<char> = "MWAgjpQ0/".chars().filter(|c| chars.contains(c)).collect();
    for c in chars {
        if !sample.contains(c) {
            sample.push(*c);
        }
        if sample.len() >= 64 {
            break;
        }
    }
    sample
}

/// V1 `fit_font_size_for_cell`.
pub fn fit_font_size_for_cell(
    font: &FontArc,
    cell: (usize, usize),
    baseline: i64,
    chars: &[char],
    preferred: i64,
) -> i64 {
    let (width, height) = (cell.0 as i64, cell.1 as i64);
    let sample = fit_sample(chars);
    if sample.is_empty() {
        return preferred.max(4);
    }
    for size in (4..=preferred.max(4)).rev() {
        let scale = scale_for(font, size as f32);
        let fits = sample.iter().all(|ch| {
            let (left, top, right, bottom) = ink_box(font, scale, *ch);
            right - left <= width && baseline + top >= 0 && baseline + bottom <= height
        });
        if fits {
            return size;
        }
    }
    4
}

/// Render `ch` into an L buffer with the pen at (`x`, `baseline_y`).
fn draw_glyph(
    font: &FontArc,
    scale: PxScale,
    ch: char,
    x: i64,
    baseline_y: i64,
    width: usize,
    height: usize,
) -> Vec<u8> {
    let mut pixels = vec![0u8; width * height];
    let glyph = font
        .glyph_id(ch)
        .with_scale_and_position(scale, point(x as f32, baseline_y as f32));
    if let Some(outlined) = font.outline_glyph(glyph) {
        let bounds = outlined.px_bounds();
        outlined.draw(|gx, gy, coverage| {
            let px = bounds.min.x as i64 + i64::from(gx);
            let py = bounds.min.y as i64 + i64::from(gy);
            if px >= 0 && py >= 0 && (px as usize) < width && (py as usize) < height {
                let value = (coverage.clamp(0.0, 1.0) * 255.0).round() as u8;
                let slot = &mut pixels[py as usize * width + px as usize];
                *slot = (*slot).max(value);
            }
        });
    }
    pixels
}

/// V1 `rasterize_characters`. `font` is `None` for the built-in path / default font.
pub fn rasterize_characters(
    pack: &mut FontPack,
    characters: &str,
    font: Option<&FontArc>,
    options: &GenerateOptions,
) -> CoreResult<Vec<char>> {
    if options.font_size <= 0 {
        return Err(CoreError::invalid("font_size must be greater than 0"));
    }
    if !(0..=255).contains(&options.threshold) {
        return Err(CoreError::invalid("threshold must be between 0 and 255"));
    }
    if !matches!(options.antialias_scale, 1 | 2 | 4) {
        return Err(CoreError::invalid("antialias_scale must be 1, 2, or 4"));
    }
    pack.set_metrics(None, None)?;
    let mut chars: Vec<char> = Vec::new();
    for c in characters.chars() {
        if !chars.contains(&c) {
            chars.push(c);
        }
    }
    if chars.is_empty() {
        return Ok(chars);
    }
    let (w, h) = pack.cell;
    let (ox, oy) = options.offset;
    let advance = pack.advance;
    let use_builtin = font.is_none()
        && (ox, oy) == (0, 0)
        && supports_builtin_5x7(pack.cell)
        && chars.iter().all(|c| has_builtin_glyph(*c));
    if use_builtin {
        for ch in &chars {
            let rows = builtin_glyph_rows(*ch, pack.cell, Some(pack.baseline))?;
            pack.set_glyph(
                *ch,
                rows,
                Some(GlyphMetrics {
                    bearing_x: 0,
                    bearing_y: 0,
                    advance,
                }),
            )?;
        }
        return Ok(chars);
    }
    let Some(font) = font else {
        return Err(CoreError::new(
            "E-FONT-FILE",
            "a TrueType font is required for characters outside the built-in OLED font",
        ));
    };
    let fitted = fit_font_size_for_cell(
        font,
        pack.cell,
        i64::from(pack.baseline) + oy,
        &chars,
        options.font_size,
    );
    let s = options.antialias_scale;
    let scale = scale_for(font, (fitted * s) as f32);
    let (mut shared_left, mut shared_right) = (0, 0);
    if options.alignment == Alignment::FontSet {
        let boxes: Vec<_> = chars.iter().map(|c| ink_box(font, scale, *c)).collect();
        shared_left = boxes.iter().map(|b| b.0).min().unwrap_or(0);
        shared_right = boxes.iter().map(|b| b.2).max().unwrap_or(0);
    }
    let (sw, sh) = (w * s as usize, h * s as usize);
    for ch in &chars {
        let (left, _, right, _) = if options.alignment == Alignment::FontSet {
            (shared_left, 0, shared_right, 0)
        } else {
            ink_box(font, scale, *ch)
        };
        let x = (sw as i64 - (right - left)).div_euclid(2) - left + ox * s;
        let y = (i64::from(pack.baseline) + oy) * s;
        let mut gray = draw_glyph(font, scale, *ch, x, y, sw, sh);
        if s > 1 {
            let rgba: Vec<u8> = gray.iter().flat_map(|v| [*v, *v, *v, 255]).collect();
            let resized = resize_lanczos(
                &RgbaImage {
                    width: sw,
                    height: sh,
                    data: rgba,
                },
                w,
                h,
            );
            gray = resized.data.chunks(4).map(|p| p[0]).collect();
        }
        let rows = gray
            .chunks(w)
            .map(|row| {
                row.iter()
                    .map(|v| u8::from(i64::from(*v) >= options.threshold))
                    .collect()
            })
            .collect();
        pack.set_glyph(
            *ch,
            rows,
            Some(GlyphMetrics {
                bearing_x: 0,
                bearing_y: 0,
                advance,
            }),
        )?;
    }
    Ok(chars)
}

/// V1 `font_generator.generate_glyphs` cell rendering: each character's ink box
/// centred in a `cell` (Pillow `textbbox` centring), thresholded to 0/1.
/// Without a font the built-in 5x7 glyphs are used (V1 falls back to Pillow's
/// default bitmap font, so this path is semantic only, D6).
pub fn render_centered_cells(
    characters: &str,
    font: Option<&FontArc>,
    font_size: i64,
    cell: (usize, usize),
    threshold: i64,
) -> CoreResult<Vec<(char, Vec<Vec<u8>>)>> {
    let mut chars: Vec<char> = Vec::new();
    for ch in characters.chars() {
        if !chars.contains(&ch) {
            chars.push(ch);
        }
    }
    if chars.is_empty() {
        return Err(CoreError::invalid("characters must not be empty"));
    }
    if font_size <= 0 {
        return Err(CoreError::invalid("font_size must be greater than 0"));
    }
    if !(0..=255).contains(&threshold) {
        return Err(CoreError::invalid("threshold must be between 0 and 255"));
    }
    let (w, h) = cell;
    if w == 0 || h == 0 || h % 8 != 0 {
        return Err(CoreError::invalid(
            "cell must be positive and height a multiple of 8",
        ));
    }
    let mut out = Vec::with_capacity(chars.len());
    for ch in chars {
        let rows = match font {
            Some(font) => {
                let scale = scale_for(font, font_size as f32);
                let (left, top, right, bottom) = ink_box(font, scale, ch);
                let x = (w as i64 - (right - left)).div_euclid(2) - left;
                let y = (h as i64 - (bottom - top)).div_euclid(2) - top;
                draw_glyph(font, scale, ch, x, y, w, h)
                    .chunks(w)
                    .map(|row| {
                        row.iter()
                            .map(|v| u8::from(i64::from(*v) >= threshold))
                            .collect()
                    })
                    .collect()
            }
            None => centered_builtin(ch, cell),
        };
        out.push((ch, rows));
    }
    Ok(out)
}

fn centered_builtin(ch: char, (w, h): (usize, usize)) -> Vec<Vec<u8>> {
    let mut rows = vec![vec![0u8; w]; h];
    let Ok(glyph) = builtin_glyph_rows(ch, (5, 7), Some(6)) else {
        return rows;
    };
    let ink: Vec<(usize, usize)> = glyph
        .iter()
        .enumerate()
        .flat_map(|(y, row)| {
            row.iter()
                .enumerate()
                .filter(|(_, v)| **v != 0)
                .map(move |(x, _)| (x, y))
        })
        .collect();
    let (Some(x0), Some(x1)) = (ink.iter().map(|p| p.0).min(), ink.iter().map(|p| p.0).max())
    else {
        return rows;
    };
    let (y0, y1) = (
        ink.iter().map(|p| p.1).min().unwrap_or(0),
        ink.iter().map(|p| p.1).max().unwrap_or(0),
    );
    let dx = (w as i64 - (x1 - x0 + 1) as i64).div_euclid(2) - x0 as i64;
    let dy = (h as i64 - (y1 - y0 + 1) as i64).div_euclid(2) - y0 as i64;
    for (x, y) in ink {
        let (nx, ny) = (x as i64 + dx, y as i64 + dy);
        if nx >= 0 && ny >= 0 && (nx as usize) < w && (ny as usize) < h {
            rows[ny as usize][nx as usize] = 1;
        }
    }
    rows
}

#[cfg(test)]
mod centered_tests {
    #![allow(clippy::unwrap_used)]
    use super::*;

    #[test]
    fn builtin_cells_are_centred_and_deduplicated() {
        let cells = render_centered_cells("AA1", None, 12, (12, 16), 128).unwrap();
        assert_eq!(cells.len(), 2);
        let rows = &cells[0].1;
        assert_eq!((rows.len(), rows[0].len()), (16, 12));
        let cols: Vec<usize> = (0..12)
            .filter(|x| rows.iter().any(|r| r[*x] == 1))
            .collect();
        assert_eq!((cols[0], *cols.last().unwrap()), (3, 7));
    }

    #[test]
    fn invalid_cells_are_rejected() {
        assert!(render_centered_cells("A", None, 12, (12, 12), 128).is_err());
        assert!(render_centered_cells("", None, 12, (12, 16), 128).is_err());
        assert!(render_centered_cells("A", None, 12, (12, 16), 256).is_err());
    }
}
