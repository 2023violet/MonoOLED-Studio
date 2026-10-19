//! G2 spike (throwaway): self-driving Slint benchmark for MonoOLED stress scenarios.

use std::cell::RefCell;
use std::rc::Rc;
use std::time::{Duration, Instant};

use slint::{Image, Model, Rgba8Pixel, SharedPixelBuffer, Timer, TimerMode, VecModel};

slint::slint! {
    import { ScrollView, ListView } from "std-widgets.slint";

    export struct Item { x: length, y: length, w: length, h: length }

    export component Bench inherits Window {
        title: "MonoOLED G2 spike — Slint";
        preferred-width: 1280px;
        preferred-height: 900px;
        in property <image> canvas;
        in property <string> code;
        in property <[Item]> items;
        in property <[string]> lines;
        in property <int> phase;
        VerticalLayout {
            Rectangle {
                height: 1040px;
                background: #07080a;
                if phase == 0: Image {
                    source: canvas;
                    width: 2048px;
                    height: 1024px;
                    image-rendering: pixelated;
                }
                if phase == 1: ScrollView {
                    Text { text: code; font-family: "Consolas"; font-size: 12px; color: #cdcdcd; }
                }
                if phase == 3: ListView {
                    for line in lines: Text { text: line; font-family: "Consolas"; font-size: 12px; color: #cdcdcd; height: 15px; }
                }
                if phase == 2: Rectangle {
                    for item in items: Rectangle {
                        x: item.x; y: item.y; width: item.w; height: item.h;
                        background: #121212;
                        border-color: #57c1ff; border-width: 1px;
                    }
                }
            }
        }
    }
}

#[derive(Default)]
struct Samples(Vec<f64>);

impl Samples {
    fn summary(&self) -> String {
        let mut v = self.0.clone();
        v.sort_by(f64::total_cmp);
        let pick = |q: f64| v.get(((v.len() as f64 - 1.0) * q).round() as usize).copied().unwrap_or(0.0);
        format!("{{\"n\":{},\"p50_ms\":{:.3},\"p95_ms\":{:.3},\"max_ms\":{:.3}}}", v.len(), pick(0.5), pick(0.95), pick(1.0))
    }
}

fn private_bytes() -> u64 {
    #[cfg(windows)]
    {
        #[repr(C)]
        #[derive(Default)]
        struct Counters { cb: u32, faults: u32, peak_ws: usize, ws: usize, qp: usize, q: usize, qpnp: usize, qnp: usize, pagefile: usize, peak_pagefile: usize, private: usize }
        unsafe extern "system" {
            fn GetCurrentProcess() -> isize;
            fn K32GetProcessMemoryInfo(process: isize, counters: *mut Counters, cb: u32) -> i32;
        }
        let mut c = Counters { cb: std::mem::size_of::<Counters>() as u32, ..Default::default() };
        // SAFETY: valid pointer to a correctly sized PROCESS_MEMORY_COUNTERS_EX.
        unsafe { K32GetProcessMemoryInfo(GetCurrentProcess(), &mut c, c.cb) };
        c.private as u64
    }
    #[cfg(not(windows))]
    {
        std::fs::read_to_string("/proc/self/statm").ok().and_then(|s| s.split_whitespace().nth(1)?.parse::<u64>().ok()).map(|p| p * 4096).unwrap_or(0)
    }
}

fn code_text() -> String {
    let mut text = String::from("#pragma once\n#include <stdint.h>\n\nstatic const uint8_t frames[] = {\n");
    let mut n = 0u32;
    while text.len() < 256 * 1024 {
        text.push_str("    ");
        for _ in 0..16 {
            text.push_str(&format!("0x{:02X}, ", (n * 37 % 251) as u8));
            n += 1;
        }
        text.push('\n');
    }
    text.push_str("};\n");
    text
}

struct State {
    pixels: SharedPixelBuffer<Rgba8Pixel>,
    step: usize,
    pending: Option<Instant>,
    canvas: Samples,
    text_first_frame: f64,
    scene: Samples,
    idle_private: u64,
    started: Instant,
}

fn main() {
    let out = std::env::args().nth(1).unwrap_or_else(|| "slint-report.json".into());
    let app = Bench::new().expect("window");
    let pixels = SharedPixelBuffer::<Rgba8Pixel>::new(256, 128);
    app.set_canvas(Image::from_rgba8(pixels.clone()));
    let items: Rc<VecModel<Item>> = Rc::new(VecModel::from(
        (0..50).map(|i| Item { x: (20 + (i % 10) * 110) as f32, y: (20 + (i / 10) * 150) as f32, w: 90.0, h: 120.0 }).collect::<Vec<_>>(),
    ));
    app.set_items(items.clone().into());
    let state = Rc::new(RefCell::new(State {
        pixels,
        step: 0,
        pending: None,
        canvas: Samples::default(),
        text_first_frame: 0.0,
        scene: Samples::default(),
        idle_private: 0,
        started: Instant::now(),
    }));

    let weak = app.as_weak();
    let st = state.clone();
    let model = items.clone();
    let out_path = out.clone();
    let notifier = app.window()
        .set_rendering_notifier(move |rendering, _| {
            if !matches!(rendering, slint::RenderingState::AfterRendering) {
                return;
            }
            let mut s = st.borrow_mut();
            let Some(t0) = s.pending.take() else { return };
            let ms = t0.elapsed().as_secs_f64() * 1000.0;
            let step = s.step;
            let app = weak.upgrade().expect("app");
            match step {
                0..400 => s.canvas.0.push(ms),
                400 => s.text_first_frame = ms,
                401..601 => s.scene.0.push(ms),
                _ => {}
            }
            s.step += 1;
            let next = s.step;
            drop(s);
            let st2 = st.clone();
            let model = model.clone();
            let out_path = out_path.clone();
            // Schedule the next input after this frame, like a real pointer event stream.
            Timer::single_shot(Duration::from_millis(2), move || {
                let mut s = st2.borrow_mut();
                match next {
                    1..400 => {
                        let i = next % 256;
                        let j = (next / 2) % 128;
                        let mut buf = s.pixels.clone();
                        buf.make_mut_slice()[j * 256 + i] = Rgba8Pixel { r: 255, g: 255, b: 255, a: 255 };
                        s.pixels = buf.clone();
                        s.pending = Some(Instant::now());
                        app.set_canvas(Image::from_rgba8(buf));
                    }
                    400 => {
                        s.pending = Some(Instant::now());
                        if std::env::var("SPIKE_TEXT").as_deref() == Ok("plain") {
                            app.set_phase(1);
                            app.set_code(code_text().into());
                        } else {
                            let lines: Vec<slint::SharedString> = code_text().lines().map(Into::into).collect();
                            app.set_lines(Rc::new(VecModel::from(lines)).into());
                            app.set_phase(3);
                        }
                    }
                    401 => {
                        s.pending = Some(Instant::now());
                        app.set_phase(2);
                    }
                    402..601 => {
                        s.pending = Some(Instant::now());
                        for row in 0..model.row_count() {
                            let mut item = model.row_data(row).expect("row");
                            item.x += 1.0;
                            model.set_row_data(row, item);
                        }
                    }
                    _ => {
                        let idle = s.idle_private;
                        let report = format!(
                            "{{\"framework\":\"slint 1.18.1\",\"text_mode\":\"{}\",\"backend\":\"{}\",\"idle_private_bytes\":{},\"canvas_stroke\":{},\"text_256k_first_frame_ms\":{:.3},\"scene_50_drag\":{},\"total_s\":{:.2}}}\n",
                            if std::env::var("SPIKE_TEXT").as_deref() == Ok("plain") { "plain Text" } else { "ListView lines" },
                            std::env::var("SLINT_BACKEND").unwrap_or_else(|_| "default".into()),
                            idle,
                            s.canvas.summary(),
                            s.text_first_frame,
                            s.scene.summary(),
                            s.started.elapsed().as_secs_f64()
                        );
                        std::fs::write(&out_path, report).expect("report");
                        let _ = slint::quit_event_loop();
                        return;
                    }
                }
                drop(s);
                app.window().request_redraw();
            });
        });
    if notifier.is_err() {
        // Software renderer: no rendering notifier. Drive the same workload on a 16 ms
        // timer and report wall time, which proves the fallback renders and stays responsive.
        let weak = app.as_weak();
        let started = Instant::now();
        let out_path = out.clone();
        let model = items.clone();
        let counter = Rc::new(RefCell::new(0usize));
        let timer = Box::leak(Box::new(Timer::default()));
        timer.start(TimerMode::Repeated, Duration::from_millis(16), move || {
            let app = weak.upgrade().expect("app");
            let mut n = counter.borrow_mut();
            *n += 1;
            match *n {
                1..200 => {
                    let mut buf = SharedPixelBuffer::<Rgba8Pixel>::new(256, 128);
                    buf.make_mut_slice()[*n] = Rgba8Pixel { r: 255, g: 255, b: 255, a: 255 };
                    app.set_canvas(Image::from_rgba8(buf));
                }
                200 => { app.set_phase(1); app.set_code(code_text().into()); }
                201 => app.set_phase(2),
                202..300 => {
                    for row in 0..model.row_count() {
                        let mut item = model.row_data(row).expect("row");
                        item.x += 1.0;
                        model.set_row_data(row, item);
                    }
                }
                _ => {
                    let report = format!("{{\"framework\":\"slint 1.18.1\",\"backend\":\"software (no rendering notifier)\",\"idle_private_bytes\":{},\"steps\":300,\"expected_s\":4.8,\"wall_s\":{:.2}}}
", private_bytes(), started.elapsed().as_secs_f64());
                    std::fs::write(&out_path, report).expect("report");
                    let _ = slint::quit_event_loop();
                }
            }
        });
        app.run().expect("run");
        return;
    }

    // Measure idle memory after the window settled, then start the first stroke.
    let st = state.clone();
    let weak = app.as_weak();
    let kick = Timer::default();
    kick.start(TimerMode::SingleShot, Duration::from_millis(1500), move || {
        let mut s = st.borrow_mut();
        s.idle_private = private_bytes();
        s.pending = Some(Instant::now());
        drop(s);
        if let Some(app) = weak.upgrade() {
            app.window().request_redraw();
        }
    });
    app.run().expect("run");
}
