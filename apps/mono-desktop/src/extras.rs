//! Designer workflow extras (V1 `gui_resource_mixin` / tools menu): templates,
//! asset import/convert/health, bitmap text, thumbnail wall, autosave and
//! recovery, the command palette and the interaction profiler.

use std::collections::BTreeSet;
use std::path::{Path, PathBuf};
use std::time::Instant;

use mono_core::CoreError;
use mono_core::render::posix;
use mono_core::state::{IntegerPolicy, build_export_states};
use mono_project::asset_ops::{convert_bitmap, import_asset};
use mono_project::autosave::AutoSaveManager;
use mono_project::export::{asset_health, build_thumbnail_wall, export_scene};
use mono_project::fontpack_io::load_font_pack;
use mono_project::scene_io::SceneDoc;
use mono_project::templates::TemplateLibrary;
use serde_json::{Value, json};
use slint::Global;

use crate::app::{App, Prompt, model, ss};
use crate::bgjob::Outcome;
use crate::i18n::trf;
use crate::{AppModel, Shell};

/// What the shared picker dialog is choosing.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum Picker {
    Command,
    Template,
}

/// V1 command palette entries: (command key, i18n label key, action id).
pub const PALETTE: [(&str, &str, &str); 16] = [
    ("save", "action.save", "save"),
    ("validate", "action.batch_validate", "batch-validate"),
    ("handoff", "action.handoff", "handoff"),
    ("undo", "action.undo", "undo"),
    ("redo", "action.redo", "redo"),
    ("assets", "action.asset_health", "asset-health"),
    ("template_save", "action.save_template", "save-template"),
    (
        "template_insert",
        "action.insert_template",
        "insert-template",
    ),
    ("convert", "action.convert_asset", "convert-asset"),
    ("c_header", "action.export_c_header", "export-c-header"),
    ("overview", "action.thumbnail_wall", "thumbnail-wall"),
    ("diagnostics", "action.diagnostics", "diagnostics"),
    ("design_mode", "workspace.design", "workspace:0"),
    ("review_mode", "workspace.review", "workspace:3"),
    ("performance", "performance.title", "performance"),
    // 2.x: delivery jobs run in the background and can be cancelled.
    ("cancel_job", "action.cancel_job", "cancel-job"),
];

/// Rolling timing samples (V1 `PerformanceProfiler(max_samples=180)`).
#[derive(Default)]
pub struct Profiler {
    pub drag: Vec<f64>,
    pub full: Vec<f64>,
}

impl Profiler {
    pub fn record(samples: &mut Vec<f64>, started: Instant) {
        samples.push(started.elapsed().as_secs_f64() * 1000.0);
        if samples.len() > 180 {
            samples.remove(0);
        }
    }

    pub fn summary(samples: &[f64]) -> (f64, f64) {
        if samples.is_empty() {
            return (0.0, 0.0);
        }
        let avg = samples.iter().sum::<f64>() / samples.len() as f64;
        let max = samples.iter().copied().fold(0.0, f64::max);
        (avg, max)
    }
}

fn message(title: &str, text: &str) {
    rfd::MessageDialog::new()
        .set_title(title)
        .set_description(text)
        .set_buttons(rfd::MessageButtons::Ok)
        .show();
}

fn confirm(title: &str, text: &str) -> bool {
    rfd::MessageDialog::new()
        .set_title(title)
        .set_description(text)
        .set_buttons(rfd::MessageButtons::YesNo)
        .show()
        == rfd::MessageDialogResult::Yes
}

impl App {
    fn scene_root(&self) -> Option<PathBuf> {
        self.session.as_ref().map(|s| s.root().to_path_buf())
    }

    fn autosave_manager(&self) -> Option<AutoSaveManager> {
        let session = self.session.as_ref()?;
        let keep = usize::try_from(self.prefs.int("autosave.snapshots")).unwrap_or(10);
        Some(AutoSaveManager::new(
            &session.doc.path,
            session.root(),
            keep,
        ))
    }

