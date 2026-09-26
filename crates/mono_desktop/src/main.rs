use eframe::egui::{self, Color32, Pos2, Rect, Sense, Stroke, Vec2};
use mono_core::pixel::{PixelDocument, PixelTool};
use serde_json::{Value, json};
use std::fs;
use std::path::Path;

struct PixelApp {
    document: PixelDocument,
    tool: PixelTool,
    zoom: f32,
    pan: Vec2,
    gesture_start: Option<(i32, i32)>,
    last_pointer: Option<Pos2>,
    status: String,
}

fn fixture_bytes(document: &PixelDocument) -> Vec<u8> {
    let payload = json!({
        "schema_version": 1,
        "width": document.width,
        "height": document.height,
        "rows": document.rows(),
    });
    serde_json::to_vec_pretty(&payload).expect("fixture JSON")
}

fn parse_fixture(bytes: &[u8]) -> Result<PixelDocument, String> {
    let payload: Value = serde_json::from_slice(bytes).map_err(|error| error.to_string())?;
    if payload.get("schema_version").and_then(Value::as_u64) != Some(1) {
        return Err("unsupported fixture schema".into());
    }
    let width = payload
        .get("width")
        .and_then(Value::as_u64)
        .ok_or_else(|| "fixture width missing".to_owned())? as usize;
    let height = payload
        .get("height")
        .and_then(Value::as_u64)
        .ok_or_else(|| "fixture height missing".to_owned())? as usize;
    let rows = payload
        .get("rows")
        .and_then(Value::as_array)
        .ok_or_else(|| "fixture rows missing".to_owned())?;
    if rows.len() != height {
        return Err("fixture height does not match rows".into());
    }
    let rows = rows
        .iter()
        .map(|row| {
            let bits = if let Some(values) = row.as_array() {
                values
                    .iter()
                    .map(|value| match value.as_u64() {
                        Some(0) => Ok(0),
                        Some(1) => Ok(1),
                        _ => Err("fixture pixel is not binary".to_owned()),
                    })
                    .collect::<Result<Vec<u8>, String>>()?
            } else if let Some(text) = row.as_str() {
                text.bytes()
                    .map(|bit| match bit {
                        b'0' => Ok(0),
                        b'1' => Ok(1),
                        _ => Err("fixture pixel is not binary".to_owned()),
                    })
                    .collect::<Result<Vec<u8>, String>>()?
            } else {
                return Err("fixture row is not an array or binary string".to_owned());
            };
            if bits.len() != width {
                return Err("fixture width does not match row".into());
            }
            Ok(bits)
        })
        .collect::<Result<Vec<Vec<u8>>, String>>()?;
    PixelDocument::from_rows(rows)
}

fn read_fixture(path: &Path) -> Result<PixelDocument, String> {
    fs::read(path)
        .map_err(|error| error.to_string())
        .and_then(|bytes| parse_fixture(&bytes))
}

fn write_fixture(path: &Path, document: &PixelDocument) -> Result<(), String> {
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent).map_err(|error| error.to_string())?;
    }
    fs::write(path, fixture_bytes(document)).map_err(|error| error.to_string())
}

fn write_export(path: &Path, document: &PixelDocument) -> Result<(), String> {
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent).map_err(|error| error.to_string())?;
    }
    let bytes = document.to_vlsb()?;
    fs::write(path, bytes).map_err(|error| error.to_string())
}

impl PixelApp {
    fn new() -> Self {
        Self {
            document: PixelDocument::new(64, 32).expect("valid default canvas"),
            tool: PixelTool::Pencil,
            zoom: 12.0,
            pan: Vec2::ZERO,
            gesture_start: None,
            last_pointer: None,
            status: "Ready".into(),
        }
    }

    fn open_fixture(&mut self) {
        let path = Path::new("target/pixel_slice_fixture.json");
        let result = read_fixture(path);
        match result {
            Ok(document) => {
                self.document = document;
                self.gesture_start = None;
                self.last_pointer = None;
                self.pan = Vec2::ZERO;
                self.status = format!("Opened {}", path.display());
            }
            Err(error) => self.status = format!("Open failed: {error}"),
        }
    }

