//! Application controller: owns the project, the Designer session and the UI
//! sync. Every UI callback goes through `App`; Slint models are rebuilt from
//! the session after each change (the scene JSON stays the single truth).

use std::path::{Path, PathBuf};

use mono_core::CoreError;
use mono_core::pixel::PixelDocument;
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
use mono_project::resources::DiskResources;
use mono_project::scene_io::{SceneDoc, load_project_scene, load_scene};
use serde_json::{Value, json};
use slint::{Global, ModelRc, SharedString, VecModel};

use crate::agent::{Agent, BridgePermission};
use crate::bgjob::{BackgroundJob, Outcome, Poll};
use crate::canvas::image_from_pixels;
use crate::extras::{Picker, Profiler};
use crate::fontlab::FontLab;
use crate::i18n::{tr, trf};
use crate::pixel::{PixelOrigin, PixelStudio};
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
    baseline_size: (usize, usize),
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
    pub font: Option<FontLab>,
    /// Export / handoff / batch validation / thumbnail wall running off the UI thread.
    pub bg_job: Option<BackgroundJob>,
    pub picker: Option<Picker>,
    pub picker_matches: Vec<(String, String, String, String)>,
    pub profiler: Profiler,
    pub last_autosave: std::time::Instant,
    pub agent: Option<Agent>,
    pub pending_permission: BridgePermission,
    /// False for screenshots, benches and tests: never block on a dialog.
    pub interactive: bool,
    /// Answer used for unsaved-changes questions when not interactive.
    pub scripted_choice: Option<crate::guard::Unsaved>,
    /// Display colour editor texts (saved only when all four are valid).
    pub display_draft: [String; 4],
    /// Visible cells of the Pixel canvas and the outline runs shown for them.
    pub cell_window: crate::canvas::CellWindow,
    pub border_lines: std::rc::Rc<slint::VecModel<crate::BorderLine>>,
}

pub(crate) fn model<T: Clone + 'static>(items: Vec<T>) -> ModelRc<T> {
    ModelRc::new(VecModel::from(items))
}

pub(crate) fn ss(text: impl AsRef<str>) -> SharedString {
    SharedString::from(text.as_ref())
}

