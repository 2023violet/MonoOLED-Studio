mod evidence;
mod worker;

use eframe::egui::{self, Color32, Pos2, Rect, Sense, Stroke, Vec2};
use mono_core::pixel::{PixelDocument, PixelTool};
use serde_json::{Value, json};
use std::fs;
use std::path::{Path, PathBuf};
use std::sync::{Arc, Mutex};
use std::time::Duration;

/// Fixture and export paths stay validation artifacts under `target/`.
pub const FIXTURE_PATH: &str = "target/pixel_slice_fixture.json";
pub const EXPORT_PATH: &str = "target/pixel_slice.bin";

struct PixelApp {
    document: PixelDocument,
    tool: PixelTool,
    zoom: f32,
    pan: Vec2,
    gesture_start: Option<(i32, i32)>,
    last_pointer: Option<Pos2>,
    status: String,
    canvas_rect: Rect,
    evidence: Option<evidence::EvidenceDriver>,
    close_path_worker: Option<worker::WorkerHandle>,
    evidence_report: Option<Arc<Mutex<evidence::EvidenceReport>>>,
}

/// Rows pre-seeded into the fixture before an evidence run.
pub fn expected_fixture_rows() -> Vec<Vec<u8>> {
    (0..32)
        .map(|y| {
            (0..64)
                .map(|x| u8::from((x * 31 + y * 17) % 5 == 0 && !(x == 0 && y == 0)))
                .collect()
        })
        .collect()
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
    fn new(evidence: Option<evidence::EvidenceDriver>) -> Self {
        Self {
            document: PixelDocument::new(64, 32).expect("valid default canvas"),
            tool: PixelTool::Pencil,
            zoom: 12.0,
            pan: Vec2::ZERO,
            gesture_start: None,
            last_pointer: None,
            status: "Ready".into(),
            canvas_rect: Rect::ZERO,
            evidence,
            close_path_worker: None,
            evidence_report: None,
        }
    }

    /// Shared interaction entry points: both the real winit pointer path in
    /// `update()` and the evidence driver call these, so scripted evidence
    /// exercises the same gesture model the mouse does.
    pub fn canvas_drag_started(&mut self, rect: Rect, position: Pos2, middle_down: bool) {
        if middle_down {
            self.last_pointer = Some(position);
        } else if let Some(point) = self.point_from_position(rect, position) {
            self.gesture_start = Some(point);
            self.document.begin_gesture();
            self.document.preview(self.tool, point, point);
        }
    }

    pub fn canvas_dragged(&mut self, rect: Rect, position: Pos2, middle_down: bool) {
        if middle_down {
            if let Some(previous) = self.last_pointer {
                self.pan += position - previous;
            }
            self.last_pointer = Some(position);
        } else if let Some(start) = self.gesture_start
            && let Some(point) = self.point_from_position(rect, position)
        {
            self.document.preview(self.tool, start, point);
        }
    }

    pub fn canvas_drag_stopped(&mut self) {
        self.last_pointer = None;
        if self.gesture_start.take().is_some() {
            self.document.finish_gesture();
            self.status = "Gesture committed".into();
        }
    }

    fn open_fixture(&mut self) {
        let path = Path::new(FIXTURE_PATH);
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
        let path = Path::new(FIXTURE_PATH);
        match write_fixture(path, &self.document) {
            Ok(()) => self.status = format!("Saved {}", path.display()),
            Err(error) => self.status = format!("Save failed: {error}"),
        }
    }

    fn export_bytes(&mut self) {
        let path = Path::new(EXPORT_PATH);
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
            self.canvas_rect = response.rect;
            self.draw_canvas(&painter, response.rect);

            let middle_down = ui.input(|input| input.pointer.middle_down());
            if response.drag_started()
                && let Some(position) = response.interact_pointer_pos()
            {
                self.canvas_drag_started(response.rect, position, middle_down);
            }
            if response.dragged()
                && let Some(position) = response.interact_pointer_pos()
            {
                self.canvas_dragged(response.rect, position, middle_down);
            }
            if response.drag_stopped() {
                self.canvas_drag_stopped();
            }
        });

        if let Some(mut driver) = self.evidence.take() {
            let continues = driver.step(self, ctx);
            if continues {
                ctx.request_repaint_after(Duration::ZERO);
                self.evidence = Some(driver);
            } else {
                // Script done: close the real window so `run_native` returns
                // and the caller can write the evidence report.
                ctx.send_viewport_cmd(egui::ViewportCommand::Close);
            }
        }

        egui::TopBottomPanel::bottom("status").show(ctx, |ui| {
            ui.label(&self.status);
        });
    }

    fn on_exit(&mut self, _gl: Option<&eframe::glow::Context>) {
        // Bounded worker shutdown on the real close path: stop signal then
        // join with a 5 s timeout, recorded into the shared evidence report.
        if let Some(handle) = self.close_path_worker.take() {
            let started = std::time::Instant::now();
            let joined = handle.request_stop_and_join(Duration::from_secs(5));
            let elapsed_ms = started.elapsed().as_millis() as u64;
            if let Some(report) = self.evidence_report.as_ref() {
                let mut report = report.lock().expect("evidence report lock");
                report.worker_close_path = Some(match joined {
                    Some(outcome) => serde_json::json!({
                        "joined_within_timeout": true,
                        "elapsed_ms": elapsed_ms,
                        "iterations": outcome.iterations,
                    }),
                    None => serde_json::json!({
                        "joined_within_timeout": false,
                        "elapsed_ms": elapsed_ms,
                    }),
                });
            }
        }
    }
}

