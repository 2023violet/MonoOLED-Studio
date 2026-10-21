//! MonoOLED Studio desktop application (Slint, ADR-005 / G2 decision).
#![cfg_attr(all(windows, not(debug_assertions)), windows_subsystem = "windows")]

mod agent;
mod app;
mod bench;
mod canvas;
mod extras;
mod fontlab;
mod fontlab_ui;
mod i18n;
mod pixel;
mod pixel_ui;
mod prefs;
mod prefs_ui;
mod workbench;

use std::cell::RefCell;
use std::path::PathBuf;
use std::rc::Rc;

use mono_core::render::posix;
use slint::{ComponentHandle, SharedString};

#[allow(clippy::all, clippy::unwrap_used, clippy::expect_used, clippy::panic)]
mod generated {
    slint::include_modules!();
}
pub use generated::*;

use app::{App, Prompt, zoom_for};
use prefs::Preferences;

/// Femtovg (OpenGL) first; fall back to the software renderer when no usable GL
/// context exists (the failure mode that stopped the egui prototype).
fn select_backend() {
    if std::env::var_os("SLINT_BACKEND").is_some() {
        return;
    }
    let gl = slint::BackendSelector::new()
        .backend_name("winit".into())
        .renderer_name("femtovg".into())
        .select();
    if gl.is_err() {
        let _ = slint::BackendSelector::new()
            .backend_name("winit".into())
            .renderer_name("software".into())
            .select();
    }
}

#[allow(unsafe_code)]
fn set_scale_env(scale: f32) {
    // SAFETY: called once at the very start of `main`, before Slint or any
    // other thread is created, so no concurrent environment access exists.
    unsafe { std::env::set_var("SLINT_SCALE_FACTOR", scale.to_string()) };
}

struct Args {
    project: Option<PathBuf>,
    screenshot: Option<PathBuf>,
    workspace: Option<i32>,
    theme: Option<String>,
    lang: Option<String>,
    select: Option<String>,
    /// `--bench <out.json>`: measure the spec §5 interactive budgets and exit.
    bench: Option<PathBuf>,
    /// Actions run after startup, in order (`--action preferences`); used for
    /// scripted screenshots and smoke checks.
    actions: Vec<String>,
}

fn parse_args() -> Args {
    let mut args = Args {
        project: None,
        screenshot: None,
        workspace: None,
        theme: None,
        lang: None,
        select: None,
        bench: None,
        actions: Vec::new(),
    };
    let raw: Vec<String> = std::env::args().skip(1).collect();
    let mut i = 0;
    while i < raw.len() {
        let value = raw.get(i + 1).cloned();
        match raw[i].as_str() {
            "--screenshot" => args.screenshot = value.map(PathBuf::from),
            "--workspace" => args.workspace = value.and_then(|v| v.parse().ok()),
            "--theme" => args.theme = value,
            "--lang" => args.lang = value,
            "--select" => args.select = value,
            "--action" => args.actions.extend(value),
            "--bench" => args.bench = value.map(PathBuf::from),
            path if !path.starts_with("--") => {
                args.project = Some(PathBuf::from(path));
                i += 1;
                continue;
            }
            _ => {}
        }
        i += 2;
    }
    args
}

fn theme_mode(prefs: &Preferences, override_mode: Option<&str>) -> i32 {
    match override_mode
        .map(str::to_string)
        .unwrap_or_else(|| prefs.str("appearance.theme_mode"))
        .as_str()
    {
        "dark" => 1,
        "high-contrast" => 2,
        "system" => i32::from(matches!(dark_light_hint(), Some(true))),
        _ => 0,
    }
}

/// Best-effort OS dark-mode hint without extra dependencies (Windows registry).
fn dark_light_hint() -> Option<bool> {
    #[cfg(windows)]
    {
        let out = std::process::Command::new("reg")
            .args([
                "query",
                r"HKCU\Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
                "/v",
                "AppsUseLightTheme",
            ])
            .output()
            .ok()?;
        let text = String::from_utf8_lossy(&out.stdout);
        Some(text.contains("0x0"))
    }
    #[cfg(not(windows))]
    {
        None
    }
}

