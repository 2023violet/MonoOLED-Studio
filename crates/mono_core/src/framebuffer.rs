#[derive(Debug, Clone, PartialEq, Eq)]
pub struct FrameBuffer {
    pub width: usize,
    pub height: usize,
    rows: Vec<Vec<u8>>,
}

impl FrameBuffer {
    pub fn new(width: usize, height: usize) -> Result<Self, String> {
        if width == 0 || height == 0 {
            return Err("framebuffer dimensions must be positive".into());
        }
        Ok(Self {
            width,
            height,
            rows: vec![vec![0; width]; height],
        })
    }

    pub fn from_rows(rows: Vec<Vec<u8>>) -> Result<Self, String> {
        if rows.is_empty() || rows[0].is_empty() {
            return Err("framebuffer rows must not be empty".into());
        }
        let width = rows[0].len();
        if rows.iter().any(|row| row.len() != width) {
            return Err("framebuffer rows must have equal width".into());
        }
        if rows.iter().flatten().any(|value| *value > 1) {
            return Err("framebuffer values must be 0 or 1".into());
        }
        Ok(Self {
            width,
            height: rows.len(),
            rows,
        })
    }

    pub fn set_pixel(&mut self, x: usize, y: usize, on: bool) -> Result<(), String> {
        self.check(x, y)?;
        self.rows[y][x] = u8::from(on);
        Ok(())
    }

    pub fn or_mask(&mut self, mask: &[Vec<u8>], x: usize, y: usize) {
        for (my, row) in mask.iter().enumerate() {
            for (mx, value) in row.iter().enumerate() {
                if *value == 0 {
                    continue;
                }
                let tx = x + mx;
                let ty = y + my;
                if tx < self.width && ty < self.height {
                    self.rows[ty][tx] = 1;
                }
            }
        }
    }

    pub fn rows(&self) -> Vec<Vec<u8>> {
        self.rows.clone()
    }

    pub fn row_strings(&self) -> Vec<String> {
        self.rows
            .iter()
            .map(|row| row.iter().map(|value| char::from(b'0' + *value)).collect())
            .collect()
    }

    pub fn to_vlsb(&self) -> Result<Vec<u8>, String> {
        if !self.height.is_multiple_of(8) {
            return Err("VLSB export requires height divisible by 8".into());
        }
        let mut output = vec![0; self.width * (self.height / 8)];
        for (y, row) in self.rows.iter().enumerate() {
            let page = y / 8;
            let bit = 1u8 << (y % 8);
            let base = page * self.width;
            for (x, value) in row.iter().enumerate() {
                if *value != 0 {
                    output[base + x] |= bit;
                }
            }
        }
        Ok(output)
    }

    fn check(&self, x: usize, y: usize) -> Result<(), String> {
        if x >= self.width || y >= self.height {
            return Err(format!(
                "pixel ({x},{y}) outside {}x{}",
                self.width, self.height
            ));
        }
        Ok(())
    }
}