fn main() -> eframe::Result {
    let mut args = std::env::args().skip(1);
    let evidence_path = if let Some(flag) = args.next()
        && flag == "--evidence"
    {
        Some(
            args.next()
                .map(PathBuf::from)
                .unwrap_or_else(|| PathBuf::from("target/evidence.json")),
        )
    } else {
        None
    };

    let report = Arc::new(Mutex::new(evidence::EvidenceReport::new()));
    let run_evidence = evidence_path.is_some();
    let driver = run_evidence.then(|| evidence::EvidenceDriver::new(Arc::clone(&report)));
    let shared_report = run_evidence.then(|| Arc::clone(&report));
    let main_report = Arc::clone(&report);

    if evidence_path.is_some() {
        // Pre-seed the fixture so open/save/reopen evidence is deterministic.
        let document = PixelDocument::from_rows(expected_fixture_rows()).expect("seed fixture");
        let path = Path::new(FIXTURE_PATH);
        if let Some(parent) = path.parent() {
            fs::create_dir_all(parent).expect("target directory");
        }
        fs::write(path, fixture_bytes(&document)).expect("pre-seed fixture");
    }

    let options = eframe::NativeOptions {
        viewport: egui::ViewportBuilder::default().with_inner_size([900.0, 600.0]),
        ..Default::default()
    };
    let run_result = eframe::run_native(
        "MonoOLED Rust Pixel Slice",
        options,
        Box::new(move |cc| {
            if run_evidence && let Some(gl) = &cc.gl {
                use eframe::glow::HasContext as _;
                // SAFETY: glow context parameters are queried between
                // frames on the main thread; no concurrent GL use here.
                let (gl_renderer, gl_version) = unsafe {
                    (
                        gl.get_parameter_string(eframe::glow::RENDERER),
                        gl.get_parameter_string(eframe::glow::VERSION),
                    )
                };
                let mut report = report.lock().expect("evidence report lock");
                report.gl_renderer = Some(gl_renderer);
                report.gl_version = Some(gl_version);
            }
            let mut app = PixelApp::new(driver);
            app.evidence_report = shared_report;
            Ok(Box::new(app))
        }),
    );

    if let Some(path) = &evidence_path {
        if let Err(error) = &run_result {
            main_report
                .lock()
                .expect("evidence report lock")
                .launch_error = Some(error.to_string());
        }
        let os = json!({
            "platform": std::env::consts::OS,
            "family": std::env::consts::FAMILY,
        });
        let env = json!({
            "DISPLAY": std::env::var("DISPLAY").ok(),
            "WAYLAND_DISPLAY": std::env::var("WAYLAND_DISPLAY").ok(),
            "WINIT_UNIX_BACKEND": std::env::var("WINIT_UNIX_BACKEND").ok(),
            "LIBGL_ALWAYS_SOFTWARE": std::env::var("LIBGL_ALWAYS_SOFTWARE").ok(),
        });
        let payload = main_report
            .lock()
            .expect("evidence report lock")
            .to_json(&os, &env);
        if let Some(parent) = path.parent() {
            fs::create_dir_all(parent).expect("evidence directory");
        }
        fs::write(
            path,
            serde_json::to_vec_pretty(&payload).expect("evidence JSON"),
        )
        .expect("evidence report write");
        println!("Evidence report: {}", path.display());
        if !payload["all_passed"].as_bool().unwrap_or(false) {
            std::process::exit(2);
        }
    }
    if let Err(error) = run_result {
        // Surface launch failures after the report was written so the
        // evidence JSON explains the nonzero exit.
        eprintln!("Launch error: {error}");
        std::process::exit(1);
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use crate::evidence::{FROZEN_STEP_NAMES, percentiles, script_position};
    use crate::worker::{WorkerConfig, WorkerHandle};
    use eframe::egui;
    use mono_core::pixel::PixelDocument;

    #[test]
    fn finite_worker_completes_and_reports_digest() {
        let (mut handle, _progress) = WorkerHandle::spawn_finite(WorkerConfig {
            document: PixelDocument::new(8, 8).unwrap(),
            target_runtime: std::time::Duration::from_millis(300),
        });
        let outcome = handle.join(std::time::Duration::from_secs(10)).unwrap();
        assert!(outcome.iterations > 0);
        assert_eq!(outcome.final_encode_sha256.len(), 64);
    }

    #[test]
    fn stoppable_worker_joins_quickly_after_stop() {
        let (handle, _progress) = WorkerHandle::spawn_finite(WorkerConfig {
            document: PixelDocument::new(8, 8).unwrap(),
            target_runtime: std::time::Duration::from_secs(600),
        });
        let started = std::time::Instant::now();
        let outcome = handle
            .request_stop_and_join(std::time::Duration::from_secs(5))
            .unwrap();
        assert!(started.elapsed() < std::time::Duration::from_secs(5));
        assert!(outcome.iterations > 0);
    }

    #[test]
    fn worker_progress_channel_never_blocks_the_worker() {
        let (mut handle, progress) = WorkerHandle::spawn_finite(WorkerConfig {
            document: PixelDocument::new(8, 8).unwrap(),
            target_runtime: std::time::Duration::from_millis(200),
        });
        // Never drain the progress receiver: try_send must drop progress
        // instead of blocking the worker loop.
        let outcome = handle.join(std::time::Duration::from_secs(10)).unwrap();
        assert!(outcome.iterations > 0);
        drop(progress);
    }

    #[test]
    fn percentiles_match_known_vector() {
        let values = vec![1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0];
        let stats = percentiles(&values);
        assert!((stats.max - 10.0).abs() < f32::EPSILON);
        assert!(stats.p50 >= 5.0 && stats.p50 <= 6.0);
        assert!(stats.p95 >= 9.0 && stats.p95 <= 10.0);
        assert!(stats.p99 >= 9.0 && stats.p99 <= 10.0);
    }

    #[test]
    fn report_aggregation_flips_all_passed_on_single_failed_step() {
        let mut report = crate::evidence::EvidenceReport::new();
        report.record_step("pencil_drag", true, "ok");
        assert!(report.all_passed());
        report.record_step("undo", false, "row mismatch");
        assert!(!report.all_passed());
    }

    #[test]
    fn script_step_names_are_frozen_in_order() {
        let expected: Vec<&str> = vec![
            "env_probe",
            "pencil_drag",
            "eraser_tap",
            "undo_redo",
            "line_preview",
            "rectangle_outline",
            "gesture_history",
            "zoom_pan_mapping",
            "dpi_probes",
            "fixture_open",
            "save_reopen_export",
            "worker_churn",
            "worker_close",
        ];
        assert_eq!(FROZEN_STEP_NAMES, expected.as_slice());
    }

    #[test]
    fn point_from_position_maps_with_nonzero_pan() {
        let mut app = super::PixelApp::new(None);
        app.zoom = 10.0;
        app.pan = egui::Vec2::new(80.0, 40.0);
        let rect =
            egui::Rect::from_min_size(egui::Pos2::new(10.0, 10.0), egui::Vec2::new(700.0, 500.0));
        let position = script_position(rect, app.zoom, app.pan, (3, 2));
        assert_eq!(app.point_from_position(rect, position), Some((3, 2)));
    }

    #[test]
    fn script_position_round_trips_point_from_position() {
        let mut app = super::PixelApp::new(None);
        app.zoom = 17.0;
        app.pan = egui::Vec2::new(-25.0, 15.0);
        let rect =
            egui::Rect::from_min_size(egui::Pos2::new(0.0, 0.0), egui::Vec2::new(800.0, 600.0));
        for point in [(0, 0), (5, 5), (31, 17), (63, 31)] {
            let position = script_position(rect, app.zoom, app.pan, point);
            assert_eq!(app.point_from_position(rect, position), Some(point));
        }
    }

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
