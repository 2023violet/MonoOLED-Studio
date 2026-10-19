//! Font Pack model and the built-in 5x7 OLED font (V1 `font_pack.py`, `builtin_oled_font.py`).

use indexmap::IndexMap;

use crate::error::{CoreError, CoreResult};

#[derive(Debug, Clone, Copy, PartialEq, Eq, Default)]
pub struct GlyphMetrics {
    pub bearing_x: i32,
    pub bearing_y: i32,
    pub advance: i32,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Glyph {
    pub ch: char,
    pub rows: Vec<Vec<u8>>,
    pub metrics: GlyphMetrics,
}

/// In-memory Font Pack; glyph order is insertion order, as in V1.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct FontPack {
    pub name: String,
    pub cell: (usize, usize),
    pub baseline: i32,
    pub advance: i32,
    glyphs: IndexMap<char, Glyph>,
}

pub fn validate_metrics(
    cell: (i64, i64),
    baseline: i64,
    advance: i64,
) -> CoreResult<((usize, usize), i32, i32)> {
    let (w, h) = cell;
    if w <= 0 || h <= 0 {
        return Err(CoreError::invalid("font cell dimensions must be positive"));
    }
    if !(0 <= baseline && baseline < h) {
        return Err(CoreError::invalid(format!(
            "font baseline must be inside cell height 0..{}",
            h - 1
        )));
    }
    if advance <= 0 {
        return Err(CoreError::invalid("font advance must be greater than 0"));
    }
    Ok(((w as usize, h as usize), baseline as i32, advance as i32))
}

/// V1 `recommended_baseline`.
pub fn recommended_baseline(cell: (usize, usize)) -> i32 {
    if cell.1 > 1 {
        (cell.1 as i32 - 2).max(0)
    } else {
        0
    }
}

/// V1 `recommended_advance`.
pub fn recommended_advance(cell: (usize, usize)) -> i32 {
    cell.0 as i32 + 1
}

impl FontPack {
    pub fn new(
        name: impl Into<String>,
        cell: (i64, i64),
        baseline: i64,
        advance: i64,
    ) -> CoreResult<Self> {
        let (cell, baseline, advance) = validate_metrics(cell, baseline, advance)?;
        Ok(Self {
            name: name.into(),
            cell,
            baseline,
            advance,
            glyphs: IndexMap::new(),
        })
    }

    /// V1 `create_font_pack` defaults.
    pub fn with_recommended(name: impl Into<String>, cell: (usize, usize)) -> CoreResult<Self> {
        Self::new(
            name,
            (cell.0 as i64, cell.1 as i64),
            i64::from(recommended_baseline(cell)),
            i64::from(recommended_advance(cell)),
        )
    }

    /// V1 `set_metrics`; an explicit advance is applied to every existing glyph.
    pub fn set_metrics(&mut self, baseline: Option<i64>, advance: Option<i64>) -> CoreResult<()> {
        let (cell, baseline_v, advance_v) = validate_metrics(
            (self.cell.0 as i64, self.cell.1 as i64),
            baseline.unwrap_or(i64::from(self.baseline)),
            advance.unwrap_or(i64::from(self.advance)),
        )?;
        self.cell = cell;
        self.baseline = baseline_v;
        self.advance = advance_v;
        if advance.is_some() {
            for glyph in self.glyphs.values_mut() {
                glyph.metrics.advance = advance_v;
            }
        }
        Ok(())
    }

    pub fn set_glyph(
        &mut self,
        ch: char,
        rows: Vec<Vec<u8>>,
        metrics: Option<GlyphMetrics>,
    ) -> CoreResult<()> {
        let (w, h) = self.cell;
        let rows: Vec<Vec<u8>> = rows
            .into_iter()
            .map(|row| row.into_iter().map(|v| u8::from(v != 0)).collect())
            .collect();
        if rows.len() != h || rows.iter().any(|row| row.len() != w) {
            return Err(CoreError::invalid(
                "glyph dimensions do not match font cell",
            ));
        }
        let metrics = metrics.unwrap_or(GlyphMetrics {
            bearing_x: 0,
            bearing_y: 0,
            advance: self.advance,
        });
        if metrics.advance <= 0 {
            return Err(CoreError::invalid("glyph advance must be greater than 0"));
        }
        self.glyphs.insert(ch, Glyph { ch, rows, metrics });
        Ok(())
    }

    pub fn glyph(&self, ch: char) -> Option<&Glyph> {
        self.glyphs.get(&ch)
    }