/// Rendered pixels, their size, and the scene elements at this instant.
fn scene_snapshot(session: &mut EditorSession) -> (Vec<u8>, (usize, usize), Vec<Value>) {
    let elements = session
        .scene()
        .get("elements")
        .and_then(Value::as_array)
        .cloned()
        .unwrap_or_default();
    match session.render() {
        Ok(result) => {
            let fb = result.framebuffer;
            (fb.pixels().to_vec(), (fb.width(), fb.height()), elements)
        }
        Err(_) => (Vec::new(), (0, 0), elements),
    }
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
            baseline_size: (0, 0),
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
            font: None,
            bg_job: None,
            picker: None,
            picker_matches: Vec::new(),
            profiler: Profiler::default(),
            last_autosave: std::time::Instant::now(),
            agent: None,
            pending_permission: BridgePermission::default(),
            interactive: false,
            scripted_choice: None,
            display_draft: Default::default(),
            cell_window: crate::canvas::CellWindow::default(),
            border_lines: std::rc::Rc::new(slint::VecModel::default()),
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
        self.remember_project(&project.path);
        let _ = self.prefs.save();
        self.log_event(format!("OPEN_PROJECT {}", posix(&project.path)));
        // Font packs belong to a project; never carry one into another.
        self.font = None;
        self.project = Some(project);
        self.bind_scene(scene)?;
        self.scan_project_files();
        self.bench_load_active();
        let blockers = self.findings.iter().filter(|f| f.is_blocking()).count();
        let multi_screen = self.project.as_ref().is_some_and(|p| p.screens().len() > 1);
        if blockers > 0 && multi_screen {
            let message = trf(
                &self.lang,
                "status.scene_blockers",
                &[("count", blockers.to_string())],
            );
            self.set_status(message);
        }
        Ok(())
    }

    pub fn open_scene_file(&mut self, path: &Path) -> Result<(), CoreError> {
        let scene = load_scene(path, None)?;
        self.font = None;
        self.project = None;
        self.bind_scene(scene)?;
        self.scan_project_files();
        self.bench_load_active();
        Ok(())
    }

    pub fn new_project(
        &mut self,
        root: &Path,
        name: &str,
        canvas: (i64, i64),
    ) -> Result<(), CoreError> {
        if canvas.0 <= 0 || canvas.1 <= 0 || canvas.1 % 8 != 0 {
            return Err(CoreError::invalid(self.t("new_project.invalid_size")));
        }
        let fallback = root
            .file_name()
            .map(|name| name.to_string_lossy().into_owned())
            .unwrap_or_else(|| "MonoOLED Project".into());
        let name = match name.trim() {
            "" => fallback,
            trimmed => trimmed.to_string(),
        };
        let project = create_project(root, &name, canvas)?;
        let path = project.path.clone();
        self.open_project(&path)
    }

    /// Resolve an element's static PNG asset to (relative path, absolute path).
    fn asset_member(&self, element_id: &str) -> Result<(String, PathBuf), CoreError> {
        let Some(project) = self.project.as_ref() else {
            return Err(CoreError::invalid(self.t("asset.no_project")));
        };
        let Some(session) = self.session.as_ref() else {
            return Err(CoreError::invalid(self.t("asset.no_selection")));
        };
        let element = session.element(element_id)?;
        if element.get("type").map(py_str).as_deref() != Some("image") {
            return Err(CoreError::invalid(self.t("asset.not_static_image")));
        }
        let rel = element
            .get("asset")
            .map(py_str)
            .unwrap_or_default()
            .trim()
            .to_string();
        if rel.is_empty() {
            return Err(CoreError::invalid(self.t("asset.not_static_image")));
        }
        if rel.contains('{') || rel.contains('}') {
            return Err(CoreError::invalid(self.t("asset.template")));
        }
        let is_png = Path::new(&rel)
            .extension()
            .is_some_and(|ext| ext.eq_ignore_ascii_case("png"));
        if !is_png {
            return Err(CoreError::invalid(self.t("asset.not_png")));
        }
        let path = project.resolve_member(&rel, "asset")?;
        Ok((rel, path))
    }

    /// Whether the primary selection is a static PNG image inside the project.
    pub fn can_edit_asset(&self) -> bool {
        self.selection
            .primary()
            .is_some_and(|id| self.asset_member(id).is_ok())
    }

    /// Open an image element's PNG in Pixel Studio as an asset-origin document.
    pub fn open_element_asset(&mut self, element_id: &str) -> Result<(), CoreError> {
        let (rel, path) = self.asset_member(element_id)?;
        let raw = std::fs::read(&path)
            .map_err(|e| CoreError::invalid(format!("{}: {e}", posix(&path))))?;
        let asset = DiskResources::decode_bitmap(&path, &raw)?;
        let doc = PixelDocument::from_rows(&asset.rows)?;
        // Ask before discarding edits, but only after the asset is known good.
        let Some(save_first) = self.confirm_unsaved_pixel() else {
            return Ok(());
        };
        if save_first && !self.pixel_save()? {
            return Ok(());
        }
        let root = self
            .project
            .as_ref()
            .map(|p| p.root.clone())
            .unwrap_or_default();
        let origin = PixelOrigin::Asset {
            root,
            rel: rel.clone(),
            element_id: element_id.to_string(),
            sha256: asset.sha256,
            inverted: asset.inverted,
        };
        let limit = self.undo_limit();
        self.pixel.open_asset(doc, origin, limit);
        self.workspace = 1;
        if let Some(ui) = self.ui.upgrade() {
            AppModel::get(&ui).set_workspace(1);
        }
        self.refresh_pixel();
        self.refresh_app();
        self.set_status(trf(&self.lang, "status.asset_opened", &[("path", rel)]));
        Ok(())
    }

    /// Recent project files that still exist, newest first.
    pub fn recent_projects(&self) -> Vec<PathBuf> {
        self.prefs
            .get("startup.recent_projects")
            .as_array()
            .map(|values| {
                values
                    .iter()
                    .filter_map(Value::as_str)
                    .map(PathBuf::from)
                    .filter(|path| path.is_file())
                    .collect()
            })
            .unwrap_or_default()
    }

    /// Labels for the welcome page: the project folder name when there is one.
    fn recent_labels(&self) -> Vec<String> {
        self.recent_projects()
            .iter()
            .map(|path| {
                path.parent()
                    .and_then(Path::file_name)
                    .map(|name| name.to_string_lossy().into_owned())
                    .filter(|name| !name.is_empty())
                    .unwrap_or_else(|| path.display().to_string())
            })
            .collect()
    }

    /// Newest entry first, no duplicates, limited to eight. Saves with the caller.
    fn remember_project(&mut self, path: &Path) {
        const CAP: usize = 8;
        let entry = posix(path);
        let mut list: Vec<String> = self
            .prefs
            .get("startup.recent_projects")
            .as_array()
            .map(|values| {
                values
                    .iter()
                    .filter_map(Value::as_str)
                    .map(str::to_string)
                    .collect()
            })
            .unwrap_or_default();
        list.retain(|item| item != &entry);
        list.insert(0, entry);
        list.truncate(CAP);
        self.prefs.set("startup.recent_projects", json!(list));
    }

    pub(crate) fn bind_scene(&mut self, scene: SceneDoc) -> Result<(), CoreError> {
        let mut session = EditorSession::new(scene)?;
        (
            self.baseline_pixels,
            self.baseline_size,
            self.baseline_elements,
        ) = scene_snapshot(&mut session);
        self.session = Some(session);
        self.selection.clear();
        self.drag = None;
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
            (
                self.baseline_pixels,
                self.baseline_size,
                self.baseline_elements,
            ) = scene_snapshot(session);
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
                if let Some(rel) = element.get("font_pack").and_then(Value::as_str) {
                    let path = root.join(rel);
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
        self.refresh_review();
        self.refresh_inspector();
        self.refresh_validation();
        self.refresh_app();
    }

    /// The save button acts on the current workspace's document.
    pub fn can_save(&self) -> bool {
        match self.workspace {
            1 => self.pixel.path.is_some() || self.pixel.doc.dirty,
            2 => self.font.is_some(),
            _ => self.session.is_some(),
        }
    }

    pub fn can_export(&self) -> bool {
        self.session.is_some()
    }

    pub fn can_handoff(&self) -> bool {
        self.session.is_some()
    }

    pub fn can_agent(&self) -> bool {
        self.agent.is_some() || self.session.is_some()
    }

    /// Context used to filter palette commands.
    pub fn command_context(&self) -> crate::commands::Requirement {
        use crate::commands::Requirement;
        if self.workspace == 1 || self.workspace == 2 {
            Requirement::PixelOrFont
        } else if self.session.is_some() {
            Requirement::Scene
        } else if self.project.is_some() {
            Requirement::Project
        } else {
            Requirement::None
        }
    }

    pub fn save_label(&self) -> String {
        let key = if self.workspace == 1 && self.pixel.is_asset() {
            "action.save_asset"
        } else {
            match self.workspace {
                1 => "action.save_pixel",
                2 => "action.save_font",
                _ => "action.save_scene",
            }
        };
        self.t(key)
    }

    /// Whether `action` has the document/project it needs to do real work.
    pub fn feature_available(&self, action: &str) -> bool {
        match action {
            "save" => self.can_save(),
            "export-current" | "export-all" | "export-c-header" | "batch-validate" => {
                self.can_export()
            }
            "handoff" => self.can_handoff(),
            "agent-bridge" => self.can_agent(),
            "assign-bitmap" | "add-placeholder" | "duplicate" | "delete" => self.session.is_some(),
            _ => true,
        }
    }

    /// Explain a no-op instead of silently doing nothing; true when allowed.
    pub fn require_document(&mut self, action: &str) -> bool {
        if self.feature_available(action) {
            return true;
        }
        let key = if action == "save" {
            "status.nothing_to_save"
        } else {
            "status.need_document"
        };
        let message = self.t(key);
        self.set_status(message);
        false
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
        app.set_has_project(self.project.is_some() || self.session.is_some());
        app.set_recent_projects(model(self.recent_labels().into_iter().map(ss).collect()));
        app.set_can_save(self.can_save());
        app.set_can_export(self.can_export());
        app.set_can_handoff(self.can_handoff());
        app.set_can_agent(self.can_agent());
        app.set_save_label(ss(self.save_label()));
        if self.workspace == 1 || self.workspace == 2 {
            let studio = self.studio();
            app.set_dirty(studio.doc.dirty);
            app.set_can_undo(studio.doc.can_undo());
            app.set_can_redo(studio.doc.can_redo());
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
        self.refresh_agent_panel();
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
                let changed = mono_core::diff::changed_count(fb.pixels(), &self.baseline_pixels);
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

    /// Side-by-side baseline/current view for the Review workspace.
    pub fn refresh_review(&mut self) {
        let lang = self.lang.clone();
        let Some(ui) = self.ui.upgrade() else { return };
        let rm = crate::ReviewModel::get(&ui);
        let blank = image_from_pixels(1, 1, &[0]);
        let rendered = self.session.as_mut().map(|session| match session.render() {
            Ok(result) => {
                let fb = result.framebuffer;
                Ok((
                    fb.pixels().to_vec(),
                    fb.width().max(1),
                    fb.height().max(1),
                    session
                        .scene()
                        .get("elements")
                        .and_then(Value::as_array)
                        .cloned()
                        .unwrap_or_default(),
                ))
            }
            Err(error) => Err(error.message),
        });
        let Some(rendered) = rendered else {
            rm.set_baseline(blank.clone());
            rm.set_current(blank);
            rm.set_baseline_w(0);
            rm.set_baseline_h(0);
            rm.set_current_w(0);
            rm.set_current_h(0);
            rm.set_changed(0);
            rm.set_percent(0.0);
            rm.set_bbox_x(0);
            rm.set_bbox_y(0);
            rm.set_bbox_w(0);
            rm.set_bbox_h(0);
            rm.set_has_baseline(false);
            rm.set_summary(ss(tr(&lang, "review.empty")));
            rm.set_detail(ss(""));
            rm.set_added(model(Vec::new()));
            rm.set_removed(model(Vec::new()));
            rm.set_modified(model(Vec::new()));
            return;
        };
        let (pixels, width, height, current_elements) = match rendered {
            Ok(data) => data,
            Err(message) => {
                rm.set_has_baseline(false);
                rm.set_summary(ss(format!(
                    "{}: {}",
                    tr(&lang, "status.render_failed"),
                    message
                )));
                return;
            }
        };
        let (bw, bh) = self.baseline_size;
        let has_baseline = !self.baseline_pixels.is_empty();
        rm.set_baseline(if has_baseline {
            image_from_pixels(bw.max(1), bh.max(1), &self.baseline_pixels)
        } else {
            blank.clone()
        });
        rm.set_current(image_from_pixels(width, height, &pixels));
        rm.set_baseline_w(bw as i32);
        rm.set_baseline_h(bh as i32);
        rm.set_current_w(width as i32);
        rm.set_current_h(height as i32);
        rm.set_has_baseline(has_baseline);
        let changed = mono_core::diff::changed_count(&pixels, &self.baseline_pixels);
        let bbox = mono_core::diff::changed_bbox(&pixels, &self.baseline_pixels, width, height);
        let total = pixels.len().max(1);
        let percent = changed as f64 * 100.0 / total as f64;
        rm.set_changed(changed as i32);
        rm.set_percent(percent as f32);
        match bbox {
            Some(b) => {
                rm.set_bbox_x(b.x as i32);
                rm.set_bbox_y(b.y as i32);
                rm.set_bbox_w(b.w as i32);
                rm.set_bbox_h(b.h as i32);
            }
            None => {
                rm.set_bbox_x(0);
                rm.set_bbox_y(0);
                rm.set_bbox_w(0);
                rm.set_bbox_h(0);
            }
        }
        rm.set_summary(ss(trf(
            &lang,
            "review.summary",
            &[
                ("pixels", changed.to_string()),
                ("percent", format!("{:.2}", percent)),
            ],
        )));
        let detail = if !has_baseline {
            self.t("review.empty")
        } else if (bw, bh) != (width, height) {
            self.t("review.size_mismatch")
        } else if let Some(b) = bbox {
            trf(
                &lang,
                "review.bbox",
                &[
                    ("x", b.x.to_string()),
                    ("y", b.y.to_string()),
                    ("w", b.w.to_string()),
                    ("h", b.h.to_string()),
                ],
            )
        } else {
            self.t("review.no_changes")
        };
        rm.set_detail(ss(detail));
        let id_of = |e: &Value| e.get("id").map(py_str).unwrap_or_default();
        let label = |e: &Value| {
            let id = id_of(e);
            let kind = e.get("type").map(py_str).unwrap_or_default();
            if kind.is_empty() {
                id
            } else {
                format!("{id} · {kind}")
            }
        };
        let before_ids: Vec<String> = self.baseline_elements.iter().map(id_of).collect();
        let after_ids: Vec<String> = current_elements.iter().map(id_of).collect();
        let added: Vec<String> = current_elements
            .iter()
            .filter(|e| !before_ids.contains(&id_of(e)))
            .map(label)
            .collect();
        let removed: Vec<String> = self
            .baseline_elements
            .iter()
            .filter(|e| !after_ids.contains(&id_of(e)))
            .map(label)
            .collect();
        let modified: Vec<String> = current_elements
            .iter()
            .filter(|e| {
                self.baseline_elements
                    .iter()
                    .any(|b| id_of(b) == id_of(e) && b != *e)
            })
            .map(label)
            .collect();
        rm.set_added(model(added.into_iter().map(ss).collect()));
        rm.set_removed(model(removed.into_iter().map(ss).collect()));
        rm.set_modified(model(modified.into_iter().map(ss).collect()));
    }

    pub fn refresh_inspector(&mut self) {
        let Some(ui) = self.ui.upgrade() else { return };
        let dm = DesignerModel::get(&ui);
        let can_edit_asset = self.can_edit_asset();
        dm.set_can_edit_asset(can_edit_asset);
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
        let Some(session) = self.session.as_mut() else {
            self.findings.clear();
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
        self.findings = findings;
        let Some(ui) = self.ui.upgrade() else { return };
        let dm = DesignerModel::get(&ui);
        let summary = trf(
            &self.lang,
            "validation.summary",
            &[
                ("count", self.findings.len().to_string()),
                ("blockers", blockers.to_string()),
            ],
        );
        dm.set_findings_summary(ss(&summary));
        dm.set_findings_tone(if blockers > 0 {
            PillTone::Error
        } else if self.findings.is_empty() {
            PillTone::Success
        } else {
            PillTone::Warning
        });
        dm.set_findings(model(
            self.findings
                .iter()
                .map(|f| FindingItem {
                    severity: ss(&f.severity),
                    code: ss(&f.code),
                    label: ss(crate::i18n::finding_label(&self.lang, &f.code)),
                    message: ss(&f.message),
                })
                .collect(),
        ));
        let app = AppModel::get(&ui);
        app.set_health_text(ss(if blockers > 0 {
            format!("{} {blockers}", self.t("health.blocked"))
        } else if self.findings.is_empty() {
            self.t("health.ok")
        } else {
            format!("{} {}", self.t("health.warnings"), self.findings.len())
        }));
        app.set_health_tone(if blockers > 0 {
            PillTone::Error
        } else if self.findings.is_empty() {
            PillTone::Success
        } else {
            PillTone::Warning
        });
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
        if !crate::commands::is_known(action) {
            self.log_event(format!("UNKNOWN ACTION {action}"));
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
            (
                self.baseline_pixels,
                self.baseline_size,
                self.baseline_elements,
            ) = scene_snapshot(session);
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
            return Ok(());
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
        self.start_background("action.export_all", move |progress| {
            let summary = export_scene(&scene, &root, &output, &states, progress)?;
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
            return Ok(());
        };
        let states = build_export_states(&scene, IntegerPolicy::Representative, 5000, false)?;
        let lang = self.lang.clone();
        self.start_background("action.handoff", move |progress| {
            let summary = build_handoff_package(
                &scene,
                &root,
                &output,
                &states,
                IntegerPolicy::Representative,
                progress,
            )?;
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

    /// Validate the boundary state matrix in the background.
    pub fn start_batch_validate(&mut self) -> Result<(), CoreError> {
        let Some((scene, root)) = self.scene_parts() else {
            return Ok(());
        };
        let states = build_export_states(&scene, IntegerPolicy::Boundaries, 5000, false)?;
        let lang = self.lang.clone();
        self.start_background("action.batch_validate", move |progress| {
            let matrix: Vec<_> = states.into_iter().map(|(_, s)| s).collect();
            let summary = validate_matrix(&scene, &root, &matrix, progress)?;
            let report = matrix_report(&summary);
            Ok(Outcome {
                status: trf(
                    &lang,
                    "status.batch_done",
                    &[
                        ("cases", summary.cases.to_string()),
                        ("findings", summary.findings.to_string()),
                        ("blockers", summary.blockers.to_string()),
                    ],
                ),
                log: report
                    .lines()
                    .filter(|l| l.starts_with("- **"))
                    .map(str::to_string)
                    .collect(),
                refresh: true,
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
        self.set_status(trf(&self.lang, "job.started", &[("label", label.clone())]));
        self.log_event(format!("JOB_START {label_key}"));
        self.bg_job = Some(BackgroundJob::spawn(label, work));
        Ok(())
    }

    /// Job timer: progress in the status bar, then the result.
    pub fn poll_background(&mut self) {
        let Some(job) = &self.bg_job else { return };
        match job.poll() {
            Poll::Running(p) => {
                let text = if p.total > 0 {
                    trf(
                        &self.lang,
                        "job.progress",
                        &[
                            ("label", job.label.clone()),
                            ("done", p.done.to_string()),
                            ("total", p.total.to_string()),
                        ],
                    )
                } else {
                    trf(&self.lang, "job.started", &[("label", job.label.clone())])
                };
                if text != self.status {
                    self.set_status(text);
                }
            }
            Poll::Finished(result) => {
                let label = job.label.clone();
                self.bg_job = None;
                match result {
                    Ok(outcome) => {
                        for line in outcome.log {
                            self.log_event(line);
                        }
                        self.log_event(format!("JOB_DONE {label}"));
                        self.set_status(outcome.status);
                        if outcome.refresh {
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

#[cfg(test)]
mod tests {
    #![allow(clippy::unwrap_used)]
    #![allow(clippy::panic)]
    use super::*;
    use crate::i18n::{tr, trf};
    use crate::prefs::Preferences;

    fn copy_dir(from: &Path, to: &Path) {
        std::fs::create_dir_all(to).unwrap();
        for entry in std::fs::read_dir(from).unwrap() {
            let entry = entry.unwrap();
            let target = to.join(entry.file_name());
            if entry.file_type().unwrap().is_dir() {
                copy_dir(&entry.path(), &target);
            } else {
                std::fs::copy(entry.path(), target).unwrap();
            }
        }
    }

    fn blank_app(name: &str) -> App {
        let root = std::env::temp_dir().join(format!("mono-app-{name}-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&root);
        let prefs = Preferences::load_from(root.join("prefs.json"));
        App::new(slint::Weak::default(), prefs)
    }

    fn project_app(name: &str) -> (App, PathBuf) {
        let root = std::env::temp_dir().join(format!("mono-asset-{name}-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&root);
        let repo = Path::new(env!("CARGO_MANIFEST_DIR")).join("../..");
        copy_dir(&repo.join("test_assets/projects/curing_lite"), &root);
        let prefs = Preferences::load_from(root.join("prefs.json"));
        let mut app = App::new(slint::Weak::default(), prefs);
        app.open_project(&root.join("project.oled.json")).unwrap();
        app.open_screen("main").unwrap();
        (app, root)
    }

    fn select(app: &mut App, id: &str) {
        let id = id.to_string();
        app.selection.replace(std::slice::from_ref(&id), Some(&id));
    }

    #[test]
    fn new_project_uses_requested_size() {
        let mut app = blank_app("new-size");
        let dir = std::env::temp_dir().join(format!("mono-new-size-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&dir);
        app.new_project(&dir, "Wide", (64, 16)).unwrap();
        let fb = app.session.as_mut().unwrap().render().unwrap().framebuffer;
        assert_eq!((fb.width(), fb.height()), (64, 16));
        assert_eq!(app.project.as_ref().unwrap().name(), "Wide");
        let _ = std::fs::remove_dir_all(&dir);
    }

    #[test]
    fn new_project_rejects_invalid_size() {
        let mut app = blank_app("new-invalid");
        let dir = std::env::temp_dir().join(format!("mono-new-invalid-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&dir);
        let error = app.new_project(&dir, "Bad", (64, 10)).unwrap_err();
        assert_eq!(error.message, tr("zh_CN", "new_project.invalid_size"));
        assert!(!dir.join("project.oled.json").exists());
        let _ = std::fs::remove_dir_all(&dir);
    }

    #[test]
    fn new_project_derives_name_from_folder_when_empty() {
        let mut app = blank_app("new-name");
        let dir = std::env::temp_dir().join(format!("Wizard-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&dir);
        app.new_project(&dir, "  ", (32, 8)).unwrap();
        let name = dir.file_name().unwrap().to_string_lossy().into_owned();
        assert_eq!(app.project.as_ref().unwrap().name(), name);
        let _ = std::fs::remove_dir_all(&dir);
    }

    #[test]
    fn save_label_matches_workspace() {
        let mut app = blank_app("labels");
        app.workspace = 0;
        assert_eq!(app.save_label(), tr("zh_CN", "action.save_scene"));
        app.workspace = 1;
        assert_eq!(app.save_label(), tr("zh_CN", "action.save_pixel"));
        app.workspace = 2;
        assert_eq!(app.save_label(), tr("zh_CN", "action.save_font"));
    }

    #[test]
    fn save_without_document_reports_status() {
        let mut app = blank_app("save");
        app.workspace = 0;
        assert!(!app.can_save());
        assert!(!app.require_document("save"));
        assert_eq!(app.status, tr("zh_CN", "status.nothing_to_save"));
    }

    #[test]
    fn export_without_project_errors() {
        let mut app = blank_app("export");
        assert!(!app.feature_available("export-current"));
        assert!(!app.require_document("export-current"));
        assert_eq!(app.status, tr("zh_CN", "status.need_document"));
        assert!(!app.can_export());
        assert!(!app.can_handoff());
    }

    #[test]
    fn agent_start_without_project_errors() {
        let mut app = blank_app("agent");
        assert!(!app.can_agent());
        let error = app.start_agent().unwrap_err();
        assert_eq!(error.message, tr("zh_CN", "bench.no_project"));
    }

    #[test]
    fn open_project_with_blockers_hints_at_scene_list() {
        let root = std::env::temp_dir().join(format!("mono-app-blockers-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&root);
        let repo = Path::new(env!("CARGO_MANIFEST_DIR")).join("../..");
        copy_dir(&repo.join("test_assets/projects/curing_lite"), &root);
        // The project opens its active screen (`123`); give it a deterministic BLOCKER.
        let scene_path = root.join("scenes/123.json");
        let mut scene: Value =
            serde_json::from_slice(&std::fs::read(&scene_path).unwrap()).unwrap();
        scene["canvas"]["h"] = serde_json::json!(30);
        std::fs::write(&scene_path, serde_json::to_vec_pretty(&scene).unwrap()).unwrap();
        let prefs = Preferences::load_from(root.join("prefs.json"));
        let mut app = App::new(slint::Weak::default(), prefs);
        app.open_project(&root.join("project.oled.json")).unwrap();
        let blockers = app.findings.iter().filter(|f| f.is_blocking()).count();
        assert!(
            blockers > 0,
            "expected blockers; scene={:?} findings={:?}",
            app.session.as_ref().map(|s| s.doc.path.clone()),
            app.findings
                .iter()
                .map(|f| (f.severity.clone(), f.code.clone()))
                .collect::<Vec<_>>()
        );
        let expected = trf(
            "zh_CN",
            "status.scene_blockers",
            &[("count", blockers.to_string())],
        );
        assert_eq!(app.status, expected);
        let _ = std::fs::remove_dir_all(&root);
    }

    #[test]
    fn recent_projects_dedupe_and_cap() {
        let mut app = blank_app("recent-cap");
        let root = std::env::temp_dir().join(format!("mono-recent-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&root);
        std::fs::create_dir_all(&root).unwrap();
        for index in 0..10 {
            std::fs::write(root.join(format!("p{index}.oled.json")), b"{}").unwrap();
        }
        for index in 0..10 {
            app.remember_project(&root.join(format!("p{index}.oled.json")));
        }
        let list = app.recent_projects();
        assert_eq!(list.len(), 8);
        assert_eq!(list[0], root.join("p9.oled.json"));
        assert_eq!(list[7], root.join("p2.oled.json"));
        app.remember_project(&root.join("p9.oled.json"));
        let list = app.recent_projects();
        assert_eq!(list.len(), 8);
        assert_eq!(list[0], root.join("p9.oled.json"));
        assert_eq!(list[7], root.join("p2.oled.json"));
        let _ = std::fs::remove_dir_all(&root);
    }

    #[test]
    fn missing_recent_entries_are_filtered() {
        let mut app = blank_app("recent-missing");
        let root = std::env::temp_dir().join(format!("mono-recent-gone-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&root);
        std::fs::create_dir_all(&root).unwrap();
        let existing = root.join("kept.oled.json");
        std::fs::write(&existing, b"{}").unwrap();
        let missing = root.join("gone.oled.json");
        app.prefs.set(
            "startup.recent_projects",
            json!([posix(&existing), posix(&missing)]),
        );
        assert_eq!(app.recent_projects(), vec![existing]);
        let _ = std::fs::remove_dir_all(&root);
    }

    #[test]
    fn opening_a_project_remembers_it_once() {
        let root = std::env::temp_dir().join(format!("mono-recent-open-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&root);
        let repo = Path::new(env!("CARGO_MANIFEST_DIR")).join("../..");
        copy_dir(&repo.join("test_assets/projects/curing_lite"), &root);
        let path = root.join("project.oled.json");
        let prefs = Preferences::load_from(root.join("prefs.json"));
        let mut app = App::new(slint::Weak::default(), prefs);
        app.open_project(&path).unwrap();
        app.open_project(&path).unwrap();
        assert_eq!(app.recent_projects(), vec![path.clone()]);
        assert_eq!(app.prefs.str("startup.last_project"), posix(&path));
        let _ = std::fs::remove_dir_all(&root);
    }

    #[test]
    fn image_element_asset_opens_canonical_rows() {
        let (mut app, root) = project_app("open");
        select(&mut app, "running_icon");
        assert!(app.can_edit_asset());
        app.open_element_asset("running_icon").unwrap();
        assert_eq!(app.workspace, 1);
        let path = root.join("assets/clinical_ui/running.png");
        let asset = DiskResources::decode_bitmap(&path, &std::fs::read(&path).unwrap()).unwrap();
        assert_eq!(app.pixel.doc.rows(), asset.rows);
        assert!(app.pixel.is_asset());
        assert_eq!(app.pixel.title(), "asset: assets/clinical_ui/running.png");
        match &app.pixel.origin {
            PixelOrigin::Asset {
                root: asset_root,
                rel,
                element_id,
                sha256,
                inverted,
            } => {
                assert_eq!(asset_root, &root);
                assert_eq!(rel, "assets/clinical_ui/running.png");
                assert_eq!(element_id, "running_icon");
                assert_eq!(sha256, &asset.sha256);
                assert_eq!(*inverted, asset.inverted);
            }
            other => panic!("unexpected origin: {other:?}"),
        }
        assert_eq!(
            app.status,
            trf(
                "zh_CN",
                "status.asset_opened",
                &[("path", "assets/clinical_ui/running.png".to_string())]
            )
        );
        let _ = std::fs::remove_dir_all(&root);
    }

    #[test]
    fn template_asset_is_refused() {
        let (mut app, root) = project_app("template");
        select(&mut app, "mode_icon");
        assert!(!app.can_edit_asset());
        let error = app.open_element_asset("mode_icon").unwrap_err();
        assert_eq!(error.message, tr("zh_CN", "asset.template"));
        let _ = std::fs::remove_dir_all(&root);
    }

    #[test]
    fn bmp_asset_is_refused() {
        let (mut app, root) = project_app("bmp");
        let element = json!({
            "id": "bmp_icon",
            "type": "image",
            "asset": "assets/clinical_ui/check.bmp",
            "x": 0,
            "y": 0
        });
        app.session
            .as_mut()
            .unwrap()
            .add_elements(vec![element], "test")
            .unwrap();
        let error = app.open_element_asset("bmp_icon").unwrap_err();
        assert_eq!(error.message, tr("zh_CN", "asset.not_png"));
        let _ = std::fs::remove_dir_all(&root);
    }

    #[test]
    fn image_seq_has_no_asset_target() {
        let (mut app, root) = project_app("seq");
        select(&mut app, "battery");
        assert!(!app.can_edit_asset());
        let error = app.open_element_asset("battery").unwrap_err();
        assert_eq!(error.message, tr("zh_CN", "asset.not_static_image"));
        let _ = std::fs::remove_dir_all(&root);
    }

    #[test]
    fn asset_outside_root_is_refused() {
        let (mut app, root) = project_app("outside");
        let element = json!({
            "id": "outside_icon",
            "type": "image",
            "asset": "../outside.png",
            "x": 0,
            "y": 0
        });
        app.session
            .as_mut()
            .unwrap()
            .add_elements(vec![element], "test")
            .unwrap();
        let error = app.open_element_asset("outside_icon").unwrap_err();
        assert!(
            error.message.contains("escapes project root"),
            "unexpected error: {}",
            error.message
        );
        let _ = std::fs::remove_dir_all(&root);
    }

    #[test]
    fn saving_an_asset_writes_the_project_file() {
        let (mut app, root) = project_app("save");
        select(&mut app, "running_icon");
        app.open_element_asset("running_icon").unwrap();
        let path = root.join("assets/clinical_ui/running.png");
        app.pixel.doc.pencil(0, 0, true);
        assert!(app.pixel.doc.dirty);
        assert!(app.pixel_save().unwrap());
        assert!(!app.pixel.doc.dirty);
        assert_eq!(
            app.status,
            trf(
                "zh_CN",
                "asset.saved",
                &[("path", "assets/clinical_ui/running.png".to_string())]
            )
        );
        let asset = DiskResources::decode_bitmap(&path, &std::fs::read(&path).unwrap()).unwrap();
        assert_eq!(asset.rows, app.pixel.doc.rows());
        let _ = std::fs::remove_dir_all(&root);
    }

    #[test]
    fn saving_an_externally_changed_asset_is_refused() {
        let (mut app, root) = project_app("external");
        select(&mut app, "running_icon");
        app.open_element_asset("running_icon").unwrap();
        let path = root.join("assets/clinical_ui/running.png");
        app.pixel.doc.pencil(0, 0, true);
        std::fs::write(&path, b"changed outside the editor").unwrap();
        let error = app.pixel_save().unwrap_err();
        assert_eq!(error.code, "E-ASSET-EXTERNAL-MODIFICATION");
        assert_eq!(std::fs::read(&path).unwrap(), b"changed outside the editor");
        assert!(app.pixel.doc.dirty);
        let _ = std::fs::remove_dir_all(&root);
    }
}
