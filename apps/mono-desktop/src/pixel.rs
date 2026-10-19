//! Pixel Studio controller (V1 `pixel_studio_qt.PixelCanvas` / `PixelStudioWindow`
//! interaction rules): left button sets pixels, right clears them, Eraser is an
//! optional traditional tool. All edits go through `PixelDocument`, so every
//! gesture is exactly one undo step.

use std::path::{Path, PathBuf};

use mono_core::pixel::PixelDocument;
use mono_core::{CoreError, CoreResult};

/// V1 zoom choices (`Fit` plus these integer pixel sizes).
pub const ZOOMS: [i32; 10] = [4, 6, 8, 10, 12, 16, 20, 24, 32, 40];
/// V1 `PixelDocument.from_image` limits.
pub const MAX_IMPORT_PIXELS: usize = 4_194_304;
pub const MAX_IMPORT_DIMENSION: usize = 4096;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Tool {
    Pencil,
    Eraser,
    Line,
    Rectangle,
    Fill,
    Select,
}

impl Tool {
    pub fn from_index(index: i32) -> Self {
        match index {
            1 => Self::Eraser,
            2 => Self::Line,
            3 => Self::Rectangle,
            4 => Self::Fill,
            5 => Self::Select,
            _ => Self::Pencil,
        }
    }

    pub fn index(self) -> i32 {
        self as i32
    }
}

pub type Rect = (usize, usize, usize, usize);

#[derive(Debug, Clone)]
enum Gesture {
    Paint {
        last: (i64, i64),
        value: bool,
    },
    Shape {
        start: (i64, i64),
        end: (i64, i64),
        value: bool,
    },
    SelectNew {
        start: (i64, i64),
        end: (i64, i64),
    },
    SelectMove {
        origin: (i64, i64),
        offset: (i64, i64),
    },
}

pub struct PixelStudio {
    pub doc: PixelDocument,
    pub path: Option<PathBuf>,
    pub tool: Tool,
    pub brush: i64,
    pub interpolation: bool,
    pub selection: Option<Rect>,
    pub clipboard: Option<Vec<Vec<u8>>>,
    pub hover: Option<(i64, i64)>,
    pub key_cursor: Option<(i64, i64)>,
    gesture: Option<Gesture>,
}

impl PixelStudio {
    pub fn new(width: usize, height: usize) -> CoreResult<Self> {
        Ok(Self {
            doc: PixelDocument::new(width, height)?,
            path: None,
            tool: Tool::Pencil,
            brush: 1,
            interpolation: true,
            selection: None,
            clipboard: None,
            hover: None,
            key_cursor: None,
            gesture: None,
        })
    }

    /// V1 default document for a new Pixel Studio tab (32x16).
    #[allow(clippy::expect_used)]
    pub fn blank() -> Self {
        // A fixed, non-zero size cannot fail validation.
        Self::new(32, 16).expect("32x16 is a valid canvas")
    }

    pub fn width(&self) -> usize {
        self.doc.width()
    }

    pub fn height(&self) -> usize {
        self.doc.height()
    }

    fn in_bounds(&self, x: i64, y: i64) -> bool {
        x >= 0 && y >= 0 && (x as usize) < self.width() && (y as usize) < self.height()
    }

    fn clamp(&self, x: i64, y: i64) -> (i64, i64) {
        (
            x.clamp(0, self.width() as i64 - 1),
            y.clamp(0, self.height() as i64 - 1),
        )
    }

    /// Replace the document (open/import/new); clears transient state.
    pub fn replace(&mut self, doc: PixelDocument, path: Option<PathBuf>, max_undo: usize) {
        self.doc = doc;
        self.doc.set_max_undo(max_undo);
        self.path = path;
        self.selection = None;
        self.gesture = None;
        self.key_cursor = None;
        self.hover = None;
    }

    pub fn title(&self) -> String {
        self.path
            .as_ref()
            .and_then(|p| p.file_name())
            .map(|n| n.to_string_lossy().into_owned())
            .unwrap_or_default()
    }

    // ------------------------------------------------------------ pointer

