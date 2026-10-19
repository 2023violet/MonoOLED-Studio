//! Application controller: owns the project, the Designer session and the UI
//! sync. Every UI callback goes through `App`; Slint models are rebuilt from
//! the session after each change (the scene JSON stays the single truth).

use std::path::{Path, PathBuf};

use mono_core::CoreError;
use mono_core::pyvalue::py_str;
use mono_core::render::posix;
use mono_core::state::{IntegerPolicy, build_export_states};
use mono_project::editor::{
    EditorSession, Selection, align_to, distribute, selection_metrics, smart_guides, snap_positions,
};
use mono_project::export::{
    Finding, build_handoff_package, check_design_rules, export_scene, matrix_report,
    validate_matrix,
};
use mono_project::project::{ProjectWorkspace, create_project};
use mono_project::scene_io::{SceneDoc, load_project_scene, load_scene};
use serde_json::{Value, json};
use slint::{Global, ModelRc, SharedString, VecModel};

use crate::canvas::image_from_pixels;
use crate::i18n::{tr, trf};
use crate::pixel::PixelStudio;
use crate::pixel_ui::ImportState;
use crate::prefs::Preferences;
use crate::workbench::Workbench;
use crate::{
    AppModel, AssetItem, DesignerModel, DocTab, ElementItem, FindingItem, MainWindow, OverlayBox,
    PillTone, ScreenItem, StateVar,
};

const ZOOM_STEPS: [f32; 8] = [0.0, 1.0, 2.0, 4.0, 6.0, 8.0, 12.0, 16.0];

pub enum Prompt {
    NewScreen,
    DuplicateScreen,
    CSymbol(PathBuf),
    GlyphCharacters,
    ProfileId,
    ProfileName(String),
}

struct Drag {
    start: (i64, i64),
    applied: (i64, i64),
    ids: Vec<String>,
    moved: bool,
}

pub struct App {
    pub ui: slint::Weak<MainWindow>,
    pub lang: String,
    pub prefs: Preferences,
    pub project: Option<ProjectWorkspace>,
    pub session: Option<EditorSession>,
    pub selection: Selection,
    drag: Option<Drag>,
    baseline_pixels: Vec<u8>,
    baseline_elements: Vec<Value>,
    pub log: Vec<String>,
    pub assets: Vec<String>,
    pub font_packs: Vec<String>,
    pub prompt: Option<Prompt>,
    pub findings: Vec<Finding>,
    pub status: String,
    pub workspace: i32,
    pub pixel: PixelStudio,
    pub import: Option<ImportState>,
    pub bench: Workbench,
}

pub(crate) fn model<T: Clone + 'static>(items: Vec<T>) -> ModelRc<T> {
    ModelRc::new(VecModel::from(items))
}

pub(crate) fn ss(text: impl AsRef<str>) -> SharedString {
    SharedString::from(text.as_ref())
}

impl App {
    pub fn new(ui: slint::Weak<MainWindow>, prefs: Preferences) -> Self {
        let lang = prefs.str("language");
        Self {
            ui,
            lang: if lang.is_empty() {
                "zh_CN".into()
            } else {
                lang
            },
            prefs,
            project: None,
            session: None,
            selection: Selection::default(),
            drag: None,
            baseline_pixels: Vec::new(),
            baseline_elements: Vec::new(),
            log: Vec::new(),
            assets: Vec::new(),
            font_packs: Vec::new(),
            prompt: None,
            findings: Vec::new(),
            status: String::new(),
            workspace: 0,
            pixel: PixelStudio::blank(),
            import: None,
            bench: Workbench::default(),
        }
    }

    pub fn t(&self, key: &str) -> String {
        tr(&self.lang, key)
    }

    pub fn log_event(&mut self, text: impl Into<String>) {
        let now = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .map(|d| d.as_secs())
            .unwrap_or(0);
        let (h, m, s) = ((now / 3600) % 24, (now / 60) % 60, now % 60);
        self.log
            .push(format!("{h:02}:{m:02}:{s:02} UTC  {}", text.into()));
        if self.log.len() > 500 {
            self.log.drain(..self.log.len() - 500);
        }
    }

    pub fn set_status(&mut self, text: impl Into<String>) {
        self.status = text.into();
        if let Some(ui) = self.ui.upgrade() {
            AppModel::get(&ui).set_status_text(ss(&self.status));
        }
    }

    pub fn error(&mut self, error: &CoreError) {
        let text = format!("{}: {}", self.t("status.error"), error.message);
        self.log_event(format!("ERROR {}", error.message));
        self.set_status(text);
    }