pub(crate) fn apply_appearance(ui: &MainWindow, app: &App, override_theme: Option<&str>) {
    Theme::get(ui).set_mode(theme_mode(&app.prefs, override_theme));
    let density = match app.prefs.str("appearance.density").as_str() {
        "compact" => 0,
        "spacious" => 2,
        _ => 1,
    };
    Metrics::get(ui).set_density(density);
    I18n::get(ui).set_lang(SharedString::from(app.lang.as_str()));
}

fn open_project_dialog(app: &Rc<RefCell<App>>) {
    let title = app.borrow().t("dialog.open_project");
    let Some(path) = rfd::FileDialog::new()
        .set_title(title)
        .add_filter("MonoOLED project", &["json"])
        .pick_file()
    else {
        return;
    };
    let mut a = app.borrow_mut();
    if let Err(e) = a.open_project(&path) {
        a.error(&e);
    }
}

fn save_dialog(title: &str, name: &str, ext: &str) -> Option<PathBuf> {
    rfd::FileDialog::new()
        .set_title(title)
        .set_file_name(name)
        .add_filter(ext, &[ext])
        .save_file()
}

fn handle_action(app: &Rc<RefCell<App>>, ui: &MainWindow, action: &str) {
    let lang = app.borrow().lang.clone();
    let t = |key: &str| i18n::tr(&lang, key);
    match action {
        "open-project" => open_project_dialog(app),
        "open-scene" => {
            if let Some(path) = rfd::FileDialog::new()
                .add_filter("Scene JSON", &["json"])
                .pick_file()
            {
                let mut a = app.borrow_mut();
                if let Err(e) = a.open_scene_file(&path) {
                    a.error(&e);
                }
            }
        }
        "new-project" => {
            if let Some(dir) = rfd::FileDialog::new()
                .set_title(t("action.new_project"))
                .pick_folder()
            {
                let name = dir
                    .file_name()
                    .map(|n| n.to_string_lossy().into_owned())
                    .unwrap_or_else(|| "MonoOLED Project".into());
                let mut a = app.borrow_mut();
                if let Err(e) = a.new_project(&dir, &name) {
                    a.error(&e);
                }
            }
        }
        "export-current" | "export-all" => {
            let Some(dir) = rfd::FileDialog::new()
                .set_title(t("action.export_all"))
                .pick_folder()
            else {
                return;
            };
            let mut a = app.borrow_mut();
            match a.export_states(action == "export-all", &dir) {
                Ok(message) => a.set_status(message),
                Err(e) => a.error(&e),
            }
        }
        "handoff" => {
            let Some(path) = save_dialog(&t("action.handoff"), "OLED_Code_AI_Handoff.zip", "zip")
            else {
                return;
            };
            let mut a = app.borrow_mut();
            match a.handoff(&path) {
                Ok(message) => a.set_status(message),
                Err(e) => a.error(&e),
            }
        }
        "export-c-header" => {
            let Some(path) = save_dialog(&t("action.export_c_header"), "oled_frame.h", "h") else {
                return;
            };
            let mut a = app.borrow_mut();
            if let Some(fb) = a.current_framebuffer() {
                let result = mono_core::c_header::framebuffer_to_c_header(&fb, "oled_frame")
                    .and_then(|text| mono_project::atomic::atomic_write(&path, text.as_bytes()));
                match result {
                    Ok(()) => a.set_status(posix(&path)),
                    Err(e) => a.error(&e),
                }
            }
        }
        "batch-validate" => {
            let mut a = app.borrow_mut();
            match a.batch_validate() {
                Ok(message) => a.set_status(message),
                Err(e) => a.error(&e),
            }
            a.refresh_app();
        }
        "preferences" => app.borrow_mut().open_preferences(),
        "about" => AppModel::get(ui).set_about_visible(true),
        "exit" => {
            let _ = slint::quit_event_loop();
        }
        "new-screen" => app.borrow_mut().show_prompt(
            Prompt::NewScreen,
            &t("action.new_screen"),
            &t("dialog.screen_id"),
            "screen_2",
        ),
        "duplicate-screen" => app.borrow_mut().show_prompt(
            Prompt::DuplicateScreen,
            &t("action.duplicate"),
            &t("dialog.screen_id"),
            "copy",
        ),
        "undo" | "redo" | "save" if app.borrow().workspace == 1 => {
            app.borrow_mut().pixel_action(action);
        }
        "save" if app.borrow().workspace == 2 => app.borrow_mut().font_action("save"),
        "undo" | "redo" if app.borrow().workspace == 2 => {
            let mut a = app.borrow_mut();
            a.pixel_action(action);
            a.refresh_font();
        }
        "new-font-pack" => {
            switch_workspace(app, ui, 2);
            app.borrow_mut().font_action("new");
        }
        "delete-screen" => {
            let mut a = app.borrow_mut();
            let active = a
                .project
                .as_ref()
                .map(mono_project::project::ProjectWorkspace::active_screen);
            if let (Some(active), Some(project)) = (active, a.project.as_mut()) {
                let others: Vec<String> = project
                    .screens()
                    .into_iter()
                    .map(|s| s.id)
                    .filter(|id| *id != active)
                    .collect();
                let result = match others.first() {
                    Some(next) => project
                        .set_active_screen(next)
                        .and_then(|()| project.remove_screen(&active, true))
                        .map(|()| next.clone()),
                    None => Err(mono_core::CoreError::invalid(
                        "project must keep at least one screen",
                    )),
                };
                match result {
                    Ok(next) => {
                        let _ = a.open_screen(&next);
                    }
                    Err(e) => a.error(&e),
                }
            }
        }
        "assign-bitmap" => {
            let Some(path) = rfd::FileDialog::new()
                .set_title(t("dialog.assign_bitmap"))
                .add_filter("Bitmap", &["png", "bmp"])
                .pick_file()
            else {
                return;
            };
            let mut a = app.borrow_mut();
            let target = a.selection.primary().map(str::to_string);
            if let (Some(id), Some(session)) = (target, a.session.as_mut()) {
                if let Err(e) = session.assign_bitmap(&id, &path) {
                    a.error(&e);
                }
            }
            a.scan_project_files();
            a.refresh_all();
        }
        "agent-bridge" => {
            let mut a = app.borrow_mut();
            if let Err(e) = a.toggle_agent() {
                a.error(&e);
            }
        }
        "canvas-only" => {
            let shell = Shell::get(ui);
            shell.set_canvas_only(!shell.get_canvas_only());
        }
        other if other.starts_with("workspace:") => {
            let index: i32 = other[10..].parse().unwrap_or(0);
            switch_workspace(app, ui, index);
        }
        other => {
            let mut a = app.borrow_mut();
            if !a.extra_action(other) {
                a.action(other);
            }
        }
    }
}