    /// Returns true when the document or overlay changed.
    pub fn pointer_down(&mut self, x: i64, y: i64, right: bool) -> bool {
        if !self.in_bounds(x, y) {
            return false;
        }
        self.hover = Some((x, y));
        if self.tool == Tool::Select {
            if right {
                return false;
            }
            if let Some((sx, sy, sw, sh)) = self.selection {
                let (sx, sy, sw, sh) = (sx as i64, sy as i64, sw as i64, sh as i64);
                if (sx..sx + sw).contains(&x) && (sy..sy + sh).contains(&y) {
                    self.gesture = Some(Gesture::SelectMove {
                        origin: (x, y),
                        offset: (0, 0),
                    });
                    return true;
                }
            }
            self.gesture = Some(Gesture::SelectNew {
                start: (x, y),
                end: (x, y),
            });
            return true;
        }
        let value = !(right || self.tool == Tool::Eraser);
        match self.tool {
            Tool::Pencil | Tool::Eraser => {
                self.doc.begin_gesture();
                self.doc.brush(x, y, value, self.brush);
                self.gesture = Some(Gesture::Paint {
                    last: (x, y),
                    value,
                });
            }
            Tool::Line | Tool::Rectangle => {
                self.gesture = Some(Gesture::Shape {
                    start: (x, y),
                    end: (x, y),
                    value,
                });
            }
            Tool::Fill => {
                self.doc.begin_gesture();
                let _ = self.doc.flood_fill(x, y, value);
                self.doc.end_gesture();
            }
            Tool::Select => {}
        }
        true
    }

    pub fn pointer_move(&mut self, x: i64, y: i64) -> bool {
        self.hover = self.in_bounds(x, y).then_some((x, y));
        let clamped = self.clamp(x, y);
        let inside = self.in_bounds(x, y);
        let (brush, interpolation) = (self.brush, self.interpolation);
        match self.gesture.as_mut() {
            Some(Gesture::Paint { last, value }) => {
                if !inside {
                    return false;
                }
                if interpolation {
                    self.doc.brush_segment(last.0, last.1, x, y, *value, brush);
                } else {
                    self.doc.brush(x, y, *value, brush);
                }
                *last = (x, y);
                true
            }
            Some(Gesture::Shape { end, .. }) | Some(Gesture::SelectNew { end, .. }) => {
                let changed = *end != clamped;
                *end = clamped;
                changed
            }
            Some(Gesture::SelectMove { origin, offset }) => {
                let next = (x - origin.0, y - origin.1);
                let changed = *offset != next;
                *offset = next;
                changed
            }
            None => false,
        }
    }

    pub fn pointer_up(&mut self, x: i64, y: i64) -> bool {
        let Some(gesture) = self.gesture.take() else {
            return false;
        };
        let (x, y) = self.clamp(x, y);
        match gesture {
            Gesture::Paint { .. } => self.doc.end_gesture(),
            Gesture::Shape { start, value, .. } => {
                self.doc.begin_gesture();
                if self.tool == Tool::Line {
                    self.doc.line(start.0, start.1, x, y, value);
                } else {
                    self.doc.rectangle(start.0, start.1, x, y, false, value);
                }
                self.doc.end_gesture();
            }
            Gesture::SelectNew { start, .. } => {
                let (xa, xb) = (start.0.min(x), start.0.max(x));
                let (ya, yb) = (start.1.min(y), start.1.max(y));
                self.selection = Some((
                    xa as usize,
                    ya as usize,
                    (xb - xa + 1) as usize,
                    (yb - ya + 1) as usize,
                ));
            }
            Gesture::SelectMove { offset, .. } => {
                if let Some(selection) = self.selection {
                    let (nx, ny) = self.moved_origin(selection, offset);
                    let (sx, sy, sw, sh) = selection;
                    let (dx, dy) = (nx - sx as i64, ny - sy as i64);
                    if (dx, dy) != (0, 0) {
                        let _ = self.doc.move_region(sx, sy, sw, sh, dx, dy);
                        self.selection = Some((nx as usize, ny as usize, sw, sh));
                    }
                }
            }
        }
        true
    }

    fn moved_origin(&self, (sx, sy, sw, sh): Rect, (dx, dy): (i64, i64)) -> (i64, i64) {
        let max_x = (self.width() - sw) as i64;
        let max_y = (self.height() - sh) as i64;
        (
            (sx as i64 + dx).clamp(0, max_x),
            (sy as i64 + dy).clamp(0, max_y),
        )
    }

