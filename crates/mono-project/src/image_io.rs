//! PNG decode/encode with Pillow-compatible RGBA conversion.

use std::io::Cursor;

use mono_core::{CoreError, CoreResult};

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct DecodedImage {
    pub width: usize,
    pub height: usize,
    /// Straight RGBA, as Pillow's `Image.convert("RGBA")` produces.
    pub rgba: Vec<u8>,
    /// Pillow mode name of the source (`1`, `L`, `LA`, `P`, `RGB`, `RGBA`, `I;16`).
    pub mode: String,
}

fn image_error(message: impl Into<String>) -> CoreError {
    CoreError::new("E-IMAGE", message)
}

/// Pillow's decompression-bomb warning threshold; larger images are refused before
/// any pixel buffer is allocated.
pub const MAX_IMAGE_PIXELS: u64 = 89_478_485;

fn check_size(width: u64, height: u64) -> CoreResult<()> {
    if width == 0 || height == 0 {
        return Err(image_error("image must not be empty"));
    }
    if width.saturating_mul(height) > MAX_IMAGE_PIXELS {
        return Err(image_error(format!(
            "Image size ({} pixels) exceeds limit of {MAX_IMAGE_PIXELS} pixels, could be decompression bomb DOS attack.",
            width.saturating_mul(height)
        )));
    }
    Ok(())
}

fn le_u16(b: &[u8], at: usize) -> Option<u32> {
    b.get(at..at + 2)
        .map(|s| u32::from(u16::from_le_bytes([s[0], s[1]])))
}

fn le_u32(b: &[u8], at: usize) -> Option<u32> {
    b.get(at..at + 4)
        .map(|s| u32::from_le_bytes([s[0], s[1], s[2], s[3]]))
}

/// Uncompressed Windows BMP (1/4/8-bit palette, 24/32-bit), as Pillow reads it.
pub fn decode_bmp(bytes: &[u8]) -> CoreResult<DecodedImage> {
    let bad = || image_error("cannot identify image file: unsupported BMP");
    let offset = le_u32(bytes, 10).ok_or_else(bad)? as usize;
    let header = le_u32(bytes, 14).ok_or_else(bad)? as usize;
    let width = le_u32(bytes, 18).ok_or_else(bad)? as i32;
    let raw_height = le_u32(bytes, 22).ok_or_else(bad)? as i32;
    let bpp = le_u16(bytes, 28).ok_or_else(bad)?;
    let compression = le_u32(bytes, 30).ok_or_else(bad)?;
    if width <= 0 || raw_height == 0 || !(compression == 0 || (compression == 3 && bpp == 32)) {
        return Err(bad());
    }
    check_size(
        u64::from(width.unsigned_abs()),
        u64::from(raw_height.unsigned_abs()),
    )?;
    let (width, height, top_down) = (
        width as usize,
        raw_height.unsigned_abs() as usize,
        raw_height < 0,
    );
    if !matches!(bpp, 1 | 4 | 8 | 24 | 32) {
        return Err(bad());
    }
    let colors = match le_u32(bytes, 46).unwrap_or(0) {
        0 if bpp <= 8 => 1usize << bpp,
        n => (n as usize).min(256),
    };
    let palette_at = 14 + header;
    let palette: Vec<[u8; 3]> = (0..if bpp <= 8 { colors } else { 0 })
        .map(|i| {
            bytes
                .get(palette_at + i * 4..palette_at + i * 4 + 3)
                .map(|p| [p[2], p[1], p[0]])
                .unwrap_or([0, 0, 0])
        })
        .collect();
    let stride = (width * bpp as usize).div_ceil(32) * 4;
    if offset
        .checked_add(stride.saturating_mul(height))
        .is_none_or(|end| end > bytes.len())
    {
        return Err(image_error("image file is truncated"));
    }
    let mut rgba = Vec::with_capacity(width * height * 4);
    for y in 0..height {
        let src_row = if top_down { y } else { height - 1 - y };
        let row = bytes
            .get(offset + src_row * stride..offset + (src_row + 1) * stride)
            .ok_or_else(bad)?;
        for x in 0..width {
            let rgb = match bpp {
                1 | 4 | 8 => {
                    let bit = x * bpp as usize;
                    let byte = row[bit / 8];
                    let index = (byte >> (8 - bpp as usize - bit % 8)) & ((1u16 << bpp) - 1) as u8;
                    palette.get(index as usize).copied().unwrap_or([0, 0, 0])
                }
                24 => [row[3 * x + 2], row[3 * x + 1], row[3 * x]],
                32 => [row[4 * x + 2], row[4 * x + 1], row[4 * x]],
                _ => return Err(bad()),
            };
            rgba.extend_from_slice(&[rgb[0], rgb[1], rgb[2], 255]);
        }
    }
    let mode = match bpp {
        1 => "1",
        4 | 8 => "P",
        _ => "RGB",
    };
    Ok(DecodedImage {
        width,
        height,
        rgba,
        mode: mode.into(),
    })
}