fn finish_prompt(app: &mut App, result: Result<(), mono_core::CoreError>) {
    if let Err(e) = result {
        app.error(&e);
    }
    app.refresh_all();
}

fn switch_workspace(app: &Rc<RefCell<App>>, ui: &MainWindow, index: i32) {
    AppModel::get(ui).set_workspace(index);
    if index == 3 {
        DesignerModel::get(ui).set_drawer_tab(1);
    }
    let mut a = app.borrow_mut();
    a.workspace = index;
    if index == 1 {
        a.refresh_pixel();
        a.refresh_bench();
    } else if index == 2 {
        a.refresh_font();
        a.refresh_pixel();
    } else {
        a.refresh_app();
    }
}

fn wire(ui: &MainWindow, app: &Rc<RefCell<App>>) {
    I18n::get(ui).on_tr(|lang, key| SharedString::from(i18n::tr(&lang, &key)));

    let (a, w) = (app.clone(), ui.as_weak());
    AppModel::get(ui).on_action(move |action| {
        if let Some(ui) = w.upgrade() {
            handle_action(&a, &ui, &action);
        }
    });

    let (a, w) = (app.clone(), ui.as_weak());
    AppModel::get(ui).on_prompt_accepted(move |text| {
        let Some(ui) = w.upgrade() else { return };
        AppModel::get(&ui).set_prompt_visible(false);
        let mut app = a.borrow_mut();
        let Some(prompt) = app.prompt.take() else {
            return;
        };
        let text = text.trim().to_string();
        let prompt = match prompt {
            Prompt::NewScreen | Prompt::DuplicateScreen => prompt,
            Prompt::NewFontPack => {
                app.create_font_pack(&text);
                return;
            }
            Prompt::TemplateName => {
                let result = app.save_template(&text);
                finish_prompt(&mut app, result);
                return;
            }
            Prompt::TemplatePrefix(name) => {
                let result = app.insert_template(&name, &text);
                finish_prompt(&mut app, result);
                return;
            }
            Prompt::BitmapText(dir) => {
                let result = app.bitmap_text_entered(dir, &text);
                finish_prompt(&mut app, result);
                return;
            }
            Prompt::BitmapTextId(dir, value) => {
                let result = app.insert_bitmap_text(&dir, &value, &text);
                finish_prompt(&mut app, result);
                return;
            }
            other => {
                app.pixel_prompt(other, &text);
                return;
            }
        };
        let result = match (Some(prompt), app.project.as_mut()) {
            (Some(Prompt::NewScreen), Some(project)) => project
                .add_screen(&text, Some(&text), None, None)
                .map(|_| Some(text.clone())),
            (Some(Prompt::DuplicateScreen), Some(project)) => {
                let active = project.active_screen();
                project
                    .duplicate_screen(&active, &text, Some(&text))
                    .map(|_| Some(text.clone()))
            }
            _ => Ok(None),
        };
        match result {
            Ok(Some(screen)) => {
                if let Err(e) = app.open_screen(&screen) {
                    app.error(&e);
                }
            }
            Ok(None) => {}
            Err(e) => app.error(&e),
        }
    });
    let a = app.clone();
    AppModel::get(ui).on_prompt_cancelled(move || {
        a.borrow_mut().prompt = None;
    });

    let a = app.clone();
    DesignerModel::get(ui).on_navigator_action(move |action, id| {
        let ui = a.borrow().ui.upgrade();
        match action.as_str() {
            "open-screen" => {
                let mut app = a.borrow_mut();
                if let Err(e) = app.open_screen(&id) {
                    app.error(&e);
                }
            }
            "filter-assets" => a.borrow_mut().refresh_navigator(),
            "place-asset" => {
                let mut app = a.borrow_mut();
                if let Err(e) = app.place_asset(&id) {
                    app.error(&e);
                }
                app.refresh_all();
            }
            "open-font-pack" => {
                if let Some(ui) = ui {
                    switch_workspace(&a, &ui, 2);
                }
                a.borrow_mut().font_action(&format!("open:{id}"));
            }
            "rescan-fonts" => {
                let mut app = a.borrow_mut();
                app.scan_project_files();
                app.refresh_navigator();
            }
            other => {
                if let Some(ui) = ui {
                    handle_action(&a, &ui, other);
                }
            }
        }
    });
    let a = app.clone();
    DesignerModel::get(ui)
        .on_element_clicked(move |id, additive| a.borrow_mut().element_clicked(&id, additive));
    let a = app.clone();
    DesignerModel::get(ui)
        .on_geometry_edited(move |field, value| a.borrow_mut().geometry_edited(&field, value));
    let (a, w) = (app.clone(), ui.as_weak());
    DesignerModel::get(ui).on_inspector_action(move |action| {
        if let Some(ui) = w.upgrade() {
            handle_action(&a, &ui, &action);
        }
    });
    let a = app.clone();
    DesignerModel::get(ui)
        .on_state_edited(move |name, value| a.borrow_mut().state_edited(&name, &value));
    let a = app.clone();
    DesignerModel::get(ui).on_canvas_pointer(move |phase, x, y, shift, ctrl| {
        if let Ok(mut app) = a.try_borrow_mut() {
            app.canvas_pointer(&phase, x, y, shift, ctrl);
        }
    });
    let a = app.clone();
    DesignerModel::get(ui).on_canvas_key(move |key| a.borrow_mut().canvas_key(&key));
    let a = app.clone();
    DesignerModel::get(ui).on_canvas_size_edited(move |w, h| a.borrow_mut().set_canvas_size(w, h));
    let (a, w) = (app.clone(), ui.as_weak());
    DesignerModel::get(ui).on_zoom_chosen(move |index| {
        let Some(ui) = w.upgrade() else { return };
        DesignerModel::get(&ui).set_zoom(zoom_for(index));
        let _ = &a;
    });
    wire_pixel(ui, app);
    wire_prefs(ui, app);
    wire_picker(ui, app);
}

