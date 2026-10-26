//! Pixel Studio document (V1 `pixel_studio.PixelDocument`).
//!
//! Undo snapshots are bit-packed (8 pixels per byte) under a 64 MiB budget; a
//! gesture (`begin_gesture`..`end_gesture`) is always exactly one undo step.

use std::collections::VecDeque;
use std::collections::hash_map::DefaultHasher;
use std::hash::{Hash, Hasher};

use crate::error::{CoreError, CoreResult};
use crate::font::FontPack;

pub const MAX_UNDO_BYTES: usize = 64 * 1024 * 1024;

type Snapshot = (usize, usize, Vec<u8>);

#[derive(Debug, Clone)]
pub struct PixelDocument {
    width: usize,
    height: usize,
    pixels: Vec<u8>,
    max_undo: usize,
    undo: Vec<Snapshot>,
    redo: Vec<Snapshot>,
    gesture_before: Option<Snapshot>,
    saved_fingerprint: u64,
    pub dirty: bool,
}

fn pack(pixels: &[u8]) -> Vec<u8> {
    let mut out = vec![0u8; pixels.len().div_ceil(8)];
    for (i, v) in pixels.iter().enumerate() {
        if *v != 0 {
            out[i >> 3] |= 1 << (i & 7);
        }
    }
    out
}

fn unpack(data: &[u8], count: usize) -> Vec<u8> {
    (0..count).map(|i| (data[i >> 3] >> (i & 7)) & 1).collect()
}

impl PixelDocument {
    pub fn new(width: usize, height: usize) -> CoreResult<Self> {
        Self::from_pixels(width, height, vec![0; width * height])
    }

    pub fn from_pixels(width: usize, height: usize, pixels: Vec<u8>) -> CoreResult<Self> {
        if width == 0 || height == 0 {
            return Err(CoreError::invalid("width and height must be positive"));
        }
        if pixels.len() != width * height {
            return Err(CoreError::invalid("pixel buffer does not match dimensions"));
        }
        let mut doc = Self {
            width,
            height,
            pixels: pixels.into_iter().map(|v| u8::from(v != 0)).collect(),
            max_undo: 200,
            undo: Vec::new(),
            redo: Vec::new(),
            gesture_before: None,
            saved_fingerprint: 0,
            dirty: false,
        };
        doc.saved_fingerprint = doc.content_fingerprint();
        Ok(doc)
    }

    pub fn from_rows(rows: &[Vec<u8>]) -> CoreResult<Self> {
        let height = rows.len();
        let width = rows.first().map_or(0, Vec::len);
        if rows.iter().any(|r| r.len() != width) {
            return Err(CoreError::invalid("pixel rows must have equal width"));
        }
        Self::from_pixels(width, height, rows.concat())
    }

    pub fn width(&self) -> usize {
        self.width
    }

    pub fn height(&self) -> usize {
        self.height
    }

    pub fn pixels(&self) -> &[u8] {
        &self.pixels
    }

    pub fn rows(&self) -> Vec<Vec<u8>> {
        self.pixels.chunks(self.width).map(<[u8]>::to_vec).collect()
    }

    pub fn can_undo(&self) -> bool {
        !self.undo.is_empty()
    }

    pub fn can_redo(&self) -> bool {
        !self.redo.is_empty()
    }

    fn state(&self) -> Snapshot {
        (self.width, self.height, pack(&self.pixels))
    }

    fn restore(&mut self, state: Snapshot) {
        let (w, h, packed) = state;
        self.width = w;
        self.height = h;
        self.pixels = unpack(&packed, w * h);
    }

    fn effective_limit(&self) -> usize {
        let snapshot = (self.width * self.height).div_ceil(8).max(1);
        self.max_undo.min((MAX_UNDO_BYTES / snapshot).max(1)).max(1)
    }

    fn push_undo(&mut self, state: Snapshot) {
        self.undo.push(state);
        let limit = self.effective_limit();
        if self.undo.len() > limit {
            let excess = self.undo.len() - limit;
            self.undo.drain(..excess);
        }
    }

    fn snapshot(&mut self) {
        if self.gesture_before.is_some() {
            return;
        }
        let state = self.state();
        self.push_undo(state);
        self.redo.clear();
    }

    fn content_fingerprint(&self) -> u64 {
        let mut hasher = DefaultHasher::new();
        self.width.hash(&mut hasher);
        self.height.hash(&mut hasher);
        self.pixels.hash(&mut hasher);
        hasher.finish()
    }

