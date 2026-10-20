//! `App` glue for the Font Lab workspace (`FontModel`).

use std::path::{Path, PathBuf};

use mono_core::CoreError;
use mono_core::render::posix;
use slint::Global;

use crate::app::{App, Prompt, model, ss};
use crate::fontlab::{FontLab, Poll, create_pack};
use crate::i18n::trf;
use crate::{FontModel, GlyphItem};

impl App {
    fn fonts_root(&self) -> Option<PathBuf> {
        self.project_root().map(|r| r.join(".oled").join("fonts"))
    }

    /// Open (or create) the pack at `root` and show it in Font Lab.
    pub fn open_font_pack(&mut self, root: &Path) -> Result<(), CoreError> {
        if let Some(font) = self.font.as_mut() {
            if font.running() {
                return Err(CoreError::invalid(self.t("font.generate.running")));
            }
            if font.dirty() {
                font.save()?;
            }
        }
        if !root.join("fontpack.json").is_file() {
            return Err(CoreError::invalid(trf(
                &self.lang,
                "font.manifest_missing",
                &[("path", posix(root))],
            )));
        }
        let mut lab = FontLab::open(root, "OLED Font", (5, 8))?;
        lab.studio.brush = self.pixel.brush;
        lab.studio.interpolation = self.pixel.interpolation;
        self.font = Some(lab);
        self.log_event(format!("OPEN_FONT_PACK {}", posix(root)));
        Ok(())
    }

    pub fn refresh_font(&mut self) {
        let Some(ui) = self.ui.upgrade() else { return };
        let fm = FontModel::get(&ui);
        fm.set_packs(model(self.font_packs.iter().map(ss).collect()));
        let Some(font) = &self.font else {
            fm.set_has_pack(false);
            fm.set_glyphs(model(Vec::new()));
            return;
        };
        fm.set_has_pack(true);
        let rel = self
            .project_root()
            .and_then(|r| font.root.strip_prefix(r).ok().map(posix))
            .unwrap_or_else(|| posix(&font.root));
        fm.set_pack_title(ss(format!(
            "{} — {rel}{}",
            font.pack.name,
            if font.dirty() { " ●" } else { "" }
        )));
        let chars = font.characters();
        fm.set_glyphs(model(
            chars
                .iter()
                .map(|c| GlyphItem {
                    text: ss(c.to_string()),
                    code: ss(format!("U+{:04X}", u32::from(*c))),
                })
                .collect(),
        ));
        fm.set_current(
            font.current
                .and_then(|c| chars.iter().position(|x| *x == c))
                .map_or(-1, |i| i as i32),
        );
        let f = &font.form;
        fm.set_characters(ss(&f.characters));
        fm.set_font_path(ss(&f.font_path));
        fm.set_font_size(f.font_size as i32);
        fm.set_cell_w(f.cell_w as i32);
        fm.set_cell_h(f.cell_h as i32);
        fm.set_baseline(f.baseline as i32);
        fm.set_advance(f.advance as i32);
        fm.set_threshold(f.threshold as i32);
        fm.set_alignment(f.alignment);
        fm.set_antialias(i32::from(f.antialias == 2));
        fm.set_busy(font.running());
        fm.set_status(ss(&font.status));
        fm.set_error(ss(&font.error));
    }

    fn refresh_font_all(&mut self) {
        self.refresh_font();
        if self.workspace == 2 {
            self.refresh_pixel();
        }
    }

    pub fn font_glyph_chosen(&mut self, index: i32) {
        let Some(font) = self.font.as_mut() else {
            return;
        };
        let Some(ch) = usize::try_from(index)
            .ok()
            .and_then(|i| font.characters().get(i).copied())
        else {
            return;
        };
        if let Err(e) = font.select(ch) {
            font.error = e.message.clone();
            self.error(&e);
        }
        self.refresh_font_all();
    }

    pub fn font_edit(&mut self, field: &str, value: &str) {
        if let Some(font) = self.font.as_mut() {
            font.edit(field, value);
        }
        self.refresh_font();
    }