    pub fn characters(&self) -> impl Iterator<Item = char> + '_ {
        self.glyphs.keys().copied()
    }

    pub fn glyphs(&self) -> impl Iterator<Item = &Glyph> {
        self.glyphs.values()
    }

    pub fn len(&self) -> usize {
        self.glyphs.len()
    }

    pub fn is_empty(&self) -> bool {
        self.glyphs.is_empty()
    }

    /// V1 `compose_text`: exact stored glyph pixels laid out with bearings and advances.
    pub fn compose_text(&self, text: &str, tracking: i32) -> CoreResult<Vec<Vec<u8>>> {
        let (cw, ch) = self.cell;
        if text.is_empty() {
            return Ok(vec![Vec::new(); ch]);
        }
        let chars: Vec<char> = text.chars().collect();
        let missing: Vec<char> = chars
            .iter()
            .copied()
            .filter(|c| !self.glyphs.contains_key(c))
            .collect();
        if !missing.is_empty() {
            let list = missing
                .iter()
                .map(|c| format!("'{c}'"))
                .collect::<Vec<_>>()
                .join(", ");
            return Err(CoreError::new(
                "E-FONT-MISSING",
                format!("'missing glyphs: [{list}]'"),
            ));
        }
        let mut starts = Vec::new();
        let (mut cursor, mut right) = (0i64, 0i64);
        for (i, c) in chars.iter().enumerate() {
            let glyph = &self.glyphs[c];
            let start = cursor + i64::from(glyph.metrics.bearing_x);
            starts.push((start, glyph));
            right = right.max(start + cw as i64);
            cursor += i64::from(glyph.metrics.advance)
                + if i + 1 < chars.len() {
                    i64::from(tracking)
                } else {
                    0
                };
        }
        let left = starts.iter().map(|(s, _)| *s).min().unwrap_or(0).min(0);
        let width = (right - left).max(0) as usize;
        let mut rows = vec![vec![0u8; width]; ch];
        for (start, glyph) in starts {
            let x0 = start - left;
            for (gy, row) in glyph.rows.iter().enumerate() {
                let ty = gy as i64 + i64::from(glyph.metrics.bearing_y);
                if ty < 0 || ty >= ch as i64 {
                    continue;
                }
                for (gx, value) in row.iter().enumerate() {
                    let tx = x0 + gx as i64;
                    if *value != 0 && tx >= 0 && (tx as usize) < width {
                        rows[ty as usize][tx as usize] = 1;
                    }
                }
            }
        }
        Ok(rows)
    }
}

pub const DEFAULT_CHARACTERS: &str = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789/";

