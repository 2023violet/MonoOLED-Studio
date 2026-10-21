//! `--bench <out.json>`: spec §5 interactive budgets measured in the real
//! window, with the G2 method: each input is issued 2 ms after the previous
//! frame finished, and latency runs from the input to the end of the frame
//! that shows it (Slint `RenderingState::AfterRendering`).
//!
//! * cold start: process start → first rendered frame (budget 1 s)
//! * pixel stroke: 256x128 canvas at 8x, pointer move → rendered (p95 ≤ 8 ms)
//! * theme switch: light ↔ dark → rendered (p95 ≤ 50 ms)
//! * UI-thread blocking: longest synchronous handler (≤ 16 ms)
//!
//! `*_render_p95_ms` is the render work of the same frames (BeforeRendering →
//! AfterRendering); the rest of a latency is waiting for the compositor to
//! schedule the frame (vsync pacing).
//!
//! A second stroke series is issued on a free-running 20 ms timer (not frame
//! aligned); it is reported as `stroke_free_running_p95_ms` and includes the
//! wait for the next vsync slot.

use std::cell::RefCell;
use std::path::PathBuf;
use std::rc::Rc;
use std::time::{Duration, Instant};

use mono_core::pixel::PixelDocument;
use serde_json::{Map, Value, json};
use slint::{ComponentHandle, Global};

use crate::app::App;
use crate::{AppModel, MainWindow, PixelModel, Theme};

const STROKES: usize = 300;
const THEMES: usize = 40;

#[derive(Clone, Copy, PartialEq, Eq)]
enum Phase {
    Start,
    Strokes,
    Themes,
    FreeRunning,
    Done,
}

struct Bench {
    phase: Phase,
    step: usize,
    pending: Option<Instant>,
    samples: Vec<f64>,
    /// Render work of the same frames: BeforeRendering -> AfterRendering.
    render: Vec<f64>,
    before: Option<Instant>,
    max_handler: f64,
    results: Map<String, Value>,
}

fn p95(samples: &mut [f64]) -> f64 {
    samples.sort_by(f64::total_cmp);
    let rank = ((samples.len() as f64 - 1.0) * 0.95).round() as usize;
    samples.get(rank).copied().unwrap_or(0.0)
}

fn stroke_point(k: usize) -> (i32, i32) {
    let k = k as i32;
    (8 + (k * 5) % 240, 8 + (k * 3) % 112)
}

/// Issue the next input of the current phase; returns false when the phase ended.
fn issue(bench: &mut Bench, app: &mut App, ui: &MainWindow) -> bool {
    let started = Instant::now();
    match bench.phase {
        Phase::Strokes if bench.step < STROKES => {
            let (x, y) = stroke_point(bench.step);
            bench.pending = Some(Instant::now());
            app.pixel_pointer(if bench.step == 0 { "down" } else { "move" }, x, y, 0);
        }
        Phase::Themes if bench.step < THEMES => {
            let theme = Theme::get(ui);
            bench.pending = Some(Instant::now());
            theme.set_mode(if theme.get_mode() == 0 { 1 } else { 0 });
        }
        _ => return false,
    }
    bench.step += 1;
    bench.max_handler = bench
        .max_handler
        .max(started.elapsed().as_secs_f64() * 1000.0);
    true
}

fn finish_phase(bench: &mut Bench, key: &str) {
    let mut render = std::mem::take(&mut bench.render);
    bench
        .results
        .insert(format!("{key}_render_p95_ms"), json!(p95(&mut render)));
    let mut samples = std::mem::take(&mut bench.samples);
    bench
        .results
        .insert(format!("{key}_samples"), json!(samples.len()));
    bench
        .results
        .insert(format!("{key}_p95_ms"), json!(p95(&mut samples)));
    bench.step = 0;
}