/// Configured shortcut → command (V1 command registry). Returns true if handled.
fn run_shortcut(app: &Rc<RefCell<App>>, ui: &MainWindow, chord: &str) -> bool {
    let Some(command) = app.borrow_mut().shortcut(chord) else {
        // V1 fixed menu shortcuts (not user-configurable).
        let action = match prefs_ui::normalize_shortcut(chord).as_str() {
            "ctrl+n" => "new-project",
            "ctrl+shift+o" => "open-project",
            "ctrl+o" => "open-scene",
            "ctrl+shift+e" => "handoff",
            "ctrl+g" => "group",
            "ctrl+shift+g" => "ungroup",
            "ctrl+j" => "diagnostics",
            "ctrl+1" => "toggle-navigator",
            "ctrl+2" => "toggle-inspector",
            "ctrl+shift+p" => "workspace:1",
            "ctrl+shift+f" => "workspace:2",
            "ctrl+k" => "command-palette",
            _ => return false,
        };
        handle_action(app, ui, action);
        return true;
    };
    let workspace = app.borrow().workspace;
    match command {
        "preferences.open" => app.borrow_mut().open_preferences(),
        "workspace.canvas_only" => {
            let shell = Shell::get(ui);
            shell.set_canvas_only(!shell.get_canvas_only());
        }
        "project.save" => handle_action(app, ui, "save"),
        "designer.undo" => handle_action(app, ui, "undo"),
        "designer.redo" => handle_action(app, ui, "redo"),
        tool if workspace == 1 || workspace == 2 => {
            let index = match tool {
                "pixel.select" => 5,
                "pixel.fill" => 4,
                _ => 0,
            };
            let mut a = app.borrow_mut();
            a.studio_mut().tool = pixel::Tool::from_index(index);
            a.refresh_pixel();
        }
        _ => return false,
    }
    true
}