    /// Extras dispatched from menus, the palette and shortcuts. Returns false
    /// when `action` is not an extra.
    pub fn extra_action(&mut self, action: &str) -> bool {
        let result: Result<(), CoreError> = match action {
            "save-template" => self.begin_save_template(),
            "insert-template" => self.begin_insert_template(),
            "convert-asset" => self.convert_asset(),
            "import-asset" => self.import_asset_dialog(),
            "asset-health" => self.show_asset_health(),
            "thumbnail-wall" => self.thumbnail_wall(),
            "cancel-job" => {
                self.cancel_background();
                Ok(())
            }
            "bitmap-text" => self.begin_bitmap_text(),
            "autosave" => self.autosave_tick(true).map(|_| ()),
            "restore-autosave" => self.restore_autosave(),
            "command-palette" => {
                self.open_picker(Picker::Command);
                Ok(())
            }
            "performance" => {
                self.show_performance();
                Ok(())
            }
            "diagnostics" | "toggle-navigator" | "toggle-inspector" | "reset-workspace" => {
                self.toggle_panel(action);
                Ok(())
            }
            _ => return false,
        };
        if let Err(e) = result {
            self.error(&e);
            message(&self.t("dialog.error"), &e.message);
        }
        self.refresh_all();
        true
    }

    fn toggle_panel(&mut self, action: &str) {
        let Some(ui) = self.ui.upgrade() else { return };
        let shell = Shell::get(&ui);
        match action {
            "diagnostics" => shell.set_hide_drawer(!shell.get_hide_drawer()),
            "toggle-navigator" => shell.set_hide_navigator(!shell.get_hide_navigator()),
            "toggle-inspector" => shell.set_hide_inspector(!shell.get_hide_inspector()),
            _ => {
                shell.set_hide_drawer(false);
                shell.set_hide_navigator(false);
                shell.set_hide_inspector(false);
                shell.set_canvas_only(false);
            }
        }
    }

    // ------------------------------------------------------------ templates

    fn begin_save_template(&mut self) -> Result<(), CoreError> {
        if self.selection.ids().is_empty() {
            return Ok(());
        }
        let (title, label) = (self.t("action.save_template"), self.t("template.name"));
        self.show_prompt(Prompt::TemplateName, &title, &label, "");
        Ok(())
    }

    pub fn save_template(&mut self, name: &str) -> Result<(), CoreError> {
        let name = name.trim();
        if name.is_empty() {
            return Ok(());
        }
        let (Some(root), Some(session)) = (self.scene_root(), self.session.as_ref()) else {
            return Ok(());
        };
        let elements = self
            .selection
            .ids()
            .iter()
            .map(|id| session.element(id).map(Value::Object))
            .collect::<Result<Vec<_>, _>>()?;
        TemplateLibrary::for_root(&root).save_template(name, &elements)?;
        self.set_status(trf(
            &self.lang,
            "template.saved",
            &[("name", name.to_string())],
        ));
        Ok(())
    }

    fn begin_insert_template(&mut self) -> Result<(), CoreError> {
        let Some(root) = self.scene_root() else {
            return Ok(());
        };
        if TemplateLibrary::for_root(&root).names().is_empty() {
            return Err(CoreError::invalid(self.t("template.none")));
        }
        self.open_picker(Picker::Template);
        Ok(())
    }

    pub fn insert_template(&mut self, name: &str, prefix: &str) -> Result<(), CoreError> {
        let Some(root) = self.scene_root() else {
            return Ok(());
        };
        let items = TemplateLibrary::for_root(&root).instantiate(name, prefix, (0, 0))?;
        if let Some(session) = self.session.as_mut() {
            let ids = session.add_elements(items, "template_insert")?;
            let primary = ids.last().cloned();
            self.selection.replace(&ids, primary.as_deref());
        }
        Ok(())
    }

    // --------------------------------------------------------------- assets

