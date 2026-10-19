//! Logical monochrome framebuffer with SSD13xx VLSB export (V1 `framebuffer.py`).

use crate::bitmap::MonoBitmap;
use crate::error::{CoreError, CoreResult};

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct FrameBuffer {
    width: usize,
    height: usize,
    pixels: Vec<u8>,
}

impl FrameBuffer {
    pub fn new(width: usize, height: usize) -> CoreResult<Self> {
        if width == 0 || height == 0 {
            return Err(CoreError::invalid(
                "framebuffer dimensions must be positive",
            ));
        }
        Ok(Self {
            width,
            height,
            pixels: vec![0; width * height],
        })
    }

    pub fn width(&self) -> usize {
        self.width
    }

    pub fn height(&self) -> usize {
        self.height
    }

    fn check(&self, x: i64, y: i64) -> CoreResult<usize> {
        if x < 0 || y < 0 || x as usize >= self.width || y as usize >= self.height {
            return Err(CoreError::new(
                "E-CORE-RANGE",
                format!("pixel ({x},{y}) outside {}x{}", self.width, self.height),
            ));
        }
        Ok(y as usize * self.width + x as usize)
    }

    pub fn set_pixel(&mut self, x: i64, y: i64, on: bool) -> CoreResult<()> {
        let index = self.check(x, y)?;
        self.pixels[index] = u8::from(on);
        Ok(())
    }

    pub fn get_pixel(&self, x: i64, y: i64) -> CoreResult<u8> {
        Ok(self.pixels[self.check(x, y)?])
    }

    /// OR a mask at an origin that may be negative; pixels outside are clipped.
    pub fn or_mask<R: AsRef<[u8]>>(&mut self, mask: &[R], x: i64, y: i64) {
        for (my, row) in mask.iter().enumerate() {
            for (mx, value) in row.as_ref().iter().enumerate() {
                if *value == 0 {
                    continue;
                }
                let tx = x + mx as i64;
                let ty = y + my as i64;
                if tx >= 0 && ty >= 0 && (tx as usize) < self.width && (ty as usize) < self.height {
                    self.pixels[ty as usize * self.width + tx as usize] = 1;
                }
            }
        }
    }

    pub fn rows(&self) -> impl Iterator<Item = &[u8]> {
        self.pixels.chunks(self.width)
    }

    pub fn pixels(&self) -> &[u8] {
        &self.pixels
    }

    pub fn to_bitmap(&self) -> MonoBitmap {
        MonoBitmap::from_raw(self.width, self.height, self.pixels.clone())
    }

    pub fn to_vlsb(&self) -> CoreResult<Vec<u8>> {
        if !self.height.is_multiple_of(8) {
            return Err(CoreError::invalid(
                "VLSB export requires height divisible by 8",
            ));
        }
        let mut out = vec![0u8; self.width * (self.height / 8)];
        for (y, row) in self.rows().enumerate() {
            let base = (y / 8) * self.width;
            let bit = 1u8 << (y % 8);
            for (x, value) in row.iter().enumerate() {
                if *value != 0 {
                    out[base + x] |= bit;
                }
            }
        }
        Ok(out)
    }
}