    /// Selection rectangle to draw, including an in-progress drag.
    pub fn overlay_selection(&self) -> Option<Rect> {
        match &self.gesture {
            Some(Gesture::SelectNew { start, end }) => {
                let (xa, xb) = (start.0.min(end.0), start.0.max(end.0));
                let (ya, yb) = (start.1.min(end.1), start.1.max(end.1));
                Some((
                    xa as usize,
                    ya as usize,
                    (xb - xa + 1) as usize,
                    (yb - ya + 1) as usize,
                ))
            }
            Some(Gesture::SelectMove { offset, .. }) => self.selection.map(|s| {
                let (nx, ny) = self.moved_origin(s, *offset);
                (nx as usize, ny as usize, s.2, s.3)
            }),
            _ => self.selection,
        }
    }

    /// Pixels to show: the document plus the uncommitted shape / move preview.
    pub fn display_pixels(&self) -> Vec<u8> {
        match &self.gesture {
            Some(Gesture::Shape { start, end, value }) => {
                let mut preview = self.doc.clone();
                if self.tool == Tool::Line {
                    preview.line(start.0, start.1, end.0, end.1, *value);
                } else {
                    preview.rectangle(start.0, start.1, end.0, end.1, false, *value);
                }
                preview.pixels().to_vec()
            }
            Some(Gesture::SelectMove { offset, .. }) if *offset != (0, 0) => {
                let mut preview = self.doc.clone();
                if let Some(selection) = self.selection {
                    let (nx, ny) = self.moved_origin(selection, *offset);
                    let (sx, sy, sw, sh) = selection;
                    let _ = preview.move_region(sx, sy, sw, sh, nx - sx as i64, ny - sy as i64);
                }
                preview.pixels().to_vec()
            }
            _ => self.doc.pixels().to_vec(),
        }
    }

    // ----------------------------------------------------------- keyboard

    /// V1 keyboard drawing: arrows place a cursor, Enter sets, Delete clears.
    pub fn key(&mut self, key: &str) -> bool {
        let moves = match key {
            "left" => Some((-1, 0)),
            "right" => Some((1, 0)),
            "up" => Some((0, -1)),
            "down" => Some((0, 1)),
            _ => None,
        };
        if let Some((dx, dy)) = moves {
            match self.key_cursor {
                None => self.key_cursor = Some((0, 0)),
                Some((x, y)) => {
                    if self.in_bounds(x + dx, y + dy) {
                        self.key_cursor = Some((x + dx, y + dy));
                    }
                }
            }
            return true;
        }
        match key {
            "enter" | "delete" => {
                let Some((x, y)) = self.key_cursor else {
                    if key == "delete" && self.selection.is_some() {
                        return self.action("cut-clear");
                    }
                    return false;
                };
                self.doc.begin_gesture();
                self.doc.brush(x, y, key == "enter", self.brush);
                self.doc.end_gesture();
                true
            }
            "escape" => {
                let had = self.key_cursor.is_some() || self.selection.is_some();
                self.key_cursor = None;
                self.selection = None;
                had
            }
            _ => false,
        }
    }

    // ------------------------------------------------------------ actions

    pub fn copy(&mut self) -> bool {
        let Some((x, y, w, h)) = self.selection else {
            return false;
        };
        match self.doc.copy_region(x, y, w, h) {
            Ok(region) => {
                self.clipboard = Some(region);
                true
            }
            Err(_) => false,
        }
    }

    /// Document actions; `Err` carries a user-visible message.
    pub fn try_action(&mut self, action: &str) -> CoreResult<bool> {
        let changed = match action {
            "undo" => self.doc.undo(),
            "redo" => self.doc.redo(),
            "invert" => {
                self.doc.invert();
                true
            }
            "flip-h" => {
                self.doc.flip_horizontal();
                true
            }
            "flip-v" => {
                self.doc.flip_vertical();
                true
            }
            "clear" => {
                self.doc.clear(false);
                true
            }
            "rotate90" => {
                self.doc.rotate90()?;
                self.selection = None;
                true
            }
            "rotate180" => {
                self.doc.rotate180();
                true
            }
            "rotate270" => {
                self.doc.rotate270();
                self.selection = None;
                true
            }
            "copy" => {
                self.copy();
                false
            }
            "cut" | "cut-clear" => {
                let Some((x, y, w, h)) = self.selection else {
                    return Ok(false);
                };
                if action == "cut" {
                    self.copy();
                }
                self.doc
                    .clear_region(x as i64, y as i64, w as i64, h as i64);
                true
            }
            "paste" => {
                let Some(region) = self.clipboard.clone() else {
                    return Ok(false);
                };
                let (x, y) = self.selection.map_or((0, 0), |s| (s.0, s.1));
                self.doc.paste_region(x as i64, y as i64, &region);
                true
            }
            "crop" => {
                let Some((x, y, w, h)) = self.selection else {
                    return Ok(false);
                };
                self.doc.crop(x as i64, y as i64, w as i64, h as i64)?;
                self.selection = None;
                true
            }
            _ => false,
        };
        if changed {
            self.key_cursor = self.key_cursor.filter(|(x, y)| self.in_bounds(*x, *y));
            if let Some((x, y, w, h)) = self.selection {
                if x + w > self.width() || y + h > self.height() {
                    self.selection = None;
                }
            }
        }
        Ok(changed)
    }

