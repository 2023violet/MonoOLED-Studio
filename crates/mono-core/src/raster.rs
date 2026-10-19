//! Colour RGBA to strict 0/1 rasterization (V1 `bitmap_raster.py`).
//!
//! Resizing reproduces Pillow's `Image.resize(..., LANCZOS)` for RGBA input:
//! premultiply to RGBa, two-pass separable convolution with 22-bit fixed-point
//! coefficients, then un-premultiply.

use crate::bitmap::MonoBitmap;
use crate::error::{CoreError, CoreResult};
use crate::profiles::{RasterProfile, ThresholdMode};

/// Straight (non-premultiplied) RGBA image, row-major, 4 bytes per pixel.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct RgbaImage {
    pub width: usize,
    pub height: usize,
    pub data: Vec<u8>,
}

impl RgbaImage {
    pub fn new(width: usize, height: usize, data: Vec<u8>) -> CoreResult<Self> {
        if data.len() != width * height * 4 {
            return Err(CoreError::invalid(
                "RGBA buffer size does not match dimensions",
            ));
        }
        Ok(Self {
            width,
            height,
            data,
        })
    }
}

const PRECISION_BITS: u32 = 32 - 8 - 2;

fn sinc(x: f64) -> f64 {
    if x == 0.0 {
        return 1.0;
    }
    let x = x * std::f64::consts::PI;
    x.sin() / x
}

fn lanczos(x: f64) -> f64 {
    if (-3.0..3.0).contains(&x) {
        sinc(x) * sinc(x / 3.0)
    } else {
        0.0
    }
}

struct Coefficients {
    ksize: usize,
    bounds: Vec<(usize, usize)>,
    weights: Vec<i32>,
}

/// Pillow `precompute_coeffs` + `normalize_coeffs_8bpc`.
fn coefficients(in_size: usize, out_size: usize) -> Coefficients {
    let scale = in_size as f64 / out_size as f64;
    let filterscale = scale.max(1.0);
    let support = 3.0 * filterscale;
    let ksize = support.ceil() as usize * 2 + 1;
    let mut bounds = Vec::with_capacity(out_size);
    let mut weights = vec![0i32; out_size * ksize];
    for xx in 0..out_size {
        let center = (xx as f64 + 0.5) * scale;
        let ss = 1.0 / filterscale;
        let xmin = ((center - support + 0.5) as i64).max(0) as usize;
        let xmax = ((center + support + 0.5) as i64).min(in_size as i64) as usize - xmin;
        let mut k = vec![0f64; ksize];
        let mut ww = 0.0;
        for (x, slot) in k.iter_mut().enumerate().take(xmax) {
            let w = lanczos((x as f64 + xmin as f64 - center + 0.5) * ss);
            *slot = w;
            ww += w;
        }
        for (x, w) in k.iter().enumerate() {
            let value = if x < xmax && ww != 0.0 { w / ww } else { *w };
            let fixed = value * f64::from(1u32 << PRECISION_BITS);
            weights[xx * ksize + x] = if value < 0.0 {
                (-0.5 + fixed) as i32
            } else {
                (0.5 + fixed) as i32
            };
        }
        bounds.push((xmin, xmax));
    }
    Coefficients {
        ksize,
        bounds,
        weights,
    }
}

fn clip8(value: i64) -> u8 {
    (value >> PRECISION_BITS).clamp(0, 255) as u8
}

fn resample_horizontal(
    src: &[u8],
    width: usize,
    rows: std::ops::Range<usize>,
    out_width: usize,
    c: &Coefficients,
) -> Vec<u8> {
    let mut out = Vec::with_capacity(rows.len() * out_width * 4);
    for y in rows {
        let row = &src[y * width * 4..(y + 1) * width * 4];
        for (xx, (xmin, xmax)) in c.bounds.iter().enumerate() {
            let k = &c.weights[xx * c.ksize..xx * c.ksize + xmax];
            for channel in 0..4 {
                let mut ss: i64 = 1 << (PRECISION_BITS - 1);
                for (x, w) in k.iter().enumerate() {
                    ss += i64::from(row[(x + xmin) * 4 + channel]) * i64::from(*w);
                }
                out.push(clip8(ss));
            }
        }
    }
    out
}