    // ----------------------------------------------------------------- loading

    pub fn open_project(&mut self, path: &Path) -> Result<(), CoreError> {
        let project = ProjectWorkspace::load(path)?;
        let scene = load_project_scene(&project, None)?;
        self.prefs
            .set("startup.last_project", json!(posix(&project.path)));
        let _ = self.prefs.save();
        self.log_event(format!("OPEN_PROJECT {}", posix(&project.path)));
        self.project = Some(project);
        self.bind_scene(scene)?;
        self.scan_project_files();
        Ok(())
    }

    pub fn open_scene_file(&mut self, path: &Path) -> Result<(), CoreError> {
        let scene = load_scene(path, None)?;
        self.project = None;
        self.bind_scene(scene)?;
        self.scan_project_files();
        Ok(())
    }

    pub fn new_project(&mut self, root: &Path, name: &str) -> Result<(), CoreError> {
        let project = create_project(root, name, (128, 32))?;
        let path = project.path.clone();
        self.open_project(&path)
    }

    fn bind_scene(&mut self, scene: SceneDoc) -> Result<(), CoreError> {
        let mut session = EditorSession::new(scene)?;
        let pixels = session
            .render()
            .map(|r| r.framebuffer.pixels().to_vec())
            .unwrap_or_default();
        self.baseline_pixels = pixels;
        self.baseline_elements = session
            .scene()
            .get("elements")
            .and_then(Value::as_array)
            .cloned()
            .unwrap_or_default();
        self.session = Some(session);
        self.selection.clear();
        self.drag = None;
        self.refresh_all();
        Ok(())
    }

    pub fn open_screen(&mut self, screen_id: &str) -> Result<(), CoreError> {
        if self.session.as_ref().is_some_and(|s| s.dirty) {
            self.save()?;
        }
        let Some(project) = self.project.as_mut() else {
            return Ok(());
        };
        project.set_active_screen(screen_id)?;
        project.save()?;
        let scene = load_project_scene(project, Some(screen_id))?;
        self.bind_scene(scene)
    }

    pub fn scan_project_files(&mut self) {
        self.assets.clear();
        self.font_packs.clear();
        let root = match (&self.project, &self.session) {
            (Some(p), _) => p.root.clone(),
            (None, Some(s)) => s.root().to_path_buf(),
            _ => return,
        };
        let dirs = self
            .project
            .as_ref()
            .map(ProjectWorkspace::asset_dirs)
            .unwrap_or_else(|| vec!["assets".into()]);
        fn walk(dir: &Path, root: &Path, assets: &mut Vec<String>, packs: &mut Vec<String>) {
            let Ok(entries) = std::fs::read_dir(dir) else {
                return;
            };
            let mut entries: Vec<_> = entries.flatten().collect();
            entries.sort_by_key(|e| e.path());
            for entry in entries {
                let path = entry.path();
                let Ok(kind) = entry.file_type() else {
                    continue;
                };
                if kind.is_dir() {
                    if path.join("fontpack.json").is_file() {
                        packs.push(posix(path.strip_prefix(root).unwrap_or(&path)));
                        continue;
                    }
                    walk(&path, root, assets, packs);
                } else if kind.is_file()
                    && path.extension().is_some_and(|e| {
                        e.eq_ignore_ascii_case("png") || e.eq_ignore_ascii_case("bmp")
                    })
                {
                    assets.push(posix(path.strip_prefix(root).unwrap_or(&path)));
                }
            }
        }
        let (mut assets, mut packs) = (Vec::new(), Vec::new());
        for dir in dirs.iter().chain(["fonts".to_string()].iter()) {
            walk(&root.join(dir), &root, &mut assets, &mut packs);
        }
        packs.sort();
        packs.dedup();
        self.assets = assets;
        self.font_packs = packs;
    }

    // ------------------------------------------------------------- refreshing

    pub fn refresh_all(&mut self) {
        self.refresh_navigator();
        self.refresh_canvas();
        self.refresh_inspector();
        self.refresh_validation();
        self.refresh_app();
    }