    /// Re-derive `dirty` from content equality with the last save point.
    pub fn sync_dirty(&mut self) {
        self.dirty = self.content_fingerprint() != self.saved_fingerprint;
    }

    /// Record the current content as the save point (called after a successful write).
    pub fn mark_saved(&mut self) {
        self.saved_fingerprint = self.content_fingerprint();
        self.dirty = false;
    }

    /// Treat the current content as accepted without writing (discard / fresh load).
    pub fn mark_clean(&mut self) {
        self.mark_saved();
    }

    /// A direct edit always dirties the document (Automation 1.3.0 keeps this
    /// contract); only undo/redo and gesture end re-derive it from the save point.
    fn touched(&mut self) {
        self.dirty = true;
    }

    pub fn set_max_undo(&mut self, limit: usize) {
        self.max_undo = limit.max(1);
        let cap = self.effective_limit();
        if self.undo.len() > cap {
            let excess = self.undo.len() - cap;
            self.undo.drain(..excess);
        }
        if self.redo.len() > cap {
            let excess = self.redo.len() - cap;
            self.redo.drain(..excess);
        }
    }

    pub fn begin_gesture(&mut self) {
        if self.gesture_before.is_none() {
            self.gesture_before = Some(self.state());
        }
    }

    pub fn end_gesture(&mut self) {
        let Some(before) = self.gesture_before.take() else {
            return;
        };
        if before != self.state() {
            self.push_undo(before);
            self.redo.clear();
        }
        self.sync_dirty();
    }

    pub fn in_gesture(&self) -> bool {
        self.gesture_before.is_some()
    }

    pub fn get(&self, x: usize, y: usize) -> u8 {
        self.pixels[y * self.width + x]
    }

    fn set_raw(&mut self, x: i64, y: i64, value: bool) {
        if x >= 0 && y >= 0 && (x as usize) < self.width && (y as usize) < self.height {
            self.pixels[y as usize * self.width + x as usize] = u8::from(value);
        }
    }

    fn brush_raw(&mut self, x: i64, y: i64, value: bool, size: i64) {
        let size = size.max(1);
        let (left, right) = ((size - 1) / 2, size / 2);
        for yy in y - left..=y + right {
            for xx in x - left..=x + right {
                self.set_raw(xx, yy, value);
            }
        }
    }

    pub fn pencil(&mut self, x: i64, y: i64, value: bool) {
        self.snapshot();
        self.set_raw(x, y, value);
        self.touched();
    }

    pub fn erase(&mut self, x: i64, y: i64) {
        self.pencil(x, y, false);
    }

    pub fn brush(&mut self, x: i64, y: i64, value: bool, size: i64) {
        self.snapshot();
        self.brush_raw(x, y, value, size);
        self.touched();
    }

    fn bresenham(mut x0: i64, mut y0: i64, x1: i64, y1: i64, mut plot: impl FnMut(i64, i64)) {
        let dx = (x1 - x0).abs();
        let sx = if x0 < x1 { 1 } else { -1 };
        let dy = -(y1 - y0).abs();
        let sy = if y0 < y1 { 1 } else { -1 };
        let mut err = dx + dy;
        loop {
            plot(x0, y0);
            if x0 == x1 && y0 == y1 {
                break;
            }
            let e2 = 2 * err;
            if e2 >= dy {
                err += dy;
                x0 += sx;
            }
            if e2 <= dx {
                err += dx;
                y0 += sy;
            }
        }
    }

    pub fn line(&mut self, x0: i64, y0: i64, x1: i64, y1: i64, value: bool) {
        self.snapshot();
        let mut points = Vec::new();
        Self::bresenham(x0, y0, x1, y1, |x, y| points.push((x, y)));
        for (x, y) in points {
            self.set_raw(x, y, value);
        }
        self.touched();
    }

    /// Continuous stroke segment; inside a gesture all segments form one undo step.
    pub fn stroke_segment(&mut self, x0: i64, y0: i64, x1: i64, y1: i64, value: bool) {
        self.line(x0, y0, x1, y1, value);
    }

    pub fn brush_segment(&mut self, x0: i64, y0: i64, x1: i64, y1: i64, value: bool, size: i64) {
        self.snapshot();
        let mut points = Vec::new();
        Self::bresenham(x0, y0, x1, y1, |x, y| points.push((x, y)));
        for (x, y) in points {
            self.brush_raw(x, y, value, size);
        }
        self.touched();
    }

