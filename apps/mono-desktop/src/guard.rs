//! Unsaved-changes protection (V1 `closeEvent`, `_confirm_project_transition`,
//! `_confirm_scene_transition`): nothing the user edited is dropped or saved
//! without asking first.

use std::path::Path;

use mono_core::CoreError;
use mono_project::editor::EditorSession;
use mono_project::scene_io::load_project_scene;

use crate::app::App;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Unsaved {
    Save,
    Discard,
    Cancel,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum DirtyDoc {
    Scene,
    Pixel,
    Font,
}

impl App {
    fn scene_dirty(&self) -> bool {
        self.session.as_ref().is_some_and(EditorSession::is_dirty)
    }

    /// Designer scene, Pixel Studio bitmap or Font Lab glyph/metrics.
    pub fn has_unsaved(&self) -> bool {
        self.scene_dirty()
            || self.pixel.doc.dirty
            || self
                .font
                .as_ref()
                .is_some_and(crate::fontlab::FontLab::dirty)
    }

    /// Which documents are dirty, so the prompt can name them instead of
    /// claiming "the scene" while a Pixel PNG is the actual change.
    pub fn dirty_documents(&self) -> Vec<DirtyDoc> {
        let mut docs = Vec::new();
        if self.scene_dirty() {
            docs.push(DirtyDoc::Scene);
        }
        if self.pixel.doc.dirty {
            docs.push(DirtyDoc::Pixel);
        }
        if self
            .font
            .as_ref()
            .is_some_and(crate::fontlab::FontLab::dirty)
        {
            docs.push(DirtyDoc::Font);
        }
        docs
    }

    fn dirty_labels(&self, docs: &[DirtyDoc]) -> String {
        docs.iter()
            .map(|doc| {
                self.t(match doc {
                    DirtyDoc::Scene => "doc.scene",
                    DirtyDoc::Pixel => "doc.pixel",
                    DirtyDoc::Font => "doc.font",
                })
            })
            .collect::<Vec<_>>()
            .join(", ")
    }

    /// The prompt that names what is unsaved. One document takes the singular
    /// verb: "Designer scene have unsaved changes" is not English, and the list
    /// is the sentence's subject, so the count has to pick the wording.
    fn unsaved_message(&self) -> String {
        let docs = self.dirty_documents();
        crate::i18n::trf(
            &self.lang,
            if docs.len() == 1 {
                "dialog.unsaved_doc"
            } else {
                "dialog.unsaved_docs"
            },
            &[("docs", self.dirty_labels(&docs))],
        )
    }

    /// Save / Discard / Cancel. Non-interactive runs (screenshots, benches,
    /// tests) never block on a dialog: they use `scripted_choice` or Cancel.
    fn ask_unsaved(&self, message: &str) -> Unsaved {
        if !self.interactive {
            return self.scripted_choice.unwrap_or(Unsaved::Cancel);
        }
        match rfd::MessageDialog::new()
            .set_title(self.t("dialog.unsaved_title"))
            .set_description(message)
            .set_buttons(rfd::MessageButtons::YesNoCancel)
            .show()
        {
            rfd::MessageDialogResult::Yes => Unsaved::Save,
            rfd::MessageDialogResult::No => Unsaved::Discard,
            _ => Unsaved::Cancel,
        }
    }

    fn report(&mut self, error: &CoreError) {
        self.error(error);
        if self.interactive {
            rfd::MessageDialog::new()
                .set_title(self.t("dialog.error"))
                .set_description(&error.message)
                .set_buttons(rfd::MessageButtons::Ok)
                .show();
        }
    }

    /// Save every dirty document; false when a save failed or was cancelled.
    fn save_everything(&mut self) -> bool {
        if self.scene_dirty() {
            if let Err(e) = self.save() {
                self.report(&e);
                return false;
            }
        }
        if self.pixel.doc.dirty {
            match self.pixel_save() {
                Ok(true) => {}
                Ok(false) => return false,
                Err(e) => {
                    self.report(&e);
                    return false;
                }
            }
        }
        if let Some(font) = self.font.as_mut() {
            if font.dirty() {
                if let Err(e) = font.save() {
                    self.report(&e);
                    return false;
                }
            }
        }
        true
    }

    /// Before closing the window, exiting or opening another project/scene.
    /// Returns true when the transition may proceed.
    pub fn confirm_transition(&mut self) -> bool {
        // Buffered preference edits are part of "saved"; write them before asking.
        self.flush_prefs();
        // A running glyph generation writes into the pack: neither Save nor
        // Discard can be honoured until it finishes.
        if self
            .font
            .as_ref()
            .is_some_and(crate::fontlab::FontLab::running)
        {
            let error = CoreError::invalid(self.t("font.generate.running"));
            self.report(&error);
            return false;
        }
        // An export / handoff job is still writing files from the old scene.
        if let Some(job) = &self.bg_job {
            let error = CoreError::invalid(crate::i18n::trf(
                &self.lang,
                "job.running_close",
                &[("label", job.label.clone())],
            ));
            self.report(&error);
            return false;
        }
        if !self.has_unsaved() {
            return true;
        }
        let message = self.unsaved_message();
        match self.ask_unsaved(&message) {
            Unsaved::Cancel => false,
            Unsaved::Discard => {
                self.pixel.doc.dirty = false;
                // Close the pack so a later glyph switch cannot auto-save it.
                if self
                    .font
                    .as_ref()
                    .is_some_and(crate::fontlab::FontLab::dirty)
                {
                    self.font = None;
                }
                true
            }
            Unsaved::Save => self.save_everything(),
        }
    }

    /// Before switching or deleting the active screen (Designer scene only).
    pub fn confirm_scene_transition(&mut self) -> bool {
        if !self.scene_dirty() {
            return true;
        }
        match self.ask_unsaved(&self.t("dialog.unsaved_message")) {
            Unsaved::Cancel => false,
            Unsaved::Discard => true,
            Unsaved::Save => match self.save() {
                Ok(()) => true,
                Err(e) => {
                    self.report(&e);
                    false
                }
            },
        }
    }

    /// Bind the Designer to `screen_id` without asking (callers confirm first).
    /// Viewing another screen is not an edit: the manifest is written on the
    /// next explicit save, so browsing never rewrites `project.oled.json`.
    pub fn switch_screen(&mut self, screen_id: &str) -> Result<(), CoreError> {
        let Some(project) = self.project.as_mut() else {
            return Ok(());
        };
        project.set_active_screen(screen_id)?;
        let scene = load_project_scene(project, Some(screen_id))?;
        self.bind_scene(scene)?;
        self.prompt_recovery();
        Ok(())
    }

    /// Delete the active screen (V1: ask first, change the project only after).
    pub fn delete_active_screen(&mut self) -> Result<(), CoreError> {
        let Some(project) = self.project.as_ref() else {
            return Ok(());
        };
        let active = project.active_screen();
        let Some(next) = project
            .screens()
            .into_iter()
            .map(|s| s.id)
            .find(|id| *id != active)
        else {
            return Err(CoreError::invalid("project must keep at least one screen"));
        };
        if !self.confirm_scene_transition() {
            return Ok(());
        }
        if let Some(project) = self.project.as_mut() {
            project.set_active_screen(&next)?;
            project.remove_screen(&active, true)?;
        }
        // Drop the deleted screen's session before switching: if the switch
        // fails, nothing may write that file back.
        self.session = None;
        self.switch_screen(&next)
    }

    /// Rename the active screen. The scene file moves on disk, so the session
    /// is dropped and re-bound afterwards: a session still pointing at the old
    /// path would resurrect that file on the next save.
    pub fn rename_active_screen(&mut self, new_id: &str) -> Result<(), CoreError> {
        if self.project.is_none() {
            return Err(CoreError::invalid(self.t("status.no_document")));
        }
        // Save-or-discard first, so the rename moves the file as the user last
        // left it.
        if !self.confirm_scene_transition() {
            self.refresh_navigator();
            return Ok(());
        }
        let active = self
            .project
            .as_ref()
            .map(|project| project.active_screen())
            .unwrap_or_default();
        // Drop the session before the rename, not after: `rename_screen` moves the
        // scene file and can fail halfway (the manifest write, or the rollback of
        // that move), and a session still bound to the old path would recreate it
        // on the next save. Nothing is lost — the prompt above already saved or
        // discarded every change.
        self.session = None;
        if let Some(project) = self.project.as_mut() {
            project.rename_screen(&active, new_id, Some(new_id))?;
        }
        self.switch_screen(new_id)
    }

    /// Open a project or scene path after the unsaved-changes check.
    pub fn open_path_guarded(&mut self, path: &Path, scene: bool) -> Result<(), CoreError> {
        if !self.confirm_transition() {
            return Ok(());
        }
        if scene {
            self.open_scene_file(path)?;
        } else {
            self.open_project(path)?;
        }
        self.prompt_recovery();
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    #![allow(clippy::unwrap_used)]
    use super::*;

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

    fn app(name: &str) -> (App, std::path::PathBuf) {
        let root = std::env::temp_dir().join(format!("mono-guard-{name}-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&root);
        let repo = Path::new(env!("CARGO_MANIFEST_DIR")).join("../..");
        copy_dir(&repo.join("test_assets/projects/curing_lite"), &root);
        let prefs = crate::prefs::Preferences::load_from(root.join("prefs.json"));
        let mut app = App::new(slint::Weak::default(), prefs);
        app.open_project(&root.join("project.oled.json")).unwrap();
        app.switch_screen("main").unwrap();
        (app, root)
    }

    fn edit(app: &mut App) {
        let session = app.session.as_mut().unwrap();
        session
            .batch_move(&["hero_digits".to_string()], 1, 0, false)
            .unwrap();
        assert!(session.is_dirty());
    }

    #[test]
    fn cancel_keeps_the_scene_and_does_not_switch() {
        let (mut app, root) = app("cancel");
        edit(&mut app);
        app.scripted_choice = Some(Unsaved::Cancel);
        assert!(!app.confirm_transition());
        app.open_screen("123").unwrap();
        assert_eq!(app.project.as_ref().unwrap().active_screen(), "main");
        assert!(app.session.as_ref().unwrap().is_dirty());
        let _ = std::fs::remove_dir_all(&root);
    }

    #[test]
    fn discard_switches_without_writing_and_save_writes() {
        let (mut app, root) = app("switch");
        let scene_file = root.join("scenes/main_scene.json");
        let before = std::fs::read(&scene_file).unwrap();
        edit(&mut app);
        app.scripted_choice = Some(Unsaved::Discard);
        app.open_screen("123").unwrap();
        assert_eq!(std::fs::read(&scene_file).unwrap(), before);
        app.open_screen("main").unwrap();
        edit(&mut app);
        app.scripted_choice = Some(Unsaved::Save);
        app.open_screen("123").unwrap();
        assert_ne!(std::fs::read(&scene_file).unwrap(), before);
        let _ = std::fs::remove_dir_all(&root);
    }

    /// Renaming moves the scene file, so the session must follow it: a session
    /// still pointing at the old path would write that file back on save.
    #[test]
    fn renaming_the_active_screen_rebinds_the_session_and_never_writes_the_old_path() {
        let (mut app, root) = app("rename");
        edit(&mut app);
        app.scripted_choice = Some(Unsaved::Save);
        app.rename_active_screen("renamed").unwrap();

        let session = app.session.as_ref().unwrap();
        assert_eq!(session.doc.path, root.join("scenes/renamed.json"));
        assert!(!session.is_dirty(), "the saved edits moved with the screen");
        assert!(
            !root.join("scenes/main_scene.json").exists(),
            "the rename left the old file behind"
        );
        assert_eq!(
            app.project.as_ref().unwrap().active_screen(),
            "renamed",
            "the manifest still points at the old id"
        );

        app.save().unwrap();
        assert!(
            !root.join("scenes/main_scene.json").exists(),
            "a later save resurrected the renamed-away file"
        );
        assert!(root.join("scenes/renamed.json").exists());
        let _ = std::fs::remove_dir_all(root);
    }

    #[test]
    fn deleting_a_dirty_screen_asks_first_and_binds_the_next_screen() {
        let (mut app, root) = app("delete");
        edit(&mut app);
        app.scripted_choice = Some(Unsaved::Cancel);
        app.delete_active_screen().unwrap();
        assert!(root.join("scenes/main_scene.json").is_file());
        app.scripted_choice = Some(Unsaved::Discard);
        app.delete_active_screen().unwrap();
        assert!(!root.join("scenes/main_scene.json").exists());
        assert_eq!(app.project.as_ref().unwrap().active_screen(), "123");
        // The new binding saves cleanly (no stale file or fingerprint).
        app.save().unwrap();
        let _ = std::fs::remove_dir_all(&root);
    }

    #[test]
    fn dirty_pixel_or_font_documents_also_block_transitions() {
        let (mut app, root) = app("pixel");
        app.pixel.doc.pencil(0, 0, true);
        app.scripted_choice = Some(Unsaved::Cancel);
        assert!(!app.confirm_transition());
        app.scripted_choice = Some(Unsaved::Discard);
        assert!(app.confirm_transition());
        assert!(!app.has_unsaved());
        let _ = std::fs::remove_dir_all(&root);
    }

    #[test]
    fn export_runs_in_the_background_and_blocks_closing_until_done() {
        let (mut app, root) = app("bgjob");
        let out = root.join("exports").join("bg");
        app.start_export(true, out.clone()).unwrap();
        // Returned without doing the work; a second job is refused.
        assert!(app.bg_job.is_some());
        assert!(app.start_batch_validate().is_err());
        assert!(!app.confirm_transition());
        let deadline = std::time::Instant::now() + std::time::Duration::from_secs(60);
        while app.bg_job.is_some() {
            assert!(
                std::time::Instant::now() < deadline,
                "export did not finish"
            );
            std::thread::sleep(std::time::Duration::from_millis(20));
            app.poll_background();
        }
        assert!(out.join("ui_contract.json").is_file());
        assert!(app.status.contains("bg"), "{}", app.status);
        assert!(app.confirm_transition());
        let _ = std::fs::remove_dir_all(&root);
    }

    #[test]
    fn discarded_font_edits_are_never_written_back() {
        let (mut app, root) = app("font");
        let pack = crate::fontlab::create_pack(&root.join(".oled/fonts"), "Guard 5x8").unwrap();
        app.open_font_pack(&pack).unwrap();
        let before = std::fs::read(pack.join("fontpack.json")).unwrap();
        app.font.as_mut().unwrap().studio.doc.pencil(0, 0, true);
        app.scripted_choice = Some(Unsaved::Discard);
        assert!(app.confirm_transition());
        assert!(!app.has_unsaved());
        assert!(app.font.is_none());
        // Opening another project starts without the old pack.
        app.open_project(&root.join("project.oled.json")).unwrap();
        assert!(app.font.is_none());
        assert_eq!(std::fs::read(pack.join("fontpack.json")).unwrap(), before);
        let _ = std::fs::remove_dir_all(&root);
    }

    #[test]
    fn dirty_documents_names_each_edited_document() {
        let (mut app, root) = app("docs");
        assert!(app.dirty_documents().is_empty());
        edit(&mut app);
        assert_eq!(app.dirty_documents(), vec![DirtyDoc::Scene]);
        app.pixel.doc.pencil(0, 0, true);
        assert_eq!(
            app.dirty_documents(),
            vec![DirtyDoc::Scene, DirtyDoc::Pixel]
        );
        let _ = std::fs::remove_dir_all(&root);
    }

    #[test]
    fn the_unsaved_prompt_agrees_with_its_subject() {
        let (mut app, root) = app("grammar");
        app.lang = "en_US".to_string();
        edit(&mut app);
        let one = app.unsaved_message();
        assert!(
            one.starts_with("Designer scene has unsaved"),
            "one document: {one}"
        );
        app.pixel.doc.pencil(0, 0, true);
        let both = app.unsaved_message();
        assert!(
            both.starts_with("Designer scene, Pixel Studio bitmap have unsaved"),
            "two documents: {both}"
        );
        let _ = std::fs::remove_dir_all(&root);
    }

    #[test]
    fn viewing_another_screen_leaves_the_manifest_untouched_until_save() {
        let (mut app, root) = app("view");
        let manifest = root.join("project.oled.json");
        let before = std::fs::read(&manifest).unwrap();
        // The fixture opens on "123"; the setup bound the Designer to "main".
        app.switch_screen("main").unwrap();
        assert_eq!(
            std::fs::read(&manifest).unwrap(),
            before,
            "merely viewing a screen must not rewrite the project file"
        );
        app.save().unwrap();
        let saved: serde_json::Value =
            serde_json::from_str(&std::fs::read_to_string(&manifest).unwrap()).unwrap();
        assert_eq!(saved["active_screen"], "main");
        assert_ne!(std::fs::read(&manifest).unwrap(), before);
        let _ = std::fs::remove_dir_all(&root);
    }
}