    fn import_asset_dialog(&mut self) -> Result<(), CoreError> {
        let Some(root) = self.project_root() else {
            return Ok(());
        };
        let Some(source) = rfd::FileDialog::new()
            .set_title(self.t("asset.import"))
            .add_filter("Bitmap", &["png", "bmp"])
            .pick_file()
        else {
            return Ok(());
        };
        import_asset(&root, &source)?;
        self.scan_project_files();
        self.set_status(self.t("status.asset_imported"));
        Ok(())
    }

    /// V1 `_resource_place_asset`: bind to a selected placeholder, else add a
    /// new element named after the file stem.
    pub fn place_asset(&mut self, rel: &str) -> Result<(), CoreError> {
        let Some(root) = self.scene_root() else {
            return Ok(());
        };
        let path = root.join(rel);
        let Some(session) = self.session.as_mut() else {
            return Ok(());
        };
        if let Some(id) = self.selection.primary().map(str::to_string) {
            let is_placeholder = session
                .element(&id)
                .is_ok_and(|e| e.get("type").and_then(Value::as_str) == Some("placeholder"));
            if is_placeholder {
                return session.assign_bitmap(&id, &path);
            }
        }
        let stem = Path::new(rel)
            .file_stem()
            .map(|s| s.to_string_lossy().into_owned())
            .unwrap_or_else(|| "image".into());
        let existing = session.element_ids();
        let mut id = stem.clone();
        let mut i = 2;
        while existing.contains(&id) {
            id = format!("{stem}_{i}");
            i += 1;
        }
        session.add_placeholder(&id, 0, 0, 1, 1, None)?;
        session.assign_bitmap(&id, &path)?;
        self.selection.replace(std::slice::from_ref(&id), Some(&id));
        Ok(())
    }

    fn convert_asset(&mut self) -> Result<(), CoreError> {
        let Some(root) = self.scene_root() else {
            return Ok(());
        };
        let Some(source) = rfd::FileDialog::new()
            .set_title(self.t("action.convert_asset"))
            .set_directory(&root)
            .add_filter("Bitmap", &["png", "bmp"])
            .pick_file()
        else {
            return Ok(());
        };
        let stem = source
            .file_stem()
            .map(|s| s.to_string_lossy().into_owned())
            .unwrap_or_default();
        let target = root
            .join("assets")
            .join("converted")
            .join(format!("{stem}.png"));
        convert_bitmap(&source, &target)?;
        if let Some(project) = self.project.as_mut() {
            project.add_asset_dir("assets")?;
        }
        self.scan_project_files();
        self.set_status(trf(
            &self.lang,
            "asset.converted",
            &[("path", posix(&target))],
        ));
        Ok(())
    }

    fn show_asset_health(&mut self) -> Result<(), CoreError> {
        let Some(root) = self.scene_root() else {
            return Ok(());
        };
        let mut used = BTreeSet::new();
        if let Some(session) = self.session.as_mut() {
            if let Ok(render) = session.render() {
                for file in render.used_files {
                    if let Ok(rel) = file.strip_prefix(&root) {
                        used.insert(posix(rel));
                    }
                }
            }
        }
        let dirs = self
            .project
            .as_ref()
            .map(mono_project::project::ProjectWorkspace::asset_dirs)
            .unwrap_or_else(|| vec!["assets".into()]);
        let health = asset_health(&root, &dirs, &used)?;
        let text = trf(
            &self.lang,
            "asset.health_summary",
            &[
                ("count", self.assets.len().to_string()),
                ("duplicates", health.duplicates.len().to_string()),
                ("unused", health.unused.len().to_string()),
                ("invalid", health.invalid.len().to_string()),
            ],
        );
        message(&self.t("action.asset_health"), &text);
        Ok(())
    }