    pub fn rectangle(&mut self, x0: i64, y0: i64, x1: i64, y1: i64, filled: bool, value: bool) {
        self.snapshot();
        let (xa, xb) = (x0.min(x1), x0.max(x1));
        let (ya, yb) = (y0.min(y1), y0.max(y1));
        for y in ya..=yb {
            for x in xa..=xb {
                if filled || x == xa || x == xb || y == ya || y == yb {
                    self.set_raw(x, y, value);
                }
            }
        }
        self.touched();
    }

    pub fn flood_fill(&mut self, x: i64, y: i64, value: bool) -> CoreResult<()> {
        if x < 0 || y < 0 || x as usize >= self.width || y as usize >= self.height {
            return Err(CoreError::new("E-CORE-RANGE", "list index out of range"));
        }
        let target = self.get(x as usize, y as usize);
        let value = u8::from(value);
        if target == value {
            return Ok(());
        }
        self.snapshot();
        let mut queue = VecDeque::from([(x, y)]);
        while let Some((cx, cy)) = queue.pop_front() {
            if cx < 0 || cy < 0 || cx as usize >= self.width || cy as usize >= self.height {
                continue;
            }
            let index = cy as usize * self.width + cx as usize;
            if self.pixels[index] != target {
                continue;
            }
            self.pixels[index] = value;
            queue.extend([(cx + 1, cy), (cx - 1, cy), (cx, cy + 1), (cx, cy - 1)]);
        }
        self.touched();
        Ok(())
    }

    pub fn clear(&mut self, value: bool) {
        self.snapshot();
        self.pixels.fill(u8::from(value));
        self.touched();
    }

    pub fn invert(&mut self) {
        self.snapshot();
        for v in &mut self.pixels {
            *v = 1 - *v;
        }
        self.touched();
    }

    pub fn flip_horizontal(&mut self) {
        self.snapshot();
        for row in self.pixels.chunks_mut(self.width) {
            row.reverse();
        }
        self.touched();
    }

    pub fn flip_vertical(&mut self) {
        self.snapshot();
        let rows: Vec<Vec<u8>> = self
            .pixels
            .chunks(self.width)
            .rev()
            .map(<[u8]>::to_vec)
            .collect();
        self.pixels = rows.concat();
        self.touched();
    }

    pub fn rotate90(&mut self) -> CoreResult<()> {
        if !self.width.is_multiple_of(8) {
            return Err(CoreError::invalid("rotated height must be a multiple of 8"));
        }
        self.snapshot();
        let (ow, oh) = (self.width, self.height);
        let old = self.pixels.clone();
        let mut out = Vec::with_capacity(ow * oh);
        for x in 0..ow {
            for y in 0..oh {
                out.push(old[(oh - 1 - y) * ow + x]);
            }
        }
        self.pixels = out;
        self.width = oh;
        self.height = ow;
        self.touched();
        Ok(())
    }

    pub fn rotate180(&mut self) {
        self.snapshot();
        self.pixels.reverse();
        self.touched();
    }

    pub fn rotate270(&mut self) {
        self.snapshot();
        let (ow, oh) = (self.width, self.height);
        let old = self.pixels.clone();
        let mut out = Vec::with_capacity(ow * oh);
        for x in 0..ow {
            for y in 0..oh {
                out.push(old[y * ow + (ow - 1 - x)]);
            }
        }
        self.pixels = out;
        self.width = oh;
        self.height = ow;
        self.touched();
    }

    pub fn copy_region(&self, x: usize, y: usize, w: usize, h: usize) -> CoreResult<Vec<Vec<u8>>> {
        if x + w > self.width || y + h > self.height {
            return Err(CoreError::new("E-CORE-RANGE", "list index out of range"));
        }
        Ok((0..h)
            .map(|cy| (0..w).map(|cx| self.get(x + cx, y + cy)).collect())
            .collect())
    }

    pub fn paste_region(&mut self, x: i64, y: i64, region: &[Vec<u8>]) {
        self.snapshot();
        for (ry, row) in region.iter().enumerate() {
            for (rx, value) in row.iter().enumerate() {
                self.set_raw(x + rx as i64, y + ry as i64, *value != 0);
            }
        }
        self.touched();
    }

    pub fn clear_region(&mut self, x: i64, y: i64, w: i64, h: i64) {
        self.snapshot();
        for yy in y..y + h {
            for xx in x..x + w {
                self.set_raw(xx, yy, false);
            }
        }
        self.touched();
    }