    pub fn refresh_app(&mut self) {
        let Some(ui) = self.ui.upgrade() else { return };
        let app = AppModel::get(&ui);
        let name = self
            .project
            .as_ref()
            .map(ProjectWorkspace::name)
            .or_else(|| {
                self.session.as_ref().map(|s| {
                    s.doc
                        .path
                        .file_stem()
                        .map(|n| n.to_string_lossy().into_owned())
                        .unwrap_or_default()
                })
            })
            .unwrap_or_default();
        app.set_project_name(ss(name));
        if self.workspace == 1 {
            app.set_dirty(self.pixel.doc.dirty);
            app.set_can_undo(self.pixel.doc.can_undo());
            app.set_can_redo(self.pixel.doc.can_redo());
        } else {
            app.set_dirty(self.session.as_ref().is_some_and(|s| s.dirty));
            app.set_can_undo(self.session.as_ref().is_some_and(EditorSession::can_undo));
            app.set_can_redo(self.session.as_ref().is_some_and(EditorSession::can_redo));
        }
        app.set_status_text(ss(&self.status));
        app.set_tabs(model(vec![DocTab {
            title: ss(self.t("workspace.design")),
            kind: ss("designer"),
            dirty: self.session.as_ref().is_some_and(|s| s.dirty),
        }]));
        let dm = DesignerModel::get(&ui);
        dm.set_log_lines(model(self.log.iter().rev().take(200).map(ss).collect()));
    }

    pub fn refresh_navigator(&mut self) {
        let Some(ui) = self.ui.upgrade() else { return };
        let dm = DesignerModel::get(&ui);
        let screens = self
            .project
            .as_ref()
            .map(|p| {
                let active = p.active_screen();
                p.screens()
                    .into_iter()
                    .map(|s| ScreenItem {
                        active: s.id == active,
                        id: ss(&s.id),
                        label: ss(&s.label),
                    })
                    .collect()
            })
            .unwrap_or_default();
        dm.set_screens(model(screens));
        let elements = self
            .session
            .as_ref()
            .map(|s| {
                s.scene()
                    .get("elements")
                    .and_then(Value::as_array)
                    .cloned()
                    .unwrap_or_default()
                    .iter()
                    .map(|e| {
                        let id = e.get("id").map(py_str).unwrap_or_default();
                        ElementItem {
                            selected: self.selection.contains(&id),
                            hidden: e.get("hidden") == Some(&Value::Bool(true)),
                            locked: e.get("locked") == Some(&Value::Bool(true)),
                            kind: ss(e.get("type").map(py_str).unwrap_or_default()),
                            detail: ss(e.get("group").map(py_str).unwrap_or_default()),
                            id: ss(id),
                        }
                    })
                    .collect()
            })
            .unwrap_or_default();
        dm.set_elements(model(elements));
        let filter = dm.get_asset_filter().to_lowercase();
        dm.set_assets(model(
            self.assets
                .iter()
                .filter(|a| filter.is_empty() || a.to_lowercase().contains(&filter))
                .map(|a| AssetItem {
                    path: ss(a),
                    detail: ss(""),
                })
                .collect(),
        ));
        dm.set_font_packs(model(self.font_packs.iter().map(ss).collect()));
    }

