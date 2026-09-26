use std::collections::BTreeMap;

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct GlyphMetrics {
    pub bearing_x: i32,
    pub bearing_y: i32,
    pub advance: i32,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Glyph {
    pub rows: Vec<Vec<u8>>,
    pub metrics: GlyphMetrics,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct FontPack {
    pub cell: (usize, usize),
    pub baseline: usize,
    pub advance: i32,
    glyphs: BTreeMap<char, Glyph>,
}

impl FontPack {
    pub fn new(cell: (usize, usize), baseline: usize, advance: i32) -> Result<Self, String> {
        if cell.0 == 0 || cell.1 == 0 {
            return Err("font cell dimensions must be positive".into());
        }
        if baseline >= cell.1 {
            return Err("font baseline must be inside cell height".into());
        }
        if advance <= 0 {
            return Err("font advance must be greater than 0".into());
        }
        Ok(Self {
            cell,
            baseline,
            advance,
            glyphs: BTreeMap::new(),
        })
    }

    pub fn set_glyph(
        &mut self,
        ch: char,
        rows: Vec<Vec<u8>>,
        metrics: GlyphMetrics,
    ) -> Result<(), String> {
        if rows.len() != self.cell.1 || rows.iter().any(|row| row.len() != self.cell.0) {
            return Err("glyph dimensions do not match font cell".into());
        }
        if rows.iter().flatten().any(|value| *value > 1) {
            return Err("glyph values must be 0 or 1".into());
        }
        if metrics.advance <= 0 {
            return Err("glyph advance must be greater than 0".into());
        }
        self.glyphs.insert(ch, Glyph { rows, metrics });
        Ok(())
    }

    pub fn glyph(&self, ch: char) -> Option<&Glyph> {
        self.glyphs.get(&ch)
    }

    pub fn compose_text(&self, text: &str, tracking: i32) -> Result<Vec<Vec<u8>>, String> {
        if text.is_empty() {
            return Ok(vec![vec![]; self.cell.1]);
        }
        let glyphs: Vec<&Glyph> = text
            .chars()
            .map(|ch| self.glyph(ch).ok_or_else(|| format!("missing glyph: {ch}")))
            .collect::<Result<_, _>>()?;
        let mut placements = Vec::with_capacity(glyphs.len());
        let mut cursor = 0i32;
        let mut left = 0i32;
        let mut right = 0i32;
        for (index, glyph) in glyphs.iter().enumerate() {
            let start = cursor + glyph.metrics.bearing_x;
            placements.push((start, *glyph));
            left = left.min(start);
            right = right.max(start + self.cell.0 as i32);
            cursor += glyph.metrics.advance;
            if index + 1 < glyphs.len() {
                cursor += tracking;
            }
        }
        let width = right - left;
        if width <= 0 {
            return Err("composed width must be positive".into());
        }
        let mut output = vec![vec![0; width as usize]; self.cell.1];
        for (start, glyph) in placements {
            let x0 = start - left;
            for (gy, row) in glyph.rows.iter().enumerate() {
                let ty = gy as i32 + glyph.metrics.bearing_y;
                if ty < 0 || ty >= self.cell.1 as i32 {
                    continue;
                }
                for (gx, value) in row.iter().enumerate() {
                    let tx = x0 + gx as i32;
                    if *value != 0 && tx >= 0 && tx < width {
                        output[ty as usize][tx as usize] = 1;
                    }
                }
            }
        }
        Ok(output)
    }
}

pub fn builtin_glyph_rows(
    ch: char,
    cell: (usize, usize),
    baseline: usize,
) -> Result<Vec<Vec<u8>>, String> {
    let pattern = match ch {
        'A' => [
            "01110", "10001", "10001", "11111", "10001", "10001", "10001",
        ],
        '0' => [
            "01110", "10001", "10011", "10101", "11001", "10001", "01110",
        ],
        _ => return Err(format!("unsupported built-in glyph: {ch}")),
    };
    if cell.0 < 5 || cell.1 < 7 || baseline >= cell.1 {
        return Err("built-in OLED 5x7 requires a compatible cell".into());
    }
    let mut rows = vec![vec![0; cell.0]; cell.1];
    let y0 = baseline + 1 - 7;
    let x0 = (cell.0 - 5) / 2;
    for (sy, source) in pattern.iter().enumerate() {
        for (sx, value) in source.bytes().enumerate() {
            if value == b'1' {
                rows[y0 + sy][x0 + sx] = 1;
            }
        }
    }
    Ok(rows)
}
