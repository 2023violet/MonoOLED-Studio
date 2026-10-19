//! Bitmap asset classification and mode-font parsing (V1 `assets.py`).
//!
//! Decoding image files is the caller's job (`mono-project`); this module
//! applies V1's strict 0/1 rules to already-decoded RGBA pixels.

use std::collections::BTreeMap;

use crate::error::{CoreError, CoreResult};

pub const ASSET_FORMAT_ERROR: &str = "E-ASSET-FORMAT";

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct BitmapAsset {
    /// Absolute POSIX-style path, as V1 reports it.
    pub path: String,
    pub width: usize,
    pub height: usize,
    pub rows: Vec<Vec<u8>>,
    pub sha256: String,
    pub source_mode: String,
    pub source_polarity: String,
    pub inverted: bool,
}

fn format_error(message: String) -> CoreError {
    CoreError::new(ASSET_FORMAT_ERROR, message)
}

fn px(rgba: &[u8], width: usize, x: usize, y: usize) -> (u8, u8, u8, u8) {
    let i = (y * width + x) * 4;
    (rgba[i], rgba[i + 1], rgba[i + 2], rgba[i + 3])
}

/// V1 `_detect_source_polarity`: `(polarity, inverted)`.
fn detect_polarity(
    path: &str,
    rgba: &[u8],
    width: usize,
    height: usize,
) -> CoreResult<(&'static str, bool)> {
    let mut any_transparent = false;
    for y in 0..height {
        for x in 0..width {
            let (r, g, b, a) = px(rgba, width, x, y);
            if a != 0 && a != 255 {
                return Err(format_error(format!(
                    "{path}: partial alpha {a} at ({x}, {y})"
                )));
            }
            if a != 0 && !((r, g, b) == (0, 0, 0) || (r, g, b) == (255, 255, 255)) {
                return Err(format_error(format!(
                    "{path}: non-binary RGB ({r}, {g}, {b}) at ({x}, {y})"
                )));
            }
            any_transparent |= a == 0;
        }
    }
    if any_transparent {
        return Ok(("transparent", false));
    }
    let mut border = Vec::new();
    if width > 0 && height > 0 {
        for x in 0..width {
            border.push(px(rgba, width, x, 0));
            if height > 1 {
                border.push(px(rgba, width, x, height - 1));
            }
        }
        for y in 1..(height.saturating_sub(1)).max(1) {
            border.push(px(rgba, width, 0, y));
            if width > 1 {
                border.push(px(rgba, width, width - 1, y));
            }
        }
    }
    let white_border = border
        .iter()
        .filter(|p| (p.0, p.1, p.2) == (255, 255, 255))
        .count();
    let black_border = border
        .iter()
        .filter(|p| (p.0, p.1, p.2) == (0, 0, 0))
        .count();
    let black_total = rgba
        .chunks(4)
        .filter(|p| (p[0], p[1], p[2]) == (0, 0, 0))
        .count();
    let white_total = width * height - black_total;
    if black_total > 0
        && (white_border > black_border
            || (white_border == black_border && white_total > black_total))
    {
        return Ok(("black_on_white", true));
    }
    Ok(("white_on_black", false))
}

/// V1 `decode_bitmap_bytes` after pixel decoding: strict binary classification with polarity detection.
pub fn bitmap_from_rgba(
    path: &str,
    width: usize,
    height: usize,
    rgba: &[u8],
    sha256: String,
    source_mode: &str,
) -> CoreResult<BitmapAsset> {
    let (polarity, inverted) = detect_polarity(path, rgba, width, height)?;
    let mut rows = Vec::with_capacity(height);
    for y in 0..height {
        let mut row = Vec::with_capacity(width);
        for x in 0..width {
            let (r, g, b, a) = px(rgba, width, x, y);
            let value = if a == 0 || (r, g, b) == (0, 0, 0) {
                0
            } else {
                1
            };
            row.push(if inverted { 1 - value } else { value });
        }
        rows.push(row);
    }
    Ok(BitmapAsset {
        path: path.to_string(),
        width,
        height,
        rows,
        sha256,
        source_mode: source_mode.to_string(),
        source_polarity: polarity.to_string(),
        inverted,
    })
}

/// 5x7 mode font: letter -> 7 rows of 5 pixels.
pub type ModeFont = BTreeMap<char, Vec<Vec<u8>>>;

/// V1 `load_mode_font`: rows like `{0x7E, 0x09, ...}, /* A */`, column-major, bit0 = top.
pub fn parse_mode_font(path: &str, text: &str) -> CoreResult<ModeFont> {
    let mut glyphs = ModeFont::new();
    let bytes = text.as_bytes();
    let mut i = 0;
    while i < bytes.len() {
        if bytes[i] != b'{' {
            i += 1;
            continue;
        }
        let Some(close) = text[i + 1..].find(['{', '}']).map(|o| i + 1 + o) else {
            break;
        };
        if bytes[close] == b'{' {
            i = close;
            continue;
        }
        let body = &text[i + 1..close];
        let rest = &text[close + 1..];
        if let Some(letter) = trailing_comment_letter(rest) {
            let cols: Vec<u32> = number_tokens(body).into_iter().map(|v| v & 0xFF).collect();
            if !body.is_empty() && cols.len() == 5 {
                let glyph = (0..7)
                    .map(|y| (0..5).map(|x| ((cols[x] >> y) & 1) as u8).collect())
                    .collect();
                glyphs.insert(letter, glyph);
            }
        }
        i = close + 1;
    }
    let missing: String = ('A'..='Z').filter(|c| !glyphs.contains_key(c)).collect();
    if !missing.is_empty() || glyphs.keys().any(|c| !c.is_ascii_uppercase()) {
        let missing = if missing.is_empty() {
            "unknown".to_string()
        } else {
            missing
        };
        return Err(format_error(format!(
            "{path}: expected A-Z 5x7 font; missing={missing}"
        )));
    }
    Ok(glyphs)
}

/// Matches V1 `\s*,?\s*/\*\s*([A-Z])\s*\*/` directly after the closing brace.
fn trailing_comment_letter(rest: &str) -> Option<char> {
    let s = rest.trim_start();
    let s = s.strip_prefix(',').unwrap_or(s).trim_start();
    let s = s.strip_prefix("/*")?.trim_start();
    let mut chars = s.chars();
    let letter = chars.next().filter(char::is_ascii_uppercase)?;
    chars
        .as_str()
        .trim_start()
        .starts_with("*/")
        .then_some(letter)
}

/// V1 `0[xX][0-9A-Fa-f]+|\d+` tokens parsed with `int(token, 0)`.
fn number_tokens(body: &str) -> Vec<u32> {
    let bytes = body.as_bytes();
    let mut out = Vec::new();
    let mut i = 0;
    while i < bytes.len() {
        if bytes[i] == b'0'
            && i + 2 < bytes.len() + 1
            && matches!(bytes.get(i + 1), Some(b'x' | b'X'))
            && bytes.get(i + 2).is_some_and(u8::is_ascii_hexdigit)
        {
            let start = i + 2;
            let mut end = start;
            while end < bytes.len() && bytes[end].is_ascii_hexdigit() {
                end += 1;
            }
            out.push(u32::from_str_radix(&body[start..end], 16).unwrap_or(u32::MAX));
            i = end;
        } else if bytes[i].is_ascii_digit() {
            let mut end = i;
            while end < bytes.len() && bytes[end].is_ascii_digit() {
                end += 1;
            }
            out.push(body[i..end].parse().unwrap_or(u32::MAX));
            i = end;
        } else {
            i += 1;
        }
    }
    out
}