fn wire_picker(ui: &MainWindow, app: &Rc<RefCell<App>>) {
    let a = app.clone();
    AppModel::get(ui)
        .on_picker_filter_changed(move |filter| a.borrow_mut().refresh_picker(&filter));
    let (a, w) = (app.clone(), ui.as_weak());
    AppModel::get(ui).on_picker_chosen(move |index| {
        let Some(ui) = w.upgrade() else { return };
        let action = a.borrow_mut().picker_chosen(index);
        if let Some(action) = action {
            handle_action(&a, &ui, &action);
        }
    });
}

fn wire_prefs(ui: &MainWindow, app: &Rc<RefCell<App>>) {
    let (a, w) = (app.clone(), ui.as_weak());
    AppModel::get(ui).on_key_chord(move |chord| {
        let Some(ui) = w.upgrade() else { return false };
        run_shortcut(&a, &ui, &chord)
    });
    let pm = PrefsModel::get(ui);
    let a = app.clone();
    pm.on_section_chosen(move |_| a.borrow_mut().refresh_prefs());
    let a = app.clone();
    pm.on_search_changed(move |_| a.borrow_mut().refresh_prefs());
    let a = app.clone();
    pm.on_changed(move |key, value| a.borrow_mut().pref_changed(&key, &value));
    let a = app.clone();
    pm.on_button(move |key| a.borrow_mut().pref_button(&key));
    let w = ui.as_weak();
    pm.on_close(move || {
        if let Some(ui) = w.upgrade() {
            AppModel::get(&ui).set_preferences_visible(false);
        }
    });
}