    pub fn move_region(
        &mut self,
        x: usize,
        y: usize,
        w: usize,
        h: usize,
        dx: i64,
        dy: i64,
    ) -> CoreResult<()> {
        if w == 0 || h == 0 || (dx == 0 && dy == 0) {
            return Ok(());
        }
        let region = self.copy_region(x, y, w, h)?;
        self.snapshot();
        for yy in y..y + h {
            for xx in x..x + w {
                self.set_raw(xx as i64, yy as i64, false);
            }
        }
        for (ry, row) in region.iter().enumerate() {
            for (rx, value) in row.iter().enumerate() {
                self.set_raw(
                    x as i64 + dx + rx as i64,
                    y as i64 + dy + ry as i64,
                    *value != 0,
                );
            }
        }
        self.touched();
        Ok(())
    }

    pub fn resize_canvas(&mut self, width: i64, height: i64, anchor: &str) -> CoreResult<()> {
        if width <= 0 || height <= 0 {
            return Err(CoreError::invalid("width and height must be positive"));
        }
        let (ax, ay) = match anchor {
            "top-left" => (0.0, 0.0),
            "top" => (0.5, 0.0),
            "top-right" => (1.0, 0.0),
            "left" => (0.0, 0.5),
            "center" => (0.5, 0.5),
            "right" => (1.0, 0.5),
            "bottom-left" => (0.0, 1.0),
            "bottom" => (0.5, 1.0),
            "bottom-right" => (1.0, 1.0),
            _ => return Err(CoreError::invalid("unsupported anchor")),
        };
        self.snapshot();
        let (ow, oh) = (self.width as i64, self.height as i64);
        // Python round() is banker's rounding.
        let dx = round_half_even((width - ow) as f64 * ax);
        let dy = round_half_even((height - oh) as f64 * ay);
        let mut out = vec![0u8; (width * height) as usize];
        for y in 0..oh {
            for x in 0..ow {
                let (nx, ny) = (x + dx, y + dy);
                if nx >= 0 && ny >= 0 && nx < width && ny < height {
                    out[(ny * width + nx) as usize] = self.pixels[(y * ow + x) as usize];
                }
            }
        }
        self.width = width as usize;
        self.height = height as usize;
        self.pixels = out;
        self.touched();
        Ok(())
    }

    pub fn crop(&mut self, x: i64, y: i64, w: i64, h: i64) -> CoreResult<()> {
        if w <= 0 || h <= 0 {
            return Err(CoreError::invalid("crop width and height must be positive"));
        }
        if x < 0 || y < 0 || x + w > self.width as i64 || y + h > self.height as i64 {
            return Err(CoreError::invalid("crop outside document"));
        }
        self.snapshot();
        let mut out = Vec::with_capacity((w * h) as usize);
        for yy in y..y + h {
            let start = yy as usize * self.width + x as usize;
            out.extend_from_slice(&self.pixels[start..start + w as usize]);
        }
        self.pixels = out;
        self.width = w as usize;
        self.height = h as usize;
        self.touched();
        Ok(())
    }

    pub fn undo(&mut self) -> bool {
        let Some(previous) = self.undo.pop() else {
            return false;
        };
        let current = self.state();
        self.redo.push(current);
        self.restore(previous);
        self.sync_dirty();
        true
    }

    pub fn redo(&mut self) -> bool {
        let Some(next) = self.redo.pop() else {
            return false;
        };
        let current = self.state();
        self.push_undo(current);
        self.restore(next);
        self.sync_dirty();
        true
    }

    pub fn to_vlsb(&self) -> Vec<u8> {
        let mut out = vec![0u8; self.width * self.height.div_ceil(8)];
        for (y, row) in self.pixels.chunks(self.width).enumerate() {
            for (x, v) in row.iter().enumerate() {
                if *v != 0 {
                    out[(y / 8) * self.width + x] |= 1 << (y % 8);
                }
            }
        }
        out
    }

