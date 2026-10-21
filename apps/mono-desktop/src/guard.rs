//! Unsaved-changes protection (V1 `closeEvent`, `_confirm_project_transition`,
//! `_confirm_scene_transition`): nothing the user edited is dropped or saved
//! without asking first.

use std::path::Path;

use mono_core::CoreError;
use mono_project::scene_io::load_project_scene;

use crate::app::App;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Unsaved {
    Save,
    Discard,
    Cancel,
}

impl App {
    fn scene_dirty(&self) -> bool {
        self.session.as_ref().is_some_and(|s| s.dirty)
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

    /// Save / Discard / Cancel. Non-interactive runs (screenshots, benches,
    /// tests) never block on a dialog: they use `scripted_choice` or Cancel.
    fn ask_unsaved(&self, message_key: &str) -> Unsaved {
        if !self.interactive {
            return self.scripted_choice.unwrap_or(Unsaved::Cancel);
        }
        match rfd::MessageDialog::new()
            .set_title(self.t("dialog.unsaved_title"))
            .set_description(self.t(message_key))
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
        if !self.has_unsaved() {
            return true;
        }
        match self.ask_unsaved("dialog.unsaved_message") {
            Unsaved::Cancel => false,
            Unsaved::Discard => {
                self.pixel.doc.dirty = false;
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
        match self.ask_unsaved("dialog.unsaved_message") {
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
    pub fn switch_screen(&mut self, screen_id: &str) -> Result<(), CoreError> {
        let Some(project) = self.project.as_mut() else {
            return Ok(());
        };
        project.set_active_screen(screen_id)?;
        project.save()?;
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
        // The deleted screen's session is gone with its file; never save it.
        if let Some(session) = self.session.as_mut() {
            session.dirty = false;
        }
        self.switch_screen(&next)
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
        assert!(session.dirty);
    }

    #[test]
    fn cancel_keeps_the_scene_and_does_not_switch() {
        let (mut app, root) = app("cancel");
        edit(&mut app);
        app.scripted_choice = Some(Unsaved::Cancel);
        assert!(!app.confirm_transition());
        app.open_screen("123").unwrap();
        assert_eq!(app.project.as_ref().unwrap().active_screen(), "main");
        assert!(app.session.as_ref().unwrap().dirty);
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
}