    pub fn font_action(&mut self, action: &str) {
        let result: Result<(), CoreError> = (|| {
            match action {
                "new" => {
                    if self.project_root().is_none() {
                        return Err(CoreError::invalid(self.t("bench.no_project")));
                    }
                    let (title, label) = (self.t("font.new_title"), self.t("font.pack_name"));
                    self.show_prompt(Prompt::NewFontPack, &title, &label, "Clinical 5x7");
                }
                "open" => {
                    let mut dialog = rfd::FileDialog::new().set_title(self.t("font.open_title"));
                    if let Some(dir) = self.fonts_root().filter(|d| d.is_dir()) {
                        dialog = dialog.set_directory(dir);
                    }
                    if let Some(dir) = dialog.pick_folder() {
                        self.open_font_pack(&dir)?;
                    }
                }
                "browse" => {
                    if let Some(path) = rfd::FileDialog::new()
                        .set_title(self.t("font.file_dialog"))
                        .add_filter("Fonts", &["ttf", "otf", "ttc"])
                        .pick_file()
                    {
                        if let Some(font) = self.font.as_mut() {
                            font.edit("font_path", &path.to_string_lossy());
                        }
                    }
                }
                "save" => {
                    if let Some(font) = self.font.as_mut() {
                        font.save()?;
                    }
                    self.scan_project_files();
                    self.refresh_all();
                }
                "generate" => {
                    let confirm = self
                        .font
                        .as_ref()
                        .is_some_and(FontLab::needs_resize_confirm);
                    if confirm {
                        let answer = rfd::MessageDialog::new()
                            .set_title(self.t("font.resize_title"))
                            .set_description(self.t("font.resize_confirm"))
                            .set_buttons(rfd::MessageButtons::YesNo)
                            .show();
                        if answer != rfd::MessageDialogResult::Yes {
                            return Ok(());
                        }
                    }
                    let running = self.t("font.generate.running");
                    if let Some(font) = self.font.as_mut() {
                        font.start_generate()?;
                        font.status = running;
                    }
                }
                other => {
                    if let Some(rel) = other.strip_prefix("open:") {
                        let root = self.project_root().unwrap_or_default().join(rel);
                        self.open_font_pack(&root)?;
                    }
                }
            }
            Ok(())
        })();
        if let Err(e) = result {
            if let Some(font) = self.font.as_mut() {
                font.error = e.message.clone();
            }
            self.error(&e);
        }
        self.refresh_font_all();
    }

    /// Timer tick: report worker progress and pick up the finished pack.
    pub fn poll_font(&mut self) {
        let Some(font) = self.font.as_mut() else {
            return;
        };
        let polled = font.poll();
        let lang = self.lang.clone();
        let status = match &polled {
            Poll::Idle => return,
            Poll::Running(done, total) => trf(
                &lang,
                "font.generate.progress",
                &[("done", done.to_string()), ("total", total.to_string())],
            ),
            Poll::Finished(Ok(count)) => {
                trf(&lang, "font.generated", &[("count", count.to_string())])
            }
            Poll::Finished(Err(_)) => crate::i18n::tr(&lang, "font.generate.failed"),
        };
        font.status = status.clone();
        match polled {
            // Progress only touches the status line, not the glyph list.
            Poll::Running(..) => {
                if let Some(ui) = self.ui.upgrade() {
                    FontModel::get(&ui).set_status(ss(status));
                }
                return;
            }
            Poll::Finished(Ok(_)) => {
                font.error.clear();
                self.scan_project_files();
                self.refresh_all();
            }
            Poll::Finished(Err(message)) => self.log_event(format!("ERROR {message}")),
            Poll::Idle => {}
        }
        self.refresh_font_all();
    }

    /// `Prompt::NewFontPack` accepted (V1 `_resource_new_font_pack`).
    pub fn create_font_pack(&mut self, name: &str) {
        let result = (|| -> Result<(), CoreError> {
            if name.trim().is_empty() {
                return Ok(());
            }
            let fonts = self
                .fonts_root()
                .ok_or_else(|| CoreError::invalid(self.t("bench.no_project")))?;
            let root = create_pack(&fonts, name).map_err(|e| {
                if e.code == "FileExistsError" {
                    CoreError::invalid(trf(&self.lang, "font.exists", &[("path", e.message)]))
                } else {
                    e
                }
            })?;
            self.scan_project_files();
            self.open_font_pack(&root)
        })();
        if let Err(e) = result {
            self.error(&e);
        }
        self.refresh_navigator();
        self.refresh_font_all();
    }
}