    fn thumbnail_wall(&mut self) -> Result<(), CoreError> {
        let (Some(root), Some(session)) = (self.scene_root(), self.session.as_ref()) else {
            return Ok(());
        };
        let scene = session.scene().clone();
        let Some(path) = rfd::FileDialog::new()
            .set_title(self.t("action.thumbnail_wall"))
            .set_directory(root.join("exports"))
            .set_file_name("screen_overview.png")
            .add_filter("PNG", &["png"])
            .save_file()
        else {
            return Ok(());
        };
        let states = build_export_states(&scene, IntegerPolicy::Representative, 5000, false)?;
        let work = std::env::temp_dir().join(format!(
            "oled_wall_{}_{}",
            std::process::id(),
            Instant::now().elapsed().as_nanos()
        ));
        let lang = self.lang.clone();
        self.start_background("action.thumbnail_wall", move |progress| {
            let result = (|| {
                export_scene(&scene, &root, &work, &states, progress)?;
                let reference = work.join("reference");
                let mut refs: Vec<PathBuf> = states
                    .iter()
                    .map(|(name, _)| reference.join(format!("{name}.png")))
                    .filter(|p| p.is_file())
                    .collect();
                if refs.is_empty() {
                    if let Ok(entries) = std::fs::read_dir(&reference) {
                        refs = entries.flatten().map(|e| e.path()).collect();
                        refs.sort();
                    }
                }
                let columns = refs.len().clamp(1, 4);
                build_thumbnail_wall(&refs, &path, columns, 4)
            })();
            let _ = std::fs::remove_dir_all(&work);
            result?;
            Ok(Outcome {
                status: trf(
                    &lang,
                    "status.exported",
                    &[("count", states.len().to_string()), ("path", posix(&path))],
                ),
                ..Outcome::default()
            })
        })
    }

    // ----------------------------------------------------------- bitmap text

    fn begin_bitmap_text(&mut self) -> Result<(), CoreError> {
        let Some(root) = self.scene_root() else {
            return Ok(());
        };
        let fonts = root.join(".oled").join("fonts");
        let _ = std::fs::create_dir_all(&fonts);
        let Some(dir) = rfd::FileDialog::new()
            .set_title(self.t("font.select_title"))
            .set_directory(&fonts)
            .pick_folder()
        else {
            return Ok(());
        };
        load_font_pack(&dir)?;
        let (title, label) = (self.t("bitmap.text_title"), self.t("bitmap.text"));
        self.show_prompt(Prompt::BitmapText(dir), &title, &label, "TEXT");
        Ok(())
    }

    /// Second step: check glyph coverage, then ask for the element id.
    pub fn bitmap_text_entered(&mut self, pack_dir: PathBuf, text: &str) -> Result<(), CoreError> {
        if text.is_empty() {
            return Ok(());
        }
        let pack = load_font_pack(&pack_dir)?;
        let missing: Vec<String> = text
            .chars()
            .filter(|c| pack.glyph(*c).is_none())
            .map(|c| format!("'{c}'"))
            .collect();
        if !missing.is_empty() {
            return Err(CoreError::invalid(trf(
                &self.lang,
                "font.missing_glyphs",
                &[("glyphs", format!("[{}]", missing.join(", ")))],
            )));
        }
        let (title, label) = (self.t("bitmap.text_title"), self.t("bitmap.element_id"));
        self.show_prompt(
            Prompt::BitmapTextId(pack_dir, text.to_string()),
            &title,
            &label,
            "bitmap_text_1",
        );
        Ok(())
    }

    pub fn insert_bitmap_text(
        &mut self,
        pack_dir: &Path,
        text: &str,
        id: &str,
    ) -> Result<(), CoreError> {
        if id.is_empty() {
            return Ok(());
        }
        let Some(root) = self.scene_root() else {
            return Ok(());
        };
        let resolved = std::fs::canonicalize(pack_dir).unwrap_or_else(|_| pack_dir.to_path_buf());
        let root_resolved = std::fs::canonicalize(&root).unwrap_or(root);
        let rel = resolved
            .strip_prefix(&root_resolved)
            .map(posix)
            .map_err(|_| CoreError::invalid(self.t("font.inside_project")))?;
        if let Some(session) = self.session.as_mut() {
            let element = json!({"id": id, "type": "bitmap_text", "text": text, "font_pack": rel, "x": 0, "y": 0});
            let ids = session.add_elements(vec![element], "bitmap_text_insert")?;
            self.selection.replace(&ids, Some(id));
        }
        self.scan_project_files();
        Ok(())
    }

