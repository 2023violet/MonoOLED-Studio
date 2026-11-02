//! Application controller: owns the project, the Designer session and the UI
//! sync. Every UI callback goes through `App`; Slint models are rebuilt from
//! the session after each change (the scene JSON stays the single truth).

use std::collections::{BTreeMap, HashMap, HashSet};
use std::path::{Path, PathBuf};

use mono_core::CoreError;
use mono_core::pyvalue::{py_int, py_str};
use mono_core::render::{member_path, posix};
use mono_core::state::{
    IntegerPolicy, RELATION_OPERATORS, build_export_states, schema_from_scene,
    validate_state_schema,
};
use mono_project::editor::{
    EditorSession, OverlayRect, Selection, align_to, distribute, overlay_rect, selection_metrics,
    smart_guides, snap_positions,
};
use mono_project::export::{
    BlockedExport, EXPORT_BLOCKED, Finding, build_handoff_package, check_design_rules,
    export_scene_with_report, matrix_report, preflight, validate_matrix, validate_scene,
    write_validation_report,
};
use mono_project::project::{ProjectWorkspace, create_project};
use mono_project::resources::DiskResources;
use mono_project::scene_io::{SceneDoc, load_project_scene, load_scene};
use serde_json::{Value, json};
use slint::{Global, ModelRc, SharedString, VecModel};

use crate::agent::Agent;
use crate::bgjob::{BackgroundJob, Outcome, Poll};
use crate::canvas::image_from_pixels;
use crate::extras::{Picker, Profiler};
use crate::fontlab::FontLab;
use crate::i18n::{tr, trf};
use crate::pixel::PixelStudio;
use crate::pixel_ui::ImportState;
use crate::prefs::Preferences;
use crate::workbench::Workbench;
use crate::{
    AppModel, AssetItem, BlockedItem, DesignerModel, ElementItem, FindingItem, MainWindow,
    OverlayBox, PillTone, RuleGroup, RuleText, RuleZone, ScreenItem, StateRelation, StateVar,
    StateVarSpec,
};

const ZOOM_STEPS: [f32; 8] = [0.0, 1.0, 2.0, 4.0, 6.0, 8.0, 12.0, 16.0];

pub enum Prompt {
    NewScreen,
    DuplicateScreen,
    /// Rename whichever screen is active when the answer arrives.
    RenameScreen,
    CSymbol(PathBuf),
    NewFontPack,
    TemplateName,
    TemplatePrefix(String),
    BitmapText(PathBuf),
    BitmapTextId(PathBuf, String),
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
    /// The last frame's resolved rects, index-aligned with the scene elements:
    /// the overlay and hit-testing read these instead of a geometry lookup per
    /// element (which clones the list, and re-renders text elements).
    last_resolved: Vec<Value>,
    /// Scheduling for the off-thread validation: the newest epoch wins, and a
    /// result computed for a scene that is no longer open is dropped.
    validation_epoch: u64,
    validation_rx: Option<std::sync::mpsc::Receiver<(u64, Vec<Finding>)>>,
    /// An edit arrived while a pass was running: validate again once it lands.
    validation_dirty: bool,
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
    pub font: Option<FontLab>,
    /// Export / handoff / batch validation / thumbnail wall running off the UI thread.
    pub bg_job: Option<BackgroundJob>,
    /// Stage last reported by the running job; changes are logged once each.
    pub job_stage: String,
    /// Schema the state panel is editing. Only set while it is invalid: a valid
    /// draft is written straight into the scene, so the panel cannot drift from
    /// what a save would produce.
    pub schema_draft: Option<Value>,
    /// Same idea for the project's design rules: held while invalid, written to
    /// the manifest as soon as it parses.
    pub rules_draft: Option<Value>,
    pub picker: Option<Picker>,
    pub picker_matches: Vec<(String, String)>,
    pub profiler: Profiler,
    pub last_autosave: std::time::Instant,
    pub agent: Option<Agent>,
    /// False for screenshots, benches and tests: never block on a dialog.
    pub interactive: bool,
    /// Answer used for unsaved-changes questions when not interactive.
    pub scripted_choice: Option<crate::guard::Unsaved>,
    /// Display colour editor texts (saved only when all four are valid).
    pub display_draft: [String; 4],
    /// Visible cells of the Pixel canvas and the outline runs shown for them.
    pub cell_window: crate::canvas::CellWindow,
    pub border_lines: std::rc::Rc<slint::VecModel<crate::BorderLine>>,
    /// Element behind each row of the blocked-export dialog.
    pub blocked_targets: Vec<Option<String>>,
    pub blocked_report: Option<PathBuf>,
    /// Preference edits buffered in memory, waiting for the debounced write.
    pub prefs_pending: bool,
    pub prefs_edit_at: Option<std::time::Instant>,
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
            last_resolved: Vec::new(),
            validation_epoch: 0,
            validation_rx: None,
            validation_dirty: false,
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
            font: None,
            bg_job: None,
            job_stage: String::new(),
            schema_draft: None,
            rules_draft: None,
            picker: None,
            picker_matches: Vec::new(),
            profiler: Profiler::default(),
            last_autosave: std::time::Instant::now(),
            agent: None,
            interactive: false,
            scripted_choice: None,
            display_draft: Default::default(),
            cell_window: crate::canvas::CellWindow::default(),
            border_lines: std::rc::Rc::new(slint::VecModel::default()),
            blocked_targets: Vec::new(),
            blocked_report: None,
            prefs_pending: false,
            prefs_edit_at: None,
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

