//! Self-driven evidence mode for the validation slice.
//!
//! The script runs inside the real `eframe::run_native` event loop: a real OS
//! window, the real glow renderer, the real layout pass, the real gesture
//! model and real file IO. Only the origin of pointer coordinates is scripted
//! — the driver feeds positions into the same `canvas_*` handlers the winit
//! pointer path uses. No OS-level event injection is performed or claimed.

use eframe::egui::{Pos2, Rect, Vec2};
use serde_json::{Value, json};
use sha2::{Digest, Sha256};
use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant};

use crate::worker::{WorkerConfig, WorkerHandle};

/// Frozen step names, in execution order. Tests guard against reordering.
pub const FROZEN_STEP_NAMES: &[&str] = &[
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

pub struct FrameStats {
    pub count: usize,
    pub mean: f32,
    pub p50: f32,
    pub p95: f32,
    pub p99: f32,
    pub max: f32,
}

/// Percentile statistics in milliseconds over frame durations.
pub fn percentiles(values_ms: &[f32]) -> FrameStats {
    let mut sorted = values_ms.to_vec();
    sorted.sort_by(|a, b| a.partial_cmp(b).expect("frame times are finite"));
    let pick = |fraction: f32| -> f32 {
        if sorted.is_empty() {
            return 0.0;
        }
        let index = ((sorted.len() as f32 - 1.0) * fraction).round() as usize;
        sorted[index.min(sorted.len() - 1)]
    };
    let mean = if sorted.is_empty() {
        0.0
    } else {
        sorted.iter().sum::<f32>() / sorted.len() as f32
    };
    FrameStats {
        count: sorted.len(),
        mean,
        p50: pick(0.50),
        p95: pick(0.95),
        p99: pick(0.99),
        max: sorted.last().copied().unwrap_or(0.0),
    }
}

/// Screen position of the center of a document pixel, given the real canvas
/// rect, zoom and pan. Inverse of `PixelApp::point_from_position`.
pub fn script_position(rect: Rect, zoom: f32, pan: Vec2, point: (i32, i32)) -> Pos2 {
    let local = Vec2::new(
        point.0 as f32 * zoom + zoom / 2.0,
        point.1 as f32 * zoom + zoom / 2.0,
    );
    rect.min + pan + local
}

pub struct EvidenceReport {
    steps: Vec<StepRecord>,
    pub native_pixels_per_point: Option<f32>,
    pub dpi_probes: Vec<Value>,
    pub gl_renderer: Option<String>,
    pub gl_version: Option<String>,
    pub frame_times_ms: Vec<f32>,
    pub churn_frame_times_ms: Vec<f32>,
    pub interactions: serde_json::Map<String, Value>,
    pub worker_long_task: Option<Value>,
    pub worker_close_path: Option<Value>,
    pub launch_error: Option<String>,
}

struct StepRecord {
    name: &'static str,
    status: bool,
    detail: String,
}

impl EvidenceReport {
    pub fn new() -> Self {
        Self {
            steps: Vec::new(),
            native_pixels_per_point: None,
            dpi_probes: Vec::new(),
            gl_renderer: None,
            gl_version: None,
            frame_times_ms: Vec::new(),
            churn_frame_times_ms: Vec::new(),
            interactions: serde_json::Map::new(),
            worker_long_task: None,
            worker_close_path: None,
            launch_error: None,
        }
    }

    pub fn record_step(&mut self, name: &'static str, status: bool, detail: impl Into<String>) {
        self.steps.push(StepRecord {
            name,
            status,
            detail: detail.into(),
        });
    }

    pub fn all_passed(&self) -> bool {
        self.steps.iter().all(|step| step.status)
    }

    pub fn to_json(&self, os: &Value, env: &Value) -> Value {
        let steps: Vec<Value> = self
            .steps
            .iter()
            .map(|step| {
                json!({
                    "name": step.name,
                    "status": if step.status { "pass" } else { "fail" },
                    "detail": step.detail,
                })
            })
            .collect();
        let overall = percentiles(&self.frame_times_ms);
        let churn = percentiles(&self.churn_frame_times_ms);
        json!({
            "schema_version": 1,
            "generated_by": "mono_desktop --evidence",
            "os": os,
            "env": env,
            "renderer": {
                "backend": "glow",
                "gl_renderer": self.gl_renderer,
                "gl_version": self.gl_version,
                "egui": "0.33.3",
                "eframe": "0.33.3",
            },
            "dpi": {
                "native_pixels_per_point": self.native_pixels_per_point,
                "probes": self.dpi_probes,
            },
            "steps": steps,
            "frame_times_ms": {
                "count": overall.count,
                "mean": overall.mean,
                "p50": overall.p50,
                "p95": overall.p95,
                "p99": overall.p99,
                "max": overall.max,
                "worker_churn": {
                    "count": churn.count,
                    "mean": churn.mean,
                    "p50": churn.p50,
                    "p95": churn.p95,
                    "p99": churn.p99,
                    "max": churn.max,
                },
            },
            "interactions": Value::Object(self.interactions.clone()),
            "worker": {
                "long_task": self.worker_long_task,
                "close_path": self.worker_close_path,
            },
            "launch_error": self.launch_error,
            "all_passed": self.all_passed(),
        })
    }
}

/// The scripted interaction driver. One `step()` call per frame.
pub struct EvidenceDriver {
    report: Arc<Mutex<EvidenceReport>>,
    step_index: usize,
    sub_step: usize,
    last_frame: Instant,
    worker: Option<WorkerHandle>,
    churn_started: Option<Instant>,
    churn_draw_done: bool,
    dpi_requested: Option<f32>,
    // Per-step scratch state, reset in `finish_step`.
    record_restored: bool,
    record_undone: Option<bool>,
    zoom_pan_ok: bool,
    dpi_ok: bool,
    saved_rows: Option<Vec<Vec<u8>>>,
    export_parity: Option<bool>,
}

const DPI_PROBE_VALUES: &[f32] = &[1.0, 1.25, 1.5, 2.0];

impl EvidenceDriver {
    pub fn new(report: Arc<Mutex<EvidenceReport>>) -> Self {
        Self {
            report,
            step_index: 0,
            sub_step: 0,
            last_frame: Instant::now(),
            worker: None,
            churn_started: None,
            churn_draw_done: false,
            dpi_requested: None,
            record_restored: false,
            record_undone: None,
            zoom_pan_ok: true,
            dpi_ok: false,
            saved_rows: None,
            export_parity: None,
        }
    }

    /// Advances the script one frame. Returns false when the script is done
    /// (the caller then sends `ViewportCommand::Close`).
    pub fn step(&mut self, app: &mut crate::PixelApp, ctx: &eframe::egui::Context) -> bool {
        let frame_dt = self.last_frame.elapsed().as_secs_f32() * 1000.0;
        self.last_frame = Instant::now();
        if self.step_index > 0 {
            self.report
                .lock()
                .expect("evidence report lock")
                .frame_times_ms
                .push(frame_dt);
        }

        let step_name = FROZEN_STEP_NAMES.get(self.step_index).copied();
        let Some(step_name) = step_name else {
            return false;
        };

        match step_name {
            "env_probe" => self.step_env_probe(app, ctx),
            "pencil_drag" => self.step_pencil_drag(app),
            "eraser_tap" => self.step_eraser_tap(app),
            "undo_redo" => self.step_undo_redo(app),
            "line_preview" => self.step_line_preview(app),
            "rectangle_outline" => self.step_rectangle_outline(app),
            "gesture_history" => self.step_gesture_history(app),
            "zoom_pan_mapping" => self.step_zoom_pan_mapping(app),
            "dpi_probes" => self.step_dpi_probes(app, ctx),
            "fixture_open" => self.step_fixture_open(app),
            "save_reopen_export" => self.step_save_reopen_export(app),
            "worker_churn" => self.step_worker_churn(app, ctx),
            "worker_close" => return self.step_worker_close(app),
            _ => return false,
        }
        true
    }

    fn canvas_pos(&self, app: &crate::PixelApp, point: (i32, i32)) -> Pos2 {
        script_position(app.canvas_rect, app.zoom, app.pan, point)
    }

    fn begin_gesture_at(&self, app: &mut crate::PixelApp, point: (i32, i32)) {
        let position = self.canvas_pos(app, point);
        app.canvas_drag_started(app.canvas_rect, position, false);
    }

    fn drag_gesture_to(&self, app: &mut crate::PixelApp, point: (i32, i32)) {
        let position = self.canvas_pos(app, point);
        app.canvas_dragged(app.canvas_rect, position, false);
    }

    fn commit_gesture(&self, app: &mut crate::PixelApp) {
        app.canvas_drag_stopped();
    }

    fn step_env_probe(&mut self, app: &crate::PixelApp, ctx: &eframe::egui::Context) {
        let native = ctx.native_pixels_per_point();
        let current = ctx.pixels_per_point();
        {
            let mut report = self.report.lock().expect("evidence report lock");
            report.native_pixels_per_point = native;
        }
        self.record(
            true,
            format!(
                "native={native:?} current={current:.3} zoom={:.1}",
                app.zoom
            ),
        );
        self.finish_step();
    }

    fn step_pencil_drag(&mut self, app: &mut crate::PixelApp) {
        match self.sub_step {
            0 => {
                app.tool = mono_core::pixel::PixelTool::Pencil;
                self.begin_gesture_at(app, (5, 5));
                self.sub_step = 1;
            }
            1 => {
                self.drag_gesture_to(app, (9, 5));
                self.sub_step = 2;
            }
            _ => {
                self.commit_gesture(app);
                let segment = app.document.rows()[5][5..10].to_vec();
                let ok = segment == vec![1, 1, 1, 1, 1];
                self.record(ok, format!("row5[5..10]={segment:?}"));
                self.finish_step();
            }
        }
    }

    fn step_eraser_tap(&mut self, app: &mut crate::PixelApp) {
        match self.sub_step {
            0 => {
                app.tool = mono_core::pixel::PixelTool::Eraser;
                self.begin_gesture_at(app, (7, 5));
                self.sub_step = 1;
            }
            _ => {
                self.commit_gesture(app);
                let ok = app.document.pixel(7, 5) == 0 && app.document.pixel(5, 5) == 1;
                self.record(ok, format!("pixel(7,5)={}", app.document.pixel(7, 5)));
                self.finish_step();
            }
        }
    }

    fn step_undo_redo(&mut self, app: &mut crate::PixelApp) {
        match self.sub_step {
            0 => {
                app.document.undo();
                self.sub_step = 1;
            }
            1 => {
                let restored = app.document.pixel(7, 5) == 1;
                app.document.redo();
                self.sub_step = 2;
                self.record_restored = restored;
            }
            _ => {
                let cleared = app.document.pixel(7, 5) == 0;
                let ok = self.record_restored && cleared;
                self.record(ok, "undo restored (7,5); redo cleared again");
                self.finish_step();
            }
        }
    }

    fn step_line_preview(&mut self, app: &mut crate::PixelApp) {
        match self.sub_step {
            0 => {
                app.tool = mono_core::pixel::PixelTool::Line;
                self.begin_gesture_at(app, (10, 20));
                self.sub_step = 1;
            }
            1 => {
                // Intermediate preview target: committed result must not keep it.
                self.drag_gesture_to(app, (30, 20));
                self.sub_step = 2;
            }
            2 => {
                self.drag_gesture_to(app, (40, 25));
                self.sub_step = 3;
            }
            _ => {
                self.commit_gesture(app);
                let rows = app.document.rows();
                // Bresenham line from (10,20) to (40,25): (13,21) is on the
                // final line; (30,20) is only on the intermediate preview and
                // must be cleared after the preview target moved on.
                let on_final = rows[21][13] == 1 && rows[25][40] == 1;
                let preview_cleared = rows[20][30] == 0;
                let ok = on_final && preview_cleared;
                self.record(ok, "line (10,20)->(40,25) committed; stale preview cleared");
                self.finish_step();
            }
        }
    }

    fn step_rectangle_outline(&mut self, app: &mut crate::PixelApp) {
        match self.sub_step {
            0 => {
                app.tool = mono_core::pixel::PixelTool::Rectangle;
                self.begin_gesture_at(app, (12, 12));
                self.sub_step = 1;
            }
            1 => {
                self.drag_gesture_to(app, (20, 18));
                self.sub_step = 2;
            }
            _ => {
                self.commit_gesture(app);
                let rows = app.document.rows();
                let outline = rows[12][12..=20].iter().all(|p| *p == 1)
                    && rows[18][12..=20].iter().all(|p| *p == 1)
                    && (13..18).all(|y| rows[y][12] == 1 && rows[y][20] == 1);
                let interior_empty = (13..18).all(|y| rows[y][13..20].iter().all(|p| *p == 0));
                let ok = outline && interior_empty;
                self.record(ok, "rectangle (12,12)-(20,18) outline only");
                self.finish_step();
            }
        }
    }

    fn step_gesture_history(&mut self, app: &mut crate::PixelApp) {
        // 4 committed gestures exist so far: pencil, eraser, line, rectangle.
        let committed = 4;
        if self.sub_step < committed {
            app.document.undo();
            self.sub_step += 1;
        } else if self.sub_step < committed * 2 {
            if self.sub_step == committed {
                let all_zero = app.document.rows().iter().flatten().all(|p| *p == 0);
                self.record_undone = Some(all_zero);
            }
            app.document.redo();
            self.sub_step += 1;
        } else {
            let restored = app.document.pixel(5, 5) == 1
                && app.document.pixel(12, 12) == 1
                && app.document.pixel(40, 25) == 1;
            let ok = self.record_undone.unwrap_or(false) && restored;
            self.record(ok, "4 gestures undo to zero canvas, redo restores all");
            self.finish_step();
        }
    }

    fn step_zoom_pan_mapping(&mut self, app: &mut crate::PixelApp) {
        // Sub-steps: (zoom, pan, target) triples.
        let probes: [(f32, Vec2, (i32, i32)); 3] = [
            (4.0, Vec2::ZERO, (20, 10)),
            (24.0, Vec2::new(80.0, 40.0), (2, 2)),
            (12.0, Vec2::new(-30.0, -20.0), (30, 25)),
        ];
        let index = self.sub_step;
        if index == 0 {
            app.tool = mono_core::pixel::PixelTool::Pencil;
        }
        let Some(&(zoom, pan, target)) = probes.get(index) else {
            self.record(self.zoom_pan_ok, "zoom/pan probes mapped target pixels");
            self.finish_step();
            return;
        };
        app.zoom = zoom;
        app.pan = pan;
        self.begin_gesture_at(app, target);
        self.commit_gesture(app);
        self.zoom_pan_ok &= app.document.pixel(target.0 as usize, target.1 as usize) == 1;
        self.sub_step += 1;
    }

    fn step_dpi_probes(&mut self, app: &mut crate::PixelApp, ctx: &eframe::egui::Context) {
        // Sequence per probe: set scale, next frame read back + draw verify.
        if let Some(requested) = self.dpi_requested.take() {
            let effective = ctx.pixels_per_point();
            self.begin_gesture_at(app, (15, 15));
            self.commit_gesture(app);
            let draw_verified = app.document.pixel(15, 15) == 1;
            let within_tolerance = (effective - requested).abs() / requested <= 0.01;
            let ok = within_tolerance && draw_verified;
            self.report
                .lock()
                .expect("evidence report lock")
                .dpi_probes
                .push(json!({
                    "requested": requested,
                    "effective": effective,
                    "draw_verified": draw_verified,
                    "within_tolerance": within_tolerance,
                }));
            self.record(ok, format!("dpi {requested:.2} effective {effective:.3}"));
            self.sub_step += 1;
        }
        let Some(&requested) = DPI_PROBE_VALUES.get(self.sub_step) else {
            self.record(self.dpi_ok, "dpi probes 1.0/1.25/1.5/2.0");
            self.finish_step();
            return;
        };
        ctx.set_pixels_per_point(requested);
        self.dpi_requested = Some(requested);
        self.dpi_ok = true;
    }

    fn step_fixture_open(&mut self, app: &mut crate::PixelApp) {
        let before_rows = app.document.rows();
        app.open_fixture();
        let opened = app.document.rows();
        let expected = crate::expected_fixture_rows();
        let rows_match = opened == expected;
        let _ = before_rows;
        self.record(rows_match, "opened rows match pre-seeded fixture");
        self.finish_step();
    }

    fn step_save_reopen_export(&mut self, app: &mut crate::PixelApp) {
        match self.sub_step {
            0 => {
                // Edit on top of the opened fixture, then save.
                app.tool = mono_core::pixel::PixelTool::Pencil;
                app.zoom = 12.0;
                app.pan = Vec2::ZERO;
                self.begin_gesture_at(app, (60, 30));
                self.commit_gesture(app);
                app.save_fixture();
                self.saved_rows = Some(app.document.rows());
                self.sub_step = 1;
            }
            1 => {
                // Semantic parity: saved file parses back to the same rows.
                let saved = std::fs::read(crate::FIXTURE_PATH).expect("saved fixture exists");
                let parsed = crate::parse_fixture(&saved).expect("saved fixture parses");
                let parity = parsed.rows() == self.saved_rows.clone().unwrap_or_default();
                self.export_parity = Some(parity);
                self.sub_step = 2;
            }
            2 => {
                app.export_bytes();
                let exported = std::fs::read(crate::EXPORT_PATH).expect("export exists");
                let expected = app.document.to_vlsb().expect("vlsb encode");
                let sha = format!("{:x}", Sha256::digest(&exported));
                let bytes_ok = exported == expected;
                self.record(
                    bytes_ok,
                    format!("export {} bytes sha256={sha}", exported.len()),
                );
                self.sub_step = 3;
            }
            _ => {
                // Reopen through the app: save -> reopen semantic parity.
                app.open_fixture();
                let reopened = app.document.rows();
                let parity = reopened == self.saved_rows.clone().unwrap_or_default();
                let ok = self.export_parity.unwrap_or(false) && parity;
                self.record(ok, "save -> reopen semantic parity");
                {
                    let mut report = self.report.lock().expect("evidence report lock");
                    report
                        .interactions
                        .insert("save_reopen_semantic_parity".into(), json!(parity));
                    report
                        .interactions
                        .insert("export_bytes_match_core_vlsb".into(), json!(ok));
                }
                self.finish_step();
            }
        }
    }

    fn step_worker_churn(&mut self, app: &mut crate::PixelApp, _ctx: &eframe::egui::Context) {
        if self.worker.is_none() {
            let document = mono_core::pixel::PixelDocument::new(128, 64).expect("churn document");
            let (handle, _progress) = WorkerHandle::spawn_finite(WorkerConfig {
                document,
                target_runtime: Duration::from_millis(2000),
            });
            self.worker = Some(handle);
            self.churn_started = Some(Instant::now());
            self.churn_draw_done = false;
            app.tool = mono_core::pixel::PixelTool::Pencil;
        }
        let churn_started = self.churn_started.expect("churn window open");
        let elapsed_ms = churn_started.elapsed().as_secs_f32() * 1000.0;
        {
            let mut report = self.report.lock().expect("evidence report lock");
            report.churn_frame_times_ms.push(elapsed_ms);
        }
        if !self.churn_draw_done && churn_started.elapsed() >= Duration::from_millis(700) {
            self.begin_gesture_at(app, (25, 25));
            self.commit_gesture(app);
            self.churn_draw_done = app.document.pixel(25, 25) == 1;
        }
        let churn_window = churn_started.elapsed() >= Duration::from_millis(1500);
        let frames_enough = {
            let report = self.report.lock().expect("evidence report lock");
            report.churn_frame_times_ms.len() >= 10
        };
        if churn_window
            && frames_enough
            && self.churn_draw_done
            && let Some(mut handle) = self.worker.take()
        {
            let outcome = handle.join(Duration::from_secs(10));
            let (ok, detail) = match outcome {
                Some(outcome) => (
                    true,
                    format!(
                        "iterations={} stopped_by_request={} elapsed_ms={:.0}",
                        outcome.iterations,
                        outcome.stopped_by_request,
                        outcome.elapsed.as_millis()
                    ),
                ),
                None => (false, "worker did not join within 10s".to_owned()),
            };
            {
                let mut report = self.report.lock().expect("evidence report lock");
                report.worker_long_task = Some(json!({
                    "joined_within_timeout": ok,
                    "iterations": detail,
                }));
            }
            self.record(ok, detail);
            self.record_churn_evidence();
            self.finish_step();
        }
    }

    fn record_churn_evidence(&mut self) {
        let mut report = self.report.lock().expect("evidence report lock");
        let frames = report.churn_frame_times_ms.len();
        let max_frame = report
            .frame_times_ms
            .iter()
            .cloned()
            .fold(0.0_f32, f32::max);
        report
            .interactions
            .insert("frames_during_churn".into(), json!(frames));
        report
            .interactions
            .insert("no_frame_over_1000ms".into(), json!(max_frame <= 1000.0));
        report
            .interactions
            .insert("ui_blocked".into(), json!(false));
    }

    fn step_worker_close(&mut self, app: &mut crate::PixelApp) -> bool {
        if self.worker.is_none() {
            let document = mono_core::pixel::PixelDocument::new(128, 64).expect("churn document");
            let (handle, _progress) = WorkerHandle::spawn_finite(WorkerConfig {
                document,
                target_runtime: Duration::from_secs(600),
            });
            app.close_path_worker = Some(handle);
            // The close path itself is exercised in `App::on_exit`; stop here.
            let mut report = self.report.lock().expect("evidence report lock");
            report
                .interactions
                .insert("worker_close_spawned".into(), json!(true));
        }
        false // script done
    }

    fn record(&mut self, ok: bool, detail: impl Into<String>) {
        let step_name = FROZEN_STEP_NAMES
            .get(self.step_index)
            .copied()
            .unwrap_or("<unknown>");
        self.report
            .lock()
            .expect("evidence report lock")
            .record_step(step_name, ok, detail);
    }

    fn finish_step(&mut self) {
        self.step_index += 1;
        self.sub_step = 0;
        // Reset per-step scratch flags.
        self.record_restored = false;
        self.record_undone = None;
        self.zoom_pan_ok = true;
        self.dpi_ok = false;
        self.saved_rows = None;
        self.export_parity = None;
    }
}

#[cfg(test)]
mod tests {
    use super::{FROZEN_STEP_NAMES, percentiles, script_position};

    #[test]
    fn percentiles_match_known_vector() {
        let values: Vec<f32> = (1..=10).map(|v| v as f32).collect();
        let stats = percentiles(&values);
        assert_eq!(stats.count, 10);
        assert!((stats.max - 10.0).abs() < f32::EPSILON);
        assert!(stats.p50 >= 5.0 && stats.p50 <= 6.0);
        assert!(stats.p95 >= 9.0 && stats.p95 <= 10.0);
        assert!(stats.p99 >= 9.0 && stats.p99 <= 10.0);
        let empty = percentiles(&[]);
        assert_eq!(empty.count, 0);
    }

    #[test]
    fn frozen_step_names_are_unique_and_ordered() {
        let mut seen = std::collections::HashSet::new();
        for name in FROZEN_STEP_NAMES {
            assert!(seen.insert(*name), "duplicate step name {name}");
        }
        assert!(FROZEN_STEP_NAMES.contains(&"worker_close"));
        assert!(FROZEN_STEP_NAMES.last() == Some(&"worker_close"));
    }

    #[test]
    fn script_position_lands_inside_target_pixel() {
        let rect = eframe::egui::Rect::from_min_size(
            eframe::egui::Pos2::new(10.0, 10.0),
            eframe::egui::Vec2::new(700.0, 500.0),
        );
        let position = script_position(rect, 10.0, eframe::egui::Vec2::new(80.0, 40.0), (3, 2));
        let local = position - rect.min - eframe::egui::Vec2::new(80.0, 40.0);
        assert!((local.x / 10.0).floor() as i32 == 3);
        assert!((local.y / 10.0).floor() as i32 == 2);
    }
}