    // -------------------------------------------------------------- autosave

    /// V1 `_autosave_tick`: snapshot when dirty (or forced).
    pub fn autosave_tick(&mut self, force: bool) -> Result<Option<PathBuf>, CoreError> {
        let dirty = self.session.as_ref().is_some_and(|s| s.dirty);
        if !(force || dirty) {
            return Ok(None);
        }
        let (Some(manager), Some(session)) = (self.autosave_manager(), self.session.as_ref())
        else {
            return Ok(None);
        };
        match manager.snapshot(session.scene(), if force { "manual" } else { "timer" }) {
            Ok(path) => {
                self.log_event(format!("AUTOSAVE {}", posix(&path)));
                self.set_status(self.t("status.autosaved"));
                Ok(Some(path))
            }
            Err(e) => {
                self.log_event(format!("AUTOSAVE_FAIL {}", e.message));
                self.set_status(self.t("status.autosave_failed"));
                Ok(None)
            }
        }
    }

    /// Timer entry: honours `autosave.enabled` and `autosave.interval_minutes`.
    pub fn autosave_due(&mut self) {
        if !self.prefs.bool("autosave.enabled") {
            return;
        }
        let interval = self.prefs.int("autosave.interval_minutes").max(1) as u64 * 60;
        if self.last_autosave.elapsed().as_secs() >= interval {
            self.last_autosave = Instant::now();
            let _ = self.autosave_tick(false);
        }
    }

    fn apply_recovery(&mut self, candidate: &Path) -> Result<(), CoreError> {
        let payload = AutoSaveManager::load_snapshot(candidate)?;
        let Some(session) = self.session.as_ref() else {
            return Ok(());
        };
        let mut data = payload;
        for (key, value) in session.scene() {
            if key.starts_with('_') {
                data.insert(key.clone(), value.clone());
            }
        }
        let doc = SceneDoc {
            data,
            path: session.doc.path.clone(),
            root: session.doc.root.clone(),
            disk_sha256: session.doc.disk_sha256.clone(),
        };
        self.bind_scene(doc)?;
        if let Some(session) = self.session.as_mut() {
            session.dirty = true;
        }
        self.log_event(format!("AUTOSAVE_RESTORE {}", posix(candidate)));
        Ok(())
    }

    fn restore_autosave(&mut self) -> Result<(), CoreError> {
        let Some(manager) = self.autosave_manager() else {
            return Ok(());
        };
        let Some(candidate) = manager.latest_recovery() else {
            return Err(CoreError::invalid(self.t("autosave.none")));
        };
        if self.session.as_ref().is_some_and(|s| s.dirty)
            && !confirm(
                &self.t("dialog.unsaved_title"),
                &self.t("dialog.unsaved_message"),
            )
        {
            return Ok(());
        }
        self.apply_recovery(&candidate)
    }

    /// V1 `_prompt_recovery_if_needed` (after a scene is opened).
    pub fn prompt_recovery(&mut self) {
        if !self.interactive || !self.prefs.bool("autosave.prompt_recovery") {
            return;
        }
        let Some(candidate) = self.autosave_manager().and_then(|m| m.recovery_candidate()) else {
            return;
        };
        let text = format!(
            "{}\n\n{}",
            self.t("autosave.recovery_message"),
            posix(&candidate)
        );
        if confirm(&self.t("autosave.recovery_title"), &text) {
            if let Err(e) = self.apply_recovery(&candidate) {
                self.error(&e);
            }
            self.refresh_all();
        }
    }

