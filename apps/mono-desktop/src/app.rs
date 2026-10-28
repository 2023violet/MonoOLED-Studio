//! Application controller: owns the project, the Designer session and the UI
//! sync. Every UI callback goes through `App`; Slint models are rebuilt from
//! the session after each change (the scene JSON stays the single truth).

use std::collections::BTreeMap;
use std::path::{Path, PathBuf};

use mono_core::CoreError;
use mono_core::c_header::framebuffer_to_c_header;
use mono_core::pixel::PixelDocument;
use mono_core::pyvalue::{py_int, py_str};
use mono_core::render::posix;
use mono_core::runtime::VecRuntimeLog;
use mono_core::state::{IntegerPolicy, build_export_states};
use mono_project::editor::{
    EditorSession, Selection, align_to, distribute, selection_metrics, smart_guides, snap_positions,
};
use mono_project::export::{
    Finding, build_handoff_package, check_design_rules, export_scene, frame_for_state,
    matrix_report, validate_matrix,
};
use mono_project::project::{ProjectWorkspace, create_project};
use mono_project::resources::{DiskResources, hex_digest};
use mono_project::review::{Annotation, AnnotationKind, Evidence, ReviewStore, Scenario};
use mono_project::review_pack::build_review_pack;
use mono_project::scene_io::{SceneDoc, load_project_scene, load_scene};
use serde_json::{Map, Value, json};
use slint::{Global, ModelRc, SharedString, VecModel};

use crate::agent::{Agent, BridgePermission};
use crate::bgjob::{BackgroundJob, Outcome, Poll};
use crate::canvas::image_from_pixels;
use crate::extras::{Picker, Profiler};
use crate::fontlab::FontLab;
use crate::gallery::{GalleryCard, GalleryJob};
use crate::i18n::{tr, trf};
use crate::pixel::{PixelOrigin, PixelStudio};
use crate::pixel_ui::ImportState;
use crate::prefs::Preferences;
use crate::preview::{Preview, timeline_continues};
use crate::workbench::Workbench;
use crate::{
    AppModel, AssetItem, DesignerModel, DocTab, ElementItem, EventItem, FindingItem, GalleryItem,
    GalleryModel, MainWindow, NoteItem, NoteModel, OverlayBox, PillTone, PresetItem, ReviewElement,
    ReviewModel, ScreenItem, StateVar,
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
    ScenarioName,
}

struct Drag {
    start: (i64, i64),
    applied: (i64, i64),
    ids: Vec<String>,
    moved: bool,
}

/// A one-click jump in the State tab: reset, then apply `set`.
#[derive(Debug, Clone)]
pub struct Preset {
    pub label: String,
    pub set: Map<String, Value>,
    pub reset_first: bool,
}

/// The annotation being written; the anchor and evidence are fixed when the
/// dialog opens so editing the canvas later cannot silently re-point it.
#[derive(Debug, Clone)]
pub struct NoteDraft {
    pub id: Option<String>,
    pub screen: String,
    pub state: Map<String, Value>,
    pub element: Option<String>,
    pub evidence: Evidence,
}

/// One render used by both the pixel diff and the code/evidence panel.
struct ReviewRender {
    pixels: Vec<u8>,
    width: usize,
    height: usize,
    elements: Vec<Value>,
    vlsb: Option<Vec<u8>>,
    c_header: Option<String>,
}