fn wire_pixel(ui: &MainWindow, app: &Rc<RefCell<App>>) {
    let pm = PixelModel::get(ui);
    let a = app.clone();
    pm.on_pointer(move |phase, x, y, button| {
        if let Ok(mut app) = a.try_borrow_mut() {
            app.pixel_pointer(&phase, x, y, button);
        }
    });
    let a = app.clone();
    pm.on_key(move |key| a.borrow_mut().pixel_key(&key));
    let a = app.clone();
    pm.on_action(move |action| a.borrow_mut().pixel_action(&action));
    let a = app.clone();
    pm.on_tool_chosen(move |index| {
        let mut app = a.borrow_mut();
        app.pixel.tool = pixel::Tool::from_index(index);
        app.refresh_pixel();
    });
    let a = app.clone();
    pm.on_brush_chosen(move |size| {
        let mut app = a.borrow_mut();
        let brush = i64::from(size.clamp(1, 8));
        app.pixel.brush = brush;
        let _ = app
            .prefs
            .set("pixel_studio.brush_size", serde_json::json!(brush));
        let _ = app.prefs.save();
    });
    let a = app.clone();
    pm.on_zoom_chosen(move |index| a.borrow_mut().pixel_zoom(index));
    let a = app.clone();
    pm.on_zoom_step(move |direction| a.borrow_mut().pixel_zoom_step(direction));
    let a = app.clone();
    pm.on_import_changed(move || a.borrow_mut().pixel_import_changed());
    let a = app.clone();
    pm.on_dialog_accepted(move || a.borrow_mut().pixel_dialog_accepted());

    let fm = FontModel::get(ui);
    let a = app.clone();
    fm.on_glyph_chosen(move |index| a.borrow_mut().font_glyph_chosen(index));
    let a = app.clone();
    fm.on_edit(move |field, value| a.borrow_mut().font_edit(&field, &value));
    let a = app.clone();
    fm.on_font_action(move |action| a.borrow_mut().font_action(&action));

    let om = OutputModel::get(ui);
    let a = app.clone();
    om.on_field(move |key, value| a.borrow_mut().bench_field(&key, &value));
    let a = app.clone();
    om.on_source_chosen(move |index| a.borrow_mut().bench_source(index));
    let a = app.clone();
    om.on_profile_chosen(move |index| a.borrow_mut().bench_profile(index));
    let a = app.clone();
    om.on_bench_action(move |action| a.borrow_mut().bench_action(&action));
}