    pub fn refresh_canvas(&mut self) {
        let lang = self.lang.clone();
        let Some(ui) = self.ui.upgrade() else { return };
        let dm = DesignerModel::get(&ui);
        let Some(session) = self.session.as_mut() else {
            return;
        };
        match session.render() {
            Ok(result) => {
                let fb = &result.framebuffer;
                let lit = fb.pixels().iter().filter(|v| **v != 0).count();
                let bytes = fb.width() * fb.height().div_ceil(8);
                dm.set_canvas(image_from_pixels(fb.width(), fb.height(), fb.pixels()));
                dm.set_doc_w(fb.width() as i32);
                dm.set_doc_h(fb.height() as i32);
                dm.set_framebuffer_summary(ss(format!("Framebuffer {bytes} B · {lit} lit px")));
                dm.set_canvas_subtitle(ss(trf(
                    &lang,
                    "canvas.production",
                    &[
                        ("width", fb.width().to_string()),
                        ("height", fb.height().to_string()),
                    ],
                )));
                // Pixel diff against the last loaded/saved frame.
                let changed = fb
                    .pixels()
                    .iter()
                    .zip(&self.baseline_pixels)
                    .filter(|(a, b)| a != b)
                    .count()
                    + fb.pixels().len().abs_diff(self.baseline_pixels.len());
                let total = fb.pixels().len().max(1);
                dm.set_diff_summary(ss(format!(
                    "{} {changed} px ({:.2}%)",
                    tr(&lang, "diff.changed"),
                    changed as f64 * 100.0 / total as f64
                )));
                let current = session
                    .scene()
                    .get("elements")
                    .and_then(Value::as_array)
                    .cloned()
                    .unwrap_or_default();
                let id_of = |e: &Value| e.get("id").map(py_str).unwrap_or_default();
                let before_ids: Vec<String> = self.baseline_elements.iter().map(id_of).collect();
                let after_ids: Vec<String> = current.iter().map(id_of).collect();
                let added = after_ids.iter().filter(|i| !before_ids.contains(i)).count();
                let removed = before_ids.iter().filter(|i| !after_ids.contains(i)).count();
                let modified = current
                    .iter()
                    .filter(|e| {
                        self.baseline_elements
                            .iter()
                            .any(|b| id_of(b) == id_of(e) && b != *e)
                    })
                    .count();
                dm.set_diff_detail(ss(trf(
                    &lang,
                    "diff.elements",
                    &[
                        ("added", added.to_string()),
                        ("removed", removed.to_string()),
                        ("modified", modified.to_string()),
                    ],
                )));
            }
            Err(error) => {
                dm.set_framebuffer_summary(ss(format!(
                    "{}: {}",
                    tr(&lang, "status.render_failed"),
                    error.message
                )));
            }
        }
        // Editor-only overlays: element bounds, selection, primary marker.
        let ids = session.element_ids();
        let hidden: Vec<bool> = session
            .scene()
            .get("elements")
            .and_then(Value::as_array)
            .map(|a| {
                a.iter()
                    .map(|e| e.get("hidden") == Some(&Value::Bool(true)))
                    .collect()
            })
            .unwrap_or_default();
        let primary = self.selection.primary().map(str::to_string);
        let mut boxes = Vec::new();
        for (index, id) in ids.iter().enumerate() {
            if let Ok(g) = session.geometry(id) {
                boxes.push(OverlayBox {
                    id: ss(id),
                    x: g.x as i32,
                    y: g.y as i32,
                    w: g.w as i32,
                    h: g.h as i32,
                    selected: self.selection.contains(id),
                    primary: primary.as_deref() == Some(id.as_str()),
                    hidden: hidden.get(index).copied().unwrap_or(false),
                });
            }
        }
        dm.set_boxes(model(boxes));
    }

    pub fn refresh_inspector(&mut self) {
        let Some(ui) = self.ui.upgrade() else { return };
        let dm = DesignerModel::get(&ui);
        let Some(session) = self.session.as_mut() else {
            dm.set_has_selection(false);
            return;
        };
        let primary = self
            .selection
            .primary()
            .map(str::to_string)
            .or_else(|| self.selection.ids().last().cloned());
        dm.set_selection_count(self.selection.ids().len() as i32);
        match primary
            .as_deref()
            .map(|id| (session.element(id), session.geometry(id)))
        {
            Some((Ok(element), Ok(g))) => {
                dm.set_has_selection(true);
                dm.set_element_id(ss(element.get("id").map(py_str).unwrap_or_default()));
                dm.set_element_type(ss(element.get("type").map(py_str).unwrap_or_default()));
                let asset = element
                    .get("asset")
                    .or_else(|| element.get("dir"))
                    .or_else(|| element.get("font_header"))
                    .or_else(|| element.get("font_pack"))
                    .map(py_str)
                    .unwrap_or_default();
                dm.set_element_asset(ss(asset));
                dm.set_geom_x(g.x as i32);
                dm.set_geom_y(g.y as i32);
                dm.set_geom_w(g.w as i32);
                dm.set_geom_h(g.h as i32);
                dm.set_edit_x(g.editable.x);
                dm.set_edit_y(g.editable.y);
                dm.set_edit_w(g.editable.w);
                dm.set_edit_h(g.editable.h);
                dm.set_element_locked(element.get("locked") == Some(&Value::Bool(true)));
                dm.set_element_hidden(element.get("hidden") == Some(&Value::Bool(true)));
            }
            _ => dm.set_has_selection(false),
        }
        let ids = self.selection.ids().to_vec();
        let measure = if ids.len() >= 2 {
            selection_metrics(session, &ids)
                .map(|m| {
                    trf(
                        &self.lang,
                        "measure.multi",
                        &[
                            ("count", ids.len().to_string()),
                            ("width", m.bounds.2.to_string()),
                            ("height", m.bounds.3.to_string()),
                            (
                                "gaps",
                                m.horizontal_gaps
                                    .iter()
                                    .map(i64::to_string)
                                    .collect::<Vec<_>>()
                                    .join("/"),
                            ),
                        ],
                    )
                })
                .unwrap_or_default()
        } else {
            String::new()
        };
        dm.set_measure_text(ss(measure));
        // State variables and runtime.
        let states = session
            .scene()
            .get("states")
            .and_then(Value::as_object)
            .cloned()
            .unwrap_or_default();
        let vars: Vec<StateVar> = states
            .iter()
            .map(|(name, spec)| {
                let kind = spec.get("type").map(py_str).unwrap_or_default();
                let value = session.state.get(name).cloned().unwrap_or(Value::Null);
                let options: Vec<String> =
                    match (kind.as_str(), spec.get("values").and_then(Value::as_array)) {
                        (_, Some(values)) => values.iter().map(py_str).collect(),
                        _ => Vec::new(),
                    };
                let enum_like = kind == "enum" || !options.is_empty();
                StateVar {
                    name: ss(name),
                    kind: ss(if enum_like { "enum" } else { "int" }),
                    current: options
                        .iter()
                        .position(|o| *o == py_str(&value))
                        .map_or(0, |p| p as i32),
                    options: model(options.iter().map(ss).collect()),
                    value: ss(py_str(&value)),
                    minimum: spec.get("min").and_then(Value::as_i64).unwrap_or(0) as i32,
                    maximum: spec.get("max").and_then(Value::as_i64).unwrap_or(999_999) as i32,
                }
            })
            .collect();
        dm.set_states(model(vars));
        dm.set_runtime_text(ss(trf(
            &self.lang,
            "preview.timeline_position",
            &[
                ("position", session.elapsed.to_string()),
                ("unit", "step".into()),
            ],
        )));
        let canvas = session.scene().get("canvas").cloned().unwrap_or(json!({}));
        dm.set_canvas_w_setting(canvas.get("w").and_then(Value::as_i64).unwrap_or(128) as i32);
        dm.set_canvas_h_setting(canvas.get("h").and_then(Value::as_i64).unwrap_or(32) as i32);
    }