    // --------------------------------------------------------------- picker

    pub fn open_picker(&mut self, picker: Picker) {
        self.picker = Some(picker);
        let Some(ui) = self.ui.upgrade() else { return };
        let am = AppModel::get(&ui);
        let title = match self.picker {
            Some(Picker::Template) => self.t("action.insert_template"),
            _ => self.t("command.title"),
        };
        am.set_picker_title(ss(title));
        am.set_picker_filter(ss(""));
        am.set_picker_visible(true);
        self.refresh_picker("");
    }

    fn picker_entries(&self) -> Vec<(String, String)> {
        match self.picker {
            Some(Picker::Template) => self
                .scene_root()
                .map(|r| TemplateLibrary::for_root(&r).names())
                .unwrap_or_default()
                .into_iter()
                .map(|n| (n.clone(), n))
                .collect(),
            _ => PALETTE
                .iter()
                .map(|(key, label, action)| {
                    (format!("{key} {}", self.t(label)), (*action).to_string())
                })
                .collect(),
        }
    }

    pub fn refresh_picker(&mut self, filter: &str) {
        let needle = filter.trim().to_lowercase();
        self.picker_matches = self
            .picker_entries()
            .into_iter()
            .filter(|(search, _)| needle.is_empty() || search.to_lowercase().contains(&needle))
            .collect();
        let labels: Vec<_> = self
            .picker_matches
            .iter()
            .map(|(search, value)| {
                let label = match self.picker {
                    Some(Picker::Command) => PALETTE
                        .iter()
                        .find(|(_, _, a)| a == value)
                        .map_or_else(|| search.clone(), |(_, l, _)| self.t(l)),
                    _ => value.clone(),
                };
                ss(label)
            })
            .collect();
        if let Some(ui) = self.ui.upgrade() {
            AppModel::get(&ui).set_picker_items(model(labels));
        }
    }

    /// Returns the action to run (palette) after closing the picker.
    pub fn picker_chosen(&mut self, index: i32) -> Option<String> {
        let chosen = usize::try_from(index)
            .ok()
            .and_then(|i| self.picker_matches.get(i))
            .map(|(_, v)| v.clone());
        if let Some(ui) = self.ui.upgrade() {
            AppModel::get(&ui).set_picker_visible(false);
        }
        let picker = self.picker.take();
        match (picker, chosen) {
            (Some(Picker::Template), Some(name)) => {
                let (title, label) = (self.t("action.insert_template"), self.t("template.prefix"));
                let prefix = format!("{name}_");
                self.show_prompt(Prompt::TemplatePrefix(name), &title, &label, &prefix);
                None
            }
            (Some(Picker::Command), action) => action,
            _ => None,
        }
    }

    // ---------------------------------------------------------- performance

    fn show_performance(&mut self) {
        let (drag_avg, drag_max) = Profiler::summary(&self.profiler.drag);
        let (full_avg, full_max) = Profiler::summary(&self.profiler.full);
        let text = trf(
            &self.lang,
            "performance.summary",
            &[
                ("drag_avg", format!("{drag_avg:.2}")),
                ("drag_max", format!("{drag_max:.2}")),
                ("full_avg", format!("{full_avg:.2}")),
                ("full_max", format!("{full_max:.2}")),
            ],
        );
        message(&self.t("performance.title"), &text);
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn profiler_keeps_180_samples_and_summarises() {
        let mut samples = Vec::new();
        for _ in 0..200 {
            Profiler::record(&mut samples, Instant::now());
        }
        assert_eq!(samples.len(), 180);
        assert_eq!(Profiler::summary(&[]), (0.0, 0.0));
        assert_eq!(Profiler::summary(&[1.0, 3.0]), (2.0, 3.0));
    }

    #[test]
    fn palette_labels_are_translated() {
        for (_, label, _) in PALETTE {
            assert_ne!(crate::i18n::tr("en_US", label), label, "{label}");
        }
    }
}