    /// V1 `to_c_header` (Legacy Pixel C Header from Pixel Studio).
    pub fn to_c_header(&self, symbol: &str) -> String {
        let clean: String = symbol
            .chars()
            .map(|c| {
                if c.is_ascii_alphanumeric() || c == '_' {
                    c
                } else {
                    '_'
                }
            })
            .collect();
        let clean = clean.trim_matches('_');
        let mut clean = if clean.is_empty() {
            "oled_bitmap".to_string()
        } else {
            clean.to_string()
        };
        if clean.as_bytes()[0].is_ascii_digit() {
            clean = format!("bitmap_{clean}");
        }
        let do_macro = clean.to_uppercase();
        let raw = self.to_vlsb();
        let body = raw
            .chunks(12)
            .map(|c| {
                format!(
                    "    {},",
                    c.iter()
                        .map(|b| format!("0x{b:02X}"))
                        .collect::<Vec<_>>()
                        .join(", ")
                )
            })
            .collect::<Vec<_>>()
            .join("\n");
        format!(
            "#define {do_macro}_WIDTH {}\n#define {do_macro}_HEIGHT {}\n#define {do_macro}_BYTES {}\n\nstatic const unsigned char {clean}[] = {{\n{body}\n}};\n",
            self.width,
            self.height,
            raw.len()
        )
    }
}

fn round_half_even(value: f64) -> i64 {
    let floor = value.floor();
    let diff = value - floor;
    let rounded = if (diff - 0.5).abs() < f64::EPSILON {
        if (floor as i64) % 2 == 0 {
            floor
        } else {
            floor + 1.0
        }
    } else {
        value.round()
    };
    rounded as i64
}

/// V1 `insert_fontpack_text`: paste exact glyphs as one undoable edit; returns (w, h).
pub fn insert_fontpack_text(
    document: &mut PixelDocument,
    pack: &FontPack,
    text: &str,
    x: i64,
    y: i64,
    tracking: i32,
) -> CoreResult<(usize, usize)> {
    let bitmap = pack.compose_text(text, tracking)?;
    let width = bitmap.first().map_or(0, Vec::len);
    let height = bitmap.len();
    if width > 0 && height > 0 {
        document.paste_region(x, y, &bitmap);
    }
    Ok((width, height))
}

#[cfg(test)]
mod tests {
    #![allow(clippy::unwrap_used)]
    use super::*;

    #[test]
    fn from_pixels_starts_clean() {
        let doc = PixelDocument::from_pixels(4, 2, vec![1, 0, 0, 1, 0, 1, 1, 0]).unwrap();
        assert!(!doc.dirty);
    }

    #[test]
    fn undo_to_saved_state_is_clean() {
        let mut doc = PixelDocument::new(8, 8).unwrap();
        doc.pencil(1, 1, true);
        assert!(doc.dirty);
        assert!(doc.undo());
        assert!(!doc.dirty);
    }

    #[test]
    fn redo_after_save_is_dirty() {
        let mut doc = PixelDocument::new(8, 8).unwrap();
        doc.pencil(1, 1, true);
        doc.mark_saved();
        assert!(!doc.dirty);
        assert!(doc.undo());
        assert!(doc.dirty);
        assert!(doc.redo());
        assert!(!doc.dirty);
    }

    #[test]
    fn mark_saved_records_the_current_content() {
        let mut doc = PixelDocument::new(8, 8).unwrap();
        doc.pencil(0, 0, true);
        doc.mark_saved();
        assert!(!doc.dirty);
        doc.clear(false);
        assert!(doc.dirty);
        doc.undo();
        assert!(!doc.dirty);
    }

    #[test]
    fn gesture_is_one_undo_step() {
        let mut doc = PixelDocument::new(16, 8).unwrap();
        doc.begin_gesture();
        doc.stroke_segment(0, 0, 5, 0, true);
        doc.stroke_segment(5, 0, 5, 5, true);
        doc.end_gesture();
        assert!(doc.undo());
        assert!(doc.pixels().iter().all(|v| *v == 0));
        assert!(!doc.undo());
        assert!(doc.redo());
        assert_eq!(doc.get(5, 5), 1);
    }

    #[test]
    fn rotate90_requires_page_aligned_width_and_swaps_size() {
        let mut doc = PixelDocument::new(10, 8).unwrap();
        assert!(doc.rotate90().is_err());
        let mut doc = PixelDocument::new(8, 4).unwrap();
        doc.pencil(0, 0, true);
        doc.rotate90().unwrap();
        assert_eq!((doc.width(), doc.height()), (4, 8));
        assert_eq!(doc.get(3, 0), 1);
    }

    #[test]
    fn resize_center_uses_bankers_rounding() {
        let mut doc = PixelDocument::new(3, 3).unwrap();
        doc.pencil(0, 0, true);
        doc.resize_canvas(4, 4, "center").unwrap();
        // round(0.5) == 0 in Python.
        assert_eq!(doc.get(0, 0), 1);
    }
}