    pub fn refresh_validation(&mut self) {
        let Some(ui) = self.ui.upgrade() else { return };
        let dm = DesignerModel::get(&ui);
        let Some(session) = self.session.as_mut() else {
            return;
        };
        let mut findings = session.validate();
        let rules = session
            .scene()
            .get("_design_rules")
            .cloned()
            .unwrap_or(json!({}));
        findings.extend(check_design_rules(session.scene(), &rules));
        let blockers = findings.iter().filter(|f| f.is_blocking()).count();
        let summary = trf(
            &self.lang,
            "validation.summary",
            &[
                ("count", findings.len().to_string()),
                ("blockers", blockers.to_string()),
            ],
        );
        dm.set_findings_summary(ss(&summary));
        dm.set_findings_tone(if blockers > 0 {
            PillTone::Error
        } else if findings.is_empty() {
            PillTone::Success
        } else {
            PillTone::Warning
        });
        dm.set_findings(model(
            findings
                .iter()
                .map(|f| FindingItem {
                    severity: ss(&f.severity),
                    code: ss(&f.code),
                    message: ss(&f.message),
                })
                .collect(),
        ));
        let app = AppModel::get(&ui);
        app.set_health_text(ss(if blockers > 0 {
            format!("{} {blockers}", self.t("health.blocked"))
        } else if findings.is_empty() {
            self.t("health.ok")
        } else {
            format!("{} {}", self.t("health.warnings"), findings.len())
        }));
        app.set_health_tone(if blockers > 0 {
            PillTone::Error
        } else if findings.is_empty() {
            PillTone::Success
        } else {
            PillTone::Warning
        });
        self.findings = findings;
    }

    // --------------------------------------------------------------- editing

    fn after_edit(&mut self) {
        self.refresh_navigator();
        self.refresh_canvas();
        self.refresh_inspector();
        self.refresh_validation();
        self.refresh_app();
    }

    pub fn element_clicked(&mut self, id: &str, additive: bool) {
        if additive {
            self.selection.toggle(id);
        } else {
            self.selection.replace(&[id.to_string()], Some(id));
        }
        self.refresh_navigator();
        self.refresh_canvas();
        self.refresh_inspector();
    }

    fn hit_test(&mut self, x: f32, y: f32) -> Option<String> {
        let session = self.session.as_mut()?;
        let ids = session.element_ids();
        for id in ids.iter().rev() {
            if let Ok(g) = session.geometry(id) {
                let (px, py) = (x as i64, y as i64);
                if px >= g.x && py >= g.y && px < g.x + g.w.max(1) && py < g.y + g.h.max(1) {
                    return Some(id.clone());
                }
            }
        }
        None
    }

