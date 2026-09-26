#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum PixelTool {
    Pencil,
    Eraser,
    Line,
    Rectangle,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct PixelDocument {
    pub width: usize,
    pub height: usize,
    pixels: Vec<u8>,
    undo: Vec<Vec<u8>>,
    redo: Vec<Vec<u8>>,
    gesture_base: Option<Vec<u8>>,
}

impl PixelDocument {
    pub fn new(width: usize, height: usize) -> Result<Self, String> {
        if width == 0 || height == 0 {
            return Err("pixel document dimensions must be positive".into());
        }
        Ok(Self {
            width,
            height,
            pixels: vec![0; width * height],
            undo: Vec::new(),
            redo: Vec::new(),
            gesture_base: None,
        })
    }

    pub fn from_rows(rows: Vec<Vec<u8>>) -> Result<Self, String> {
        let bitmap = crate::bitmap::MonoBitmap::from_rows(rows)?;
        Ok(Self {
            width: bitmap.width,
            height: bitmap.height,
            pixels: bitmap.rows.into_iter().flatten().collect(),
            undo: Vec::new(),
            redo: Vec::new(),
            gesture_base: None,
        })
    }

    pub fn rows(&self) -> Vec<Vec<u8>> {
        self.pixels
            .chunks(self.width)
            .map(|row| row.to_vec())
            .collect()
    }

    pub fn pixel(&self, x: usize, y: usize) -> u8 {
        self.pixels[y * self.width + x]
    }

    pub fn begin_gesture(&mut self) {
        if self.gesture_base.is_none() {
            self.gesture_base = Some(self.pixels.clone());
            self.undo.push(self.pixels.clone());
            self.redo.clear();
        }
    }

    pub fn preview(&mut self, tool: PixelTool, start: (i32, i32), end: (i32, i32)) {
        if let Some(base) = &self.gesture_base {
            self.pixels.clone_from(base);
        }
        match tool {
            PixelTool::Pencil => self.draw_line(start, end, true),
            PixelTool::Eraser => self.draw_line(start, end, false),
            PixelTool::Line => self.draw_line(start, end, true),
            PixelTool::Rectangle => self.draw_rectangle(start, end, true),
        }
    }

    pub fn finish_gesture(&mut self) {
        self.gesture_base = None;
        self.trim_history();
    }

    pub fn cancel_gesture(&mut self) {
        if let Some(base) = self.gesture_base.take() {
            self.pixels = base;
            self.undo.pop();
        }
    }

    pub fn undo(&mut self) {
        if let Some(previous) = self.undo.pop() {
            self.redo.push(self.pixels.clone());
            self.pixels = previous;
        }
    }

    pub fn redo(&mut self) {
        if let Some(next) = self.redo.pop() {
            self.undo.push(self.pixels.clone());
            self.pixels = next;
        }
    }

    pub fn to_vlsb(&self) -> Result<Vec<u8>, String> {
        let framebuffer = crate::framebuffer::FrameBuffer::from_rows(self.rows())?;
        framebuffer.to_vlsb()
    }

    fn draw_line(&mut self, start: (i32, i32), end: (i32, i32), on: bool) {
        let (mut x0, mut y0) = start;
        let (x1, y1) = end;
        let dx = (x1 - x0).abs();
        let sx = if x0 < x1 { 1 } else { -1 };
        let dy = -(y1 - y0).abs();
        let sy = if y0 < y1 { 1 } else { -1 };
        let mut error = dx + dy;
        loop {
            self.set_if_inside(x0, y0, on);
            if x0 == x1 && y0 == y1 {
                break;
            }
            let twice = 2 * error;
            if twice >= dy {
                error += dy;
                x0 += sx;
            }
            if twice <= dx {
                error += dx;
                y0 += sy;
            }
        }
    }

    fn draw_rectangle(&mut self, start: (i32, i32), end: (i32, i32), on: bool) {
        let left = start.0.min(end.0);
        let right = start.0.max(end.0);
        let top = start.1.min(end.1);
        let bottom = start.1.max(end.1);
        self.draw_line((left, top), (right, top), on);
        self.draw_line((right, top), (right, bottom), on);
        self.draw_line((right, bottom), (left, bottom), on);
        self.draw_line((left, bottom), (left, top), on);
    }

    fn set_if_inside(&mut self, x: i32, y: i32, on: bool) {
        if x >= 0 && y >= 0 && (x as usize) < self.width && (y as usize) < self.height {
            self.pixels[y as usize * self.width + x as usize] = u8::from(on);
        }
    }

    fn trim_history(&mut self) {
        const MAX_HISTORY: usize = 128;
        if self.undo.len() > MAX_HISTORY {
            let drain = self.undo.len() - MAX_HISTORY;
            self.undo.drain(0..drain);
        }
    }
}

#[cfg(test)]
mod tests {
    use super::{PixelDocument, PixelTool};

    #[test]
    fn pencil_eraser_and_line_share_gesture_history() {
        let mut document = PixelDocument::new(8, 8).unwrap();
        document.begin_gesture();
        document.preview(PixelTool::Pencil, (1, 1), (3, 1));
        document.finish_gesture();
        assert_eq!(document.rows()[1][1..4], [1, 1, 1]);

        document.begin_gesture();
        document.preview(PixelTool::Eraser, (2, 1), (2, 1));
        document.finish_gesture();
        assert_eq!(document.pixel(2, 1), 0);

        document.begin_gesture();
        document.preview(PixelTool::Line, (0, 0), (3, 3));
        document.finish_gesture();
        assert_eq!(document.pixel(0, 0), 1);
        assert_eq!(document.pixel(3, 3), 1);
        document.undo();
        assert_eq!(document.pixel(3, 3), 0);
    }

    #[test]
    fn rows_roundtrip_preserves_vlsb_pixels() {
        let source = vec![
            vec![1, 0, 0, 1],
            vec![0, 1, 1, 0],
            vec![0, 0, 0, 0],
            vec![1, 1, 0, 0],
            vec![0, 0, 1, 1],
            vec![1, 0, 1, 0],
            vec![0, 1, 0, 1],
            vec![1, 1, 1, 1],
        ];
        let document = PixelDocument::from_rows(source.clone()).unwrap();
        assert_eq!(document.rows(), source);
        assert_eq!(document.to_vlsb().unwrap(), vec![0xA9, 0xCA, 0xB2, 0xD1]);
    }

    #[test]
    fn rectangle_preview_and_undo_are_one_gesture() {
        let mut document = PixelDocument::new(8, 8).unwrap();
        document.begin_gesture();
        document.preview(PixelTool::Rectangle, (1, 1), (4, 4));
        document.finish_gesture();
        assert_eq!(document.pixel(1, 1), 1);
        assert_eq!(document.pixel(2, 2), 0);
        document.undo();
        assert_eq!(document.pixel(1, 1), 0);
        document.redo();
        assert_eq!(document.pixel(4, 4), 1);
    }
}
