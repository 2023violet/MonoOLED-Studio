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

pub fn decode_png(bytes: &[u8]) -> CoreResult<DecodedImage> {
    let mut decoder = png::Decoder::new(Cursor::new(bytes));
    decoder.set_transformations(png::Transformations::EXPAND | png::Transformations::STRIP_16);
    let mut reader = decoder
        .read_info()
        .map_err(|e| image_error(format!("cannot identify image file: {e}")))?;
    let info = reader.info();
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
