//! Font Lab (V1 `font_lab_qt.FontLabEditor`): edit one Font Pack glyph by glyph
//! and (re)generate glyphs from the built-in 5x7 font or a TrueType file.
//!
//! Generation runs on a worker thread (V1 `_FontGenerateWorker`); the UI polls
//! `poll()` from a timer, so a large character set never blocks the window.

use std::path::{Path, PathBuf};
use std::sync::{Arc, Mutex};

use mono_core::font::{
    DEFAULT_CHARACTERS, FontPack, GlyphMetrics, recommended_advance, recommended_baseline,
    validate_metrics,
};
use mono_core::pixel::PixelDocument;
use mono_core::profiles::Alignment;
use mono_core::{CoreError, CoreResult};
use mono_font::{
    GenerateOptions, load_font, rasterize_characters_with_progress, recommended_font_size,
    recommended_truetype_layout,
};
use mono_project::fontpack_io::{load_font_pack, save_font_pack};

use crate::pixel::PixelStudio;

/// V1 `_resource_new_font_pack`: folder name from the display name.
pub fn safe_pack_dir(name: &str) -> String {
    let safe: String = name
        .trim()
        .chars()
        .map(|c| {
            if c.is_alphanumeric() || c == '-' || c == '_' {
                c
            } else {
                '_'
            }
        })
        .collect();
    let safe = safe.trim_matches('_').to_string();
    if safe.is_empty() {
        "font_pack".into()
    } else {
        safe
    }
}

/// V1 new pack: `create_font_pack(root, name, cell=(5, 8), baseline=6, advance=6).save()`.
pub fn create_pack(fonts_root: &Path, name: &str) -> CoreResult<PathBuf> {
    let root = fonts_root.join(safe_pack_dir(name));
    if root.join("fontpack.json").exists() {
        return Err(CoreError::new(
            "FileExistsError",
            root.display().to_string(),
        ));
    }
    let pack = FontPack::new(name.trim(), (5, 8), 6, 6)?;
    save_font_pack(&root, &pack, None)?;
    Ok(root)
}

#[derive(Debug, Clone)]
pub struct FontForm {
    pub characters: String,
    pub font_path: String,
    pub font_size: i64,
    pub cell_w: i64,
    pub cell_h: i64,
    pub baseline: i64,
    pub advance: i64,
    pub threshold: i64,
    /// 0 = font set, 1 = glyph width (V1 default).
    pub alignment: i32,
    /// 1 or 2.
    pub antialias: i64,
    baseline_override: bool,
    advance_override: bool,
    size_override: bool,
}

#[derive(Debug, Default)]
pub struct JobState {
    pub done: usize,
    pub total: usize,
    pub result: Option<Result<(FontPack, usize), String>>,
}

pub enum Poll {
    Idle,
    Running(usize, usize),
    Finished(Result<usize, String>),
}

pub struct FontLab {
    pub root: PathBuf,
    pub pack: FontPack,
    pub current: Option<char>,
    pub studio: PixelStudio,
    pub form: FontForm,
    pub status: String,
    pub error: String,
    job: Option<Arc<Mutex<JobState>>>,
}

fn blank_glyph(pack: &FontPack) -> CoreResult<PixelStudio> {
    let mut studio = PixelStudio::new(pack.cell.0, pack.cell.1)?;
    studio.doc.dirty = false;
    Ok(studio)
}

impl FontLab {
    /// Open an existing pack, or create it with recommended metrics (V1 constructor).
    pub fn open(root: &Path, name: &str, cell: (usize, usize)) -> CoreResult<Self> {
        let pack = if root.join("fontpack.json").exists() {
            load_font_pack(root)?
        } else {
            let pack = FontPack::with_recommended(name, cell)?;
            save_font_pack(root, &pack, None)?;
            pack
        };
        let form = FontForm {
            characters: DEFAULT_CHARACTERS.into(),
            font_path: String::new(),
            font_size: recommended_font_size(pack.cell),
            cell_w: pack.cell.0 as i64,
            cell_h: pack.cell.1 as i64,
            baseline: i64::from(pack.baseline),
            advance: i64::from(pack.advance),
            threshold: 128,
            alignment: 1,
            antialias: 1,
            baseline_override: false,
            advance_override: false,
            size_override: false,
        };
        let mut lab = Self {
            root: root.to_path_buf(),
            studio: blank_glyph(&pack)?,
            pack,
            current: None,
            form,
            status: String::new(),
            error: String::new(),
            job: None,
        };
        lab.refresh_glyphs()?;
        Ok(lab)
    }