pub fn run(ui: &MainWindow, app: &Rc<RefCell<App>>, out: PathBuf, process_start: Instant) {
    let bench = Rc::new(RefCell::new(Bench {
        phase: Phase::Start,
        step: 0,
        pending: None,
        samples: Vec::new(),
        render: Vec::new(),
        before: None,
        max_handler: 0.0,
        results: Map::new(),
    }));
    let (b, a, weak) = (Rc::clone(&bench), Rc::clone(app), ui.as_weak());
    let _ = ui.window().set_rendering_notifier(move |state, _| {
        if matches!(state, slint::RenderingState::RenderingSetup) {
            b.borrow_mut().results.insert(
                "rendering_setup_ms".into(),
                json!(process_start.elapsed().as_secs_f64() * 1000.0),
            );
            return;
        }
        if matches!(state, slint::RenderingState::BeforeRendering) {
            let mut s = b.borrow_mut();
            if s.phase == Phase::Start && !s.results.contains_key("first_before_rendering_ms") {
                s.results.insert(
                    "first_before_rendering_ms".into(),
                    json!(process_start.elapsed().as_secs_f64() * 1000.0),
                );
            }
            s.before = Some(Instant::now());
            return;
        }
        if !matches!(state, slint::RenderingState::AfterRendering) {
            return;
        }
        let now = Instant::now();
        let mut s = b.borrow_mut();
        if s.phase == Phase::Start {
            let cold = now.duration_since(process_start).as_secs_f64() * 1000.0;
            s.results.insert("cold_start_ms".into(), json!(cold));
            s.phase = Phase::Strokes;
            drop(s);
            // Prepare a 256x128 canvas at 8x, then start the frame-aligned strokes.
            let (b2, a2, w2) = (Rc::clone(&b), Rc::clone(&a), weak.clone());
            slint::Timer::single_shot(Duration::from_millis(200), move || {
                let Some(ui) = w2.upgrade() else { return };
                {
                    let mut app = a2.borrow_mut();
                    AppModel::get(&ui).set_workspace(1);
                    app.workspace = 1;
                    if let Ok(doc) = PixelDocument::new(256, 128) {
                        app.pixel.replace(doc, None, 200);
                    }
                    app.pixel_zoom(3); // combo index 3 = 8x
                    app.refresh_pixel();
                }
                let (b3, a3, w3) = (Rc::clone(&b2), Rc::clone(&a2), w2.clone());
                slint::Timer::single_shot(Duration::from_millis(300), move || {
                    let Some(ui) = w3.upgrade() else { return };
                    issue(&mut b3.borrow_mut(), &mut a3.borrow_mut(), &ui);
                });
            });
            return;
        }
        let Some(started) = s.pending.take() else {
            return;
        };
        s.samples
            .push(now.duration_since(started).as_secs_f64() * 1000.0);
        if let Some(before) = s.before.take() {
            s.render
                .push(now.duration_since(before).as_secs_f64() * 1000.0);
        }
        if s.phase == Phase::FreeRunning {
            return;
        }
        drop(s);
        let (b2, a2, w2) = (Rc::clone(&b), Rc::clone(&a), weak.clone());
        // Like a real pointer stream: the next input arrives just after the frame.
        slint::Timer::single_shot(Duration::from_millis(2), move || {
            let Some(ui) = w2.upgrade() else { return };
            let mut s = b2.borrow_mut();
            let mut app = a2.borrow_mut();
            if issue(&mut s, &mut app, &ui) {
                return;
            }
            match s.phase {
                Phase::Strokes => {
                    app.pixel_pointer("up", 0, 0, 0);
                    finish_phase(&mut s, "stroke");
                    s.phase = Phase::Themes;
                    issue(&mut s, &mut app, &ui);
                }
                Phase::Themes => {
                    finish_phase(&mut s, "theme_switch");
                    s.phase = Phase::FreeRunning;
                    drop(s);
                    drop(app);
                    start_free_running(&b2, &a2, &w2, &out_free(&b2));
                }
                _ => {}
            }
        });
    });
    let out_cell = Rc::new(out);
    bench
        .borrow_mut()
        .results
        .insert("_out".into(), json!(out_cell.display().to_string()));
}

fn out_free(bench: &Rc<RefCell<Bench>>) -> PathBuf {
    PathBuf::from(
        bench
            .borrow()
            .results
            .get("_out")
            .and_then(Value::as_str)
            .unwrap_or_default(),
    )
}

fn start_free_running(
    bench: &Rc<RefCell<Bench>>,
    app: &Rc<RefCell<App>>,
    weak: &slint::Weak<MainWindow>,
    out: &std::path::Path,
) {
    let timer = Rc::new(slint::Timer::default());
    let (b, a, w, t, out) = (
        Rc::clone(bench),
        Rc::clone(app),
        weak.clone(),
        Rc::clone(&timer),
        out.to_path_buf(),
    );
    timer.start(
        slint::TimerMode::Repeated,
        Duration::from_millis(20),
        move || {
            let Some(ui) = w.upgrade() else { return };
            let mut s = b.borrow_mut();
            let stale = s
                .pending
                .is_some_and(|p| p.elapsed() > Duration::from_secs(1));
            if s.pending.is_some() && !stale {
                return;
            }
            s.pending = None;
            if s.step < 120 {
                let (x, y) = stroke_point(STROKES + s.step);
                s.pending = Some(Instant::now());
                s.step += 1;
                a.borrow_mut().pixel_pointer("move", x, y, 0);
                return;
            }
            finish_phase(&mut s, "stroke_free_running");
            s.phase = Phase::Done;
            let max_handler = s.max_handler;
            let mut r = s.results.clone();
            r.remove("_out");
            r.insert("max_handler_ms".into(), json!(max_handler));
            r.insert(
                "canvas".into(),
                json!([
                    PixelModel::get(&ui).get_doc_w(),
                    PixelModel::get(&ui).get_doc_h()
                ]),
            );
            r.insert("zoom".into(), json!(PixelModel::get(&ui).get_zoom()));
            r.insert(
                "method".into(),
                json!("G2: next input 2 ms after AfterRendering; latency input -> AfterRendering"),
            );
            r.insert(
                "build".into(),
                json!(if cfg!(debug_assertions) {
                    "debug"
                } else {
                    "release"
                }),
            );
            let _ = std::fs::write(
                &out,
                serde_json::to_string_pretty(&Value::Object(r)).unwrap_or_default(),
            );
            t.stop();
            // Stay idle briefly so an external probe can read idle memory.
            slint::Timer::single_shot(Duration::from_secs(3), || {
                let _ = slint::quit_event_loop();
            });
        },
    );
    std::mem::forget(timer);
}