    fn save_fixture(&mut self) {
        let path = Path::new("target/pixel_slice_fixture.json");
        match write_fixture(path, &self.document) {
            Ok(()) => self.status = format!("Saved {}", path.display()),
            Err(error) => self.status = format!("Save failed: {error}"),
        }
    }

    fn export_bytes(&mut self) {
        let path = Path::new("target/pixel_slice.bin");
        match write_export(path, &self.document) {
            Ok(()) => self.status = format!("Exported {}", path.display()),
            Err(error) => self.status = format!("Export failed: {error}"),
        }
    }

    fn point_from_position(&self, rect: Rect, position: Pos2) -> Option<(i32, i32)> {
        let local = position - rect.min - self.pan;
        let x = (local.x / self.zoom).floor() as i32;
        let y = (local.y / self.zoom).floor() as i32;
        (x >= 0 && y >= 0 && x < self.document.width as i32 && y < self.document.height as i32)
            .then_some((x, y))
    }

    fn draw_canvas(&self, painter: &egui::Painter, rect: Rect) {
        let canvas_min = rect.min + self.pan;
        let canvas_size = Vec2::new(
            self.document.width as f32 * self.zoom,
            self.document.height as f32 * self.zoom,
        );
        let canvas = Rect::from_min_size(canvas_min, canvas_size);
        painter.rect_filled(canvas, 0.0, Color32::from_gray(22));
        for y in 0..self.document.height {
            for x in 0..self.document.width {
                if self.document.pixel(x, y) == 1 {
                    let min = canvas_min + Vec2::new(x as f32 * self.zoom, y as f32 * self.zoom);
                    painter.rect_filled(
                        Rect::from_min_size(min, Vec2::splat(self.zoom - 1.0)),
                        0.0,
                        Color32::WHITE,
                    );
                }
            }
        }
        let grid_color = Color32::from_gray(65);
        for x in 0..=self.document.width {
            let px = canvas_min.x + x as f32 * self.zoom;
            painter.line_segment(
                [Pos2::new(px, canvas_min.y), Pos2::new(px, canvas.max.y)],
                Stroke::new(0.5_f32, grid_color),
            );
        }
        for y in 0..=self.document.height {
            let py = canvas_min.y + y as f32 * self.zoom;
            painter.line_segment(
                [Pos2::new(canvas_min.x, py), Pos2::new(canvas.max.x, py)],
                Stroke::new(0.5_f32, grid_color),
            );
        }
    }

    fn tool_button(ui: &mut egui::Ui, label: &str, selected: bool) -> bool {
        ui.selectable_label(selected, label).clicked()
    }
}

impl eframe::App for PixelApp {
    fn update(&mut self, ctx: &egui::Context, _frame: &mut eframe::Frame) {
        egui::TopBottomPanel::top("toolbar").show(ctx, |ui| {
            ui.horizontal(|ui| {
                ui.label("MonoOLED Rust Pixel Slice");
                if Self::tool_button(ui, "Pencil", self.tool == PixelTool::Pencil) {
                    self.tool = PixelTool::Pencil;
                }
                if Self::tool_button(ui, "Eraser", self.tool == PixelTool::Eraser) {
                    self.tool = PixelTool::Eraser;
                }
                if Self::tool_button(ui, "Line", self.tool == PixelTool::Line) {
                    self.tool = PixelTool::Line;
                }
                if Self::tool_button(ui, "Rectangle", self.tool == PixelTool::Rectangle) {
                    self.tool = PixelTool::Rectangle;
                }
                if ui.button("Undo").clicked() {
                    self.document.undo();
                }
                if ui.button("Redo").clicked() {
                    self.document.redo();
                }
                if ui.button("Open").clicked() {
                    self.open_fixture();
                }
                if ui.button("Save").clicked() {
                    self.save_fixture();
                }
                if ui.button("Export").clicked() {
                    self.export_bytes();
                }
                ui.add(egui::Slider::new(&mut self.zoom, 4.0..=24.0).text("Zoom"));
                ui.label(format!("Pan {:.0},{:.0}", self.pan.x, self.pan.y));
            });
        });

        egui::CentralPanel::default().show(ctx, |ui| {
            let available = ui.available_size();
            let (response, painter) = ui.allocate_painter(available, Sense::click_and_drag());
            self.draw_canvas(&painter, response.rect);

            if response.drag_started()
                && let Some(position) = response.interact_pointer_pos()
            {
                if ui.input(|input| input.pointer.middle_down()) {
                    self.last_pointer = Some(position);
                } else if let Some(point) = self.point_from_position(response.rect, position) {
                    self.gesture_start = Some(point);
                    self.document.begin_gesture();
                    self.document.preview(self.tool, point, point);
                }
            }
            if response.dragged()
                && let Some(position) = response.interact_pointer_pos()
            {
                if ui.input(|input| input.pointer.middle_down()) {
                    if let Some(previous) = self.last_pointer {
                        self.pan += position - previous;
                    }
                    self.last_pointer = Some(position);
                } else if let Some(start) = self.gesture_start
                    && let Some(point) = self.point_from_position(response.rect, position)
                {
                    self.document.preview(self.tool, start, point);
                }
            }
            if response.drag_stopped() {
                self.last_pointer = None;
                if self.gesture_start.take().is_some() {
                    self.document.finish_gesture();
                    self.status = "Gesture committed".into();
                }
            }
        });

        egui::TopBottomPanel::bottom("status").show(ctx, |ui| {
            ui.label(&self.status);
        });
    }
}