fn main() {
    let process_start = std::time::Instant::now();
    let args = parse_args();
    // V1 `appearance.ui_scale`: Slint reads its scale factor when the window is created.
    if std::env::var_os("SLINT_SCALE_FACTOR").is_none() {
        let scale = Preferences::load().str("appearance.ui_scale");
        if let Some(percent) = scale.strip_suffix('%').and_then(|p| p.parse::<f32>().ok()) {
            set_scale_env(percent / 100.0);
        }
    }
    select_backend();
    let trace = std::env::var_os("MONO_TRACE_STARTUP").is_some();
    let mark = |label: &str| {
        if trace {
            eprintln!(
                "startup {label}: {:.1} ms",
                process_start.elapsed().as_secs_f64() * 1000.0
            );
        }
    };
    mark("main");
    let ui = match MainWindow::new() {
        Ok(ui) => ui,
        Err(error) => {
            eprintln!("MonoOLED Studio could not create its window: {error}");
            std::process::exit(1);
        }
    };
    let mut prefs = Preferences::load();
    if let Some(lang) = &args.lang {
        prefs.set("language", serde_json::json!(lang));
    }
    mark("window created");
    let app = Rc::new(RefCell::new(App::new(ui.as_weak(), prefs)));
    apply_appearance(&ui, &app.borrow(), args.theme.as_deref());
    wire(&ui, &app);
    {
        let mut a = app.borrow_mut();
        let last = a.prefs.str("startup.last_project");
        let reopen = a.prefs.bool("startup.reopen_last_project");
        let target = args
            .project
            .clone()
            .or_else(|| (reopen && !last.is_empty()).then(|| PathBuf::from(&last)));
        if let Some(path) = target {
            let result = if path.extension().is_some_and(|e| e == "json")
                && path.file_name().is_some_and(|n| n != "project.oled.json")
            {
                a.open_scene_file(&path)
            } else {
                let path = if path.is_dir() {
                    path.join("project.oled.json")
                } else {
                    path
                };
                a.open_project(&path)
            };
            if let Err(e) = result {
                a.error(&e);
            }
        }
        if let Some(id) = &args.select {
            a.element_clicked(id, false);
        }
        a.refresh_app();
    }
    {
        let mut a = app.borrow_mut();
        a.apply_pixel_preferences();
        a.bench_load_active();
        a.refresh_agent_status();
    }
    // Background jobs (Font Lab generation) report through this tick.
    let jobs = slint::Timer::default();
    let a = app.clone();
    jobs.start(
        slint::TimerMode::Repeated,
        std::time::Duration::from_millis(60),
        move || {
            if let Ok(mut app) = a.try_borrow_mut() {
                app.poll_font();
                app.poll_agent();
            }
        },
    );
    // V1 autosave timer: checked every few seconds against the preference interval.
    let autosave = slint::Timer::default();
    let a = app.clone();
    autosave.start(
        slint::TimerMode::Repeated,
        std::time::Duration::from_secs(5),
        move || {
            if let Ok(mut app) = a.try_borrow_mut() {
                app.autosave_due();
            }
        },
    );
    if args.screenshot.is_none() && args.bench.is_none() {
        app.borrow_mut().prompt_recovery();
    }
    if let Some(index) = args.workspace {
        switch_workspace(&app, &ui, index);
    }
    for action in &args.actions {
        match action.strip_prefix("font:") {
            Some(rest) => app.borrow_mut().font_action(rest),
            None => handle_action(&app, &ui, action),
        }
    }
    if let Some(out) = args.bench.clone() {
        bench::run(&ui, &app, out, process_start);
    }
    if let Some(path) = args.screenshot.clone() {
        let w = ui.as_weak();
        slint::Timer::single_shot(std::time::Duration::from_millis(900), move || {
            if let Some(ui) = w.upgrade() {
                match ui.window().take_snapshot() {
                    Ok(buffer) => {
                        let rgba: Vec<u8> = buffer.as_bytes().to_vec();
                        let png = mono_project::image_io::encode_rgba_png(
                            buffer.width() as usize,
                            buffer.height() as usize,
                            &rgba,
                        );
                        if let Ok(png) = png {
                            let _ = std::fs::write(&path, png);
                        }
                    }
                    Err(error) => eprintln!("snapshot failed: {error}"),
                }
            }
            let _ = slint::quit_event_loop();
        });
    }
    mark("project loaded, entering event loop");
    if let Err(error) = ui.run() {
        eprintln!("MonoOLED Studio stopped: {error}");
    }
}