fn resample_vertical(src: &[u8], width: usize, c: &Coefficients, first_row: usize) -> Vec<u8> {
    let mut out = Vec::with_capacity(c.bounds.len() * width * 4);
    for (yy, (ymin, ymax)) in c.bounds.iter().enumerate() {
        let k = &c.weights[yy * c.ksize..yy * c.ksize + ymax];
        let ymin = ymin - first_row;
        for xx in 0..width {
            for channel in 0..4 {
                let mut ss: i64 = 1 << (PRECISION_BITS - 1);
                for (y, w) in k.iter().enumerate() {
                    ss += i64::from(src[((y + ymin) * width + xx) * 4 + channel]) * i64::from(*w);
                }
                out.push(clip8(ss));
            }
        }
    }
    out
}

fn muldiv255(a: u8, b: u8) -> u8 {
    let tmp = u32::from(a) * u32::from(b) + 128;
    (((tmp >> 8) + tmp) >> 8) as u8
}

fn premultiply(data: &[u8]) -> Vec<u8> {
    data.chunks(4)
        .flat_map(|p| {
            [
                muldiv255(p[0], p[3]),
                muldiv255(p[1], p[3]),
                muldiv255(p[2], p[3]),
                p[3],
            ]
        })
        .collect()
}

fn unpremultiply(data: &[u8]) -> Vec<u8> {
    data.chunks(4)
        .flat_map(|p| {
            let alpha = p[3];
            if alpha == 0 || alpha == 255 {
                [p[0], p[1], p[2], alpha]
            } else {
                let f = |v: u8| ((255 * u32::from(v)) / u32::from(alpha)).min(255) as u8;
                [f(p[0]), f(p[1]), f(p[2]), alpha]
            }
        })
        .collect()
}

/// Pillow `Image.resize((w, h), LANCZOS)` for an RGBA image.
pub fn resize_lanczos(image: &RgbaImage, width: usize, height: usize) -> RgbaImage {
    if image.width == width && image.height == height {
        return image.clone();
    }
    let mut data = premultiply(&image.data);
    let horizontal = coefficients(image.width, width);
    let vertical = coefficients(image.height, height);
    let need_horizontal = width != image.width;
    let need_vertical = height != image.height;
    let mut current_width = image.width;
    let mut first_row = 0;
    if need_horizontal {
        let first = vertical.bounds.first().map_or(0, |b| b.0);
        let last = vertical.bounds.last().map_or(image.height, |b| b.0 + b.1);
        let rows = if need_vertical {
            first..last
        } else {
            0..image.height
        };
        first_row = rows.start;
        data = resample_horizontal(&data, image.width, rows, width, &horizontal);
        current_width = width;
    }
    if need_vertical {
        data = resample_vertical(&data, current_width, &vertical, first_row);
    }
    RgbaImage {
        width,
        height,
        data: unpremultiply(&data),
    }
}

/// V1 `rasterize_image`: transparent pixels are off; luma or all-channel thresholds.
pub fn rasterize(
    image: &RgbaImage,
    profile: &RasterProfile,
    output_size: Option<(usize, usize)>,
) -> CoreResult<MonoBitmap> {
    profile.validate()?;
    let mut source = image.clone();
    if let Some((width, height)) = output_size {
        if width == 0 || height == 0 {
            return Err(CoreError::invalid("output_size must be positive"));
        }
        let scale = usize::from(profile.antialias_scale);
        source = resize_lanczos(&source, width * scale, height * scale);
        if scale > 1 {
            source = resize_lanczos(&source, width, height);
        }
    }
    if source.width == 0 || source.height == 0 {
        return Err(CoreError::invalid("image must not be empty"));
    }
    let rows = source.data.chunks(source.width * 4).map(|row| {
        row.chunks(4)
            .map(|p| {
                if p[3] == 0 {
                    return 0;
                }
                let lit = match profile.threshold_mode {
                    ThresholdMode::RgbAll => {
                        p[0] >= profile.red_threshold
                            && p[1] >= profile.green_threshold
                            && p[2] >= profile.blue_threshold
                    }
                    ThresholdMode::Luma => {
                        let luma = (299 * u32::from(p[0])
                            + 587 * u32::from(p[1])
                            + 114 * u32::from(p[2])
                            + 500)
                            / 1000;
                        luma >= u32::from(profile.luma_threshold)
                    }
                };
                u8::from(lit != profile.invert_source)
            })
            .collect::<Vec<u8>>()
    });
    MonoBitmap::from_rows(rows)
}