/// Decode by content (PNG or BMP), regardless of the file extension, like Pillow.
pub fn decode_image(bytes: &[u8]) -> CoreResult<DecodedImage> {
    if bytes.starts_with(b"BM") {
        return decode_bmp(bytes);
    }
    decode_png(bytes)
}

pub fn decode_png(bytes: &[u8]) -> CoreResult<DecodedImage> {
    let mut decoder = png::Decoder::new(Cursor::new(bytes));
    decoder.set_transformations(png::Transformations::EXPAND | png::Transformations::STRIP_16);
    let mut reader = decoder
        .read_info()
        .map_err(|e| image_error(format!("cannot identify image file: {e}")))?;
    let info = reader.info();
    check_size(u64::from(info.width), u64::from(info.height))?;
    let mode = match (info.color_type, info.bit_depth) {
        (png::ColorType::Grayscale, png::BitDepth::One) => "1",
        (png::ColorType::Grayscale, png::BitDepth::Sixteen) => "I;16",
        (png::ColorType::Grayscale, _) => "L",
        (png::ColorType::GrayscaleAlpha, _) => "LA",
        (png::ColorType::Indexed, _) => "P",
        (png::ColorType::Rgb, _) => "RGB",
        (png::ColorType::Rgba, _) => "RGBA",
    }
    .to_string();
    let mut buffer = vec![
        0;
        reader
            .output_buffer_size()
            .ok_or_else(|| image_error("image too large"))?
    ];
    let frame = reader
        .next_frame(&mut buffer)
        .map_err(|e| image_error(format!("image decode failed: {e}")))?;
    let (width, height) = (frame.width as usize, frame.height as usize);
    let data = &buffer[..frame.buffer_size()];
    let mut rgba = Vec::with_capacity(width * height * 4);
    let row_bytes = frame.line_size;
    for y in 0..height {
        let row = &data[y * row_bytes..(y + 1) * row_bytes];
        for x in 0..width {
            let pixel = match frame.color_type {
                png::ColorType::Grayscale => [row[x], row[x], row[x], 255],
                png::ColorType::GrayscaleAlpha => {
                    [row[2 * x], row[2 * x], row[2 * x], row[2 * x + 1]]
                }
                png::ColorType::Rgb => [row[3 * x], row[3 * x + 1], row[3 * x + 2], 255],
                png::ColorType::Rgba => {
                    [row[4 * x], row[4 * x + 1], row[4 * x + 2], row[4 * x + 3]]
                }
                png::ColorType::Indexed => return Err(image_error("indexed PNG was not expanded")),
            };
            rgba.extend_from_slice(&pixel);
        }
    }
    Ok(DecodedImage {
        width,
        height,
        rgba,
        mode,
    })
}

/// Encode a strict 0/1 bitmap as a 1-bit grayscale PNG (V1 `Image.new('1')` + save).
pub fn encode_bitmap_png(width: usize, height: usize, rows: &[Vec<u8>]) -> CoreResult<Vec<u8>> {
    let mut out = Vec::new();
    {
        let mut encoder = png::Encoder::new(&mut out, width as u32, height as u32);
        encoder.set_color(png::ColorType::Grayscale);
        encoder.set_depth(png::BitDepth::One);
        let mut writer = encoder
            .write_header()
            .map_err(|e| image_error(e.to_string()))?;
        let stride = width.div_ceil(8);
        let mut packed = vec![0u8; stride * height];
        for (y, row) in rows.iter().enumerate() {
            for (x, value) in row.iter().enumerate() {
                if *value != 0 {
                    packed[y * stride + x / 8] |= 0x80 >> (x % 8);
                }
            }
        }
        writer
            .write_image_data(&packed)
            .map_err(|e| image_error(e.to_string()))?;
    }
    Ok(out)
}

/// Encode straight RGBA as an 8-bit RGBA PNG.
pub fn encode_rgba_png(width: usize, height: usize, rgba: &[u8]) -> CoreResult<Vec<u8>> {
    let mut out = Vec::new();
    {
        let mut encoder = png::Encoder::new(&mut out, width as u32, height as u32);
        encoder.set_color(png::ColorType::Rgba);
        encoder.set_depth(png::BitDepth::Eight);
        let mut writer = encoder
            .write_header()
            .map_err(|e| image_error(e.to_string()))?;
        writer
            .write_image_data(rgba)
            .map_err(|e| image_error(e.to_string()))?;
    }
    Ok(out)
}