    pub fn canvas_pointer(&mut self, phase: &str, x: f32, y: f32, shift: bool, ctrl: bool) {
        let point = (x.floor() as i64, y.floor() as i64);
        match phase {
            "down" => {
                match self.hit_test(x, y) {
                    Some(id) => {
                        if shift || ctrl {
                            self.selection.toggle(&id);
                        } else if !self.selection.contains(&id) {
                            self.selection.replace(std::slice::from_ref(&id), Some(&id));
                        }
                        self.drag = Some(Drag {
                            start: point,
                            applied: (0, 0),
                            ids: self.selection.ids().to_vec(),
                            moved: false,
                        });
                    }
                    None => {
                        if !shift {
                            self.selection.clear();
                        }
                        self.drag = None;
                    }
                }
                self.refresh_navigator();
                self.refresh_canvas();
                self.refresh_inspector();
            }
            "move" => {
                let Some(drag) = self.drag.as_mut() else {
                    return;
                };
                let target = (point.0 - drag.start.0, point.1 - drag.start.1);
                let delta = (target.0 - drag.applied.0, target.1 - drag.applied.1);
                if delta == (0, 0) {
                    return;
                }
                let ids = drag.ids.clone();
                drag.applied = target;
                drag.moved = true;
                if let Some(session) = self.session.as_mut() {
                    let _ = session.batch_move(&ids, delta.0, delta.1, true);
                    let guides = ids
                        .first()
                        .and_then(|id| smart_guides(session, id, 2).ok())
                        .unwrap_or_default();
                    if let Some(ui) = self.ui.upgrade() {
                        let dm = DesignerModel::get(&ui);
                        dm.set_guides_x(model(guides.0.iter().map(|v| *v as i32).collect()));
                        dm.set_guides_y(model(guides.1.iter().map(|v| *v as i32).collect()));
                    }
                }
                // Fast drag preview: canvas + overlays only; validation runs on release.
                self.refresh_canvas();
                self.refresh_inspector();
            }
            "up" => {
                if let Some(drag) = self.drag.take() {
                    if let Some(session) = self.session.as_mut() {
                        session.end_coalesced_edit();
                    }
                    if let Some(ui) = self.ui.upgrade() {
                        let dm = DesignerModel::get(&ui);
                        dm.set_guides_x(model(Vec::new()));
                        dm.set_guides_y(model(Vec::new()));
                    }
                    if drag.moved {
                        self.log_event(format!(
                            "MOVE {} by {:?}",
                            drag.ids.join(","),
                            drag.applied
                        ));
                        self.after_edit();
                    }
                }
            }
            _ => {}
        }
    }

    pub fn canvas_key(&mut self, key: &str) {
        let step = if key.ends_with("10") { 10 } else { 1 };
        let (dx, dy) = match key.trim_end_matches("10") {
            "left" => (-step, 0),
            "right" => (step, 0),
            "up" => (0, -step),
            "down" => (0, step),
            "delete" => {
                self.action("delete");
                return;
            }
            "escape" => {
                self.selection.clear();
                self.after_edit();
                return;
            }
            _ => return,
        };
        let ids = self.selection.ids().to_vec();
        if let Some(session) = self.session.as_mut() {
            if let Err(e) = session.batch_move(&ids, dx, dy, false) {
                self.error(&e);
            }
        }
        self.after_edit();
    }

    pub fn geometry_edited(&mut self, field: &str, value: i32) {
        let Some(id) = self.selection.primary().map(str::to_string) else {
            return;
        };
        let result = self
            .session
            .as_mut()
            .map(|s| s.set_geometry(&id, &[(field, i64::from(value))], false));
        if let Some(Err(e)) = result {
            self.error(&e);
        }
        self.after_edit();
    }

    pub fn state_edited(&mut self, name: &str, value: &str) {
        let Some(session) = self.session.as_mut() else {
            return;
        };
        let spec = session
            .scene()
            .get("states")
            .and_then(|s| s.get(name))
            .cloned()
            .unwrap_or(json!({}));
        let parsed = match spec
            .get("values")
            .and_then(Value::as_array)
            .and_then(|v| v.iter().find(|o| py_str(o) == value))
        {
            Some(option) => option.clone(),
            None => value
                .parse::<i64>()
                .map(Value::from)
                .unwrap_or_else(|_| Value::from(value)),
        };
        if let Err(e) = session.set_state(name, parsed) {
            self.error(&e);
        }
        self.refresh_canvas();
        self.refresh_inspector();
        self.refresh_validation();
    }

    fn selected(&self) -> Vec<String> {
        self.selection.ids().to_vec()
    }