    pub fn running(&self) -> bool {
        self.job.is_some()
    }

    /// Metrics differ from the saved pack (V1 `_metrics_changed`).
    pub fn metrics_dirty(&self) -> bool {
        self.form.baseline != i64::from(self.pack.baseline)
            || self.form.advance != i64::from(self.pack.advance)
    }

    pub fn dirty(&self) -> bool {
        self.metrics_dirty() || self.studio.doc.dirty
    }

    pub fn characters(&self) -> Vec<char> {
        self.pack.characters().collect()
    }

    /// V1 `refresh_glyphs`: keep the current glyph, else select the first one.
    pub fn refresh_glyphs(&mut self) -> CoreResult<()> {
        let chars = self.characters();
        let target = self
            .current
            .filter(|c| chars.contains(c))
            .or_else(|| chars.first().copied());
        self.current = None;
        match target {
            Some(ch) => self.load_glyph(ch),
            None => {
                self.studio = blank_glyph(&self.pack)?;
                Ok(())
            }
        }
    }

    fn load_glyph(&mut self, ch: char) -> CoreResult<()> {
        let rows = self
            .pack
            .glyph(ch)
            .map(|g| g.rows.clone())
            .ok_or_else(|| CoreError::new("KeyError", format!("{ch:?}")))?;
        let (tool, brush) = (self.studio.tool, self.studio.brush);
        let mut studio = blank_glyph(&self.pack)?;
        let flat: Vec<u8> = rows.into_iter().flatten().collect();
        studio.doc = PixelDocument::from_pixels(self.pack.cell.0, self.pack.cell.1, flat)?;
        studio.doc.dirty = false;
        studio.tool = tool;
        studio.brush = brush;
        self.studio = studio;
        self.current = Some(ch);
        Ok(())
    }

    /// V1 `_select_glyph`: an edited glyph is saved before switching.
    pub fn select(&mut self, ch: char) -> CoreResult<()> {
        if self.current == Some(ch) {
            return Ok(());
        }
        if self.current.is_some() && self.studio.doc.dirty {
            self.save()?;
        }
        self.load_glyph(ch)
    }

    /// V1 `save`: current glyph (keeping its metrics) plus pack metrics.
    pub fn save(&mut self) -> CoreResult<()> {
        if self.running() {
            // Never report a save that did not happen.
            return Err(CoreError::invalid("glyph generation is running"));
        }
        let mut changed = Vec::new();
        if let Some(ch) = self.current {
            let metrics = self
                .pack
                .glyph(ch)
                .map(|g| g.metrics)
                .unwrap_or(GlyphMetrics {
                    bearing_x: 0,
                    bearing_y: 0,
                    advance: self.pack.advance,
                });
            self.pack
                .set_glyph(ch, self.studio.doc.rows(), Some(metrics))?;
            if self.studio.doc.dirty {
                changed.push(ch);
            }
        }
        self.pack
            .set_metrics(Some(self.form.baseline), Some(self.form.advance))?;
        save_font_pack(&self.root, &self.pack, Some(&changed))?;
        self.studio.doc.dirty = false;
        Ok(())
    }

    // ------------------------------------------------------------- form

    fn cell(&self) -> (usize, usize) {
        (
            self.form.cell_w.max(1) as usize,
            self.form.cell_h.max(1) as usize,
        )
    }

    /// V1 `_apply_auto_font_layout`.
    fn auto_layout(&mut self) {
        let cell = self.cell();
        let path = self.form.font_path.trim().to_string();
        if path.is_empty() {
            if !self.form.baseline_override {
                self.form.baseline = i64::from(recommended_baseline(cell));
            }
            if !self.form.advance_override {
                self.form.advance = i64::from(recommended_advance(cell));
            }
            if !self.form.size_override {
                self.form.font_size = recommended_font_size(cell);
            }
            return;
        }
        let Ok(bytes) = std::fs::read(&path) else {
            return;
        };
        let Ok(font) = load_font(bytes) else { return };
        let Ok((fitted, baseline)) =
            recommended_truetype_layout(&font, cell, &self.form.characters, self.form.font_size)
        else {
            return;
        };
        if !self.form.size_override {
            self.form.font_size = fitted;
        }
        if !self.form.baseline_override {
            self.form.baseline = baseline;
        }
    }

