use crate::error::{CoreError, CoreResult};

/// Strict 0/1 monochrome bitmap stored row-major, one byte per pixel.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct MonoBitmap {
    width: usize,
    height: usize,
    pixels: Vec<u8>,
}

impl MonoBitmap {
    pub fn new(width: usize, height: usize) -> CoreResult<Self> {
        if width == 0 || height == 0 {
            return Err(CoreError::invalid("monochrome bitmap must not be empty"));
        }
        Ok(Self {
            width,
            height,
            pixels: vec![0; width * height],
        })
    }

    /// Build from rows, rejecting empty, ragged or non-binary input (V1 `MonoBitmap.from_rows`).
    pub fn from_rows<R, I>(rows: R) -> CoreResult<Self>
    where
        R: IntoIterator<Item = I>,
        I: IntoIterator<Item = u8>,
    {
        let rows: Vec<Vec<u8>> = rows
            .into_iter()
            .map(|row| row.into_iter().collect())
            .collect();
        let Some(first) = rows.first() else {
            return Err(CoreError::invalid("monochrome bitmap must not be empty"));
        };
        let width = first.len();
        if width == 0 {
            return Err(CoreError::invalid("monochrome bitmap must not be empty"));
        }
        if rows.iter().any(|row| row.len() != width) {
            return Err(CoreError::invalid(
                "monochrome bitmap rows must have equal width",
            ));
        }
        if rows.iter().flatten().any(|value| *value > 1) {
            return Err(CoreError::invalid(
                "monochrome bitmap values must be 0 or 1",
            ));
        }
        let height = rows.len();
        Ok(Self {
            width,
            height,
            pixels: rows.into_iter().flatten().collect(),
        })
    }

    /// Callers inside the crate guarantee non-zero size, `pixels.len() == w*h` and 0/1 values.
    pub(crate) fn from_raw(width: usize, height: usize, pixels: Vec<u8>) -> Self {
        Self {
            width,
            height,
            pixels,
        }
    }

    pub fn width(&self) -> usize {
        self.width
    }

    pub fn height(&self) -> usize {
        self.height
    }

    pub fn get(&self, x: usize, y: usize) -> u8 {
        self.pixels[y * self.width + x]
    }

    pub fn set(&mut self, x: usize, y: usize, value: bool) {
        self.pixels[y * self.width + x] = u8::from(value);
    }

    pub fn row(&self, y: usize) -> &[u8] {
        &self.pixels[y * self.width..(y + 1) * self.width]
    }

    pub fn rows(&self) -> impl Iterator<Item = &[u8]> {
        self.pixels.chunks(self.width)
    }

    pub fn pixels(&self) -> &[u8] {
        &self.pixels
    }
}