    fn unique_id(&self, base: &str) -> String {
        let ids = self
            .session
            .as_ref()
            .map(EditorSession::element_ids)
            .unwrap_or_default();
        (1..)
            .map(|n| format!("{base}_{n}"))
            .find(|c| !ids.contains(c))
            .unwrap_or_else(|| base.to_string())
    }

    /// Menu, command bar and inspector actions.
    pub fn action(&mut self, action: &str) {
        let result: Result<(), CoreError> = (|| {
            match action {
                "undo" => {
                    if let Some(s) = self.session.as_mut() {
                        s.undo();
                    }
                }
                "redo" => {
                    if let Some(s) = self.session.as_mut() {
                        s.redo();
                    }
                }
                "save" => self.save()?,
                "add-placeholder" => {
                    let id = self.unique_id("placeholder");
                    if let Some(s) = self.session.as_mut() {
                        s.add_placeholder(&id, 8, 8, 24, 8, None)?;
                    }
                    self.selection.replace(std::slice::from_ref(&id), Some(&id));
                }
                "delete" => {
                    let ids = self.selected();
                    if let Some(s) = self.session.as_mut() {
                        s.remove_elements(&ids)?;
                    }
                    self.selection.clear();
                }
                "duplicate" => {
                    let ids = self.selected();
                    let mut copies = Vec::new();
                    if let Some(s) = self.session.as_ref() {
                        let mut taken = s.element_ids();
                        for id in &ids {
                            let mut element = Value::Object(s.element(id)?);
                            let new_id = (1..)
                                .map(|n| format!("{id}_copy{n}"))
                                .find(|c| !taken.contains(c))
                                .unwrap_or_default();
                            taken.push(new_id.clone());
                            element["id"] = json!(new_id);
                            for key in ["x", "y"] {
                                if let Some(v) = element.get(key).and_then(Value::as_i64) {
                                    element[key] = json!(v + 2);
                                }
                            }
                            copies.push(element);
                        }
                    }
                    if let Some(s) = self.session.as_mut() {
                        let new_ids = s.add_elements(copies, "duplicate")?;
                        self.selection
                            .replace(&new_ids, new_ids.last().map(String::as_str));
                    }
                }
                "front" => self.session_ids(|s, ids| s.bring_to_front(ids))?,
                "back" => self.session_ids(|s, ids| s.send_to_back(ids))?,
                "lock" => self.session_ids(|s, ids| s.set_locked(ids, true))?,
                "unlock" => self.session_ids(|s, ids| s.set_locked(ids, false))?,
                "hide" => self.session_ids(|s, ids| s.set_hidden(ids, true))?,
                "show" => self.session_ids(|s, ids| s.set_hidden(ids, false))?,
                "group" => {
                    let id = self.unique_id("group");
                    self.session_ids(|s, ids| s.group_elements(ids, &id).map(|_| ()))?;
                }
                "ungroup" => self.session_ids(|s, ids| s.ungroup_elements(ids))?,
                "snap" => {
                    let grid = self.prefs.int("canvas.snap").max(1);
                    self.session_ids(|s, ids| snap_positions(s, ids, grid))?;
                }
                "toggle-play" | "step" => {
                    if let Some(s) = self.session.as_mut() {
                        s.step(1)?;
                    }
                }
                "reset-runtime" => {
                    if let Some(s) = self.session.as_mut() {
                        s.reset_runtime()?;
                    }
                }
                other if other.starts_with("align:") => {
                    let mode = &other[6..];
                    let reference = self
                        .ui
                        .upgrade()
                        .map(|ui| DesignerModel::get(&ui).get_align_reference())
                        .unwrap_or(0);
                    let reference =
                        ["selection", "primary", "canvas"][reference.clamp(0, 2) as usize];
                    let primary = self.selection.primary().map(str::to_string);
                    let ids = self.selected();
                    if let Some(s) = self.session.as_mut() {
                        align_to(s, &ids, mode, reference, primary.as_deref())?;
                    }
                }
                other if other.starts_with("distribute:") => {
                    let axis = &other[11..];
                    let ids = self.selected();
                    if let Some(s) = self.session.as_mut() {
                        distribute(s, &ids, axis)?;
                    }
                }
                _ => return Err(CoreError::new("E-APP-UNHANDLED", action.to_string())),
            }
            Ok(())
        })();
        match result {
            Ok(()) => {
                self.log_event(action.to_uppercase());
                self.selection.retain_existing(
                    &self
                        .session
                        .as_ref()
                        .map(EditorSession::element_ids)
                        .unwrap_or_default(),
                );
                self.after_edit();
            }
            Err(e) if e.code == "E-APP-UNHANDLED" => {}
            Err(e) => {
                self.error(&e);
                self.after_edit();
            }
        }
    }

