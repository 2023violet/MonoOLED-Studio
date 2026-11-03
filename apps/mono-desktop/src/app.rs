//! Application controller: owns the project, the Designer session and the UI
//! sync. Every UI callback goes through `App`; Slint models are rebuilt from
//! the session after each change (the scene JSON stays the single truth).

use std::collections::{BTreeMap, HashMap, HashSet};
use std::path::{Path, PathBuf};

use mono_core::CoreError;
use mono_core::c_header::framebuffer_to_c_header;
use mono_core::pixel::PixelDocument;
use mono_core::pyvalue::{py_int, py_str};
use mono_core::render::{member_path, posix};
use mono_core::runtime::VecRuntimeLog;
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
    export_scene_with_report, frame_for_state, matrix_report, preflight, validate_matrix,
    validate_scene, write_validation_report,
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
    AppModel, AssetItem, BlockedItem, DesignerModel, ElementItem, EventItem, FindingItem,
    GalleryItem, GalleryModel, MainWindow, NoteItem, NoteModel, OverlayBox, PillTone, PresetItem,
    ReviewElement, ReviewModel, RuleGroup, RuleText, RuleZone, ScreenItem, StateRelation, StateVar,
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
    /// A multi-screen project just opened: name its blockers once they are known.
    blocker_hint: bool,
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
    /// True only while a refresh that has just run `refresh_canvas` refreshes
    /// the Inspector, so the note rows reuse that frame instead of rendering
    /// the scene a second time (`refresh_inspector_after_canvas`).
    canvas_evidence_fresh: bool,
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
            last_resolved: Vec::new(),
            validation_epoch: 0,
            validation_rx: None,
            validation_dirty: false,
            blocker_hint: false,
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
            pending_permission: BridgePermission::default(),
            preview: Preview::default(),
            review: None,
            presets: Vec::new(),
            note_draft: None,
            frame_evidence: None,
            canvas_evidence_fresh: false,
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
        self.remember_project(&project.path);
        let _ = self.prefs.save();
        self.log_event(format!("OPEN_PROJECT {}", posix(&project.path)));
        // Font packs belong to a project; never carry one into another.
        self.font = None;
        self.reset_gallery_cache();
        self.project = Some(project);
        self.bind_scene(scene)?;
        self.review = self.load_review();
        self.contract = None;
        self.contract_path = None;
        self.discover_contract();
        self.scan_project_files();
        self.bench_load_active();
        self.reset_status();
        // Validation of the opened screen runs on the worker, so the hint waits
        // for its result (`apply_findings`) instead of reading empty findings.
        self.blocker_hint = self.project.as_ref().is_some_and(|p| p.screens().len() > 1);
        Ok(())
    }

    pub fn open_scene_file(&mut self, path: &Path) -> Result<(), CoreError> {
        let scene = load_scene(path, None)?;
        self.font = None;
        self.reset_gallery_cache();
        self.project = None;
        self.review = None;
        self.contract = None;
        self.contract_path = None;
        self.bind_scene(scene)?;
        self.scan_project_files();
        self.bench_load_active();
        self.reset_status();
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
        // Anything the worker is still validating belongs to the old scene.
        self.validation_epoch += 1;
        self.validation_rx = None;
        self.validation_dirty = false;
        self.blocker_hint = false;
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
        // Review renders the scene again, builds its code and diffs every
        // element; it is rebuilt here only while visible, and on entry
        // (`switch_workspace`).
        if self.workspace == REVIEW_WORKSPACE {
            self.refresh_review();
        }
        // The Inspector refreshes the notes too, reusing the canvas frame.
        self.refresh_inspector_after_canvas();
        self.refresh_presets();
        self.refresh_state_schema();
        self.refresh_design_rules();
        self.schedule_validation();
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
        let repo = env!("CARGO_PKG_REPOSITORY");
        app.set_repo_url(ss(repo));
        app.set_docs_url(ss(format!("{repo}/blob/main/docs/README.md")));
        let dm = DesignerModel::get(&ui);
        dm.set_log_lines(model(self.log.iter().rev().take(200).map(ss).collect()));
        self.refresh_agent_panel();
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

    /// The current frame for the Review panel, or the renderer's refusal
    /// (for example a member escaping the project root); `None` without a scene.
    fn review_render(&mut self) -> Option<Result<ReviewRender, String>> {
        self.session.as_mut().map(|session| match session.render() {
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
        })
    }

    /// Side-by-side baseline/current view for the Review workspace.
    pub fn refresh_review(&mut self) {
        let lang = self.lang.clone();
        let Some(ui) = self.ui.upgrade() else { return };
        let rm = ReviewModel::get(&ui);
        let blank = image_from_pixels(1, 1, &[0]);
        rm.set_mode(self.review_mode);
        let rendered = self.review_render();
        let Some(rendered) = rendered else {
            rm.set_baseline(blank.clone());
            rm.set_current(blank);
            rm.set_baseline_w(0);
            rm.set_baseline_h(0);
            rm.set_current_w(0);
            rm.set_current_h(0);
            rm.set_changed(0);
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
                rm.set_summary(ss(render_failed(&lang, &message)));
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
        let (added, removed, modified) = element_diff(&self.baseline_elements, current_elements);
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
                blocked: None,
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
        self.reset_gallery_cache();
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

    fn reset_gallery_cache(&mut self) {
        self.gallery_cards.clear();
        self.gallery_job = None;
        self.gallery_stamp = None;
    }

    fn ensure_gallery(&mut self) {
        let Some(project) = self.project.clone() else {
            self.reset_gallery_cache();
            return;
        };
        let stamp = self.gallery_stamp_value();
        if self.gallery_stamp == Some(stamp) {
            return;
        }
        self.gallery_cards.clear();
        self.gallery_stamp = Some(stamp);
        self.gallery_job = Some(GalleryJob::spawn(project, stamp));
    }

    pub fn gallery_tick(&mut self) {
        let Some(job) = &self.gallery_job else { return };
        let Some(result) = job.poll() else { return };
        let stamp = job.stamp();
        self.gallery_job = None;
        if Some(stamp) != self.gallery_stamp || stamp != self.gallery_stamp_value() {
            self.gallery_stamp = None;
            if self.gallery_visible {
                self.refresh_gallery();
            }
            return;
        }
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

    /// Identity of the saved gallery input: the project, its screen ids and each
    /// scene file's length and mtime. Unsaved editor edits do not change it,
    /// because the cards render the files on disk.
    fn gallery_stamp_value(&self) -> u64 {
        use std::hash::{Hash, Hasher};
        let mut hasher = std::collections::hash_map::DefaultHasher::new();
        if let Some(project) = &self.project {
            project.path.hash(&mut hasher);
            for screen in project.screens() {
                screen.id.hash(&mut hasher);
                if let Ok(path) = project.screen_path(&screen.id) {
                    file_stamp(&path).hash(&mut hasher);
                }
            }
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
        let counts = self
            .review
            .as_ref()
            .map(ReviewStore::counts_by_screen)
            .unwrap_or_default();
        crate::gallery::merge_note_counts(&mut self.gallery_cards, &counts);
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
                detail: ss(gallery_detail(&lang, card)),
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

    /// `refresh_inspector` right after `refresh_canvas` in the same call: the
    /// canvas just stored this frame's evidence, so the note rows reuse it.
    fn refresh_inspector_after_canvas(&mut self) {
        self.canvas_evidence_fresh = true;
        self.refresh_inspector();
        self.canvas_evidence_fresh = false;
    }

    pub fn refresh_inspector(&mut self) {
        self.refresh_notes();
        let Some(ui) = self.ui.upgrade() else { return };
        let dm = DesignerModel::get(&ui);
        let can_edit_asset = self.can_edit_asset();
        dm.set_can_edit_asset(can_edit_asset);
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
            self.findings.clear();
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
        let blockers = findings.iter().filter(|f| f.is_blocking()).count();
        self.findings = findings;
        if std::mem::take(&mut self.blocker_hint) && blockers > 0 {
            let message = trf(
                &self.lang,
                "status.scene_blockers",
                &[("count", blockers.to_string())],
            );
            self.set_status(message);
        }
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
            // The Review workspace's render, code and element diff.
            ("review", time(RUNS, || self.refresh_review())),
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
        self.refresh_inspector_after_canvas();
        self.refresh_state_schema();
        self.refresh_design_rules();
        self.schedule_validation();
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
        self.refresh_inspector_after_canvas();
        true
    }

    pub(crate) fn load_review(&mut self) -> Option<ReviewStore> {
        let root = self.project_root()?;
        match ReviewStore::for_root(&root) {
            Ok(store) => Some(store),
            Err(error) => {
                self.error(&error);
                None
            }
        }
    }

    pub(crate) fn active_screen_id(&self) -> String {
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
            && !(self.canvas_evidence_fresh && self.frame_evidence.is_some())
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
        self.refresh_inspector_after_canvas();
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
        self.refresh_inspector_after_canvas();
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
        self.refresh_inspector_after_canvas();
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
        if !crate::commands::is_known(action) {
            self.log_event(format!("UNKNOWN ACTION {action}"));
            return;
        }
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
        self.pending_contract = Some(output.join("ui_contract.json"));
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
                            // A refused export wrote no contract; never adopt a stale one.
                            self.pending_contract = None;
                            self.show_blocked(blocked);
                        } else if let Some(path) = self.pending_contract.take()
                            && self.adopt_contract(&path).is_ok()
                        {
                            // Review may already be open; re-evaluate its badge.
                            self.refresh_review();
                        }
                        if refresh {
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

/// Cheap file identity: length plus modification time, zero when unreadable.
fn file_stamp(path: &Path) -> (u64, u128) {
    let Ok(meta) = std::fs::metadata(path) else {
        return (0, 0);
    };
    let modified = meta
        .modified()
        .ok()
        .and_then(|time| time.duration_since(std::time::UNIX_EPOCH).ok())
        .map(|delta| delta.as_nanos())
        .unwrap_or(0);
    (meta.len(), modified)
}

fn evidence_text(lang: &str, evidence: &Evidence) -> String {
    let hash: String = evidence.sha256.chars().take(12).collect();
    trf(
        lang,
        "notes.evidence",
        &[("hash", hash), ("lit", evidence.lit_pixels.to_string())],
    )
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

/// `AppModel.workspace` index of the Review workspace.
pub const REVIEW_WORKSPACE: i32 = 3;

/// Review's element lists against the baseline: added and modified in scene
/// order, removed in baseline order, each labelled `id · type`. Ids are
/// indexed once, so a large scene costs O(n) instead of a scan per element.
fn element_diff(before: &[Value], after: &[Value]) -> (Vec<String>, Vec<String>, Vec<String>) {
    let id_of = |e: &Value| e.get("id").map(py_str).unwrap_or_default();
    let label = |id: &str, e: &Value| {
        let kind = e.get("type").map(py_str).unwrap_or_default();
        if kind.is_empty() {
            id.to_string()
        } else {
            format!("{id} · {kind}")
        }
    };
    let after_ids: Vec<String> = after.iter().map(id_of).collect();
    let mut before_by_id: HashMap<String, Vec<&Value>> = HashMap::new();
    let before_ids: Vec<String> = before
        .iter()
        .map(|b| {
            let id = id_of(b);
            before_by_id.entry(id.clone()).or_default().push(b);
            id
        })
        .collect();
    let after_set: HashSet<&str> = after_ids.iter().map(String::as_str).collect();
    let mut added = Vec::new();
    let mut modified = Vec::new();
    for (id, e) in after_ids.iter().zip(after) {
        match before_by_id.get(id) {
            None => added.push(label(id, e)),
            Some(olds) if olds.iter().any(|b| *b != e) => modified.push(label(id, e)),
            Some(_) => {}
        }
    }
    let removed = before_ids
        .iter()
        .zip(before)
        .filter(|(id, _)| !after_set.contains(id.as_str()))
        .map(|(id, b)| label(id, b))
        .collect();
    (added, removed, modified)
}

/// "Render failed: <reason>", as the status bar, the Review panel and the
/// gallery card word a refused render.
fn render_failed(lang: &str, message: &str) -> String {
    format!("{}: {}", tr(lang, "status.render_failed"), message)
}

/// The gallery card's detail line: counts first, then why its frame is missing.
fn gallery_detail(lang: &str, card: &GalleryCard) -> String {
    let counts = trf(
        lang,
        "gallery.card",
        &[
            ("id", card.id.clone()),
            ("blockers", card.blockers.to_string()),
            ("warnings", card.warnings.to_string()),
            ("notes", card.annotations.to_string()),
        ],
    );
    match &card.render_error {
        Some(message) => format!("{counts} · {}", render_failed(lang, message)),
        None => counts,
    }
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
        app.flush_validation();
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

    /// The indexed diff must list exactly what the pairwise definition 2.3.0
    /// shipped listed, in the same order, duplicate ids included.
    #[test]
    fn review_element_diff_matches_the_pairwise_definition() {
        fn pairwise(before: &[Value], after: &[Value]) -> (Vec<String>, Vec<String>, Vec<String>) {
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
            let before_ids: Vec<String> = before.iter().map(id_of).collect();
            let after_ids: Vec<String> = after.iter().map(id_of).collect();
            (
                after
                    .iter()
                    .filter(|e| !before_ids.contains(&id_of(e)))
                    .map(label)
                    .collect(),
                before
                    .iter()
                    .filter(|e| !after_ids.contains(&id_of(e)))
                    .map(label)
                    .collect(),
                after
                    .iter()
                    .filter(|e| before.iter().any(|b| id_of(b) == id_of(e) && b != *e))
                    .map(label)
                    .collect(),
            )
        }
        let before = vec![
            json!({"id": "a", "type": "text", "x": 0}),
            json!({"id": "b", "type": "image", "x": 1}),
            json!({"id": "dup", "type": "text", "x": 2}),
            json!({"id": "dup", "type": "text", "x": 3}),
            json!({"id": "gone", "x": 4}),
            json!({"type": "placeholder"}),
        ];
        let after = vec![
            json!({"id": "new", "type": "digits"}),
            json!({"id": "b", "type": "image", "x": 9}),
            json!({"id": "a", "type": "text", "x": 0}),
            json!({"id": "dup", "type": "text", "x": 2}),
            json!({"type": "placeholder", "w": 1}),
            json!({"id": "new2"}),
        ];
        let got = element_diff(&before, &after);
        assert_eq!(got, pairwise(&before, &after));
        assert_eq!(got.0, ["new · digits", "new2"]);
        assert_eq!(got.1, ["gone"]);
        assert_eq!(got.2, ["b · image", "dup · text", " · placeholder"]);
    }

    /// A project at `<base>/project` whose main scene, on disk, holds an image
    /// member `../outside.png`. The file exists at `<base>/outside.png` and is a
    /// decodable image larger than the declared 1x1, so reading it would add an
    /// `ASSET_SIZE_MISMATCH` finding; its absence proves it was never opened.
    fn escape_app(name: &str) -> (App, PathBuf) {
        let base = std::env::temp_dir().join(format!("mono-escape-{name}-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&base);
        let repo = Path::new(env!("CARGO_MANIFEST_DIR")).join("../..");
        let root = base.join("project");
        copy_dir(&repo.join("test_assets/projects/curing_lite"), &root);
        std::fs::copy(
            root.join("assets/clinical_ui/running.png"),
            base.join("outside.png"),
        )
        .unwrap();
        let scene_path = root.join("scenes/main_scene.json");
        let mut scene: Value =
            serde_json::from_str(&std::fs::read_to_string(&scene_path).unwrap()).unwrap();
        scene["elements"].as_array_mut().unwrap().push(json!({
            "id": "outside_icon", "type": "image", "asset": "../outside.png",
            "x": 0, "y": 0, "w": 1, "h": 1
        }));
        std::fs::write(&scene_path, scene.to_string()).unwrap();
        let root = mono_project::project::py_resolve(&root);
        let prefs = Preferences::load_from(base.join("prefs.json"));
        let mut app = App::new(slint::Weak::default(), prefs);
        app.open_project(&root.join("project.oled.json")).unwrap();
        app.open_screen("main").unwrap();
        (app, base)
    }

    fn assert_outside_unread(app: &App) {
        let project = app.project.as_ref().unwrap();
        let scene = app.session.as_ref().unwrap().scene();
        let findings = mono_project::export::validate_scene(
            scene,
            &project.root,
            None,
            &mut DiskResources::new(),
        );
        assert!(
            findings
                .iter()
                .any(|f| f.code == "ASSET_PATH_ESCAPE" && f.is_blocking()),
            "{findings:?}"
        );
        assert!(
            !findings.iter().any(|f| f.code == "ASSET_SIZE_MISMATCH"),
            "the outside file was opened: {findings:?}"
        );
    }

    #[test]
    fn gallery_card_reports_an_escaping_member_without_reading_it() {
        let (mut app, base) = escape_app("gallery");
        assert_outside_unread(&app);
        app.ensure_gallery();
        for _ in 0..600 {
            std::thread::sleep(std::time::Duration::from_millis(5));
            app.gallery_tick();
            if app.gallery_job.is_none() {
                break;
            }
        }
        assert!(app.gallery_job.is_none(), "worker did not finish");
        let card = app
            .gallery_cards
            .iter()
            .find(|card| card.id == "main")
            .unwrap();
        assert!(card.image.is_none(), "a refused frame must not be drawn");
        assert!(card.blockers > 0);
        let detail = gallery_detail("en_US", card);
        assert!(
            detail.contains(&tr("en_US", "status.render_failed"))
                && detail.contains("escapes project root"),
            "the card must say why it has no frame: {detail}"
        );
        let _ = std::fs::remove_dir_all(&base);
    }

    #[test]
    fn review_panel_reports_an_escaping_member_without_reading_it() {
        let (mut app, base) = escape_app("review");
        assert_outside_unread(&app);
        let message = match app.review_render() {
            Some(Err(message)) => message,
            Some(Ok(_)) => panic!("the Review render must refuse an escaping member"),
            None => panic!("no session"),
        };
        assert!(message.contains("escapes project root"), "{message}");
        let summary = render_failed("en_US", &message);
        assert!(summary.starts_with(&tr("en_US", "status.render_failed")));
        // The evidence panel shows no hash and no code for a refused frame.
        let view = app.evidence_view(None);
        assert!(view.frame_sha.is_empty());
        assert!(view.code_c.is_empty() && view.code_hex.is_empty());
        assert_ne!(view.status, "golden-match");
        let _ = std::fs::remove_dir_all(&base);
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
        assert!(!app.session.as_ref().unwrap().is_dirty());
        app.action("toggle-play");
        let now = std::time::Instant::now();
        app.preview.last_step = Some(now);
        assert!(app.preview_tick(now + interval));
        assert!(!app.session.as_ref().unwrap().is_dirty());
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
    fn renaming_a_screen_moves_its_notes() {
        let (mut app, root) = project_app("note-rename");
        app.begin_note().unwrap();
        app.save_note("Battery clips", "at minimum", 0).unwrap();
        app.rename_active_screen("renamed").unwrap();
        let store = ReviewStore::for_root(&root).unwrap();
        assert_eq!(store.annotations_for("renamed").len(), 1);
        assert!(store.annotations_for("main").is_empty());
        assert_eq!(
            app.review
                .as_ref()
                .unwrap()
                .annotations_for("renamed")
                .len(),
            1
        );
        let _ = std::fs::remove_dir_all(&root);
    }

    /// A bridged rename while the note dialog is open: the store is reloaded
    /// from disk and the draft follows the page instead of saving under the
    /// old id.
    #[test]
    fn an_open_note_follows_a_bridged_rename() {
        let (mut app, root) = project_app("note-bridged-rename");
        app.begin_note().unwrap();
        let before = app.screen_ids_for_test();
        let project = app.project.as_mut().unwrap();
        project.rename_screen("main", "renamed", None).unwrap();
        app.reload_review_after_structure_change(&before);
        assert_eq!(app.note_draft.as_ref().unwrap().screen, "renamed");
        app.save_note("Battery clips", "", 0).unwrap();
        let store = ReviewStore::for_root(&root).unwrap();
        assert_eq!(store.annotations_for("renamed").len(), 1);
        assert!(store.annotations_for("main").is_empty());
        let _ = std::fs::remove_dir_all(&root);
    }

    #[test]
    fn an_open_note_for_a_vanished_page_is_closed_not_saved() {
        let (mut app, root) = project_app("note-bridged-delete");
        app.begin_note().unwrap();
        app.note_draft.as_mut().unwrap().screen = "gone".into();
        let before = app.screen_ids_for_test();
        app.reload_review_after_structure_change(&before);
        assert!(app.note_draft.is_none());
        let _ = std::fs::remove_dir_all(&root);
    }

    #[test]
    fn a_refused_rename_keeps_the_page_open() {
        let (mut app, root) = project_app("rename-refused");
        let main = app.project.as_ref().unwrap().screen_path("main").unwrap();
        // An id `validate_screen_id` refuses, then an id another page already has.
        for refused in ["bad id/..", "123"] {
            assert!(app.rename_active_screen(refused).is_err(), "{refused}");
            assert!(
                app.session.is_some(),
                "{refused}: the Designer keeps a scene"
            );
            let session = app.session.as_ref().unwrap();
            assert_eq!(session.doc.path, main, "{refused}");
            assert!(!session.is_dirty(), "{refused}");
        }
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

    /// Note rows render the frame themselves unless the canvas stored it in the
    /// same refresh; then they reuse it instead of rendering the scene again.
    #[test]
    fn note_rows_reuse_the_canvas_frame_only_right_after_it() {
        let (mut app, root) = project_app("note-reuse");
        let sentinel = Evidence {
            sha256: "canvas".into(),
            ..Evidence::default()
        };
        app.frame_evidence = Some(sentinel.clone());
        app.canvas_evidence_fresh = true;
        app.note_rows();
        assert_eq!(app.frame_evidence.as_ref().unwrap().sha256, "canvas");
        app.canvas_evidence_fresh = false;
        app.note_rows();
        assert_eq!(app.frame_evidence.as_ref().unwrap().sha256.len(), 64);
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
    fn gallery_stamp_follows_the_scene_files_not_unsaved_edits() {
        let (mut app, root) = project_app("gallery-cache");
        app.gallery_stamp = Some(app.gallery_stamp_value());
        let before = app.gallery_stamp;
        // Cards render the files on disk, so unsaved edits keep the cache.
        if let Some(session) = app.session.as_mut() {
            let elements = session.doc.data["elements"].as_array_mut().unwrap();
            let element = elements[0].as_object_mut().unwrap();
            let x = element.get("x").and_then(Value::as_i64).unwrap_or(0);
            element.insert("x".into(), json!(x + 1));
        }
        app.refresh_gallery();
        assert_eq!(app.gallery_stamp, before);
        assert!(app.gallery_job.is_none());
        // A scene file change invalidates the cache.
        let scene_path = root.join("scenes/main_scene.json");
        let text = std::fs::read_to_string(&scene_path).unwrap();
        std::fs::write(&scene_path, format!("{text}\n")).unwrap();
        app.refresh_gallery();
        assert_ne!(app.gallery_stamp, before);
        assert!(app.gallery_job.is_some());
        app.gallery_job = None;
        let _ = std::fs::remove_dir_all(&root);
    }

    #[test]
    fn opening_a_project_drops_cached_gallery_state() {
        let (mut app, root) = project_app("gallery-switch");
        app.gallery_stamp = Some(7);
        app.gallery_cards = vec![crate::gallery::GalleryCard {
            id: "stale".into(),
            label: "Stale".into(),
            category: "Screens".into(),
            blockers: 0,
            warnings: 0,
            annotations: 0,
            image: None,
            render_error: None,
        }];
        let other = root
            .parent()
            .unwrap()
            .join(format!("mono-gallery-switch-other-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&other);
        app.new_project(&other, "Other", (128, 64)).unwrap();
        assert!(app.gallery_cards.is_empty());
        assert!(app.gallery_job.is_none());
        assert_eq!(app.gallery_stamp, None);
        let _ = std::fs::remove_dir_all(&other);
        let _ = std::fs::remove_dir_all(&root);
    }

    #[test]
    fn reopening_gallery_rebuilds_saved_resources() {
        let (mut app, root) = project_app("gallery-resource-refresh");
        app.gallery_stamp = Some(app.gallery_stamp_value());
        app.open_gallery();
        assert!(app.gallery_job.is_some());
        app.gallery_job = None;
        let _ = std::fs::remove_dir_all(&root);
    }

    #[test]
    fn inflight_gallery_refresh_uses_current_disk_stamp() {
        let (mut app, root) = project_app("gallery-inflight-refresh");
        app.ensure_gallery();
        let path = root.join("scenes/main_scene.json");
        let text = std::fs::read_to_string(&path).unwrap();
        std::fs::write(path, format!("{text}\n")).unwrap();
        app.ensure_gallery();
        assert_eq!(
            app.gallery_job.as_ref().unwrap().stamp(),
            app.gallery_stamp_value()
        );
        app.gallery_job = None;
        let _ = std::fs::remove_dir_all(&root);
    }

    #[test]
    fn results_from_a_stale_gallery_job_are_dropped() {
        let (mut app, root) = project_app("gallery-stale");
        let project = app.project.clone().unwrap();
        app.gallery_stamp = Some(1);
        app.gallery_job = Some(crate::gallery::GalleryJob::spawn(project, 2));
        for _ in 0..300 {
            std::thread::sleep(std::time::Duration::from_millis(5));
            app.gallery_tick();
            if app.gallery_job.is_none() {
                break;
            }
        }
        assert!(app.gallery_job.is_none(), "worker did not finish");
        assert!(app.gallery_cards.is_empty());
        let _ = std::fs::remove_dir_all(&root);
    }

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