    /// Apply one form edit (V1 signal handlers, including the override flags).
    pub fn edit(&mut self, field: &str, value: &str) {
        let int = || value.trim().parse::<i64>().ok();
        match field {
            "characters" => self.form.characters = value.to_string(),
            "font_path" => {
                self.form.font_path = value.to_string();
                self.auto_layout();
            }
            "font_size" => {
                if let Some(v) = int() {
                    self.form.font_size = v.clamp(4, 96);
                    self.form.size_override = true;
                    self.auto_layout();
                }
            }
            "cell_w" => {
                if let Some(v) = int() {
                    self.form.cell_w = v.clamp(1, 128);
                    let cell = self.cell();
                    if !self.form.advance_override {
                        self.form.advance = i64::from(recommended_advance(cell));
                    }
                    if !self.form.size_override {
                        self.form.font_size = recommended_font_size(cell);
                    }
                    self.auto_layout();
                }
            }
            "cell_h" => {
                if let Some(v) = int() {
                    self.form.cell_h = v.clamp(1, 128);
                    let cell = self.cell();
                    let maximum = (self.form.cell_h - 1).max(0);
                    if !self.form.baseline_override {
                        self.form.baseline = i64::from(recommended_baseline(cell));
                    } else if self.form.baseline > maximum {
                        self.form.baseline = maximum;
                    }
                    if !self.form.size_override {
                        self.form.font_size = recommended_font_size(cell);
                    }
                    self.auto_layout();
                }
            }
            "baseline" => {
                if let Some(v) = int() {
                    self.form.baseline = v.clamp(0, (self.form.cell_h - 1).max(0));
                    self.form.baseline_override = true;
                }
            }
            "advance" => {
                if let Some(v) = int() {
                    self.form.advance = v.clamp(1, 128);
                    self.form.advance_override = true;
                }
            }
            "threshold" => {
                if let Some(v) = int() {
                    self.form.threshold = v.clamp(0, 255);
                }
            }
            "alignment" => self.form.alignment = i32::from(value == "1"),
            "antialias" => self.form.antialias = if value == "2" { 2 } else { 1 },
            _ => {}
        }
    }

    /// True when generation would rebuild an existing, non-empty pack at a new cell.
    pub fn needs_resize_confirm(&self) -> bool {
        self.cell() != self.pack.cell && !self.pack.is_empty()
    }

    // --------------------------------------------------------- generation

    /// V1 `generate`: validate, then rasterize + save on a worker thread.
    pub fn start_generate(&mut self) -> CoreResult<()> {
        if self.running() {
            return Ok(());
        }
        let cell = self.cell();
        validate_metrics(
            (cell.0 as i64, cell.1 as i64),
            self.form.baseline,
            self.form.advance,
        )?;
        let resize = cell != self.pack.cell;
        let mut pack = if resize {
            FontPack::new(
                self.pack.name.clone(),
                (cell.0 as i64, cell.1 as i64),
                self.form.baseline,
                self.form.advance,
            )?
        } else {
            let mut pack = self.pack.clone();
            pack.set_metrics(Some(self.form.baseline), Some(self.form.advance))?;
            pack
        };
        let font_path = self.form.font_path.trim().to_string();
        let characters = self.form.characters.clone();
        let options = GenerateOptions {
            font_size: self.form.font_size,
            threshold: self.form.threshold,
            alignment: if self.form.alignment == 0 {
                Alignment::FontSet
            } else {
                Alignment::GlyphWidth
            },
            antialias_scale: self.form.antialias,
            ..GenerateOptions::default()
        };
        let mut unique: Vec<char> = Vec::new();
        for c in characters.chars() {
            if !unique.contains(&c) {
                unique.push(c);
            }
        }
        let state = Arc::new(Mutex::new(JobState {
            total: unique.len(),
            ..JobState::default()
        }));
        let shared = Arc::clone(&state);
        let root = self.root.clone();
        std::thread::spawn(move || {
            let report = Arc::clone(&shared);
            let result = (|| -> CoreResult<(FontPack, usize)> {
                let font = if font_path.is_empty() {
                    None
                } else {
                    let bytes = std::fs::read(&font_path).map_err(|e| {
                        mono_project::resources::io_error(Path::new(&font_path), &e)
                    })?;
                    Some(load_font(bytes)?)
                };
                let chars = rasterize_characters_with_progress(
                    &mut pack,
                    &characters,
                    font.as_ref(),
                    &options,
                    &mut |done, total| {
                        if let Ok(mut s) = report.lock() {
                            s.done = done;
                            s.total = total;
                        }
                    },
                )?;
                save_font_pack(&root, &pack, Some(&chars))?;
                Ok((pack, chars.len()))
            })();
            if let Ok(mut s) = shared.lock() {
                s.result = Some(result.map_err(|e| e.message));
            }
        });
        self.job = Some(state);
        self.error.clear();
        Ok(())
    }