    fn session_ids(
        &mut self,
        f: impl FnOnce(&mut EditorSession, &[String]) -> Result<(), CoreError>,
    ) -> Result<(), CoreError> {
        let ids = self.selected();
        if ids.is_empty() {
            return Ok(());
        }
        match self.session.as_mut() {
            Some(s) => f(s, &ids),
            None => Ok(()),
        }
    }

    pub fn save(&mut self) -> Result<(), CoreError> {
        if let Some(session) = self.session.as_mut() {
            let path = session.save()?;
            self.baseline_pixels = session
                .render()
                .map(|r| r.framebuffer.pixels().to_vec())
                .unwrap_or_default();
            self.baseline_elements = session
                .scene()
                .get("elements")
                .and_then(Value::as_array)
                .cloned()
                .unwrap_or_default();
            let message = trf(&self.lang, "status.saved_to", &[("path", posix(&path))]);
            self.log_event(format!("SAVE {}", posix(&path)));
            self.set_status(message);
        }
        if let Some(project) = self.project.as_mut() {
            project.save()?;
        }
        Ok(())
    }

    pub fn set_canvas_size(&mut self, w: i32, h: i32) {
        if let Some(s) = self.session.as_mut() {
            if let Err(e) = s.set_canvas_size(i64::from(w), i64::from(h)) {
                self.error(&e);
            }
        }
        self.after_edit();
    }

    // -------------------------------------------------------------- delivery

    fn scene_parts(&self) -> Option<(serde_json::Map<String, Value>, PathBuf)> {
        self.session
            .as_ref()
            .map(|s| (s.scene().clone(), s.root().to_path_buf()))
    }

    pub fn export_states(&mut self, all: bool, output: &Path) -> Result<String, CoreError> {
        let Some((scene, root)) = self.scene_parts() else {
            return Ok(String::new());
        };
        let states = if all {
            build_export_states(&scene, IntegerPolicy::Representative, 5000, false)?
        } else {
            let state = self
                .session
                .as_ref()
                .map(|s| s.state.clone())
                .unwrap_or_default();
            vec![("current".to_string(), state)]
        };
        let summary = export_scene(&scene, &root, output, &states, &mut |_, _, _| true)?;
        Ok(trf(
            &self.lang,
            "status.exported",
            &[
                ("count", summary.frame_count.to_string()),
                ("path", posix(output)),
            ],
        ))
    }

    pub fn handoff(&mut self, output: &Path) -> Result<String, CoreError> {
        let Some((scene, root)) = self.scene_parts() else {
            return Ok(String::new());
        };
        let states = build_export_states(&scene, IntegerPolicy::Representative, 5000, false)?;
        let summary = build_handoff_package(
            &scene,
            &root,
            output,
            &states,
            IntegerPolicy::Representative,
            &mut |_, _, _| true,
        )?;
        Ok(trf(
            &self.lang,
            "status.handoff_done",
            &[
                ("count", summary.frame_count.to_string()),
                ("path", posix(output)),
            ],
        ))
    }

    pub fn batch_validate(&mut self) -> Result<String, CoreError> {
        let Some((scene, root)) = self.scene_parts() else {
            return Ok(String::new());
        };
        let states = build_export_states(&scene, IntegerPolicy::Boundaries, 5000, false)?;
        let matrix: Vec<_> = states.into_iter().map(|(_, s)| s).collect();
        let summary = validate_matrix(&scene, &root, &matrix, &mut |_, _, _| true)?;
        let report = matrix_report(&summary);
        for line in report.lines().filter(|l| l.starts_with("- **")) {
            self.log_event(line.to_string());
        }
        Ok(trf(
            &self.lang,
            "status.batch_done",
            &[
                ("cases", summary.cases.to_string()),
                ("findings", summary.findings.to_string()),
                ("blockers", summary.blockers.to_string()),
            ],
        ))
    }

    pub fn current_framebuffer(&mut self) -> Option<mono_core::FrameBuffer> {
        self.session
            .as_mut()
            .and_then(|s| s.render().ok())
            .map(|r| r.framebuffer)
    }
}

pub fn zoom_for(index: i32) -> f32 {
    ZOOM_STEPS
        .get(index.max(0) as usize)
        .copied()
        .unwrap_or(0.0)
}