/// Evidence for the Review panel; pure so it can be asserted without a UI.
#[derive(Debug, Clone)]
struct EvidenceView {
    state_label: String,
    status: &'static str,
    frame_sha: String,
    golden_sha: String,
    lit: usize,
    golden_lit: u64,
    elements: Vec<ReviewElement>,
    code_c: String,
    code_hex: String,
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
    /// Playback clock and the runtime event feed shown in Designer.
    pub preview: Preview,
    /// Annotations and named scenarios for the open project (`review/review.json`).
    pub review: Option<ReviewStore>,
    /// Presets shown in the State tab, matching the Slint model order.
    pub presets: Vec<Preset>,
    /// The annotation being written, if the dialog is open.
    pub note_draft: Option<NoteDraft>,
    /// Evidence for the frame currently on the canvas (annotation staleness).
    pub frame_evidence: Option<Evidence>,
    /// Exported contract backing the Review evidence panel.
    pub contract: Option<Value>,
    pub contract_path: Option<PathBuf>,
    /// Contract written by the running export; adopted when that job finishes.
    pub pending_contract: Option<PathBuf>,
    /// Review view: 0 device diff, 1 code/hex.
    pub review_mode: i32,
    /// SHA-256 of the frame shown in Review (copy target).
    pub review_sha: String,
    /// Screen gallery cards, the worker building them, and the scene stamp
    /// they were built from.
    pub gallery_cards: Vec<GalleryCard>,
    pub gallery_job: Option<GalleryJob>,
    pub gallery_stamp: Option<u64>,
    pub gallery_query: String,
    pub gallery_filter: i32,
    pub gallery_visible: bool,
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
            preview: Preview::default(),
            review: None,
            presets: Vec::new(),
            note_draft: None,
            frame_evidence: None,
            contract: None,
            contract_path: None,
            pending_contract: None,
            review_mode: 0,
            review_sha: String::new(),
            gallery_cards: Vec::new(),
            gallery_job: None,
            gallery_stamp: None,
            gallery_query: String::new(),
            gallery_filter: 0,
            gallery_visible: false,
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
        self.review = self.load_review();
        self.contract = None;
        self.contract_path = None;
        self.discover_contract();
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
        self.review = None;
        self.contract = None;
        self.contract_path = None;
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
        self.refresh_presets();
        self.refresh_notes();
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
                if let Ok(vlsb) = fb.to_vlsb() {
                    self.frame_evidence = Some(Evidence {
                        sha256: hex_digest(&vlsb),
                        lit_pixels: lit,
                        frame: None,
                        source: "designer".into(),
                    });
                }
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
        let rm = ReviewModel::get(&ui);
        let blank = image_from_pixels(1, 1, &[0]);
        rm.set_mode(self.review_mode);
        let rendered = self.session.as_mut().map(|session| match session.render() {
            Ok(result) => {
                let fb = result.framebuffer;
                let vlsb = fb.to_vlsb().ok();
                let c_header = framebuffer_to_c_header(&fb, "ui_frame").ok();
                Ok(ReviewRender {
                    pixels: fb.pixels().to_vec(),
                    width: fb.width().max(1),
                    height: fb.height().max(1),
                    elements: session
                        .scene()
                        .get("elements")
                        .and_then(Value::as_array)
                        .cloned()
                        .unwrap_or_default(),
                    vlsb,
                    c_header,
                })
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
            self.refresh_evidence(&rm, None);
            return;
        };
        let render = match rendered {
            Ok(render) => render,
            Err(message) => {
                rm.set_has_baseline(false);
                rm.set_summary(ss(format!(
                    "{}: {}",
                    tr(&lang, "status.render_failed"),
                    message
                )));
                self.refresh_evidence(&rm, None);
                return;
            }
        };
        let (pixels, width, height, current_elements) = (
            render.pixels.as_slice(),
            render.width,
            render.height,
            render.elements.as_slice(),
        );
        let (bw, bh) = self.baseline_size;
        let has_baseline = !self.baseline_pixels.is_empty();
        rm.set_baseline(if has_baseline {
            image_from_pixels(bw.max(1), bh.max(1), &self.baseline_pixels)
        } else {
            blank.clone()
        });
        rm.set_current(image_from_pixels(width, height, pixels));
        rm.set_baseline_w(bw as i32);
        rm.set_baseline_h(bh as i32);
        rm.set_current_w(width as i32);
        rm.set_current_h(height as i32);
        rm.set_has_baseline(has_baseline);
        let changed = mono_core::diff::changed_count(pixels, &self.baseline_pixels);
        let bbox = mono_core::diff::changed_bbox(pixels, &self.baseline_pixels, width, height);
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
        self.refresh_evidence(&rm, Some(&render));
    }

    /// Device/code evidence: the live frame hash against the exported contract
    /// for the same state. Nothing here is inferred; every badge points at a
    /// hash recorded by the renderer or by `ui_contract.json`.
    fn refresh_evidence(&mut self, rm: &ReviewModel, render: Option<&ReviewRender>) {
        let view = self.evidence_view(render);
        rm.set_state_label(ss(&view.state_label));
        rm.set_has_contract(self.contract.is_some());
        rm.set_contract_name(ss(self.contract_name()));
        rm.set_contract_status(ss(view.status));
        rm.set_frame_sha(ss(&view.frame_sha));
        rm.set_golden_sha(ss(&view.golden_sha));
        rm.set_hash_match(view.status == "golden-match");
        rm.set_lit_pixels(view.lit as i32);
        rm.set_golden_lit(view.golden_lit as i32);
        rm.set_elements(model(view.elements));
        rm.set_code_c(ss(&view.code_c));
        rm.set_code_hex(ss(&view.code_hex));
        self.review_sha = view.frame_sha;
    }

    fn evidence_view(&self, render: Option<&ReviewRender>) -> EvidenceView {
        let state = self.current_state_map();
        let (frame_sha, lit, code_hex) = match render.and_then(|render| render.vlsb.as_ref()) {
            Some(vlsb) => (
                hex_digest(vlsb),
                vlsb.iter().map(|byte| byte.count_ones() as usize).sum(),
                crate::workbench::hex_spaced(vlsb),
            ),
            None => (String::new(), 0, String::new()),
        };
        let frame = self
            .contract
            .as_ref()
            .and_then(|contract| frame_for_state(contract, &state));
        let golden_sha = frame
            .and_then(|frame| frame.get("golden_sha256"))
            .and_then(Value::as_str)
            .unwrap_or_default()
            .to_string();
        let golden_lit = frame
            .and_then(|frame| frame.get("lit_pixels"))
            .and_then(Value::as_u64)
            .unwrap_or(0);
        let status = if self.contract.is_none() {
            "no-contract"
        } else if frame.is_none() {
            "not-exported"
        } else if golden_sha == frame_sha {
            "golden-match"
        } else {
            "frame-changed"
        };
        EvidenceView {
            state_label: Self::state_label(&state),
            status,
            frame_sha,
            golden_sha,
            lit,
            golden_lit,
            elements: frame.map(contract_elements).unwrap_or_default(),
            code_c: render
                .and_then(|render| render.c_header.clone())
                .unwrap_or_default(),
            code_hex,
        }
    }

    fn contract_name(&self) -> String {
        self.contract_path
            .as_deref()
            .map(|path| self.display_path(path))
            .unwrap_or_default()
    }

    /// 0 = device diff, 1 = code/hex.
    pub fn set_review_mode(&mut self, mode: i32) {
        self.review_mode = mode.clamp(0, 1);
        if let Some(ui) = self.ui.upgrade() {
            ReviewModel::get(&ui).set_mode(self.review_mode);
        }
    }

    /// Adopt a `ui_contract.json` from disk (Review evidence panel).
    pub fn load_contract(&mut self, path: &Path) -> Result<(), CoreError> {
        self.adopt_contract(path)?;
        self.set_status(self.t("review.contract_loaded"));
        self.refresh_review();
        Ok(())
    }

    pub fn load_contract_dialog(&mut self) {
        let Some(path) = rfd::FileDialog::new()
            .set_title(self.t("review.load_contract"))
            .add_filter("ui_contract.json", &["json"])
            .pick_file()
        else {
            return;
        };
        if let Err(error) = self.load_contract(&path) {
            self.error(&error);
        }
    }

    /// Pick up `<root>/exports/latest/ui_contract.json` when present.
    pub fn discover_contract(&mut self) {
        if self.contract.is_some() {
            return;
        }
        let Some(root) = self.project_root() else {
            return;
        };
        for candidate in [
            root.join("exports/latest/ui_contract.json"),
            root.join("exports/ui_contract.json"),
        ] {
            if candidate.is_file() && self.adopt_contract(&candidate).is_ok() {
                return;
            }
        }
    }

    fn adopt_contract(&mut self, path: &Path) -> Result<(), CoreError> {
        let text = std::fs::read_to_string(path).map_err(|error| {
            CoreError::new("E-REVIEW-CONTRACT", format!("{}: {error}", posix(path)))
        })?;
        let value: Value = serde_json::from_str(&text).map_err(|error| {
            CoreError::new("E-REVIEW-CONTRACT", format!("{}: {error}", posix(path)))
        })?;
        if value.get("frames").and_then(Value::as_object).is_none() {
            return Err(CoreError::new(
                "E-REVIEW-CONTRACT",
                format!("{}: {}", posix(path), self.t("review.contract_invalid")),
            ));
        }
        self.contract = Some(value);
        self.contract_path = Some(path.to_path_buf());
        Ok(())
    }

    pub fn copy_frame_hash(&mut self) {
        if self.review_sha.is_empty() {
            return;
        }
        match arboard::Clipboard::new()
            .and_then(|mut clipboard| clipboard.set_text(self.review_sha.clone()))
        {
            Ok(()) => self.set_status(self.t("review.hash_copied")),
            Err(error) => self.error(&CoreError::new("E-CLIPBOARD", error.to_string())),
        }
    }

    // --------------------------------------------------------- review pack

    pub fn review_pack_dialog(&mut self) -> Result<(), CoreError> {
        let Some(root) = self.project_root() else {
            return Ok(());
        };
        let directory = root.join("review");
        let Some(path) = rfd::FileDialog::new()
            .set_title(self.t("action.review_pack"))
            .set_directory(directory)
            .set_file_name("review.html")
            .add_filter("HTML", &["html"])
            .save_file()
        else {
            return Ok(());
        };
        self.start_review_pack(path)
    }

    pub fn start_review_pack(&mut self, output: PathBuf) -> Result<(), CoreError> {
        let Some(project) = self.project.clone() else {
            return Ok(());
        };
        let annotations = self
            .review
            .as_ref()
            .map(ReviewStore::annotations)
            .unwrap_or_default();
        let lang = self.lang.clone();
        self.start_background("action.review_pack", move |progress| {
            let summary = build_review_pack(&project, &annotations, &output, progress)?;
            Ok(Outcome {
                status: trf(
                    &lang,
                    "status.review_pack",
                    &[
                        ("frames", summary.frames.to_string()),
                        ("path", posix(&summary.output)),
                    ],
                ),
                log: vec![format!(
                    "REVIEW_PACK {} {}",
                    posix(&summary.output),
                    summary.sha256
                )],
                refresh: false,
            })
        })
    }

    // ------------------------------------------------------------- gallery

    pub fn toggle_gallery(&mut self) {
        if self.gallery_visible {
            self.close_gallery();
        } else {
            self.open_gallery();
        }
    }

    pub fn open_gallery(&mut self) {
        self.gallery_visible = true;
        self.gallery_query.clear();
        self.gallery_filter = 0;
        if let Some(ui) = self.ui.upgrade() {
            let model_handle = GalleryModel::get(&ui);
            model_handle.set_visible(true);
            model_handle.set_query(ss(""));
            model_handle.set_filter(0);
        }
        self.refresh_gallery();
    }

    pub fn close_gallery(&mut self) {
        self.gallery_visible = false;
        if let Some(ui) = self.ui.upgrade() {
            GalleryModel::get(&ui).set_visible(false);
        }
    }

    /// Rebuild rows from the cached cards, or start a build when the scene
    /// changed since the cards were rendered.
    pub fn refresh_gallery(&mut self) {
        self.ensure_gallery();
        self.fill_gallery();
    }

    fn ensure_gallery(&mut self) {
        if self.gallery_job.is_some() {
            return;
        }
        let Some(project) = self.project.clone() else {
            self.gallery_cards.clear();
            self.gallery_stamp = None;
            return;
        };
        let stamp = self.gallery_stamp_value();
        if self.gallery_stamp == Some(stamp) {
            return;
        }
        self.gallery_cards.clear();
        self.gallery_stamp = Some(stamp);
        let annotations = self
            .review
            .as_ref()
            .map(ReviewStore::counts_by_screen)
            .unwrap_or_default();
        self.gallery_job = Some(GalleryJob::spawn(project, annotations));
    }

    pub fn gallery_tick(&mut self) {
        let Some(job) = &self.gallery_job else { return };
        let Some(result) = job.poll() else { return };
        self.gallery_job = None;
        match result {
            Ok(cards) => {
                self.gallery_cards = cards;
                if self.gallery_visible {
                    self.fill_gallery();
                }
            }
            Err(error) => self.error(&error),
        }
    }

    pub fn gallery_search(&mut self, query: &str) {
        self.gallery_query = query.to_string();
        self.fill_gallery();
    }

    pub fn gallery_set_filter(&mut self, filter: i32) {
        self.gallery_filter = filter.clamp(0, 2);
        self.fill_gallery();
    }

    /// Open a card in Designer (unsaved guard first), then reset the runtime so
    /// the canvas shows the init frame the card promised.
    pub fn gallery_open_screen(&mut self, screen: &str) -> Result<(), CoreError> {
        self.close_gallery();
        self.open_screen(screen)?;
        self.preview_reset()
    }

    fn gallery_stamp_value(&self) -> u64 {
        use std::hash::{Hash, Hasher};
        let mut hasher = std::collections::hash_map::DefaultHasher::new();
        if let Some(project) = &self.project {
            project.path.hash(&mut hasher);
            project.screens().len().hash(&mut hasher);
        }
        if let Some(session) = &self.session {
            session.fingerprint().hash(&mut hasher);
        }
        hasher.finish()
    }

    fn fill_gallery(&mut self) {
        let Some(ui) = self.ui.upgrade() else { return };
        let gm = GalleryModel::get(&ui);
        if self.gallery_job.is_some() && self.gallery_cards.is_empty() {
            gm.set_summary(ss(self.t("gallery.rendering")));
            gm.set_truncated(false);
            gm.set_items(model(Vec::new()));
            return;
        }
        let lang = self.lang.clone();
        let query = self.gallery_query.to_lowercase();
        let filter = self.gallery_filter;
        let visible: Vec<&GalleryCard> = self
            .gallery_cards
            .iter()
            .filter(|card| {
                let hit = query.is_empty()
                    || card.label.to_lowercase().contains(&query)
                    || card.id.to_lowercase().contains(&query)
                    || card.category.to_lowercase().contains(&query);
                let keep = match filter {
                    1 => card.blockers > 0,
                    2 => card.annotations > 0,
                    _ => true,
                };
                hit && keep
            })
            .collect();
        let mut counts: BTreeMap<&str, usize> = BTreeMap::new();
        for card in &visible {
            *counts.entry(card.category.as_str()).or_default() += 1;
        }
        let mut rows = Vec::new();
        let mut current: Option<&str> = None;
        for card in visible {
            if current != Some(card.category.as_str()) {
                let count = counts.get(card.category.as_str()).copied().unwrap_or(0);
                rows.push(GalleryItem {
                    header: true,
                    title: ss(&card.category),
                    detail: ss(trf(
                        &lang,
                        "gallery.category",
                        &[("count", count.to_string())],
                    )),
                    badge: ss(""),
                    bad: false,
                    screen: ss(""),
                    image: Default::default(),
                });
                current = Some(card.category.as_str());
            }
            rows.push(GalleryItem {
                header: false,
                title: ss(&card.label),
                detail: ss(trf(
                    &lang,
                    "gallery.card",
                    &[
                        ("id", card.id.clone()),
                        ("blockers", card.blockers.to_string()),
                        ("warnings", card.warnings.to_string()),
                        ("notes", card.annotations.to_string()),
                    ],
                )),
                badge: ss(if card.blockers > 0 {
                    trf(
                        &lang,
                        "gallery.blockers",
                        &[("count", card.blockers.to_string())],
                    )
                } else {
                    tr(&lang, "gallery.valid")
                }),
                bad: card.blockers > 0,
                screen: ss(&card.id),
                image: card
                    .image
                    .as_ref()
                    .map(|frame| image_from_pixels(frame.width, frame.height, &frame.pixels))
                    .unwrap_or_default(),
            });
        }
        let blockers: usize = self.gallery_cards.iter().map(|card| card.blockers).sum();
        let notes: usize = self.gallery_cards.iter().map(|card| card.annotations).sum();
        gm.set_summary(ss(trf(
            &lang,
            "gallery.summary",
            &[
                ("screens", self.gallery_cards.len().to_string()),
                ("blocking", blockers.to_string()),
                ("notes", notes.to_string()),
            ],
        )));
        gm.set_truncated(self.gallery_cards.len() >= crate::gallery::MAX_SCREENS);
        gm.set_items(model(rows));
    }

    fn display_path(&self, path: &Path) -> String {
        if let Some(root) = self.project_root()
            && let Ok(relative) = path.strip_prefix(&root)
        {
            return posix(relative);
        }
        path.file_name()
            .map(|name| name.to_string_lossy().into_owned())
            .unwrap_or_default()
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
        dm.set_playing(self.preview.playing);
        dm.set_preview_boundary(ss(tr(&self.lang, "preview.boundary")));
        let reset_label = tr(&self.lang, "preview.event_reset");
        let events: Vec<EventItem> = self
            .preview
            .events
            .iter()
            .rev()
            .take(40)
            .map(|event| EventItem {
                at: ss(format!("t={}", event.at)),
                kind: ss(event.kind.clone()),
                detail: ss(if event.kind == "RESET" {
                    reset_label.clone()
                } else {
                    format!("{}: {} → {}", event.name, event.before, event.after)
                }),
            })
            .collect();
        dm.set_events(model(events));
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

    /// Advance the preview one timeline step and record what changed.
    pub fn preview_step(&mut self) -> Result<(), CoreError> {
        let mut log = VecRuntimeLog::default();
        if let Some(session) = self.session.as_mut() {
            session.step_logged(1, &mut log)?;
        }
        self.preview.absorb(log.take());
        Ok(())
    }

    pub fn preview_reset(&mut self) -> Result<(), CoreError> {
        let mut log = VecRuntimeLog::default();
        if let Some(session) = self.session.as_mut() {
            session.reset_runtime_logged(&mut log)?;
        }
        self.preview.clear();
        self.preview.absorb(log.take());
        Ok(())
    }

    /// Drive playback from the UI timer: at most one step per tick, and only
    /// while the timeline still has work after the current position.
    pub fn preview_tick(&mut self, now: std::time::Instant) -> bool {
        if !self.preview.due(now) {
            return false;
        }
        let continues = self
            .session
            .as_ref()
            .is_some_and(|s| timeline_continues(s.scene(), s.elapsed));
        if !continues {
            self.preview.pause();
            self.refresh_inspector();
            return false;
        }
        self.preview.last_step = Some(now);
        if self.preview_step().is_err() {
            self.preview.pause();
            return false;
        }
        self.refresh_canvas();
        self.refresh_inspector();
        true
    }

    fn load_review(&mut self) -> Option<ReviewStore> {
        let root = self.project_root()?;
        match ReviewStore::for_root(&root) {
            Ok(store) => Some(store),
            Err(error) => {
                self.error(&error);
                None
            }
        }
    }

    fn active_screen_id(&self) -> String {
        self.project
            .as_ref()
            .map(|project| project.active_screen())
            .unwrap_or_default()
    }

    fn current_state_map(&self) -> Map<String, Value> {
        self.session
            .as_ref()
            .map(|session| session.state.clone())
            .unwrap_or_default()
    }

    /// `battery=0, phase=running` with sorted keys; `init` when empty.
    fn state_label(state: &Map<String, Value>) -> String {
        let mut pairs: Vec<String> = state
            .iter()
            .map(|(name, value)| format!("{name}={}", py_str(value)))
            .collect();
        pairs.sort();
        if pairs.is_empty() {
            "init".into()
        } else {
            pairs.join(", ")
        }
    }

    /// Rebuild the State-tab presets from the scene and the review sidecar.
    pub fn refresh_presets(&mut self) {
        let states = self
            .session
            .as_ref()
            .and_then(|session| {
                session
                    .scene()
                    .get("states")
                    .and_then(Value::as_object)
                    .cloned()
            })
            .unwrap_or_default();
        let scenarios = self
            .review
            .as_ref()
            .map(|store| store.scenarios())
            .unwrap_or_default();
        let presets = build_presets(&self.lang, &states, &scenarios);
        if let Some(ui) = self.ui.upgrade() {
            let items: Vec<PresetItem> = presets
                .iter()
                .enumerate()
                .map(|(index, preset)| PresetItem {
                    label: ss(preset.label.clone()),
                    index: index as i32,
                })
                .collect();
            DesignerModel::get(&ui).set_presets(model(items));
        }
        self.presets = presets;
    }

    fn note_rows(&mut self) -> Vec<NoteItem> {
        if self.session.is_some()
            && let Some(evidence) = self.compute_frame_evidence()
        {
            self.frame_evidence = Some(evidence);
        }
        let screen = self.active_screen_id();
        let current = self.current_state_map();
        let current_sha = self
            .frame_evidence
            .as_ref()
            .map(|evidence| evidence.sha256.clone())
            .unwrap_or_default();
        match &self.review {
            Some(store) => store
                .annotations_for(&screen)
                .into_iter()
                .map(|note| {
                    let same_state = note.state == current;
                    NoteItem {
                        id: ss(note.id),
                        kind: ss(note.kind.as_str()),
                        kind_label: ss(tr(
                            &self.lang,
                            &format!("notes.kind.{}", note.kind.as_str()),
                        )),
                        title: ss(note.title),
                        anchor: ss(format!(
                            "{} · {}",
                            Self::state_label(&note.state),
                            note.element.unwrap_or_else(|| "—".into())
                        )),
                        stale: same_state
                            && !note.evidence.sha256.is_empty()
                            && note.evidence.sha256 != current_sha,
                        updated: ss(short_stamp(&note.updated_utc)),
                    }
                })
                .collect(),
            None => Vec::new(),
        }
    }

    pub fn refresh_notes(&mut self) {
        let Some(ui) = self.ui.upgrade() else { return };
        let model_handle = NoteModel::get(&ui);
        let screen = self.active_screen_id();
        model_handle.set_can_add(self.review.is_some() && !screen.is_empty());
        let labels: Vec<SharedString> = ["defect", "decision", "explanation"]
            .iter()
            .map(|kind| ss(tr(&self.lang, &format!("notes.kind.{kind}"))))
            .collect();
        model_handle.set_kind_labels(model(labels));
        let rows = self.note_rows();
        model_handle.set_items(model(rows));
    }

    /// Render the current frame when the canvas has not done it (headless tests,
    /// or a note opened before the first paint).
    fn compute_frame_evidence(&mut self) -> Option<Evidence> {
        let result = self.session.as_mut()?.render().ok()?;
        let vlsb = result.framebuffer.to_vlsb().ok()?;
        Some(Evidence {
            sha256: hex_digest(&vlsb),
            lit_pixels: result
                .framebuffer
                .pixels()
                .iter()
                .filter(|v| **v != 0)
                .count(),
            frame: None,
            source: "designer".into(),
        })
    }

    pub fn begin_note(&mut self) -> Result<(), CoreError> {
        if self.review.is_none() {
            return Err(CoreError::new(
                "E-REVIEW-NO-PROJECT",
                self.t("notes.no_project"),
            ));
        }
        let screen = self.active_screen_id();
        if screen.is_empty() {
            return Err(CoreError::new(
                "E-REVIEW-NO-PROJECT",
                self.t("notes.no_project"),
            ));
        }
        let state = self.current_state_map();
        let selection = self.selection.primary().map(str::to_string);
        let evidence = match self.frame_evidence.clone() {
            Some(evidence) => evidence,
            None => self.compute_frame_evidence().unwrap_or_default(),
        };
        self.frame_evidence = Some(evidence.clone());
        self.note_draft = Some(NoteDraft {
            id: None,
            screen: screen.clone(),
            state: state.clone(),
            element: selection.clone(),
            evidence: evidence.clone(),
        });
        if let Some(ui) = self.ui.upgrade() {
            let model_handle = NoteModel::get(&ui);
            model_handle.set_dialog_title(ss(tr(&self.lang, "notes.dialog_add")));
            model_handle.set_anchor(ss(note_anchor(&screen, &state, selection.as_deref())));
            model_handle.set_evidence(ss(evidence_text(&self.lang, &evidence)));
            model_handle.set_draft_title(ss(""));
            model_handle.set_draft_body(ss(""));
            model_handle.set_kind_index(0);
            model_handle.set_error(ss(""));
            model_handle.set_visible(true);
        }
        Ok(())
    }

    pub fn edit_note(&mut self, id: &str) -> Result<(), CoreError> {
        let Some(note) = self
            .review
            .as_ref()
            .and_then(|store| store.annotations().into_iter().find(|note| note.id == id))
        else {
            return Ok(());
        };
        self.note_draft = Some(NoteDraft {
            id: Some(note.id.clone()),
            screen: note.screen.clone(),
            state: note.state.clone(),
            element: note.element.clone(),
            evidence: note.evidence.clone(),
        });
        if let Some(ui) = self.ui.upgrade() {
            let model_handle = NoteModel::get(&ui);
            model_handle.set_dialog_title(ss(tr(&self.lang, "notes.dialog_edit")));
            model_handle.set_anchor(ss(note_anchor(
                &note.screen,
                &note.state,
                note.element.as_deref(),
            )));
            model_handle.set_evidence(ss(evidence_text(&self.lang, &note.evidence)));
            model_handle.set_draft_title(ss(note.title));
            model_handle.set_draft_body(ss(note.body));
            model_handle.set_kind_index(match note.kind {
                AnnotationKind::Defect => 0,
                AnnotationKind::Decision => 1,
                AnnotationKind::Explanation => 2,
            });
            model_handle.set_error(ss(""));
            model_handle.set_visible(true);
        }
        Ok(())
    }

    pub fn cancel_note(&mut self) {
        self.note_draft = None;
        if let Some(ui) = self.ui.upgrade() {
            NoteModel::get(&ui).set_visible(false);
        }
    }

    pub fn save_note(&mut self, title: &str, body: &str, kind_index: i32) -> Result<(), CoreError> {
        let Some(draft) = self.note_draft.clone() else {
            return Ok(());
        };
        let kind = match kind_index {
            0 => AnnotationKind::Defect,
            1 => AnnotationKind::Decision,
            _ => AnnotationKind::Explanation,
        };
        let created = self
            .review
            .as_ref()
            .and_then(|store| {
                store
                    .annotations()
                    .into_iter()
                    .find(|note| Some(&note.id) == draft.id.as_ref())
            })
            .map(|note| note.created_utc)
            .unwrap_or_default();
        let annotation = Annotation {
            id: draft.id.clone().unwrap_or_default(),
            kind,
            screen: draft.screen.clone(),
            state: draft.state.clone(),
            element: draft.element.clone(),
            title: title.to_string(),
            body: body.to_string(),
            evidence: draft.evidence.clone(),
            created_utc: created,
            updated_utc: String::new(),
        };
        match self.review.as_mut() {
            Some(store) => store.upsert_annotation(annotation).map(|_| ())?,
            None => {
                return Err(CoreError::new(
                    "E-REVIEW-NO-PROJECT",
                    self.t("notes.no_project"),
                ));
            }
        }
        self.note_draft = None;
        if let Some(ui) = self.ui.upgrade() {
            NoteModel::get(&ui).set_visible(false);
        }
        self.set_status(self.t("notes.saved"));
        self.refresh_notes();
        Ok(())
    }

    pub fn delete_note(&mut self, id: &str) {
        let result = match self.review.as_mut() {
            Some(store) => store.remove_annotation(id),
            None => Ok(false),
        };
        match result {
            Ok(true) => {
                self.set_status(self.t("notes.deleted"));
                self.refresh_notes();
            }
            Ok(false) => {}
            Err(error) => self.error(&error),
        }
    }

    /// Apply a State-tab preset: optional reset, then every declared value.
    pub fn apply_preset(&mut self, index: usize) -> Result<(), CoreError> {
        let Some(preset) = self.presets.get(index).cloned() else {
            return Ok(());
        };
        self.preview.pause();
        let mut log = VecRuntimeLog::default();
        if let Some(session) = self.session.as_mut() {
            if preset.reset_first {
                session.reset_runtime_logged(&mut log)?;
            }
            for (name, value) in &preset.set {
                session.set_state_logged(name, value.clone(), &mut log)?;
            }
        }
        if preset.reset_first {
            self.preview.clear();
        }
        self.preview.absorb(log.take());
        self.refresh_canvas();
        self.refresh_inspector();
        self.refresh_validation();
        self.refresh_notes();
        Ok(())
    }

    pub fn prompt_scenario(&mut self) {
        let title = self.t("preview.save_scenario");
        let label = self.t("preview.scenario_name");
        self.show_prompt(Prompt::ScenarioName, &title, &label, "");
    }

    /// Save the current state as a named scenario in `review/review.json`.
    pub fn save_scenario(&mut self, label: &str) -> Result<(), CoreError> {
        if label.trim().is_empty() {
            return Err(CoreError::invalid(self.t("preview.scenario_name_empty")));
        }
        let state = self.current_state_map();
        let Some(store) = self.review.as_mut() else {
            return Err(CoreError::new(
                "E-REVIEW-NO-PROJECT",
                self.t("notes.no_project"),
            ));
        };
        store.upsert_scenario(Scenario {
            id: String::new(),
            label: label.trim().to_string(),
            set: state,
            created_utc: String::new(),
        })?;
        self.refresh_presets();
        self.set_status(self.t("preview.scenario_saved"));
        Ok(())
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
                "toggle-play" => {
                    self.preview.playing = !self.preview.playing;
                    self.preview.last_step = self.preview.playing.then(std::time::Instant::now);
                }
                "step" => {
                    self.preview.pause();
                    self.preview_step()?;
                }
                "reset-runtime" => {
                    self.preview.pause();
                    self.preview_reset()?;
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
        self.pending_contract = Some(output.join("ui_contract.json"));
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
                        if let Some(path) = self.pending_contract.take() {
                            let _ = self.adopt_contract(&path);
                        }
                        if outcome.refresh {
                            self.refresh_app();
                        }
                    }
                    Err(e) if e.code == mono_project::export::CANCELLED => {
                        self.pending_contract = None;
                        self.log_event(format!("JOB_CANCELLED {label}"));
                        self.set_status(trf(&self.lang, "job.cancelled", &[("label", label)]));
                    }
                    Err(e) => {
                        self.pending_contract = None;
                        self.error(&e);
                    }
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

/// Init, every non-init enum value and every int bound, then named scenarios.
/// No semantic guessing: a "fault" preset only exists if the project declares
/// that state.
fn build_presets(lang: &str, states: &Map<String, Value>, scenarios: &[Scenario]) -> Vec<Preset> {
    let mut presets: Vec<Preset> = vec![Preset {
        label: tr(lang, "preview.preset_init"),
        set: Map::new(),
        reset_first: true,
    }];
    let mut state_names: Vec<&String> = states.keys().collect();
    state_names.sort();
    for name in state_names {
        let spec = &states[name];
        let init = spec.get("init").cloned().unwrap_or(Value::Null);
        let mut values: Vec<&Value> = Vec::new();
        if let Some(list) = spec.get("values").and_then(Value::as_array) {
            values.extend(list.iter());
        } else if spec.get("type").map(py_str).as_deref() == Some("int") {
            values.extend([spec.get("min"), spec.get("max")].into_iter().flatten());
        }
        for value in values {
            if *value == init || value.is_null() {
                continue;
            }
            let mut set = Map::new();
            set.insert(name.clone(), value.clone());
            presets.push(Preset {
                label: format!("{name} = {}", py_str(value)),
                set,
                reset_first: false,
            });
        }
    }
    for scenario in scenarios {
        presets.push(Preset {
            label: scenario.label.clone(),
            set: scenario.set.clone(),
            reset_first: true,
        });
    }
    presets
}

/// Visible elements of an exported contract frame, as shown in Review.
fn contract_elements(frame: &Value) -> Vec<ReviewElement> {
    frame
        .get("elements")
        .and_then(Value::as_array)
        .into_iter()
        .flatten()
        .filter(|element| element.get("visible") != Some(&Value::Bool(false)))
        .map(|element| {
            let number = |key: &str| element.get(key).and_then(py_int).unwrap_or(0);
            ReviewElement {
                id: ss(element.get("id").map(py_str).unwrap_or_default()),
                kind: ss(element.get("type").map(py_str).unwrap_or_default()),
                geometry: ss(format!(
                    "{},{} · {}×{}",
                    number("x"),
                    number("y"),
                    number("w"),
                    number("h")
                )),
                visible: element.get("visible") == Some(&Value::Bool(true)),
            }
        })
        .collect()
}

/// `screen · state · element`; no firmware file:line exists in this product.
fn note_anchor(screen: &str, state: &Map<String, Value>, element: Option<&str>) -> String {
    let base = format!("{screen} · {}", App::state_label(state));
    match element {
        Some(id) if !id.is_empty() => format!("{base} · {id}"),
        _ => base,
    }
}

fn short_stamp(iso: &str) -> String {
    iso.chars()
        .take(16)
        .map(|c| if c == 'T' { ' ' } else { c })
        .collect()
}

fn evidence_text(lang: &str, evidence: &Evidence) -> String {
    let hash: String = evidence.sha256.chars().take(12).collect();
    trf(
        lang,
        "notes.evidence",
        &[("hash", hash), ("lit", evidence.lit_pixels.to_string())],
    )
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
        // `py_resolve` canonicalises the project root, and some CI temp dirs are
        // symlinks (`/var` → `/private/var`, Windows short names); compare like
        // with like so the assertion is about the project, not the temp prefix.
        let root = mono_project::project::py_resolve(&root);
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
        let root = mono_project::project::py_resolve(&root);
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

    #[test]
    fn toggle_play_sets_playing() {
        let (mut app, root) = project_app("preview-toggle");
        assert!(!app.preview.playing);
        app.action("toggle-play");
        assert!(app.preview.playing);
        app.action("toggle-play");
        assert!(!app.preview.playing);
        let _ = std::fs::remove_dir_all(&root);
    }

    #[test]
    fn step_pauses_playback_and_records_the_change() {
        let (mut app, root) = project_app("preview-step");
        app.action("toggle-play");
        app.action("step");
        assert!(!app.preview.playing);
        for _ in 0..5 {
            app.action("step");
        }
        assert!(
            app.preview
                .events
                .iter()
                .any(|e| e.kind == "STATE" && e.name == "phase" && e.after == "running")
        );
        let _ = std::fs::remove_dir_all(&root);
    }

    #[test]
    fn preview_tick_advances_one_step_per_interval() {
        let (mut app, root) = project_app("preview-tick");
        let interval = app.preview.interval;
        let start = std::time::Instant::now();
        app.preview.playing = true;
        app.preview.last_step = Some(start);
        assert!(!app.preview_tick(start));
        assert!(app.preview_tick(start + interval));
        assert_eq!(app.session.as_ref().unwrap().elapsed, 1);
        assert!(!app.preview_tick(start + interval));
        assert_eq!(app.session.as_ref().unwrap().elapsed, 1);
        let _ = std::fs::remove_dir_all(&root);
    }

    #[test]
    fn playback_does_not_mark_the_scene_dirty() {
        let (mut app, root) = project_app("preview-dirty");
        let interval = app.preview.interval;
        assert!(!app.session.as_ref().unwrap().dirty);
        app.action("toggle-play");
        let now = std::time::Instant::now();
        app.preview.last_step = Some(now);
        assert!(app.preview_tick(now + interval));
        assert!(!app.session.as_ref().unwrap().dirty);
        let _ = std::fs::remove_dir_all(&root);
    }

    #[test]
    fn reset_clears_the_event_feed() {
        let (mut app, root) = project_app("preview-reset");
        // The fixture changes `phase` at t=5; earlier steps record nothing.
        for _ in 0..5 {
            app.action("step");
        }
        assert!(!app.preview.events.is_empty());
        app.action("reset-runtime");
        assert_eq!(app.preview.events.len(), 1);
        assert_eq!(app.preview.events[0].kind, "RESET");
        let _ = std::fs::remove_dir_all(&root);
    }

    #[test]
    fn note_uses_current_screen_state_and_frame_hash() {
        let (mut app, root) = project_app("note-anchor");
        select(&mut app, "running_icon");
        app.begin_note().unwrap();
        app.save_note("Battery clips", "at minimum", 0).unwrap();
        let store = ReviewStore::for_root(&root).unwrap();
        let notes = store.annotations_for("main");
        assert_eq!(notes.len(), 1);
        assert_eq!(notes[0].kind, AnnotationKind::Defect);
        assert_eq!(notes[0].state["phase"], "standby");
        assert_eq!(notes[0].element.as_deref(), Some("running_icon"));
        assert_eq!(notes[0].evidence.sha256.len(), 64);
        assert!(notes[0].evidence.lit_pixels > 0);
        assert_eq!(notes[0].evidence.source, "designer");
        let _ = std::fs::remove_dir_all(&root);
    }

    #[test]
    fn note_is_stale_when_the_frame_changes_in_the_same_state() {
        let (mut app, root) = project_app("note-stale");
        app.begin_note().unwrap();
        app.save_note("first", "", 2).unwrap();
        assert!(!app.note_rows()[0].stale);
        select(&mut app, "battery");
        app.geometry_edited("x", 20);
        assert!(app.note_rows()[0].stale);
        let _ = std::fs::remove_dir_all(&root);
    }

    #[test]
    fn delete_note_removes_it_from_disk() {
        let (mut app, root) = project_app("note-delete");
        app.begin_note().unwrap();
        app.save_note("gone", "", 1).unwrap();
        let id = ReviewStore::for_root(&root).unwrap().annotations()[0]
            .id
            .clone();
        app.delete_note(&id);
        assert!(
            ReviewStore::for_root(&root)
                .unwrap()
                .annotations()
                .is_empty()
        );
        assert!(app.note_rows().is_empty());
        let _ = std::fs::remove_dir_all(&root);
    }

    #[test]
    fn derived_presets_include_init_enum_values_and_int_bounds() {
        let (app, root) = project_app("presets");
        let states = app.session.as_ref().unwrap().scene()["states"]
            .as_object()
            .cloned()
            .unwrap();
        let presets = build_presets(&app.lang, &states, &[]);
        assert_eq!(presets[0].label, "初始状态");
        assert!(presets.iter().any(|p| p.label == "phase = running"));
        assert!(presets.iter().any(|p| p.label == "battery = 0"));
        assert!(presets.iter().any(|p| p.label == "seconds = 999"));
        // The init value itself is not a preset.
        assert!(!presets.iter().any(|p| p.label == "battery = 4"));
        let _ = std::fs::remove_dir_all(&root);
    }

    #[test]
    fn saved_scenario_applies_on_top_of_init() {
        let (mut app, root) = project_app("scenario-apply");
        app.state_edited("battery", "0");
        app.save_scenario("Low battery").unwrap();
        app.state_edited("battery", "4");
        let index = app
            .presets
            .iter()
            .position(|preset| preset.label == "Low battery")
            .unwrap();
        app.apply_preset(index).unwrap();
        let state = &app.session.as_ref().unwrap().state;
        assert_eq!(state["battery"], 0);
        assert_eq!(state["phase"], "standby");
        let _ = std::fs::remove_dir_all(&root);
    }

    #[test]
    fn preset_with_unknown_state_is_rejected() {
        let (mut app, root) = project_app("preset-bad");
        let mut set = Map::new();
        set.insert("nope".into(), json!(1));
        app.presets = vec![Preset {
            label: "bad".into(),
            set,
            reset_first: true,
        }];
        let error = app.apply_preset(0).unwrap_err();
        assert_eq!(error.code, "E-CORE-KEY");
        let _ = std::fs::remove_dir_all(&root);
    }

    fn review_render(app: &mut App) -> ReviewRender {
        let session = app.session.as_mut().unwrap();
        let result = session.render().unwrap();
        let fb = result.framebuffer;
        let vlsb = fb.to_vlsb().ok();
        let c_header = framebuffer_to_c_header(&fb, "ui_frame").ok();
        ReviewRender {
            pixels: fb.pixels().to_vec(),
            width: fb.width().max(1),
            height: fb.height().max(1),
            elements: session
                .scene()
                .get("elements")
                .and_then(Value::as_array)
                .cloned()
                .unwrap_or_default(),
            vlsb,
            c_header,
        }
    }

    fn contract_for(app: &App, golden: &str) -> Value {
        let mut state = app.current_state_map();
        let frame = json!({
            "state": Value::Object(std::mem::take(&mut state)),
            "golden_sha256": golden,
            "lit_pixels": 7,
            "elements": [
                {"id": "battery", "type": "image_seq", "visible": true, "x": 0, "y": 0, "w": 8, "h": 16},
                {"id": "ghost", "type": "image", "visible": false, "x": 0, "y": 0, "w": 1, "h": 1},
            ],
        });
        json!({"frames": {"current": frame}})
    }

    #[test]
    fn review_evidence_reports_golden_match() {
        let (mut app, root) = project_app("evidence-match");
        let render = review_render(&mut app);
        let sha = hex_digest(render.vlsb.as_ref().unwrap());
        app.contract = Some(contract_for(&app, &sha));
        let view = app.evidence_view(Some(&render));
        assert_eq!(view.status, "golden-match");
        assert_eq!(view.frame_sha, sha);
        assert_eq!(view.golden_sha, sha);
        assert_eq!(view.lit, 686);
        assert_eq!(view.golden_lit, 7);
        assert_eq!(view.elements.len(), 1);
        assert_eq!(view.elements[0].id, "battery");
        let _ = std::fs::remove_dir_all(&root);
    }

    #[test]
    fn review_evidence_reports_frame_changed() {
        let (mut app, root) = project_app("evidence-changed");
        let render = review_render(&mut app);
        app.contract = Some(contract_for(&app, "00"));
        let view = app.evidence_view(Some(&render));
        assert_eq!(view.status, "frame-changed");
        assert_ne!(view.golden_sha, view.frame_sha);
        let _ = std::fs::remove_dir_all(&root);
    }

    #[test]
    fn review_evidence_handles_missing_contract() {
        let (mut app, root) = project_app("evidence-none");
        let render = review_render(&mut app);
        let view = app.evidence_view(Some(&render));
        assert_eq!(view.status, "no-contract");
        assert_eq!(view.frame_sha.len(), 64);
        let mut other = Map::new();
        other.insert("nope".into(), json!(1));
        let frame = json!({"state": other, "golden_sha256": "aa"});
        app.contract = Some(json!({"frames": {"other": frame}}));
        let view = app.evidence_view(Some(&render));
        assert_eq!(view.status, "not-exported");
        assert!(view.elements.is_empty());
        let _ = std::fs::remove_dir_all(&root);
    }

    #[test]
    fn review_code_and_hex_are_deterministic() {
        let (mut app, root) = project_app("evidence-code");
        let first = review_render(&mut app);
        let second = review_render(&mut app);
        let view = app.evidence_view(Some(&first));
        assert_eq!(
            view.code_hex,
            crate::workbench::hex_spaced(first.vlsb.as_ref().unwrap())
        );
        assert_eq!(view.code_hex, app.evidence_view(Some(&second)).code_hex);
        assert!(view.code_c.contains("ui_frame"));
        assert_eq!(view.code_c, app.evidence_view(Some(&second)).code_c);
        let _ = std::fs::remove_dir_all(&root);
    }

    #[test]
    fn discover_contract_adopts_the_latest_export() {
        let (mut app, root) = project_app("evidence-discover");
        let dir = root.join("exports/latest");
        std::fs::create_dir_all(&dir).unwrap();
        std::fs::write(
            dir.join("ui_contract.json"),
            json!({"frames": {"current": {"state": {}, "golden_sha256": "aa"}}}).to_string(),
        )
        .unwrap();
        app.discover_contract();
        assert!(app.contract.is_some());
        assert_eq!(app.contract_name(), "exports/latest/ui_contract.json");
        let _ = std::fs::remove_dir_all(&root);
    }

    #[test]
    fn gallery_open_screen_resets_runtime_state() {
        let (mut app, root) = project_app("gallery-open");
        app.preview_step().unwrap();
        assert!(app.session.as_ref().unwrap().elapsed > 0);
        app.gallery_open_screen("123").unwrap();
        let session = app.session.as_ref().unwrap();
        let init = mono_core::state::init_state(session.scene());
        assert_eq!(session.state, init);
        assert!(!app.preview.playing);
        let _ = std::fs::remove_dir_all(&root);
    }

    #[test]
    fn gallery_cache_invalidates_after_edit() {
        let (mut app, root) = project_app("gallery-cache");
        app.gallery_stamp = Some(app.gallery_stamp_value());
        app.gallery_cards = Vec::new();
        let before = app.gallery_stamp;
        // Scene edits change the stamp; runtime-only state changes do not.
        if let Some(session) = app.session.as_mut() {
            let elements = session.doc.data["elements"].as_array_mut().unwrap();
            let element = elements[0].as_object_mut().unwrap();
            let x = element.get("x").and_then(Value::as_i64).unwrap_or(0);
            element.insert("x".into(), json!(x + 1));
        }
        app.refresh_gallery();
        assert_ne!(app.gallery_stamp, before);
        assert!(app.gallery_job.is_some());
        app.gallery_job = None;
        let _ = std::fs::remove_dir_all(&root);
    }
}