    pub fn poll(&mut self) -> Poll {
        let Some(job) = &self.job else {
            return Poll::Idle;
        };
        let finished = {
            let Ok(mut state) = job.lock() else {
                return Poll::Idle;
            };
            match state.result.take() {
                Some(result) => result,
                None => return Poll::Running(state.done, state.total),
            }
        };
        self.job = None;
        match finished {
            Ok((pack, count)) => {
                self.pack = pack;
                self.current = None;
                self.form.cell_w = self.pack.cell.0 as i64;
                self.form.cell_h = self.pack.cell.1 as i64;
                if let Err(e) = self.refresh_glyphs() {
                    self.error = e.message.clone();
                    return Poll::Finished(Err(e.message));
                }
                Poll::Finished(Ok(count))
            }
            Err(message) => {
                self.error = message.clone();
                Poll::Finished(Err(message))
            }
        }
    }

    /// Block until the worker finishes (tests and shutdown).
    #[cfg(test)]
    pub fn wait(&mut self) -> Poll {
        loop {
            match self.poll() {
                Poll::Running(..) => std::thread::sleep(std::time::Duration::from_millis(5)),
                other => return other,
            }
        }
    }
}

#[cfg(test)]
mod tests {
    #![allow(clippy::unwrap_used, clippy::panic)]
    use super::*;

    fn temp(name: &str) -> PathBuf {
        let dir = std::env::temp_dir().join(format!("mono-fontlab-{name}-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&dir);
        dir
    }

    #[test]
    fn new_pack_uses_v1_defaults_and_refuses_duplicates() {
        let fonts = temp("new");
        let root = create_pack(&fonts, "Clinical 5x7").unwrap();
        assert_eq!(root.file_name().unwrap(), "Clinical_5x7");
        let pack = load_font_pack(&root).unwrap();
        assert_eq!((pack.cell, pack.baseline, pack.advance), ((5, 8), 6, 6));
        assert!(create_pack(&fonts, "Clinical 5x7").is_err());
        assert_eq!(safe_pack_dir("  "), "font_pack");
        let _ = std::fs::remove_dir_all(&fonts);
    }

    #[test]
    fn builtin_generation_runs_off_thread_and_saves() {
        let root = temp("gen");
        let mut lab = FontLab::open(&root, "OLED Font", (5, 8)).unwrap();
        assert!(lab.characters().is_empty());
        lab.edit("characters", "AB1");
        lab.start_generate().unwrap();
        match lab.wait() {
            Poll::Finished(Ok(count)) => assert_eq!(count, 3),
            _ => panic!("generation did not finish"),
        }
        assert_eq!(lab.current, Some('A'));
        assert_eq!(load_font_pack(&root).unwrap().len(), 3);
        let _ = std::fs::remove_dir_all(&root);
    }

    #[test]
    fn edited_glyph_is_saved_when_switching() {
        let root = temp("edit");
        let mut lab = FontLab::open(&root, "OLED Font", (5, 8)).unwrap();
        lab.edit("characters", "AB");
        lab.start_generate().unwrap();
        lab.wait();
        lab.studio.doc.clear(true);
        lab.select('B').unwrap();
        let saved = load_font_pack(&root).unwrap();
        assert!(
            saved
                .glyph('A')
                .unwrap()
                .rows
                .iter()
                .flatten()
                .all(|v| *v == 1)
        );
        assert_eq!(lab.current, Some('B'));
        let _ = std::fs::remove_dir_all(&root);
    }

    #[test]
    fn cell_edits_follow_recommendations_until_overridden() {
        let root = temp("form");
        let mut lab = FontLab::open(&root, "OLED Font", (5, 8)).unwrap();
        lab.edit("cell_w", "8");
        assert_eq!(lab.form.advance, 9);
        lab.edit("advance", "7");
        lab.edit("cell_w", "10");
        assert_eq!(lab.form.advance, 7);
        lab.edit("baseline", "99");
        assert_eq!(lab.form.baseline, 7);
        lab.edit("cell_h", "4");
        assert_eq!(lab.form.baseline, 3);
        let _ = std::fs::remove_dir_all(&root);
    }

    #[test]
    fn invalid_metrics_and_missing_font_report_errors() {
        let root = temp("err");
        let mut lab = FontLab::open(&root, "OLED Font", (5, 8)).unwrap();
        lab.edit("characters", "中");
        lab.start_generate().unwrap();
        assert!(matches!(lab.wait(), Poll::Finished(Err(_))));
        assert!(!lab.error.is_empty());
        let _ = std::fs::remove_dir_all(&root);
    }
}