    pub fn action(&mut self, action: &str) -> bool {
        self.try_action(action).unwrap_or(false)
    }

    pub fn resize(&mut self, width: i64, height: i64, anchor: &str) -> CoreResult<()> {
        self.doc.resize_canvas(width, height, anchor)?;
        self.selection = None;
        self.key_cursor = None;
        Ok(())
    }

    pub fn lit_in_selection(&self) -> usize {
        let Some((x, y, w, h)) = self.selection else {
            return 0;
        };
        (y..y + h)
            .flat_map(|yy| (x..x + w).map(move |xx| (xx, yy)))
            .filter(|(xx, yy)| self.doc.get(*xx, *yy) != 0)
            .count()
    }

    /// Rows of the selection (or the whole canvas).
    pub fn selection_rows(&self) -> Vec<Vec<u8>> {
        match self.selection {
            Some((x, y, w, h)) => self.doc.copy_region(x, y, w, h).unwrap_or_default(),
            None => self.doc.rows(),
        }
    }

    // ----------------------------------------------------------------- IO

    /// V1 `save_png`: forces the `.png` suffix, writes atomically, clears dirty.
    pub fn save_png(&mut self, path: &Path) -> CoreResult<PathBuf> {
        let target = if path
            .extension()
            .is_some_and(|e| e.eq_ignore_ascii_case("png"))
        {
            path.to_path_buf()
        } else {
            path.with_extension("png")
        };
        let png = mono_project::image_io::encode_bitmap_png(
            self.width(),
            self.height(),
            &self.doc.rows(),
        )?;
        mono_project::atomic::atomic_write(&target, &png)?;
        self.doc.dirty = false;
        self.path = Some(target.clone());
        Ok(target)
    }

    pub fn save_bin(&self, path: &Path) -> CoreResult<()> {
        mono_project::atomic::atomic_write(path, &self.doc.to_vlsb())
    }

    pub fn save_c_header(&self, path: &Path, symbol: &str) -> CoreResult<()> {
        mono_project::atomic::atomic_write(path, self.doc.to_c_header(symbol).as_bytes())
    }
}

/// V1 default C symbol: file stem with `-` and spaces replaced.
pub fn default_symbol(path: Option<&Path>) -> String {
    path.and_then(|p| p.file_stem())
        .map(|s| s.to_string_lossy().replace(['-', ' '], "_"))
        .unwrap_or_else(|| "oled_bitmap".into())
}

/// Decode an image for the import dialog, enforcing V1's Pixel Studio limits.
pub fn load_import_source(path: &Path) -> CoreResult<mono_core::raster::RgbaImage> {
    let bytes = std::fs::read(path).map_err(|e| mono_project::resources::io_error(path, &e))?;
    let decoded = mono_project::image_io::decode_image(&bytes)?;
    if decoded.width > MAX_IMPORT_DIMENSION
        || decoded.height > MAX_IMPORT_DIMENSION
        || decoded.width * decoded.height > MAX_IMPORT_PIXELS
    {
        return Err(CoreError::invalid(format!(
            "image too large for Pixel Studio: {}x{}",
            decoded.width, decoded.height
        )));
    }
    mono_core::raster::RgbaImage::new(decoded.width, decoded.height, decoded.rgba)
}

#[cfg(test)]
mod tests {
    #![allow(clippy::unwrap_used)]
    use super::*;

    fn studio() -> PixelStudio {
        PixelStudio::new(16, 8).unwrap()
    }

    #[test]
    fn pencil_stroke_is_one_undo_step_and_right_button_clears() {
        let mut s = studio();
        s.pointer_down(0, 0, false);
        s.pointer_move(5, 0);
        s.pointer_up(5, 0);
        assert!((0..6).all(|x| s.doc.get(x, 0) == 1));
        s.pointer_down(2, 0, true);
        s.pointer_up(2, 0);
        assert_eq!(s.doc.get(2, 0), 0);
        assert!(s.action("undo"));
        assert_eq!(s.doc.get(2, 0), 1);
        assert!(s.action("undo"));
        assert!(s.doc.pixels().iter().all(|v| *v == 0));
    }