const BUILTIN_5X7: [(char, [&str; 7]); 37] = [
    (
        'A',
        [
            "01110", "10001", "10001", "11111", "10001", "10001", "10001",
        ],
    ),
    (
        'B',
        [
            "11110", "10001", "10001", "11110", "10001", "10001", "11110",
        ],
    ),
    (
        'C',
        [
            "01110", "10001", "10000", "10000", "10000", "10001", "01110",
        ],
    ),
    (
        'D',
        [
            "11110", "10001", "10001", "10001", "10001", "10001", "11110",
        ],
    ),
    (
        'E',
        [
            "11111", "10000", "10000", "11110", "10000", "10000", "11111",
        ],
    ),
    (
        'F',
        [
            "11111", "10000", "10000", "11110", "10000", "10000", "10000",
        ],
    ),
    (
        'G',
        [
            "01110", "10001", "10000", "10111", "10001", "10001", "01110",
        ],
    ),
    (
        'H',
        [
            "10001", "10001", "10001", "11111", "10001", "10001", "10001",
        ],
    ),
    (
        'I',
        [
            "11111", "00100", "00100", "00100", "00100", "00100", "11111",
        ],
    ),
    (
        'J',
        [
            "00111", "00010", "00010", "00010", "00010", "10010", "01100",
        ],
    ),
    (
        'K',
        [
            "10001", "10010", "10100", "11000", "10100", "10010", "10001",
        ],
    ),
    (
        'L',
        [
            "10000", "10000", "10000", "10000", "10000", "10000", "11111",
        ],
    ),
    (
        'M',
        [
            "10001", "11011", "10101", "10101", "10001", "10001", "10001",
        ],
    ),
    (
        'N',
        [
            "10001", "11001", "10101", "10011", "10001", "10001", "10001",
        ],
    ),
    (
        'O',
        [
            "01110", "10001", "10001", "10001", "10001", "10001", "01110",
        ],
    ),
    (
        'P',
        [
            "11110", "10001", "10001", "11110", "10000", "10000", "10000",
        ],
    ),
    (
        'Q',
        [
            "01110", "10001", "10001", "10001", "10101", "10010", "01101",
        ],
    ),
    (
        'R',
        [
            "11110", "10001", "10001", "11110", "10100", "10010", "10001",
        ],
    ),
    (
        'S',
        [
            "01111", "10000", "10000", "01110", "00001", "00001", "11110",
        ],
    ),
    (
        'T',
        [
            "11111", "00100", "00100", "00100", "00100", "00100", "00100",
        ],
    ),
    (
        'U',
        [
            "10001", "10001", "10001", "10001", "10001", "10001", "01110",
        ],
    ),
    (
        'V',
        [
            "10001", "10001", "10001", "10001", "10001", "01010", "00100",
        ],
    ),
    (
        'W',
        [
            "10001", "10001", "10001", "10101", "10101", "10101", "01010",
        ],
    ),
    (
        'X',
        [
            "10001", "01010", "00100", "00100", "00100", "01010", "10001",
        ],
    ),
    (
        'Y',
        [
            "10001", "01010", "00100", "00100", "00100", "00100", "00100",
        ],
    ),
    (
        'Z',
        [
            "11111", "00001", "00010", "00100", "01000", "10000", "11111",
        ],
    ),
    (
        '0',
        [
            "01110", "10001", "10011", "10101", "11001", "10001", "01110",
        ],
    ),
    (
        '1',
        [
            "00100", "01100", "00100", "00100", "00100", "00100", "01110",
        ],
    ),
    (
        '2',
        [
            "01110", "10001", "00001", "00010", "00100", "01000", "11111",
        ],
    ),
    (
        '3',
        [
            "11110", "00001", "00001", "01110", "00001", "00001", "11110",
        ],
    ),
    (
        '4',
        [
            "00010", "00110", "01010", "10010", "11111", "00010", "00010",
        ],
    ),
    (
        '5',
        [
            "11111", "10000", "10000", "11110", "00001", "00001", "11110",
        ],
    ),
    (
        '6',
        [
            "01110", "10000", "10000", "11110", "10001", "10001", "01110",
        ],
    ),
    (
        '7',
        [
            "11111", "00001", "00010", "00100", "01000", "01000", "01000",
        ],
    ),
    (
        '8',
        [
            "01110", "10001", "10001", "01110", "10001", "10001", "01110",
        ],
    ),
    (
        '9',
        [
            "01110", "10001", "10001", "01111", "00001", "00001", "01110",
        ],
    ),
    (
        '/',
        [
            "00001", "00010", "00100", "01000", "10000", "00000", "00000",
        ],
    ),
];

pub fn has_builtin_glyph(ch: char) -> bool {
    BUILTIN_5X7.iter().any(|(c, _)| *c == ch)
}

pub fn supports_builtin_5x7(cell: (usize, usize)) -> bool {
    cell.0 >= 5 && cell.1 >= 7
}

/// V1 `builtin_glyph_rows`: integer-scaled 5x7 glyph sharing the baseline.
pub fn builtin_glyph_rows(
    ch: char,
    cell: (usize, usize),
    baseline: Option<i32>,
) -> CoreResult<Vec<Vec<u8>>> {
    let pattern = BUILTIN_5X7
        .iter()
        .find(|(c, _)| *c == ch)
        .map(|(_, rows)| rows)
        .ok_or_else(|| CoreError::new("E-FONT-MISSING", format!("'{ch}'")))?;
    let (width, height) = cell;
    if !supports_builtin_5x7(cell) {
        return Err(CoreError::invalid(
            "built-in OLED 5x7 requires a cell of at least 5x7",
        ));
    }
    let baseline = baseline.unwrap_or_else(|| recommended_baseline(cell)) as i64;
    if !(0 <= baseline && baseline < height as i64) {
        return Err(CoreError::invalid(
            "font baseline must be inside cell height",
        ));
    }
    let (w, h) = (width as i64, height as i64);
    let mut scale = 1.max((w / 5).min((baseline + 1) / 7));
    let mut x0 = 0.max((w - 5 * scale).div_euclid(2));
    let mut y0 = baseline - 7 * scale + 1;
    if y0 < 0 {
        scale = 1;
        x0 = 0.max((w - 5).div_euclid(2));
        y0 = 0;
    }
    let mut rows = vec![vec![0u8; width]; height];
    for (sy, source) in pattern.iter().enumerate() {
        for (sx, value) in source.bytes().enumerate() {
            if value != b'1' {
                continue;
            }
            for dy in 0..scale {
                let yy = y0 + sy as i64 * scale + dy;
                if yy < 0 || yy >= h {
                    continue;
                }
                for dx in 0..scale {
                    let xx = x0 + sx as i64 * scale + dx;
                    if xx >= 0 && xx < w {
                        rows[yy as usize][xx as usize] = 1;
                    }
                }
            }
        }
    }
    Ok(rows)
}