fn main() -> eframe::Result {
    let options = eframe::NativeOptions::default();
    eframe::run_native(
        "MonoOLED Rust Pixel Slice",
        options,
        Box::new(|_creation_context| Ok(Box::new(PixelApp::new()))),
    )
}

#[cfg(test)]
mod tests {
    use mono_core::pixel::PixelDocument;

    #[test]
    fn fixture_save_payload_roundtrips_pixel_document() {
        let source = PixelDocument::from_rows(vec![vec![1, 0, 1, 0], vec![0, 1, 0, 1]]).unwrap();
        let payload = super::fixture_bytes(&source);
        let restored = super::parse_fixture(&payload).unwrap();
        assert_eq!(restored.rows(), source.rows());
        assert_eq!(restored.width, source.width);
        assert_eq!(restored.height, source.height);
    }

    #[test]
    fn fixture_parser_rejects_non_binary_rows() {
        let invalid = br#"{"schema_version":1,"width":2,"height":1,"rows":["02"]}"#;
        assert!(super::parse_fixture(invalid).is_err());
    }

    #[test]
    fn fixture_parser_accepts_binary_string_rows() {
        let legacy = br#"{"schema_version":1,"width":4,"height":1,"rows":["0101"]}"#;
        let restored = super::parse_fixture(legacy).unwrap();
        assert_eq!(restored.rows(), vec![vec![0, 1, 0, 1]]);
    }

    #[test]
    fn fixture_file_roundtrip_writes_and_reads_real_bytes() {
        let source = PixelDocument::from_rows(vec![vec![1, 0], vec![0, 1]]).unwrap();
        let path = std::env::temp_dir().join(format!(
            "mono-oled-rust-fixture-{}.json",
            std::process::id()
        ));
        super::write_fixture(&path, &source).unwrap();
        let restored = super::read_fixture(&path).unwrap();
        std::fs::remove_file(&path).unwrap();
        assert_eq!(restored.rows(), source.rows());
    }

    #[test]
    fn export_file_writes_the_document_vlsb_bytes() {
        let source = PixelDocument::from_rows(vec![
            vec![1, 0],
            vec![0, 1],
            vec![1, 1],
            vec![0, 0],
            vec![0, 0],
            vec![0, 0],
            vec![0, 0],
            vec![0, 0],
        ])
        .unwrap();
        let path =
            std::env::temp_dir().join(format!("mono-oled-rust-export-{}.bin", std::process::id()));
        super::write_export(&path, &source).unwrap();
        let bytes = std::fs::read(&path).unwrap();
        std::fs::remove_file(&path).unwrap();
        assert_eq!(bytes, source.to_vlsb().unwrap());
    }
}