    #[test]
    fn line_previews_without_touching_document_until_release() {
        let mut s = studio();
        s.tool = Tool::Line;
        s.pointer_down(0, 0, false);
        s.pointer_move(7, 0);
        assert!(s.doc.pixels().iter().all(|v| *v == 0));
        assert_eq!(s.display_pixels().iter().filter(|v| **v == 1).count(), 8);
        // Releasing outside clamps to the canvas.
        s.pointer_up(99, 0);
        assert_eq!(s.doc.get(15, 0), 1);
        assert!(s.doc.can_undo());
    }

    #[test]
    fn selection_drag_moves_region_clamped_to_canvas() {
        let mut s = studio();
        s.doc.pencil(0, 0, true);
        s.tool = Tool::Select;
        s.pointer_down(0, 0, false);
        s.pointer_move(1, 1);
        s.pointer_up(1, 1);
        assert_eq!(s.selection, Some((0, 0, 2, 2)));
        s.pointer_down(0, 0, false);
        s.pointer_move(40, 3);
        assert_eq!(s.overlay_selection(), Some((14, 3, 2, 2)));
        s.pointer_up(40, 3);
        assert_eq!(s.selection, Some((14, 3, 2, 2)));
        assert_eq!(s.doc.get(14, 3), 1);
        assert_eq!(s.doc.get(0, 0), 0);
    }

    #[test]
    fn copy_cut_paste_and_crop_follow_selection() {
        let mut s = studio();
        s.doc.pencil(1, 1, true);
        s.selection = Some((1, 1, 2, 2));
        assert!(s.action("cut"));
        assert_eq!(s.doc.get(1, 1), 0);
        s.selection = Some((4, 4, 1, 1));
        assert!(s.action("paste"));
        assert_eq!(s.doc.get(4, 4), 1);
        s.selection = Some((4, 4, 3, 2));
        assert!(s.action("crop"));
        assert_eq!((s.width(), s.height()), (3, 2));
        assert_eq!(s.selection, None);
    }

    #[test]
    fn keyboard_cursor_draws_and_stays_in_bounds() {
        let mut s = studio();
        s.key("left");
        assert_eq!(s.key_cursor, Some((0, 0)));
        s.key("left");
        assert_eq!(s.key_cursor, Some((0, 0)));
        s.key("right");
        s.key("enter");
        assert_eq!(s.doc.get(1, 0), 1);
        s.key("delete");
        assert_eq!(s.doc.get(1, 0), 0);
        assert!(s.key("escape"));
        assert_eq!(s.key_cursor, None);
    }

    #[test]
    fn rotate90_error_surfaces_and_fill_is_undoable() {
        let mut s = PixelStudio::new(10, 8).unwrap();
        assert!(s.try_action("rotate90").is_err());
        s.tool = Tool::Fill;
        s.pointer_down(3, 3, false);
        assert!(s.doc.pixels().iter().all(|v| *v == 1));
        assert!(s.action("undo"));
        assert!(s.doc.pixels().iter().all(|v| *v == 0));
    }

    #[test]
    fn save_png_forces_suffix_and_round_trips() {
        let dir = std::env::temp_dir().join(format!("mono-pixel-{}", std::process::id()));
        std::fs::create_dir_all(&dir).unwrap();
        let mut s = studio();
        s.doc.pencil(3, 2, true);
        let saved = s.save_png(&dir.join("glyph.bmp")).unwrap();
        assert_eq!(saved.extension().unwrap(), "png");
        assert!(!s.doc.dirty);
        let decoded =
            mono_project::image_io::decode_image(&std::fs::read(&saved).unwrap()).unwrap();
        assert_eq!((decoded.width, decoded.height), (16, 8));
        assert_eq!(decoded.rgba[(2 * 16 + 3) * 4], 255);
        let _ = std::fs::remove_dir_all(&dir);
    }

    #[test]
    fn default_symbol_matches_v1() {
        assert_eq!(
            default_symbol(Some(Path::new("a/my-icon 2.png"))),
            "my_icon_2"
        );
        assert_eq!(default_symbol(None), "oled_bitmap");
    }
}