    /// Clear a status left over from the previous project / workspace.
    pub fn reset_status(&mut self) {
        if self.bg_job.is_none() {
            let text = self.t("status.ready");
            self.set_status(text);
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
        // Font packs belong to a project; never carry one into another.
        self.font = None;
        self.project = Some(project);
        self.bind_scene(scene)?;
        self.scan_project_files();
        self.reset_status();
        Ok(())
    }

    pub fn open_scene_file(&mut self, path: &Path) -> Result<(), CoreError> {
        let scene = load_scene(path, None)?;
        self.font = None;
        self.project = None;
        self.bind_scene(scene)?;
        self.scan_project_files();
        self.reset_status();
        Ok(())
    }

    pub fn new_project(&mut self, root: &Path, name: &str) -> Result<(), CoreError> {
        let project = create_project(root, name, (128, 32))?;
        let path = project.path.clone();
        self.open_project(&path)
    }

    pub(crate) fn bind_scene(&mut self, scene: SceneDoc) -> Result<(), CoreError> {
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
        // Anything the worker is still validating belongs to the old scene.
        self.validation_epoch += 1;
        self.validation_rx = None;
        self.validation_dirty = false;
        self.selection.clear();
        self.drag = None;
        self.schema_draft = None;
        self.rules_draft = None;
        self.refresh_all();
        Ok(())
    }

    /// V1 `_project_screen_changed`: ask about unsaved edits, then switch.
    pub fn open_screen(&mut self, screen_id: &str) -> Result<(), CoreError> {
        if !self.confirm_scene_transition() {
            self.refresh_navigator();
            return Ok(());
        }
        self.switch_screen(screen_id)
    }

    /// Re-derive the pixel-diff baseline after the session was rebound in place
    /// (Agent `project.open_screen` and friends).
    pub fn rebaseline(&mut self) {
        if let Some(session) = self.session.as_mut() {
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
        }
        self.selection.clear();
        self.drag = None;
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
        let (mut assets, mut ignored) = (Vec::new(), Vec::new());
        for dir in &dirs {
            walk(&root.join(dir), &root, &mut assets, &mut ignored);
        }
        // V1 `_resource_scan_fonts`: `.oled/fonts`, `fonts` and the packs scene
        // elements reference, each searched recursively inside the project.
        let mut candidates = vec![root.join(".oled").join("fonts"), root.join("fonts")];
        if let Some(elements) = self
            .session
            .as_ref()
            .and_then(|s| s.scene().get("elements").and_then(Value::as_array).cloned())
        {
            for element in elements {
                let rel = element.get("font_pack").and_then(Value::as_str);
                // A member outside the project is reported by validation; the
                // scan must not walk it or offer it for opening.
                if let Some(path) = rel.and_then(|rel| member_path(&root, Path::new(rel)).ok()) {
                    candidates.push(if path.is_dir() {
                        path
                    } else {
                        path.parent().map(Path::to_path_buf).unwrap_or(path)
                    });
                }
            }
        }
        let mut packs = Vec::new();
        for candidate in candidates {
            if !candidate.starts_with(&root) || !candidate.is_dir() {
                continue;
            }
            if candidate.join("fontpack.json").is_file() {
                packs.push(posix(candidate.strip_prefix(&root).unwrap_or(&candidate)));
            } else {
                walk(&candidate, &root, &mut ignored, &mut packs);
            }
        }
        packs.sort();
        packs.dedup();
        self.assets = assets;
        self.font_packs = packs;
    }

    // ------------------------------------------------------------- refreshing

    pub fn refresh_all(&mut self) {
        let started = std::time::Instant::now();
        self.refresh_all_inner();
        Profiler::record(&mut self.profiler.full, started);
    }

    fn refresh_all_inner(&mut self) {
        self.refresh_navigator();
        self.refresh_canvas();
        self.refresh_inspector();
        self.refresh_state_schema();
        self.refresh_design_rules();
        self.schedule_validation();
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
        // The title dot speaks for the project scene only; Pixel (standalone
        // PNG) and Font Lab keep their own dots in their headers.
        app.set_dirty(self.session.as_ref().is_some_and(EditorSession::is_dirty));
        if self.workspace == 1 || self.workspace == 2 {
            let studio = self.studio();
            app.set_can_undo(studio.doc.can_undo());
            app.set_can_redo(studio.doc.can_redo());
        } else {
            app.set_can_undo(self.session.as_ref().is_some_and(EditorSession::can_undo));
            app.set_can_redo(self.session.as_ref().is_some_and(EditorSession::can_redo));
        }
        app.set_status_text(ss(&self.status));
        app.set_undo_text(ss(self.undo_text()));
        app.set_has_document(self.session.is_some());
        app.set_recent_project(ss(self.prefs.str("startup.last_project")));
        let repo = env!("CARGO_PKG_REPOSITORY");
        app.set_repo_url(ss(repo));
        app.set_docs_url(ss(format!("{repo}/blob/main/docs/README.md")));
        let dm = DesignerModel::get(&ui);
        dm.set_log_lines(model(self.log.iter().rev().take(200).map(ss).collect()));
    }

    /// "Undo" on its own when nothing named is pending; "Undo: move" once the
    /// designer stack knows the last step. Pixel / Font Lab keep their own
    /// histories and report no labels, so they get the plain verb.
    fn undo_text(&self) -> String {
        let token = match self.workspace {
            1 | 2 => None,
            _ => self
                .session
                .as_ref()
                .and_then(EditorSession::undo_label)
                .map(str::to_string),
        };
        match token {
            Some(token) => trf(
                &self.lang,
                "undo.menu",
                &[("what", undo_phrase(&self.lang, &token))],
            ),
            None => self.t("action.undo"),
        }
    }

    pub fn refresh_navigator(&mut self) {
        let Some(ui) = self.ui.upgrade() else { return };
        let dm = DesignerModel::get(&ui);
        let mut screen_current = -1;
        let screens = self
            .project
            .as_ref()
            .map(|p| {
                let active = p.active_screen();
                p.screens()
                    .into_iter()
                    .enumerate()
                    .map(|(index, s)| {
                        if s.id == active {
                            screen_current = index as i32;
                        }
                        ScreenItem {
                            active: s.id == active,
                            id: ss(&s.id),
                            label: ss(&s.label),
                        }
                    })
                    .collect()
            })
            .unwrap_or_default();
        dm.set_screens(model(screens));
        dm.set_screen_current(screen_current);
        let elements: Vec<ElementItem> = self
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
        let element_current = self
            .selection
            .primary()
            .and_then(|primary| {
                elements
                    .iter()
                    .position(|element| element.id.as_str() == primary)
            })
            .map_or(-1, |index| index as i32);
        dm.set_elements(model(elements));
        dm.set_element_current(element_current);
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
        let rules = self.effective_rules();
        let Some(session) = self.session.as_mut() else {
            return;
        };
        let mut resolved: Vec<Value> = Vec::new();
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
                    .map(Vec::as_slice)
                    .unwrap_or(&[]);
                let id_of = |e: &Value| e.get("id").map(py_str).unwrap_or_default();
                let before_ids: HashSet<String> =
                    self.baseline_elements.iter().map(id_of).collect();
                let after_ids: HashSet<String> = current.iter().map(id_of).collect();
                let added = after_ids.difference(&before_ids).count();
                let removed = before_ids.difference(&after_ids).count();
                // One index of the baseline instead of a scan per element.
                let before_by_id: HashMap<String, &Value> = self
                    .baseline_elements
                    .iter()
                    .map(|b| (id_of(b), b))
                    .collect();
                let modified = current
                    .iter()
                    .filter(|e| before_by_id.get(&id_of(e)).is_some_and(|b| *b != *e))
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
                resolved = result.resolved_elements;
            }
            Err(error) => {
                dm.set_framebuffer_summary(ss(format!(
                    "{}: {}",
                    tr(&lang, "status.render_failed"),
                    error.message
                )));
            }
        }
        // Editor-only overlays: element bounds, selection, primary marker. The
        // rects are this frame's resolved elements (one per scene element, in
        // order), so nothing here needs an element or geometry lookup.
        let primary = self.selection.primary().map(str::to_string);
        let rows: Vec<(String, bool, OverlayRect)> = {
            let elements = session
                .scene()
                .get("elements")
                .and_then(Value::as_array)
                .map(Vec::as_slice)
                .unwrap_or(&[]);
            elements
                .iter()
                .enumerate()
                .map(|(index, element)| {
                    (
                        element.get("id").map(py_str).unwrap_or_default(),
                        element.get("hidden") == Some(&Value::Bool(true)),
                        overlay_rect(element, &resolved, index),
                    )
                })
                .collect()
        };
        let mut boxes = Vec::with_capacity(rows.len());
        for (id, hidden, rect) in rows {
            // A hidden element's render entry carries its raw fields, which may
            // be null; the geometry path still resolves those (few, not hot).
            let (x, y, w, h) = match rect {
                Some(rect) => rect,
                None => match session.geometry(&id) {
                    Ok(g) => (g.x, g.y, g.w, g.h),
                    Err(_) => continue,
                },
            };
            boxes.push(OverlayBox {
                id: ss(&id),
                x: x as i32,
                y: y as i32,
                w: w as i32,
                h: h as i32,
                selected: self.selection.contains(&id),
                primary: primary.as_deref() == Some(id.as_str()),
                hidden,
            });
        }
        self.last_resolved = resolved;
        dm.set_boxes(model(boxes));
        // Zones come from the same `design_rules.zones` map that produces
        // ELEMENT_OUTSIDE_ZONE, so the overlay and the finding cannot disagree.
        let mut zones = Vec::new();
        if let Some(rules) = rules.get("zones").and_then(Value::as_object) {
            for (id, rect) in rules {
                let edge = |key: &str| rect.get(key).and_then(Value::as_i64).unwrap_or(0) as i32;
                zones.push(OverlayBox {
                    id: ss(id),
                    x: edge("x"),
                    y: edge("y"),
                    w: edge("w"),
                    h: edge("h"),
                    selected: false,
                    primary: false,
                    hidden: false,
                });
            }
        }
        zones.sort_by(|a, b| a.id.cmp(&b.id));
        dm.set_zones(model(zones));
    }

    pub fn refresh_inspector(&mut self) {
        let Some(ui) = self.ui.upgrade() else { return };
        let dm = DesignerModel::get(&ui);
        let Some(session) = self.session.as_mut() else {
            dm.set_has_selection(false);
            dm.set_selection_text(ss(""));
            return;
        };
        let primary = self
            .selection
            .primary()
            .map(str::to_string)
            .or_else(|| self.selection.ids().last().cloned());
        // The property fields below describe the primary element only, so name
        // the whole selection when it is bigger than one element.
        let count = self.selection.ids().len();
        dm.set_selection_text(if count > 1 {
            ss(trf(
                &self.lang,
                "inspector.selected_count",
                &[("count", count.to_string())],
            ))
        } else {
            ss("")
        });
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

    /// The schema the panel edits: the pending draft, else the scene's own.
    fn schema_snapshot(&self) -> Value {
        if let Some(draft) = &self.schema_draft {
            return draft.clone();
        }
        self.session
            .as_ref()
            .map(|s| schema_from_scene(&s.doc.data))
            .unwrap_or_else(|| json!({"variables": {}, "relations": []}))
    }

    pub fn refresh_state_schema(&mut self) {
        let Some(ui) = self.ui.upgrade() else { return };
        let dm = DesignerModel::get(&ui);
        let draft = self.schema_snapshot();
        let checked = validate_state_schema(&draft);
        let valid = checked.get("valid") == Some(&json!(true));
        let errors = if valid {
            String::new()
        } else {
            let text = checked
                .get("errors")
                .and_then(Value::as_array)
                .map(|list| {
                    list.iter()
                        .map(|e| e.get("message").map(py_str).unwrap_or_default())
                        .collect::<Vec<_>>()
                        .join("; ")
                })
                .unwrap_or_default();
            trf(&self.lang, "state.schema_invalid", &[("errors", text)])
        };
        let (vars, relations, names) = schema_rows(&draft);
        dm.set_schema_vars(model(vars));
        dm.set_relations(model(relations));
        dm.set_var_names(model(names.iter().map(ss).collect()));
        dm.set_relation_ops(model(RELATION_OPERATORS.iter().map(|o| ss(*o)).collect()));
        dm.set_schema_valid(valid);
        dm.set_schema_errors(ss(&errors));
    }

    /// One edit in the state schema panel. A result the engine accepts goes
    /// into the scene as one undo step; anything else stays visible as a draft
    /// with the validator's own message, so nothing the user typed is dropped.
    pub fn schema_edit(&mut self, action: &str, key: &str, value: &str) {
        let mut draft = self.schema_snapshot();
        let handled = edit_variables(&mut draft, action, key, value)
            | edit_relations(&mut draft, action, key, value);
        if !handled {
            return;
        }
        let checked = validate_state_schema(&draft);
        if checked.get("valid") != Some(&json!(true)) {
            self.schema_draft = Some(draft);
            self.refresh_state_schema();
            return;
        }
        let normalized = checked
            .get("schema")
            .cloned()
            .unwrap_or_else(|| json!({"variables": {}, "relations": []}));
        self.schema_draft = None;
        let changed = self
            .session
            .as_mut()
            .is_some_and(|session| session.set_state_schema(&normalized));
        if changed {
            self.after_edit();
        } else {
            self.refresh_state_schema();
        }
    }

    /// The rules the panel edits: the pending draft, else the manifest's own.
    fn rules_snapshot(&self) -> Value {
        if let Some(draft) = &self.rules_draft {
            return draft.clone();
        }
        self.project
            .as_ref()
            .and_then(|project| project.data.get("design_rules"))
            .cloned()
            .unwrap_or_else(|| json!({"required_elements": [], "zones": {}, "baseline_groups": []}))
    }

    /// The rules the overlay and the findings must use. The manifest is the
    /// source of truth: a scene undo restores the whole document, including the
    /// `_design_rules` snapshot injected at load, so reading it back from the
    /// session would let the findings disagree with the file after a Ctrl+Z.
    fn effective_rules(&self) -> Value {
        self.project
            .as_ref()
            .and_then(|project| project.data.get("design_rules"))
            .cloned()
            .or_else(|| {
                self.session
                    .as_ref()
                    .and_then(|session| session.scene().get("_design_rules").cloned())
            })
            .unwrap_or_else(|| json!({"required_elements": [], "zones": {}, "baseline_groups": []}))
    }

    pub fn refresh_design_rules(&mut self) {
        let Some(ui) = self.ui.upgrade() else { return };
        let dm = DesignerModel::get(&ui);
        let rules = self.rules_snapshot();
        let required = rules
            .get("required_elements")
            .and_then(Value::as_array)
            .map(|list| {
                list.iter()
                    .map(|item| RuleText {
                        value: ss(py_str(item)),
                    })
                    .collect()
            })
            .unwrap_or_default();
        let zones = rules
            .get("zones")
            .and_then(Value::as_object)
            .map(|map| {
                map.iter()
                    .map(|(name, rect)| RuleZone {
                        h: ss(rule_edge(rect, "h")),
                        name: ss(name),
                        w: ss(rule_edge(rect, "w")),
                        x: ss(rule_edge(rect, "x")),
                        y: ss(rule_edge(rect, "y")),
                    })
                    .collect()
            })
            .unwrap_or_default();
        let groups = rules
            .get("baseline_groups")
            .and_then(Value::as_array)
            .map(|list| {
                list.iter()
                    .map(|group| RuleGroup {
                        axis: ss(group.get("axis").map(py_str).unwrap_or_else(|| "y".into())),
                        ids: ss(group
                            .get("ids")
                            .and_then(Value::as_array)
                            .map(|ids| ids.iter().map(py_str).collect::<Vec<_>>().join(","))
                            .unwrap_or_default()),
                    })
                    .collect()
            })
            .unwrap_or_default();
        let (valid, errors) = match check_rules_draft(&rules) {
            Ok(()) => (true, String::new()),
            Err(problem) => (
                false,
                trf(&self.lang, "rules.invalid", &[("errors", problem)]),
            ),
        };
        let status = self
            .project
            .as_ref()
            .map(|project| {
                trf(
                    &self.lang,
                    "rules.saved_to",
                    &[("path", posix(&project.path))],
                )
            })
            .unwrap_or_default();
        dm.set_rule_required(model(required));
        dm.set_rule_zones(model(zones));
        dm.set_rule_groups(model(groups));
        dm.set_rules_valid(valid);
        dm.set_rules_errors(ss(&errors));
        dm.set_rules_status(ss(&status));
    }

    /// One edit in the design-rules panel. Rules live in the project manifest,
    /// so a valid result is written to disk immediately and re-injected into
    /// the scene; an invalid one stays on screen.
    pub fn rule_edit(&mut self, action: &str, row: &str, field: &str, value: &str) {
        let mut draft = self.rules_snapshot();
        if !edit_rules(&mut draft, action, row, field, value) {
            return;
        }
        if let Err(problem) = check_rules_draft(&draft) {
            self.rules_draft = Some(draft);
            self.set_status(trf(&self.lang, "rules.invalid", &[("errors", problem)]));
            self.refresh_design_rules();
            return;
        }
        self.rules_draft = None;
        match self.apply_rules(&draft) {
            Ok(()) => {}
            Err(error) => {
                self.rules_draft = Some(draft);
                self.error(&error);
                self.refresh_design_rules();
            }
        }
    }

    fn apply_rules(&mut self, rules: &Value) -> Result<(), CoreError> {
        if self.project.is_none() {
            return Err(CoreError::invalid(self.t("status.no_document")));
        }
        if let Some(project) = self.project.as_mut() {
            project.set_design_rules(rules.clone())?;
        }
        // The scene carries the rules as `_design_rules`, which is what the
        // validator reads; refresh it so findings follow without a reopen.
        if let Some(session) = self.session.as_mut() {
            session
                .doc
                .data
                .insert("_design_rules".into(), rules.clone());
        }
        self.log_event("DESIGN_RULES");
        self.refresh_canvas();
        self.schedule_validation();
        self.refresh_design_rules();
        Ok(())
    }

    /// One validation on this thread, on the session's cached resources: the
    /// bench's `panel_validation` row. Interface paths use `schedule_validation`.
    /// It supersedes anything the worker still holds, so its epoch must be newer
    /// and its receiver dropped.
    pub fn refresh_validation(&mut self) {
        self.validation_epoch += 1;
        self.validation_rx = None;
        self.validation_dirty = false;
        let rules = self.effective_rules();
        let Some(session) = self.session.as_mut() else {
            return;
        };
        let mut findings = session.validate();
        findings.extend(check_design_rules(session.scene(), &rules));
        self.apply_findings(findings);
    }

    /// Validate a snapshot off the UI thread. A handler must not wait for a scene
    /// render plus a content hash of every referenced asset; the job tick
    /// applies the result, and only the newest epoch is kept. A drag can ask
    /// faster than one pass completes, so a new pass starts only after the current
    /// one lands: later edits move the epoch, and the tick validates the newest
    /// scene. Only a result is ever waited for: a pass abandoned by a scene switch
    /// may still be finishing next to the new one, and its result is dropped.
    fn schedule_validation(&mut self) {
        if self.session.is_none() {
            return;
        }
        self.validation_epoch += 1;
        self.validation_dirty = true;
        if self.validation_rx.is_none() {
            self.start_validation();
        }
    }

    fn start_validation(&mut self) {
        let Some(session) = self.session.as_ref() else {
            self.validation_dirty = false;
            return;
        };
        self.validation_dirty = false;
        let scene = session.scene().clone();
        let root = session.root().to_path_buf();
        let state = session.state.clone();
        let rules = self.effective_rules();
        let epoch = self.validation_epoch;
        let (tx, rx) = std::sync::mpsc::channel();
        self.validation_rx = Some(rx);
        std::thread::spawn(move || {
            let _ = tx.send((epoch, validate_snapshot(&scene, &root, &state, &rules)));
        });
    }

    /// Apply a finished background validation if it is still the newest one,
    /// then start the pass an edit asked for while this one was running.
    pub fn poll_validation(&mut self) {
        let Some(rx) = self.validation_rx.as_ref() else {
            return;
        };
        let outcome = match rx.try_recv() {
            Err(std::sync::mpsc::TryRecvError::Empty) => return,
            other => other,
        };
        self.validation_rx = None;
        match outcome {
            Ok((epoch, findings)) if epoch == self.validation_epoch => {
                self.apply_findings(findings);
            }
            Ok(_) => {}
            // The worker died without an answer. Keep the receiver and no later
            // edit could ever start a pass again.
            Err(_) => self.log_event("VALIDATION_WORKER_LOST"),
        }
        if self.validation_dirty {
            self.start_validation();
        }
    }

    /// Scripted dumps read findings right after an edit, so they wait for the
    /// pending validation instead of reporting the previous scene.
    pub fn flush_validation(&mut self) {
        loop {
            let Some(rx) = self.validation_rx.take() else {
                if self.validation_dirty {
                    self.start_validation();
                }
                return;
            };
            match rx.recv() {
                Ok((epoch, findings)) if epoch == self.validation_epoch => {
                    self.apply_findings(findings);
                }
                Ok(_) => {}
                Err(_) => self.log_event("VALIDATION_WORKER_LOST"),
            }
            if !self.validation_dirty {
                return;
            }
            self.start_validation();
        }
    }

    /// Nothing the worker still holds may land on the state left behind when a
    /// session is dropped without a replacement.
    pub(crate) fn drop_session(&mut self) {
        self.session = None;
        self.validation_epoch += 1;
        self.validation_rx = None;
        self.validation_dirty = false;
    }

    fn apply_findings(&mut self, findings: Vec<Finding>) {
        let Some(ui) = self.ui.upgrade() else {
            self.findings = findings;
            return;
        };
        let dm = DesignerModel::get(&ui);
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

    // --------------------------------------------------------------- bench

    /// Bench instrumentation: put the Designer back in front and select an
    /// element, so `geometry_edited` has a target. False when the bench ran
    /// without a project.
    pub fn bench_designer_ready(&mut self, ui: &MainWindow) -> bool {
        AppModel::get(ui).set_workspace(0);
        self.workspace = 0;
        if self
            .session
            .as_ref()
            .is_none_or(|s| s.element_ids().is_empty())
        {
            // The fixture opens on an empty screen; the phase needs content.
            let screens: Vec<String> = self
                .project
                .as_ref()
                .map(|p| p.screens().into_iter().map(|s| s.id).collect())
                .unwrap_or_default();
            for id in screens {
                if self.switch_screen(&id).is_ok()
                    && self
                        .session
                        .as_ref()
                        .is_some_and(|s| !s.element_ids().is_empty())
                {
                    break;
                }
            }
            self.refresh_all();
        }
        let Some(id) = self
            .session
            .as_ref()
            .and_then(|s| s.element_ids().into_iter().next())
        else {
            return false;
        };
        self.element_clicked(&id, false);
        true
    }

    /// Bench instrumentation: median wall time of each refresh entry point, so
    /// one edit's latency can be attributed to a panel instead of guessed at.
    pub fn bench_panels(&mut self) -> Vec<(&'static str, f64)> {
        const RUNS: usize = 5;
        fn median(mut runs: Vec<f64>) -> f64 {
            runs.sort_by(f64::total_cmp);
            runs.get(runs.len() / 2).copied().unwrap_or(0.0)
        }
        /// A handler sample that pays for its own validation snapshot: a pass
        /// left pending by the previous sample would make it skip the clone.
        fn time_handler(app: &mut App, runs: usize, mut run: impl FnMut(&mut App)) -> f64 {
            let mut samples = Vec::with_capacity(runs);
            for _ in 0..runs {
                app.flush_validation();
                let started = std::time::Instant::now();
                run(app);
                samples.push(started.elapsed().as_secs_f64() * 1000.0);
            }
            median(samples)
        }
        fn time(runs: usize, mut run: impl FnMut()) -> f64 {
            let mut samples = Vec::with_capacity(runs);
            for _ in 0..runs {
                let started = std::time::Instant::now();
                run();
                samples.push(started.elapsed().as_secs_f64() * 1000.0);
            }
            median(samples)
        }
        let target = self.selection.primary().map(str::to_string);
        let mut next_x = 8i64;
        let mut edit_x = 6;
        let snapshot = self
            .session
            .as_ref()
            .map(|s| (s.scene().clone(), s.root().to_path_buf(), s.state.clone()));
        let rules = self.effective_rules();
        // The first enum state with two values, for a real state edit.
        let choice = snapshot.as_ref().and_then(|(scene, ..)| {
            let states = scene.get("states").and_then(Value::as_object)?;
            states.iter().find_map(|(name, spec)| {
                let values = spec.get("values").and_then(Value::as_array)?;
                let (first, second) = (values.first()?, values.get(1)?);
                Some((name.clone(), py_str(first), py_str(second)))
            })
        });
        let mut use_first = false;
        let rows = vec![
            ("navigator", time(RUNS, || self.refresh_navigator())),
            ("canvas", time(RUNS, || self.refresh_canvas())),
            ("inspector", time(RUNS, || self.refresh_inspector())),
            ("schema", time(RUNS, || self.refresh_state_schema())),
            ("rules", time(RUNS, || self.refresh_design_rules())),
            ("validation", time(RUNS, || self.refresh_validation())),
            // The worker's pass: a fresh resource cache, on this thread only so
            // that it can be timed.
            (
                "validation_worker",
                time(RUNS, || {
                    if let Some((scene, root, state)) = &snapshot {
                        let _ = validate_snapshot(scene, root, state, &rules);
                    }
                }),
            ),
            ("app", time(RUNS, || self.refresh_app())),
            // The refresh body of a screen open or Agent refresh, on the UI thread.
            (
                "refresh_all",
                time_handler(self, RUNS, |app| app.refresh_all_inner()),
            ),
            // A state edit, on the UI thread.
            (
                "state_edit",
                time_handler(self, 3, |app| {
                    if let Some((name, first, second)) = &choice {
                        use_first = !use_first;
                        app.state_edited(name, if use_first { first } else { second });
                    }
                }),
            ),
            // The core render alone, then the whole edit handler body: what the
            // panel rows do not add up to is model-write and snapshot overhead.
            (
                "render",
                time(RUNS, || {
                    if let Some(session) = self.session.as_mut() {
                        let _ = session.render();
                    }
                }),
            ),
            ("edit", time(3, || self.after_edit())),
            // The same entry point the designer phase drives, undo snapshot
            // included, to separate it from the refresh body above.
            (
                "geometry_edit",
                time_handler(self, 3, |app| {
                    // Alternate: an unchanged value skips the transaction.
                    edit_x = if edit_x == 6 { 7 } else { 6 };
                    app.geometry_edited("x", edit_x);
                }),
            ),
            // Just the editor transaction (undo snapshot included), so the
            // difference above splits into refresh body versus scene mutation.
            (
                "set_geometry",
                time(3, || {
                    // Alternate so every sample carries a real change, not the
                    // early return an unchanged value takes.
                    next_x = if next_x == 8 { 12 } else { 8 };
                    if let (Some(session), Some(id)) = (self.session.as_mut(), target.as_deref()) {
                        let _ = session.set_geometry(id, &[("x", next_x)], false);
                    }
                }),
            ),
        ];
        // Nothing the rows above scheduled may run into the next bench phase.
        self.flush_validation();
        rows
    }

    /// Bench instrumentation: what `start_export` pays on the UI thread before
    /// its worker starts — the representative state matrix of the open scene,
    /// timed once (a dense scene can make this the largest block by far).
    pub fn bench_matrix_ms(&mut self) -> Option<(f64, usize)> {
        let scene = self.session.as_ref()?.scene().clone();
        let started = std::time::Instant::now();
        let states =
            build_export_states(&scene, IntegerPolicy::Representative, 5000, false).ok()?;
        let elapsed = started.elapsed().as_secs_f64() * 1000.0;
        Some((elapsed, states.len()))
    }

    // --------------------------------------------------------------- editing

    fn after_edit(&mut self) {
        self.refresh_navigator();
        self.refresh_canvas();
        self.refresh_inspector();
        self.refresh_state_schema();
        self.refresh_design_rules();
        self.schedule_validation();
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

    /// Topmost element under the pointer, from the last frame's resolved rects
    /// (the same rects the overlay draws). Hidden elements without coordinates
    /// are the one case the render result leaves unresolved; those still take
    /// the geometry path, so a click lands where it did before.
    fn hit_test(&mut self, x: f32, y: f32) -> Option<String> {
        let (px, py) = (x as i64, y as i64);
        let mut ids: Vec<String> = Vec::new();
        let mut rects: Vec<OverlayRect> = Vec::new();
        {
            let resolved = &self.last_resolved;
            let session = self.session.as_ref()?;
            let elements = session
                .scene()
                .get("elements")
                .and_then(Value::as_array)
                .map(Vec::as_slice)
                .unwrap_or(&[]);
            for (index, element) in elements.iter().enumerate() {
                ids.push(element.get("id").map(py_str).unwrap_or_default());
                rects.push(overlay_rect(element, resolved, index));
            }
        }
        if rects.iter().any(Option::is_none) {
            if let Some(session) = self.session.as_mut() {
                for (index, rect) in rects.iter_mut().enumerate() {
                    if rect.is_none() {
                        if let Ok(g) = session.geometry(&ids[index]) {
                            *rect = Some((g.x, g.y, g.w, g.h));
                        }
                    }
                }
            }
        }
        topmost_at(&rects, px, py).map(|index| ids[index].clone())
    }

    pub fn canvas_pointer(&mut self, phase: &str, x: f32, y: f32, shift: bool, ctrl: bool) {
        let started = std::time::Instant::now();
        self.canvas_pointer_inner(phase, x, y, shift, ctrl);
        if phase == "move" && self.drag.as_ref().is_some_and(|d| d.moved) {
            Profiler::record(&mut self.profiler.drag, started);
        }
    }

    fn canvas_pointer_inner(&mut self, phase: &str, x: f32, y: f32, shift: bool, ctrl: bool) {
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
        self.schedule_validation();
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
        // Every action here edits the Designer scene; without one, say so
        // instead of silently doing nothing.
        if self.session.is_none() {
            let message = self.t("status.no_document");
            self.error(&CoreError::invalid(message));
            return;
        }
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
                "step" => {
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

    /// Export the current state or the whole state matrix in the background.
    pub fn start_export(&mut self, all: bool, output: PathBuf) -> Result<(), CoreError> {
        let Some((scene, root)) = self.scene_parts() else {
            return Err(CoreError::invalid(self.t("status.no_document")));
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
        let lang = self.lang.clone();
        let report = output.join("validation_report.md");
        self.start_background("action.export_all", move |progress| {
            let result =
                export_scene_with_report(&scene, &root, &output, &states, Some(&report), progress);
            let summary = match result {
                Err(failure) if failure.code == EXPORT_BLOCKED => {
                    return blocked_after_failure(&scene, &root, &states, report, &lang, failure);
                }
                other => other?,
            };
            Ok(Outcome {
                status: trf(
                    &lang,
                    "status.exported",
                    &[
                        ("count", summary.frame_count.to_string()),
                        ("path", posix(&output)),
                    ],
                ),
                ..Outcome::default()
            })
        })
    }

    /// Build the Code AI handoff ZIP in the background.
    pub fn start_handoff(&mut self, output: PathBuf) -> Result<(), CoreError> {
        let Some((scene, root)) = self.scene_parts() else {
            return Err(CoreError::invalid(self.t("status.no_document")));
        };
        let states = build_export_states(&scene, IntegerPolicy::Representative, 5000, false)?;
        let lang = self.lang.clone();
        let report = output.with_extension("validation.md");
        self.start_background("action.handoff", move |progress| {
            let result = build_handoff_package(
                &scene,
                &root,
                &output,
                &states,
                IntegerPolicy::Representative,
                progress,
            );
            let summary = match result {
                Err(failure) if failure.code == EXPORT_BLOCKED => {
                    return blocked_after_failure(&scene, &root, &states, report, &lang, failure);
                }
                other => other?,
            };
            Ok(Outcome {
                status: trf(
                    &lang,
                    "status.handoff_done",
                    &[
                        ("count", summary.frame_count.to_string()),
                        ("path", posix(&output)),
                    ],
                ),
                ..Outcome::default()
            })
        })
    }

    /// Write the current frame as a C header, refusing scenes that fail the
    /// same release gate as every other export.
    pub fn export_c_header(&mut self, path: &Path) -> Result<(), CoreError> {
        let Some((scene, root)) = self.scene_parts() else {
            return Err(CoreError::invalid(self.t("status.no_document")));
        };
        let state = self
            .session
            .as_ref()
            .map(|s| s.state.clone())
            .unwrap_or_default();
        let findings = preflight(&scene, &root, &[("current".into(), state)])?;
        if BlockedExport::has_blockers(&findings) {
            let report = root.join(".oled").join("validation_report.md");
            write_validation_report(&report, &findings)?;
            let count = findings
                .values()
                .flatten()
                .filter(|f| f.is_blocking())
                .count();
            self.set_status(trf(
                &self.lang,
                "status.export_blocked",
                &[("count", count.to_string()), ("report", posix(&report))],
            ));
            self.show_blocked(&BlockedExport {
                findings,
                report: Some(report),
            });
            return Ok(());
        }
        let fb = self.current_framebuffer()?;
        let text = mono_core::c_header::framebuffer_to_c_header(&fb, "oled_frame")?;
        mono_project::atomic::atomic_write(path, text.as_bytes())?;
        self.set_status(posix(path));
        Ok(())
    }

    /// Validate the boundary state matrix in the background.
    pub fn start_batch_validate(&mut self) -> Result<(), CoreError> {
        let Some((scene, root)) = self.scene_parts() else {
            return Err(CoreError::invalid(self.t("status.no_document")));
        };
        let states = build_export_states(&scene, IntegerPolicy::Representative, 5000, false)?;
        let lang = self.lang.clone();
        self.start_background("action.batch_validate", move |progress| {
            let matrix: Vec<_> = states.into_iter().map(|(_, s)| s).collect();
            let summary = validate_matrix(&scene, &root, &matrix, progress)?;
            // Same policy and rules as the export gate, so the panel and the
            // batch report cannot disagree about a release.
            let rules =
                check_design_rules(&scene, scene.get("_design_rules").unwrap_or(&json!({})));
            let mut report = matrix_report(&summary);
            if !rules.is_empty() {
                report.push_str("\n## Project Design Rules\n\n");
                for finding in &rules {
                    report.push_str(&format!(
                        "- **{}/{}**: {}\n",
                        finding.severity, finding.code, finding.message
                    ));
                }
            }
            let findings = summary.findings + rules.len();
            let blockers = summary.blockers + rules.iter().filter(|f| f.is_blocking()).count();
            Ok(Outcome {
                status: trf(
                    &lang,
                    "status.batch_done",
                    &[
                        ("cases", summary.cases.to_string()),
                        ("findings", findings.to_string()),
                        ("blockers", blockers.to_string()),
                    ],
                ),
                log: report
                    .lines()
                    .filter(|l| l.starts_with("- **"))
                    .map(str::to_string)
                    .collect(),
                refresh: true,
                blocked: None,
            })
        })
    }

    /// Start `work` on a worker thread; one background job at a time.
    pub fn start_background<F>(&mut self, label_key: &str, work: F) -> Result<(), CoreError>
    where
        F: FnOnce(&mut dyn FnMut(&str, usize, usize) -> bool) -> Result<Outcome, CoreError>
            + Send
            + 'static,
    {
        if let Some(job) = &self.bg_job {
            return Err(CoreError::invalid(trf(
                &self.lang,
                "job.busy",
                &[("label", job.label.clone())],
            )));
        }
        let label = self.t(label_key);
        let started = trf(&self.lang, "job.started", &[("label", label.clone())]);
        self.set_status(started.clone());
        self.log_event(format!("JOB_START {label_key}"));
        self.job_stage.clear();
        self.bg_job = Some(BackgroundJob::spawn(label, work));
        // The status bar shows the busy text instead of the status line, so it
        // has to carry something before the first progress poll.
        self.report_job(true, &started);
        Ok(())
    }

    /// Mirror the running job into the status bar (label + cancel control).
    fn report_job(&mut self, running: bool, text: &str) {
        let Some(ui) = self.ui.upgrade() else {
            return;
        };
        let app = AppModel::get(&ui);
        app.set_busy(running);
        app.set_busy_text(ss(text));
    }

    /// Job timer: progress in the status bar, then the result.
    pub fn poll_background(&mut self) {
        let Some(job) = &self.bg_job else { return };
        match job.poll() {
            Poll::Running(p) => {
                let label = job.label.clone();
                let text = if p.total > 0 {
                    trf(
                        &self.lang,
                        "job.progress",
                        &[
                            ("label", label.clone()),
                            ("done", p.done.to_string()),
                            ("total", p.total.to_string()),
                        ],
                    )
                } else {
                    trf(&self.lang, "job.started", &[("label", label.clone())])
                };
                // The worker's own stage name is a diagnostic token, so it goes
                // to the log rather than the status bar.
                if !p.stage.is_empty() && p.stage != self.job_stage {
                    self.job_stage = p.stage.clone();
                    self.log_event(format!(
                        "JOB_STAGE {label} {} {}/{}",
                        p.stage, p.done, p.total
                    ));
                }
                self.report_job(true, &text);
            }
            Poll::Finished(result) => {
                let label = job.label.clone();
                self.bg_job = None;
                self.job_stage.clear();
                self.report_job(false, "");
                match result {
                    Ok(outcome) => {
                        let Outcome {
                            status,
                            log,
                            refresh,
                            blocked,
                        } = outcome;
                        for line in log {
                            self.log_event(line);
                        }
                        self.log_event(format!("JOB_DONE {label}"));
                        self.set_status(status);
                        if let Some(blocked) = &blocked {
                            self.show_blocked(blocked);
                        }
                        if refresh {
                            self.refresh_app();
                        }
                    }
                    Err(e) if e.code == mono_project::export::CANCELLED => {
                        self.log_event(format!("JOB_CANCELLED {label}"));
                        self.set_status(trf(&self.lang, "job.cancelled", &[("label", label)]));
                    }
                    Err(e) => self.error(&e),
                }
            }
        }
    }

    /// Ask the running background job to stop at its next progress report.
    pub fn cancel_background(&mut self) {
        if let Some(job) = &self.bg_job {
            job.cancel();
            let label = job.label.clone();
            self.set_status(trf(&self.lang, "job.cancelling", &[("label", label)]));
        }
    }

    pub fn current_framebuffer(&mut self) -> Result<mono_core::FrameBuffer, CoreError> {
        let message = self.t("status.no_document");
        let session = self
            .session
            .as_mut()
            .ok_or_else(|| CoreError::invalid(message))?;
        Ok(session.render()?.framebuffer)
    }

    // ------------------------------------------------------------ blocked gate

    /// Fill and show the blocked-export dialog from a refused job.
    pub fn show_blocked(&mut self, blocked: &BlockedExport) {
        let mut items = Vec::new();
        let mut targets = Vec::new();
        for (frame, findings) in &blocked.findings {
            for finding in findings.iter().filter(|f| f.is_blocking()) {
                let target = finding.element_id.clone().filter(|id| !id.is_empty());
                items.push(BlockedItem {
                    severity: ss(&finding.severity),
                    code: ss(&finding.code),
                    message: ss(&finding.message),
                    frame: ss(frame),
                    jumpable: target.is_some(),
                });
                targets.push(target);
            }
        }
        let count = items.len();
        self.blocked_targets = targets;
        self.blocked_report = blocked.report.clone();
        self.log_event(format!("EXPORT_BLOCKED {count}"));
        if let Some(ui) = self.ui.upgrade() {
            let app = AppModel::get(&ui);
            app.set_blocked_items(model(items));
            app.set_blocked_report(ss(blocked.report.as_deref().map(posix).unwrap_or_default()));
            app.set_blocked_summary(ss(trf(
                &self.lang,
                "dialog.blocked_summary",
                &[("count", count.to_string())],
            )));
            app.set_blocked_visible(true);
        }
    }

    pub fn hide_blocked(&mut self) {
        self.blocked_targets.clear();
        self.blocked_report = None;
        if let Some(ui) = self.ui.upgrade() {
            AppModel::get(&ui).set_blocked_visible(false);
        }
    }

    /// Show the offending element in the Designer and open the validation tab.
    pub fn blocked_jump(&mut self, index: i32) {
        let Some(Some(id)) = usize::try_from(index)
            .ok()
            .and_then(|i| self.blocked_targets.get(i))
            .cloned()
        else {
            return;
        };
        self.hide_blocked();
        if let Some(ui) = self.ui.upgrade() {
            AppModel::get(&ui).set_workspace(0);
            DesignerModel::get(&ui).set_drawer_tab(0);
        }
        self.workspace = 0;
        self.element_clicked(&id, false);
        self.refresh_app();
    }

    pub fn copy_blocked_report(&mut self) {
        let Some(report) = self.blocked_report.as_ref() else {
            return;
        };
        let text = posix(report);
        match arboard::Clipboard::new().and_then(|mut c| c.set_text(text.clone())) {
            Ok(()) => self.set_status(text),
            Err(e) => self.error(&CoreError::invalid(e.to_string())),
        }
    }
}

/// Index of the last, so topmost, rect containing the point. An empty rect still
/// answers on its own corner pixel.
fn topmost_at(rects: &[OverlayRect], px: i64, py: i64) -> Option<usize> {
    rects.iter().rposition(|rect| {
        rect.is_some_and(|(x, y, w, h)| {
            px >= x && py >= y && px < x + w.max(1) && py < y + h.max(1)
        })
    })
}

/// One validation pass over a snapshot, as the worker runs it: a fresh resource
/// cache, plus the design rules.
fn validate_snapshot(
    scene: &serde_json::Map<String, Value>,
    root: &Path,
    state: &mono_core::state::State,
    rules: &Value,
) -> Vec<Finding> {
    let mut resources = DiskResources::default();
    let mut findings = validate_scene(scene, root, Some(state), &mut resources);
    findings.extend(check_design_rules(scene, rules));
    findings
}

/// Outcome for a job the release gate refused: the UI opens the blocked dialog.
pub(crate) fn blocked_outcome(
    lang: &str,
    findings: BTreeMap<String, Vec<Finding>>,
    report: PathBuf,
) -> Outcome {
    let count = findings
        .values()
        .flatten()
        .filter(|f| f.is_blocking())
        .count();
    Outcome {
        status: trf(
            lang,
            "status.export_blocked",
            &[("count", count.to_string()), ("report", posix(&report))],
        ),
        blocked: Some(BlockedExport {
            findings,
            report: Some(report),
        }),
        ..Outcome::default()
    }
}

/// A job failed with `EXPORT_BLOCKED`. The gate stops at the first blocking
/// frame, and `preflight` stops there too, so the findings collected here to fill
/// the dialog cover the same frames as the report. A successful export is not
/// validated twice. If the scene has since become exportable, the original error
/// is what the user hears.
pub(crate) fn blocked_after_failure(
    scene: &serde_json::Map<String, serde_json::Value>,
    root: &Path,
    states: &[(String, mono_core::state::State)],
    report: PathBuf,
    lang: &str,
    failure: CoreError,
) -> Result<Outcome, CoreError> {
    let findings = preflight(scene, root, states)?;
    if BlockedExport::has_blockers(&findings) {
        Ok(blocked_outcome(lang, findings, report))
    } else {
        Err(failure)
    }
}

pub fn zoom_for(index: i32) -> f32 {
    ZOOM_STEPS
        .get(index.max(0) as usize)
        .copied()
        .unwrap_or(0.0)
}

/// Undo tokens are machine labels produced by `EditorSession` and the
/// Automation API (`move_batch`, `geometry:battery`). A verb we have copy for
/// translates; an unknown token stays verbatim, which is still more useful to
/// the user than a generic "last edit".
pub(crate) fn undo_phrase(lang: &str, token: &str) -> String {
    let exact = format!("undo.{token}");
    let label = tr(lang, &exact);
    if label != exact {
        return label;
    }
    match token.split_once(':') {
        Some((verb, rest)) => {
            let key = format!("undo.{verb}");
            let phrase = tr(lang, &key);
            if phrase == key {
                token.to_string()
            } else {
                format!("{phrase} {}", rest.replace(':', " "))
            }
        }
        None => token.to_string(),
    }
}

/// Panel rows for a schema draft. The indices point into the name and operator
/// lists so the combo boxes can show each row's current choice.
fn schema_rows(schema: &Value) -> (Vec<StateVarSpec>, Vec<StateRelation>, Vec<String>) {
    let mut names: Vec<String> = Vec::new();
    let mut vars: Vec<StateVarSpec> = Vec::new();
    if let Some(map) = schema.get("variables").and_then(Value::as_object) {
        for (name, spec) in map {
            names.push(name.clone());
            let number = |key: &str| match spec.get(key) {
                Some(Value::String(text)) => text.clone(),
                Some(other) => other.to_string(),
                None => String::new(),
            };
            vars.push(StateVarSpec {
                init: ss(spec.get("init").map(py_str).unwrap_or_default()),
                kind: ss(spec.get("type").map(py_str).unwrap_or_default()),
                max: ss(number("max")),
                min: ss(number("min")),
                name: ss(name),
                values: ss(spec
                    .get("values")
                    .and_then(Value::as_array)
                    .map(|list| list.iter().map(py_str).collect::<Vec<_>>().join(","))
                    .unwrap_or_default()),
            });
        }
    }
    let index_of = |needle: &str| {
        names
            .iter()
            .position(|n| n == needle)
            .map_or(-1, |i| i as i32)
    };
    let relations = schema
        .get("relations")
        .and_then(Value::as_array)
        .map(|list| {
            list.iter()
                .map(|row| {
                    let left = row.get("left").map(py_str).unwrap_or_default();
                    let operator = row.get("operator").map(py_str).unwrap_or_default();
                    let right = row.get("right").map(py_str).unwrap_or_default();
                    StateRelation {
                        left_index: index_of(&left),
                        left: ss(&left),
                        operator_index: RELATION_OPERATORS
                            .iter()
                            .position(|o| *o == operator)
                            .map_or(-1, |i| i as i32),
                        operator: ss(&operator),
                        right_index: index_of(&right),
                        right: ss(&right),
                    }
                })
                .collect()
        })
        .unwrap_or_default();
    (vars, relations, names)
}

/// Apply a variable edit to the draft. False when the action is not one of
/// these, so the caller can still try the relation edits.
fn edit_variables(draft: &mut Value, action: &str, name: &str, value: &str) -> bool {
    let Some(root) = draft.as_object_mut() else {
        return false;
    };
    if !root.contains_key("variables") {
        root.insert("variables".into(), json!({}));
    }
    let Some(vars) = root.get_mut("variables").and_then(Value::as_object_mut) else {
        return false;
    };
    match action {
        "add-variable" => {
            if name.trim().is_empty() {
                return false;
            }
            vars.insert(
                name.trim().to_string(),
                json!({"type": "int", "init": 0, "min": 0, "max": 100}),
            );
        }
        "remove-variable" => {
            vars.shift_remove(name);
        }
        "set-kind" | "set-init" | "set-min" | "set-max" | "set-values" => {
            let Some(spec) = vars.get_mut(name).and_then(Value::as_object_mut) else {
                return false;
            };
            match action {
                "set-kind" => {
                    spec.insert("type".into(), json!(value));
                    if value == "int" {
                        // Discrete int values and enum values are different
                        // shapes; keeping the old list would fail validation.
                        spec.shift_remove("values");
                    }
                }
                "set-init" => {
                    let as_int = spec.get("type").map(py_str).unwrap_or_default() == "int";
                    let parsed = value.trim().parse::<i64>();
                    let next = if as_int {
                        parsed.map_or(json!(value), |n| json!(n))
                    } else {
                        json!(value)
                    };
                    spec.insert("init".into(), next);
                }
                "set-min" | "set-max" => {
                    let field = if action == "set-min" { "min" } else { "max" };
                    let parsed = value.trim().parse::<i64>();
                    spec.insert(field.into(), parsed.map_or(json!(value), |n| json!(n)));
                }
                _ => {
                    let values: Vec<String> = value
                        .split(',')
                        .map(str::trim)
                        .filter(|v| !v.is_empty())
                        .map(str::to_string)
                        .collect();
                    spec.insert("values".into(), json!(values));
                }
            }
        }
        _ => return false,
    }
    true
}

/// Apply a relation edit to the draft. Deleting a variable drops the relations
/// that named it, because they could never validate again.
fn edit_relations(draft: &mut Value, action: &str, row: &str, value: &str) -> bool {
    match action {
        "remove-variable" => {
            if let Some(list) = draft.get_mut("relations").and_then(Value::as_array_mut) {
                list.retain(|relation| {
                    relation.get("left").map(py_str) != Some(row.to_string())
                        && relation.get("right").map(py_str) != Some(row.to_string())
                });
            }
            return true;
        }
        "add-relation" | "remove-relation" | "set-relation-left" | "set-relation-op"
        | "set-relation-right" => {}
        _ => return false,
    }
    let names: Vec<String> = draft
        .get("variables")
        .and_then(Value::as_object)
        .map(|map| map.keys().cloned().collect())
        .unwrap_or_default();
    let root = match draft.as_object_mut() {
        Some(root) => root,
        None => return false,
    };
    if !root.contains_key("relations") {
        root.insert("relations".into(), json!([]));
    }
    let Some(list) = root.get_mut("relations").and_then(Value::as_array_mut) else {
        return false;
    };
    if action == "add-relation" {
        if names.len() < 2 {
            return false;
        }
        list.push(json!({"left": names[0], "operator": "<=", "right": names[1]}));
        return true;
    }
    let Ok(index) = row.parse::<usize>() else {
        return false;
    };
    if action == "remove-relation" {
        if index >= list.len() {
            return false;
        }
        list.remove(index);
        return true;
    }
    let Some(relation) = list.get_mut(index).and_then(Value::as_object_mut) else {
        return false;
    };
    let (field, next) = match action {
        "set-relation-left" | "set-relation-right" => {
            let field = if action == "set-relation-left" {
                "left"
            } else {
                "right"
            };
            (field, names.iter().find(|n| *n == value).cloned())
        }
        "set-relation-op" => (
            "operator",
            RELATION_OPERATORS
                .iter()
                .find(|o| **o == value)
                .map(|o| (*o).to_string()),
        ),
        _ => return false,
    };
    match next {
        Some(name) => {
            relation.insert(field.into(), json!(name));
            true
        }
        None => false,
    }
}

/// A zone edge as panel text: an unparseable entry keeps whatever the user
/// typed so the field does not silently reset.
fn rule_edge(rect: &Value, key: &str) -> String {
    match rect.get(key) {
        Some(Value::String(text)) => text.clone(),
        Some(other) => other.to_string(),
        None => String::new(),
    }
}

/// The rules engine reads zone coordinates as integers and looks elements up by
/// id, so those are the two things the panel can get wrong.
fn check_rules_draft(rules: &Value) -> Result<(), String> {
    let mut problems = Vec::new();
    if let Some(map) = rules.get("zones").and_then(Value::as_object) {
        for (name, rect) in map {
            for key in ["x", "y", "w", "h"] {
                // Same acceptance as the engine's `py_int`, so the panel never
                // rejects what a save would keep.
                if rect.get(key).and_then(py_int).is_none() {
                    problems.push(format!("{name}.{key}"));
                }
            }
        }
    }
    if let Some(list) = rules.get("required_elements").and_then(Value::as_array) {
        for (index, item) in list.iter().enumerate() {
            if item.as_str().map(str::trim).unwrap_or_default().is_empty() {
                problems.push(format!("required_elements[{index}]"));
            }
        }
    }
    if let Some(list) = rules.get("baseline_groups").and_then(Value::as_array) {
        for (index, group) in list.iter().enumerate() {
            let axis = group.get("axis").map(py_str).unwrap_or_default();
            if axis != "x" && axis != "y" {
                problems.push(format!("baseline_groups[{index}].axis"));
            }
            let ids = group
                .get("ids")
                .and_then(Value::as_array)
                .map(|ids| ids.is_empty())
                .unwrap_or(true);
            if ids {
                problems.push(format!("baseline_groups[{index}].ids"));
            }
        }
    }
    if problems.is_empty() {
        Ok(())
    } else {
        Err(problems.join(", "))
    }
}

/// Apply one design-rule edit to the draft. Rows are addressed by index; the
/// zone map is ordered, so the panel's row order is the manifest's.
fn edit_rules(draft: &mut Value, action: &str, row: &str, field: &str, value: &str) -> bool {
    let Some(target) = draft.as_object_mut() else {
        return false;
    };
    let index = row.parse::<usize>().ok();
    match action {
        "add-required" | "set-required" | "remove-required" => {
            let Value::Array(list) = target
                .entry("required_elements".to_string())
                .or_insert_with(|| json!([]))
            else {
                return false;
            };
            let text = value.trim().to_string();
            match action {
                "add-required" => {
                    if text.is_empty() {
                        return false;
                    }
                    list.push(json!(text));
                }
                "remove-required" => {
                    let Some(i) = index.filter(|i| *i < list.len()) else {
                        return false;
                    };
                    list.remove(i);
                }
                _ => {
                    let Some(item) = index.and_then(|i| list.get_mut(i)) else {
                        return false;
                    };
                    *item = json!(text);
                }
            }
        }
        "add-zone" => {
            let Value::Object(map) = target
                .entry("zones".to_string())
                .or_insert_with(|| json!({}))
            else {
                return false;
            };
            let mut next = 1;
            while map.contains_key(&format!("zone_{next}")) {
                next += 1;
            }
            map.insert(
                format!("zone_{next}"),
                json!({"x": 0, "y": 0, "w": 16, "h": 16}),
            );
        }
        "set-zone" | "remove-zone" => {
            let Some(i) = index else { return false };
            let names: Vec<String> = target
                .get("zones")
                .and_then(Value::as_object)
                .map(|map| map.keys().cloned().collect())
                .unwrap_or_default();
            let Some(name) = names.get(i).cloned() else {
                return false;
            };
            let Some(map) = target.get_mut("zones").and_then(Value::as_object_mut) else {
                return false;
            };
            if action == "remove-zone" {
                map.shift_remove(&name);
                return true;
            }
            if field == "name" {
                let text = value.trim().to_string();
                if text.is_empty() || map.contains_key(&text) {
                    return false;
                }
                let Some(rect) = map.shift_remove(&name) else {
                    return false;
                };
                map.insert(text, rect);
                return true;
            }
            if !matches!(field, "x" | "y" | "w" | "h") {
                return false;
            }
            let Some(rect) = map.get_mut(&name).and_then(Value::as_object_mut) else {
                return false;
            };
            let parsed = value.trim().parse::<i64>();
            rect.insert(field.to_string(), parsed.map_or(json!(value), |n| json!(n)));
        }
        "add-group" => {
            let Value::Array(list) = target
                .entry("baseline_groups".to_string())
                .or_insert_with(|| json!([]))
            else {
                return false;
            };
            list.push(json!({"axis": "y", "ids": []}));
        }
        "remove-group" => {
            let Some(i) = index else { return false };
            let Some(list) = target
                .get_mut("baseline_groups")
                .and_then(Value::as_array_mut)
            else {
                return false;
            };
            if i >= list.len() {
                return false;
            }
            list.remove(i);
        }
        "set-group" => {
            let Some(i) = index else { return false };
            let Some(group) = target
                .get_mut("baseline_groups")
                .and_then(Value::as_array_mut)
                .and_then(|list| list.get_mut(i))
                .and_then(Value::as_object_mut)
            else {
                return false;
            };
            match field {
                "axis" => {
                    group.insert("axis".into(), json!(if value == "x" { "x" } else { "y" }));
                }
                "ids" => {
                    let ids: Vec<String> = value
                        .split(',')
                        .map(str::trim)
                        .filter(|id| !id.is_empty())
                        .map(str::to_string)
                        .collect();
                    group.insert("ids".into(), json!(ids));
                }
                _ => return false,
            }
        }
        _ => return false,
    }
    true
}

#[cfg(test)]
mod tests {
    #![allow(clippy::unwrap_used)]

    use super::undo_phrase;
    use crate::i18n::has_key;

    /// The canvas redraw must read the frame it just rendered. One `geometry`
    /// fallback is allowed (a render failure, or a hidden element whose render
    /// entry has no rect); a loop over element ids asking `geometry` is the
    /// O(n²) shape that made one edit of a 1005-element scene take 480 ms.
    #[test]
    fn the_canvas_redraw_does_not_look_up_geometry_per_element() {
        let source = include_str!("app.rs");
        let start = source.find("pub fn refresh_canvas(&mut self) {").unwrap();
        let end = source[start..]
            .find(
                "
    pub fn refresh_inspector",
            )
            .unwrap()
            + start;
        let body = &source[start..end];
        assert!(
            body.contains("resolved"),
            "the overlay no longer reads the rects the frame resolved"
        );
        let calls = body.matches("geometry(").count();
        assert!(
            calls <= 1,
            "refresh_canvas asks geometry() {calls} times; keep the one fallback"
        );
        assert!(
            !body.contains("element_ids()"),
            "refresh_canvas iterates ids again; that is the per-element geometry loop"
        );
    }

    /// The overlay, the Inspector and a click share one rect: a complete zone
    /// wins, then explicit coordinates, then the renderer's resolved rect under
    /// the element's own fields. A text element in a zone is drawn and hit at the
    /// zone, not at its glyph box.
    #[test]
    fn the_overlay_rect_follows_the_inspector_precedence() {
        use super::overlay_rect;
        use serde_json::json;

        let zoned =
            json!({"id": "label", "type": "text", "zone": {"x": 8, "y": 2, "w": 36, "h": 12}});
        let explicit = json!({"id": "icon", "x": 10, "y": 4, "w": 6, "h": 8});
        let resolved = json!([
            {"id": "label", "x": 8, "y": 4, "w": 35, "h": 7},
            {"id": "icon", "x": 1, "y": 1, "w": 1, "h": 1},
            {"id": "hidden", "x": null, "y": null, "w": null, "h": null}
        ]);
        let resolved = resolved.as_array().unwrap();
        assert_eq!(overlay_rect(&zoned, resolved, 0), Some((8, 2, 36, 12)));
        assert_eq!(overlay_rect(&explicit, resolved, 1), Some((10, 4, 6, 8)));
        let sized = json!({"id": "digits", "x": 4, "y": 6});
        assert_eq!(overlay_rect(&sized, resolved, 0), Some((4, 6, 35, 7)));
        let unsized_element = json!({"id": "digits"});
        assert_eq!(
            overlay_rect(&unsized_element, resolved, 0),
            Some((8, 4, 35, 7))
        );
        let bare = json!({"id": "hidden", "hidden": true});
        assert_eq!(overlay_rect(&bare, resolved, 2), None);
    }

    fn opened(name: &str) -> (super::App, std::path::PathBuf) {
        let (mut app, root) = crate::guard::tests::app(name);
        app.flush_validation();
        (app, root)
    }

    fn draft_element() -> serde_json::Value {
        serde_json::json!({"id": "draft", "type": "placeholder", "x": 0, "y": 0, "w": 8, "h": 8})
    }

    fn flags_draft(app: &super::App) -> bool {
        app.findings.iter().any(|f| f.code == "DRAFT_PLACEHOLDER")
    }

    fn add_draft(app: &mut super::App) {
        app.session
            .as_mut()
            .unwrap()
            .add_elements(vec![draft_element()], "add")
            .unwrap();
    }

    #[test]
    fn a_scripted_dump_waits_for_the_scheduled_pass() {
        let (mut app, root) = opened("validation-flush");
        assert!(!flags_draft(&app));
        add_draft(&mut app);
        app.schedule_validation();
        assert!(
            app.validation_rx.is_some(),
            "the pass did not go off-thread"
        );
        app.flush_validation();
        assert!(flags_draft(&app), "{:?}", app.findings);
        assert!(app.validation_rx.is_none());
        std::fs::remove_dir_all(&root).unwrap();
    }

    #[test]
    fn an_edit_during_a_pass_is_validated_after_it_lands() {
        let (mut app, root) = opened("validation-dirty");
        app.schedule_validation();
        add_draft(&mut app);
        app.schedule_validation();
        assert!(app.validation_dirty);
        app.flush_validation();
        assert!(!app.validation_dirty);
        assert!(flags_draft(&app), "{:?}", app.findings);
        std::fs::remove_dir_all(&root).unwrap();
    }

    #[test]
    fn a_result_from_an_older_epoch_is_dropped() {
        let (mut app, root) = opened("validation-epoch");
        let (tx, rx) = std::sync::mpsc::channel();
        let stale = super::Finding {
            severity: "BLOCKER".into(),
            code: "STALE".into(),
            message: "old scene".into(),
            element_id: None,
        };
        tx.send((app.validation_epoch, vec![stale])).unwrap();
        app.validation_rx = Some(rx);
        app.validation_epoch += 1;
        app.poll_validation();
        assert!(!app.findings.iter().any(|f| f.code == "STALE"));
        assert!(app.validation_rx.is_none());
        std::fs::remove_dir_all(&root).unwrap();
    }

    /// The old pass never answers here. Had the switch kept waiting for it, the
    /// new scene's pass would only be marked dirty and could never start.
    #[test]
    fn a_screen_switch_abandons_the_pass_in_flight() {
        let (mut app, root) = opened("validation-switch");
        let (held_open, rx) = std::sync::mpsc::channel();
        app.validation_rx = Some(rx);
        app.switch_screen("123").unwrap();
        assert!(!app.validation_dirty, "the new scene waits on the old pass");
        app.flush_validation();
        let scheduled = app.findings.clone();
        app.refresh_validation();
        assert_eq!(scheduled, app.findings);
        drop(held_open);
        std::fs::remove_dir_all(&root).unwrap();
    }

    #[test]
    fn a_flush_ignores_a_result_from_an_older_epoch() {
        let (mut app, root) = opened("validation-flush-epoch");
        let (tx, rx) = std::sync::mpsc::channel();
        let stale = super::Finding {
            severity: "BLOCKER".into(),
            code: "STALE".into(),
            message: "old scene".into(),
            element_id: None,
        };
        tx.send((app.validation_epoch, vec![stale])).unwrap();
        app.validation_rx = Some(rx);
        app.validation_epoch += 1;
        app.flush_validation();
        assert!(!app.findings.iter().any(|f| f.code == "STALE"));
        std::fs::remove_dir_all(&root).unwrap();
    }

    #[test]
    fn the_topmost_rect_under_the_pointer_wins() {
        use super::topmost_at;
        let rects = [
            Some((0, 0, 16, 16)),
            None,
            Some((8, 8, 16, 16)),
            Some((40, 0, 0, 0)),
        ];
        assert_eq!(topmost_at(&rects, 10, 10), Some(2));
        assert_eq!(topmost_at(&rects, 2, 2), Some(0));
        assert_eq!(topmost_at(&rects, 16, 2), None);
        assert_eq!(topmost_at(&rects, 40, 0), Some(3));
        assert_eq!(topmost_at(&rects, 41, 0), None);
    }

    #[test]
    fn a_lost_worker_does_not_stop_later_validation() {
        let (mut app, root) = opened("validation-lost");
        let (tx, rx) = std::sync::mpsc::channel();
        drop(tx);
        app.validation_rx = Some(rx);
        app.poll_validation();
        assert!(app.validation_rx.is_none(), "the dead receiver was kept");
        add_draft(&mut app);
        app.schedule_validation();
        app.flush_validation();
        assert!(flags_draft(&app), "{:?}", app.findings);
        std::fs::remove_dir_all(&root).unwrap();
    }

    #[test]
    fn every_edit_path_validates_off_the_ui_thread() {
        let (mut app, root) = opened("validation-paths");
        app.selection
            .replace(&["hero_digits".to_string()], Some("hero_digits"));
        app.geometry_edited("x", 7);
        assert!(
            app.validation_rx.is_some(),
            "geometry edit validated in place"
        );
        app.flush_validation();
        app.state_edited("mode", "HIGH");
        assert!(app.validation_rx.is_some(), "state edit validated in place");
        app.flush_validation();
        let rules = app.effective_rules();
        app.apply_rules(&rules).unwrap();
        assert!(app.validation_rx.is_some(), "rule edit validated in place");
        app.flush_validation();
        app.refresh_all();
        assert!(app.validation_rx.is_some(), "refresh validated in place");
        app.flush_validation();
        std::fs::remove_dir_all(&root).unwrap();
    }

    #[test]
    fn dropping_the_session_also_drops_the_pass_in_flight() {
        let (mut app, root) = opened("validation-drop");
        app.schedule_validation();
        let epoch = app.validation_epoch;
        app.drop_session();
        assert!(app.session.is_none());
        assert!(app.validation_epoch > epoch);
        assert!(app.validation_rx.is_none());
        std::fs::remove_dir_all(&root).unwrap();
    }

    /// Every verb the editor and the automation bridge can push onto the undo
    /// stack is either translated or deliberately shown verbatim.
    #[test]
    fn rule_edits_validate_the_way_the_engine_does() {
        use super::{check_rules_draft, edit_rules};
        use serde_json::json;

        let mut rules = json!({"required_elements": [], "zones": {}, "baseline_groups": []});
        assert!(edit_rules(&mut rules, "add-zone", "", "", ""));
        // A whole number written as text is still an integer to `py_int`.
        assert!(edit_rules(&mut rules, "set-zone", "0", "w", "24"));
        assert!(check_rules_draft(&rules).is_ok(), "{rules}");
        assert!(edit_rules(&mut rules, "set-zone", "0", "h", "abc"));
        assert_eq!(
            check_rules_draft(&rules).err(),
            Some("zone_1.h".to_string())
        );

        assert!(edit_rules(&mut rules, "set-zone", "0", "name", "battery"));
        assert_eq!(rules["zones"]["battery"]["w"], json!(24));
        assert!(rules.get("zone_1").is_none(), "the rename left a copy");

        assert!(edit_rules(&mut rules, "add-group", "", "", ""));
        assert!(
            check_rules_draft(&rules).is_err(),
            "an empty group is not a rule"
        );
        assert!(edit_rules(&mut rules, "set-group", "0", "ids", "a, b"));
        assert_eq!(rules["baseline_groups"][0]["ids"], json!(["a", "b"]));
        assert_eq!(
            check_rules_draft(&rules),
            Err("battery.h".to_string()),
            "the earlier bad zone must still be reported under its new name"
        );
        assert!(edit_rules(&mut rules, "set-zone", "0", "h", "8"));
        assert!(check_rules_draft(&rules).is_ok(), "{rules}");
    }

    #[test]
    fn known_undo_tokens_have_copy() {
        for token in [
            "add_placeholder",
            "assign_bitmap",
            "bitmap_text_insert",
            "duplicate",
            "group",
            "hide",
            "lock",
            "move_batch",
            "remove_elements",
            "show",
            "ungroup",
            "unlock",
        ] {
            assert!(has_key(&format!("undo.{token}")), "undo.{token}");
            assert!(
                undo_phrase("zh_CN", token) != token,
                "{token} renders as its machine token"
            );
        }
        for verb in ["geometry", "align_to", "distribute", "snap"] {
            assert!(has_key(&format!("undo.{verb}")), "undo.{verb}");
        }
    }

    #[test]
    fn parameterised_and_unknown_undo_tokens_stay_readable() {
        assert_eq!(undo_phrase("en_US", "geometry:battery"), "geometry battery");
        assert_eq!(
            undo_phrase("en_US", "align_to:canvas:left"),
            "align canvas left"
        );
        assert_eq!(undo_phrase("zh_CN", "geometry:battery"), "调整 battery");
        // No invented translation for tokens we do not know: show what it is.
        assert_eq!(
            undo_phrase("zh_CN", "agent_transaction"),
            "agent_transaction"
        );
    }
}
