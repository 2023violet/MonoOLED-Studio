//! `App` glue for the Pixel Studio workspace and the output workbench: UI
//! callbacks in, `PixelModel` / `OutputModel` properties out.

use std::path::{Path, PathBuf};

use mono_core::CoreError;
use mono_core::formatter::OutputItem;
use mono_core::pixel::{PixelDocument, insert_fontpack_text};
use mono_core::profiles::{OutputProfile, RasterProfile, ThresholdMode};
use mono_core::raster::{RgbaImage, rasterize};
use mono_core::render::posix;
use mono_project::atomic::{atomic_write, atomic_write_json};
use mono_project::fontpack_io::load_font_pack;
use mono_project::resources::hex_digest;
use serde_json::{Map, Value, json};
use slint::Global;

use crate::app::{App, Prompt, model, ss};
use crate::canvas::{image_from_pixels, image_with_colors};
use crate::i18n::trf;
use crate::pixel::{PixelOrigin, PixelStudio, ZOOMS, default_symbol, load_import_source};
use crate::workbench::{MODES, SOURCES, bitmap_item, font_items, merged_profiles};
use crate::{OutputModel, PillTone, PixelModel, ProfileItem};

pub const ANCHORS: [&str; 9] = [
    "top-left",
    "top",
    "top-right",
    "left",
    "center",
    "right",
    "bottom-left",
    "bottom",
    "bottom-right",
];

const TEMPLATE_FIELDS: [&str; 9] = [
    "segment_prefix",
    "segment_suffix",
    "comment_prefix",
    "comment_suffix",
    "data_prefix",
    "data_suffix",
    "line_prefix",
    "line_suffix",
    "line_end",
];

/// V1 legacy glyph exporter cell (`font_generator(cell=(12, 16))`).
const GLYPH_CELL: (usize, usize) = (12, 16);

/// The import dialog's source image and the document it currently produces.
pub struct ImportState {
    pub path: PathBuf,
    pub image: RgbaImage,
    pub doc: Option<PixelDocument>,
}

fn vlsb(rows: &[Vec<u8>], width: usize) -> Vec<u8> {
    let height = rows.len();
    let mut out = vec![0u8; width * height.div_ceil(8)];
    for (y, row) in rows.iter().enumerate() {
        for (x, value) in row.iter().enumerate() {
            if *value != 0 {
                out[(y / 8) * width + x] |= 1 << (y % 8);
            }
        }
    }
    out
}

/// V1 `generate_glyphs` output: `U+XXXX.png`, `glyph_manifest.json`, `glyphs.h`;
/// stale managed PNGs from a previous manifest are removed.
pub fn write_glyph_dir(
    cells: &[(char, Vec<Vec<u8>>)],
    output: &Path,
    font_size: i64,
) -> Result<usize, CoreError> {
    std::fs::create_dir_all(output).map_err(|e| mono_project::resources::io_error(output, &e))?;
    let (w, h) = GLYPH_CELL;
    let manifest_path = output.join("glyph_manifest.json");
    let mut previous: Vec<String> = Vec::new();
    if let Ok(raw) = std::fs::read(&manifest_path) {
        if let Ok(Value::Object(old)) = serde_json::from_slice::<Value>(&raw) {
            if let Some(Value::Object(glyphs)) = old.get("glyphs") {
                for meta in glyphs.values() {
                    if let Some(file) = meta.get("file").and_then(Value::as_str) {
                        let plain = Path::new(file).file_name().is_some_and(|n| n == file);
                        if plain && file.starts_with("U+") && file.ends_with(".png") {
                            previous.push(file.to_string());
                        }
                    }
                }
            }
        }
    }
    let mut glyphs = Map::new();
    let mut arrays = Vec::new();
    let mut written = Vec::new();
    for (ch, rows) in cells {
        let code = u32::from(*ch);
        let file = format!("U+{code:04X}.png");
        let png = mono_project::image_io::encode_bitmap_png(w, h, rows)?;
        atomic_write(&output.join(&file), &png)?;
        let raw = vlsb(rows, w);
        let symbol = format!("glyph_{code:04X}");
        let body: Vec<String> = raw.iter().map(|b| format!("0x{b:02X}")).collect();
        arrays.push(format!(
            "static const unsigned char {symbol}[{}] = {{{}}};",
            raw.len(),
            body.join(",")
        ));
        glyphs.insert(
            ch.to_string(),
            json!({"file": file, "w": w, "h": h, "bytes": raw.len(), "symbol": symbol}),
        );
        written.push(file);
    }
    let manifest = json!({"cell": {"w": w, "h": h}, "font_size": font_size, "glyphs": glyphs});
    atomic_write_json(&manifest_path, &manifest)?;
    let header = format!("#pragma once\n\n{}\n", arrays.join("\n"));
    atomic_write(&output.join("glyphs.h"), header.as_bytes())?;
    previous.sort();
    for stale in previous.iter().filter(|f| !written.contains(f)) {
        let _ = std::fs::remove_file(output.join(stale));
    }
    Ok(cells.len())
}

fn pick_image() -> Option<PathBuf> {
    rfd::FileDialog::new()
        .add_filter("Bitmap", &["png", "bmp"])
        .pick_file()
}

impl App {
    /// The canvas the shared PixelCanvas edits: the Font Lab glyph in workspace 2.
    pub fn studio(&self) -> &PixelStudio {
        match (&self.font, self.workspace) {
            (Some(font), 2) => &font.studio,
            _ => &self.pixel,
        }
    }

    pub fn studio_mut(&mut self) -> &mut PixelStudio {
        match (&mut self.font, self.workspace) {
            (Some(font), 2) => &mut font.studio,
            _ => &mut self.pixel,
        }
    }

    pub fn project_root(&self) -> Option<PathBuf> {
        match (&self.project, &self.session) {
            (Some(p), _) => Some(p.root.clone()),
            (None, Some(s)) => Some(s.root().to_path_buf()),
            _ => None,
        }
    }

    pub(crate) fn undo_limit(&self) -> usize {
        usize::try_from(self.prefs.int("performance.undo_history")).unwrap_or(200)
    }

    pub fn show_prompt(&mut self, prompt: Prompt, title: &str, label: &str, text: &str) {
        self.prompt = Some(prompt);
        if let Some(ui) = self.ui.upgrade() {
            let m = crate::AppModel::get(&ui);
            m.set_prompt_title(title.into());
            m.set_prompt_label(label.into());
            m.set_prompt_text(text.into());
            m.set_prompt_visible(true);
        }
    }

    /// `None` = cancel, `Some(true)` = save first, `Some(false)` = discard.
    pub(crate) fn confirm_unsaved_pixel(&self) -> Option<bool> {
        if !self.pixel.doc.dirty {
            return Some(false);
        }
        let result = rfd::MessageDialog::new()
            .set_title(self.t("dialog.unsaved_title"))
            .set_description(self.t("dialog.unsaved_pixel"))
            .set_buttons(rfd::MessageButtons::YesNoCancel)
            .show();
        match result {
            rfd::MessageDialogResult::Yes => Some(true),
            rfd::MessageDialogResult::No => Some(false),
            _ => None,
        }
    }

    /// Pixel Studio and input preferences (V1 `RuntimeSettings`).
    pub fn apply_pixel_preferences(&mut self) {
        self.pixel.brush = self.prefs.int("pixel_studio.brush_size").clamp(1, 8);
        self.pixel.interpolation = self.prefs.bool("pixel_studio.stroke_interpolation");
        let limit = self.undo_limit();
        self.pixel.doc.set_max_undo(limit);
        let Some(ui) = self.ui.upgrade() else { return };
        let pm = PixelModel::get(&ui);
        pm.set_show_grid(self.prefs.bool("pixel_studio.pixel_grid"));
        pm.set_show_rulers(self.prefs.bool("pixel_studio.rulers"));
        pm.set_show_preview(self.prefs.bool("pixel_studio.actual_preview"));
        pm.set_wheel_zoom(self.prefs.str("input.wheel_action") == "zoom");
        pm.set_middle_pan(self.prefs.str("input.middle_drag") == "pan");
        pm.set_space_pan(self.prefs.str("input.space_drag") == "pan");
        pm.set_brush_size(self.pixel.brush as i32);
        self.load_display_draft();
        self.refresh_display_model();
    }

    // ------------------------------------------------------------- refresh

    pub fn refresh_pixel(&mut self) {
        let Some(ui) = self.ui.upgrade() else { return };
        let pm = PixelModel::get(&ui);
        let p = self.studio();
        let (w, h) = (p.width(), p.height());
        let colors = self.display_colors();
        let pixels = p.display_pixels();
        pm.set_canvas(image_with_colors(
            w,
            h,
            &pixels,
            colors.fill,
            colors.background,
        ));
        self.refresh_overlay(&pixels);
        let p = self.studio();
        pm.set_doc_w(w as i32);
        pm.set_doc_h(h as i32);
        pm.set_asset_locked(p.is_asset());
        let title = match (&self.font, self.workspace) {
            (Some(font), 2) => font
                .current
                .map(|c| format!("{} · '{c}'", font.pack.name))
                .unwrap_or_else(|| font.pack.name.clone()),
            _ if p.path.is_some() || p.is_asset() => p.title(),
            _ => self.t("pixel.title"),
        };
        pm.set_title(ss(format!(
            "{title}{}",
            if p.doc.dirty { " ●" } else { "" }
        )));
        pm.set_tool(p.tool.index());
        pm.set_brush_size(p.brush as i32);
        match p.overlay_selection() {
            Some((x, y, sw, sh)) => {
                pm.set_has_selection(true);
                pm.set_sel_x(x as i32);
                pm.set_sel_y(y as i32);
                pm.set_sel_w(sw as i32);
                pm.set_sel_h(sh as i32);
            }
            None => pm.set_has_selection(false),
        }
        match p.key_cursor {
            Some((x, y)) => {
                pm.set_has_key_cursor(true);
                pm.set_key_x(x as i32);
                pm.set_key_y(y as i32);
            }
            None => pm.set_has_key_cursor(false),
        }
        pm.set_has_clipboard(p.clipboard.is_some());
        pm.set_info_text(ss(format!("{w} × {h} · {} B VLSB", w * h.div_ceil(8))));
        let selection = match p.selection {
            Some((x, y, sw, sh)) => format!(
                "{} · {}",
                trf(
                    &self.lang,
                    "pixel.selection",
                    &[
                        ("x", x.to_string()),
                        ("y", y.to_string()),
                        ("w", sw.to_string()),
                        ("h", sh.to_string())
                    ]
                ),
                trf(
                    &self.lang,
                    "pixel.selection.lit",
                    &[("lit", p.lit_in_selection().to_string())]
                )
            ),
            None => self.t("pixel.selection.none"),
        };
        pm.set_selection_text(ss(selection));
        self.refresh_pixel_cursor();
        self.refresh_app();
        // Font Lab shares this canvas: keep the pack title/state in step.
        if self.workspace == 2 {
            self.refresh_font();
        }
    }

    fn refresh_pixel_cursor(&self) {
        let Some(ui) = self.ui.upgrade() else { return };
        let p = self.studio();
        let text = match p.hover.or(p.key_cursor) {
            Some((x, y)) => {
                let (xu, yu) = (x as usize, y as usize);
                trf(
                    &self.lang,
                    "pixel.status",
                    &[
                        ("x", x.to_string()),
                        ("y", y.to_string()),
                        ("value", p.doc.get(xu, yu).to_string()),
                        ("page", (yu / 8).to_string()),
                        ("bit", (yu % 8).to_string()),
                        ("byte", ((yu / 8) * p.width() + xu).to_string()),
                    ],
                )
            }
            None => self.t("font.status.pixel"),
        };
        PixelModel::get(&ui).set_cursor_text(ss(text));
    }

    // ------------------------------------------------------------- input

    pub fn pixel_pointer(&mut self, phase: &str, x: i32, y: i32, button: i32) {
        let (x, y) = (i64::from(x), i64::from(y));
        let changed = match phase {
            "down" => self.studio_mut().pointer_down(x, y, button == 1),
            "move" => self.studio_mut().pointer_move(x, y),
            "up" => self.studio_mut().pointer_up(x, y),
            "hover" => {
                self.studio_mut().pointer_move(x, y);
                false
            }
            _ => {
                self.studio_mut().hover = None;
                false
            }
        };
        if changed {
            self.refresh_pixel();
        } else {
            self.refresh_pixel_cursor();
        }
        if phase == "up" && changed {
            self.bench_document_changed();
        }
    }

    pub fn pixel_key(&mut self, key: &str) {
        if self.studio_mut().key(key) {
            self.refresh_pixel();
            self.bench_document_changed();
        }
    }

    pub fn pixel_zoom(&mut self, index: i32) {
        let Some(ui) = self.ui.upgrade() else { return };
        let zoom = usize::try_from(index - 1)
            .ok()
            .and_then(|i| ZOOMS.get(i))
            .copied()
            .unwrap_or(0);
        let pm = PixelModel::get(&ui);
        pm.set_zoom_index(index);
        pm.set_zoom(zoom as f32);
    }

    /// V1 wheel zoom: +-2 px within 4..40 (from Fit, start at the nearest step).
    pub fn pixel_zoom_step(&mut self, direction: i32) {
        let Some(ui) = self.ui.upgrade() else { return };
        let pm = PixelModel::get(&ui);
        let current = pm.get_zoom() as i32;
        let current = if current == 0 { 10 } else { current };
        let next = (current + 2 * direction.signum()).clamp(4, 40);
        pm.set_zoom(next as f32);
        let index = ZOOMS
            .iter()
            .position(|z| *z == next)
            .map_or(0, |i| i as i32 + 1);
        pm.set_zoom_index(index);
    }

    pub fn pixel_action(&mut self, action: &str) {
        let result: Result<(), CoreError> = (|| {
            match action {
                "new" => {
                    let Some(save_first) = self.confirm_unsaved_pixel() else {
                        return Ok(());
                    };
                    if save_first && !self.pixel_save()? {
                        return Ok(());
                    }
                    let limit = self.undo_limit();
                    self.pixel.replace(PixelDocument::new(32, 16)?, None, limit);
                }
                "open" => {
                    let Some(path) = pick_image() else {
                        return Ok(());
                    };
                    self.pixel_begin_import(&path)?;
                }
                "save" => {
                    self.pixel_save()?;
                }
                "save-bin" => {
                    let Some(path) = rfd::FileDialog::new()
                        .set_file_name("oled_bitmap.bin")
                        .add_filter("BIN", &["bin"])
                        .save_file()
                    else {
                        return Ok(());
                    };
                    self.pixel.save_bin(&path)?;
                    self.set_status(posix(&path));
                }
                "save-c" => {
                    let Some(path) = rfd::FileDialog::new()
                        .set_file_name("oled_bitmap.h")
                        .add_filter("C Header", &["h"])
                        .save_file()
                    else {
                        return Ok(());
                    };
                    let symbol = default_symbol(self.pixel.path.as_deref());
                    let (title, label) = (self.t("pixel.action.export_c"), self.t("pixel.symbol"));
                    self.show_prompt(Prompt::CSymbol(path), &title, &label, &symbol);
                }
                "font-generator" => {
                    let (title, label) =
                        (self.t("pixel.action.font"), self.t("pixel.font.characters"));
                    self.show_prompt(Prompt::GlyphCharacters, &title, &label, "");
                }
                "canvas-size" => {
                    if self.pixel.asset_locked() {
                        self.set_status(self.t("asset.size_locked"));
                        return Ok(());
                    }
                    if let Some(ui) = self.ui.upgrade() {
                        let pm = PixelModel::get(&ui);
                        pm.set_resize_w(self.pixel.width() as i32);
                        pm.set_resize_h(self.pixel.height() as i32);
                        pm.set_resize_anchor(4);
                        pm.set_dialog_error("".into());
                        pm.set_dialog(1);
                    }
                }
                "insert-text" => {
                    if self.font_packs.is_empty() {
                        self.set_status(self.t("pixel.font_missing"));
                        return Ok(());
                    }
                    if let Some(ui) = self.ui.upgrade() {
                        let pm = PixelModel::get(&ui);
                        pm.set_font_packs(model(self.font_packs.iter().map(ss).collect()));
                        let (x, y) = self.pixel.selection.map_or((0, 0), |s| (s.0, s.1));
                        pm.set_text_x(x as i32);
                        pm.set_text_y(y as i32);
                        pm.set_dialog_error("".into());
                        pm.set_dialog(3);
                    }
                }
                other => {
                    if !self.studio_mut().try_action(other)? {
                        self.refresh_pixel();
                        return Ok(());
                    }
                }
            }
            self.refresh_pixel();
            self.bench_document_changed();
            Ok(())
        })();
        if let Err(e) = result {
            if e.code == "E-ASSET-SIZE-LOCKED" {
                let message = self.t("asset.size_locked");
                self.set_status(message);
            } else {
                self.error(&e);
            }
            self.refresh_pixel();
        }
    }

    /// V1 `save_png`: reuse the current `.png` path, else ask. Returns false on cancel.
    pub fn pixel_save(&mut self) -> Result<bool, CoreError> {
        if self.pixel.is_asset() {
            return self.pixel_save_asset();
        }
        let path = match &self.pixel.path {
            Some(p) if p.extension().is_some_and(|e| e.eq_ignore_ascii_case("png")) => p.clone(),
            _ => {
                let mut dialog = rfd::FileDialog::new().add_filter("PNG", &["png"]);
                if let Some(root) = self.project_root() {
                    dialog = dialog.set_directory(root);
                }
                let Some(p) = dialog.set_file_name("bitmap.png").save_file() else {
                    return Ok(false);
                };
                p
            }
        };
        let saved = self.pixel.save_png(&path)?;
        self.set_status(posix(&saved));
        self.scan_project_files();
        self.refresh_navigator();
        self.refresh_pixel();
        Ok(true)
    }

    /// Write the asset document back to its project PNG. Returns false on cancel.
    fn pixel_save_asset(&mut self) -> Result<bool, CoreError> {
        let rel = match &self.pixel.origin {
            PixelOrigin::Asset { rel, .. } => rel.clone(),
            _ => String::new(),
        };
        match self.pixel.save_asset(false) {
            Ok(_) => {}
            Err(e) if e.code == "E-ASSET-EXTERNAL-MODIFICATION" => {
                if !self.interactive {
                    return Err(e);
                }
                let answer = rfd::MessageDialog::new()
                    .set_title(self.t("dialog.unsaved_title"))
                    .set_description(self.t("asset.external_changed"))
                    .set_buttons(rfd::MessageButtons::YesNo)
                    .show();
                if answer != rfd::MessageDialogResult::Yes {
                    return Ok(false);
                }
                self.pixel.save_asset(true)?;
            }
            Err(e) if e.code == "E-ASSET-ENCODE-POLARITY" => {
                return Err(CoreError::invalid(self.t("asset.polarity")));
            }
            Err(e) => return Err(e),
        }
        if let Some(session) = self.session.as_mut() {
            session.clear_resource_cache();
        }
        self.refresh_canvas();
        self.refresh_navigator();
        self.refresh_pixel();
        self.set_status(trf(&self.lang, "asset.saved", &[("path", rel)]));
        Ok(true)
    }

    pub fn pixel_begin_import(&mut self, path: &Path) -> Result<(), CoreError> {
        let image = load_import_source(path)?;
        self.import = Some(ImportState {
            path: path.to_path_buf(),
            image,
            doc: None,
        });
        if let Some(ui) = self.ui.upgrade() {
            let pm = PixelModel::get(&ui);
            pm.set_import_path(ss(posix(path)));
            pm.set_dialog_error("".into());
            pm.set_dialog(2);
        }
        self.pixel_import_changed();
        Ok(())
    }

    pub fn pixel_import_changed(&mut self) {
        let Some(ui) = self.ui.upgrade() else { return };
        let pm = PixelModel::get(&ui);
        let Some(import) = self.import.as_mut() else {
            return;
        };
        let clamp = |v: i32| v.clamp(0, 255) as u8;
        let profile = RasterProfile {
            threshold_mode: if pm.get_import_mode() == 1 {
                ThresholdMode::RgbAll
            } else {
                ThresholdMode::Luma
            },
            luma_threshold: clamp(pm.get_import_threshold()),
            red_threshold: clamp(pm.get_import_red()),
            green_threshold: clamp(pm.get_import_green()),
            blue_threshold: clamp(pm.get_import_blue()),
            invert_source: pm.get_import_invert(),
            ..RasterProfile::default()
        };
        match rasterize(&import.image, &profile, None).and_then(|b| {
            PixelDocument::from_rows(&b.rows().map(<[u8]>::to_vec).collect::<Vec<_>>())
        }) {
            Ok(doc) => {
                pm.set_import_preview(image_from_pixels(doc.width(), doc.height(), doc.pixels()));
                pm.set_import_info(ss(format!("{} × {}", doc.width(), doc.height())));
                pm.set_dialog_error("".into());
                import.doc = Some(doc);
            }
            Err(e) => {
                pm.set_dialog_error(ss(e.message));
                import.doc = None;
            }
        }
    }

    pub fn pixel_dialog_accepted(&mut self) {
        let Some(ui) = self.ui.upgrade() else { return };
        let pm = PixelModel::get(&ui);
        let result: Result<(), CoreError> = (|| {
            match pm.get_dialog() {
                1 => {
                    let anchor = ANCHORS
                        .get(pm.get_resize_anchor().max(0) as usize)
                        .copied()
                        .unwrap_or("center");
                    self.pixel.resize(
                        i64::from(pm.get_resize_w()),
                        i64::from(pm.get_resize_h()),
                        anchor,
                    )?;
                }
                2 => {
                    let Some(save_first) = self.confirm_unsaved_pixel() else {
                        return Ok(());
                    };
                    if save_first && !self.pixel_save()? {
                        return Ok(());
                    }
                    let Some(import) = self.import.take() else {
                        return Ok(());
                    };
                    let Some(doc) = import.doc else {
                        return Err(CoreError::invalid("image must not be empty"));
                    };
                    let limit = self.undo_limit();
                    self.pixel.replace(doc, Some(import.path), limit);
                }
                3 => {
                    let text = pm.get_text_value().to_string();
                    let pack_id = self
                        .font_packs
                        .get(pm.get_text_font().max(0) as usize)
                        .cloned()
                        .unwrap_or_default();
                    if text.is_empty() || pack_id.is_empty() {
                        pm.set_dialog(0);
                        return Ok(());
                    }
                    let root = self.project_root().unwrap_or_default();
                    let pack = load_font_pack(&root.join(&pack_id))?;
                    let (x, y) = (i64::from(pm.get_text_x()), i64::from(pm.get_text_y()));
                    let (w, h) = insert_fontpack_text(
                        &mut self.pixel.doc,
                        &pack,
                        &text,
                        x,
                        y,
                        pm.get_text_tracking(),
                    )?;
                    let fits = x >= 0
                        && y >= 0
                        && x as usize + w <= self.pixel.width()
                        && y as usize + h <= self.pixel.height();
                    self.pixel.selection =
                        (w > 0 && h > 0 && fits).then_some((x as usize, y as usize, w, h));
                }
                _ => {}
            }
            pm.set_dialog(0);
            Ok(())
        })();
        match result {
            Ok(()) => {
                self.refresh_pixel();
                self.bench_document_changed();
            }
            Err(e) => pm.set_dialog_error(ss(e.message)),
        }
    }

    /// Prompts raised by Pixel Studio / the workbench. Returns false if not ours.
    pub fn pixel_prompt(&mut self, prompt: Prompt, text: &str) -> bool {
        let result: Result<(), CoreError> = match prompt {
            Prompt::CSymbol(path) => {
                if text.is_empty() {
                    return true;
                }
                self.pixel
                    .save_c_header(&path, text)
                    .map(|()| self.set_status(posix(&path)))
            }
            Prompt::GlyphCharacters => {
                if text.is_empty() {
                    return true;
                }
                let Some(output) = rfd::FileDialog::new()
                    .set_title(self.t("pixel.font.output"))
                    .pick_folder()
                else {
                    return true;
                };
                mono_font::render_centered_cells(text, None, 12, GLYPH_CELL, 128)
                    .and_then(|cells| write_glyph_dir(&cells, &output, 12))
                    .map(|count| {
                        let message = trf(
                            &self.lang,
                            "pixel.font.done",
                            &[("count", count.to_string())],
                        );
                        self.set_status(message);
                    })
            }
            Prompt::ProfileId => {
                if text.is_empty() {
                    return true;
                }
                let (title, label) = (self.t("bench.save_as"), self.t("bench.profile_name"));
                self.show_prompt(Prompt::ProfileName(text.to_string()), &title, &label, text);
                Ok(())
            }
            Prompt::ProfileName(id) => {
                if text.is_empty() {
                    return true;
                }
                let previous_id = self.bench.profile_id.clone();
                let previous_profile = self.bench.profile.clone();
                let previous_dirty = self.bench.profile_dirty;
                let mut profile = previous_profile.clone();
                profile.name = text.to_string();
                self.bench.profile_id = id;
                self.bench.profile = profile;
                let result = self.bench_commit_profile(true);
                if result.is_err() {
                    self.bench.profile_id = previous_id;
                    self.bench.profile = previous_profile;
                    self.bench.profile_dirty = previous_dirty;
                }
                result
            }
            _ => return false,
        };
        if let Err(e) = result {
            self.bench.message = e.message.clone();
            self.error(&e);
        }
        self.refresh_bench();
        true
    }

    // ------------------------------------------------------------ workbench

    fn saved_profiles(&self) -> (String, Vec<(String, OutputProfile)>) {
        self.project
            .as_ref()
            .and_then(|p| p.output_profiles().ok())
            .unwrap_or_else(|| ("ssd1306_vlsb_c".into(), Vec::new()))
    }

    /// Load the project's active profile (project open / workspace switch).
    pub fn bench_load_active(&mut self) {
        let (active, saved) = self.saved_profiles();
        let merged = merged_profiles(&saved);
        let (id, profile) = merged
            .iter()
            .find(|(id, _)| *id == active)
            .or_else(|| merged.first())
            .cloned()
            .unwrap_or_default();
        self.bench.profile_id = id;
        self.bench.profile = profile;
        self.bench.profile_dirty = false;
        self.bench.last = None;
        self.refresh_bench();
    }

    pub fn refresh_bench(&mut self) {
        let Some(ui) = self.ui.upgrade() else { return };
        let om = OutputModel::get(&ui);
        let b = &self.bench;
        om.set_sources(model(
            SOURCES
                .iter()
                .map(|s| ss(self.t(&format!("bench.source.{s}"))))
                .collect(),
        ));
        om.set_source(b.source as i32);
        let (active, saved) = self.saved_profiles();
        let merged = merged_profiles(&saved);
        let in_project = saved.iter().any(|(id, _)| *id == b.profile_id);
        om.set_profile_dirty(b.profile_dirty);
        om.set_profile_source(i32::from(in_project));
        om.set_profile_is_default(active == b.profile_id);
        om.set_profile_state_text(ss(if b.profile_dirty {
            self.t("bench.profile_state.draft")
        } else if in_project {
            self.t("bench.profile_state.project")
        } else {
            self.t("bench.profile_state.builtin")
        }));
        om.set_profile_state_tone(if b.profile_dirty {
            PillTone::Warning
        } else if in_project {
            PillTone::Success
        } else {
            PillTone::Neutral
        });
        om.set_profiles(model(
            merged
                .iter()
                .map(|(id, p)| ProfileItem {
                    id: ss(id),
                    name: ss(&p.name),
                })
                .collect(),
        ));
        om.set_profile_names(model(merged.iter().map(|(_, p)| ss(&p.name)).collect()));
        om.set_profile(
            merged
                .iter()
                .position(|(id, _)| *id == b.profile_id)
                .unwrap_or(0) as i32,
        );
        om.set_project_profiles(self.project.is_some());
        om.set_font_packs(model(self.font_packs.iter().map(ss).collect()));
        om.set_modes(model(MODES.iter().map(|(label, _, _)| ss(label)).collect()));
        om.set_mode(b.mode_index() as i32);
        let pick = |key: &str, first: &str| i32::from(b.field(key) != first);
        om.set_bit_order(pick("encoding.bit_order", "msb_first"));
        om.set_polarity(pick("encoding.polarity", "one_is_lit"));
        om.set_container(pick("text.container", "text"));
        om.set_radix(pick("text.radix", "hex"));
        om.set_index_mode(match b.field("text.index_mode").as_str() {
            "inline" => 1,
            "sidecar" => 2,
            _ => 0,
        });
        let int = |key: &str| b.field(key).parse::<i32>().unwrap_or(0);
        om.set_bytes_per_line(int("text.bytes_per_line"));
        om.set_index_per_line(int("text.index_entries_per_line"));
        om.set_minimal(b.field("text.minimal_data") == "true");
        om.set_compact(b.field("text.compact_spacing") == "true");
        om.set_uppercase(b.field("text.uppercase") == "true");
        om.set_threshold_mode(pick("raster.threshold_mode", "luma"));
        om.set_threshold(int("raster.luma_threshold"));
        om.set_red(int("raster.red_threshold"));
        om.set_green(int("raster.green_threshold"));
        om.set_blue(int("raster.blue_threshold"));
        om.set_invert(b.field("raster.invert_source") == "true");
        om.set_template_keys(model(TEMPLATE_FIELDS.iter().map(ss).collect()));
        om.set_template_labels(model(
            TEMPLATE_FIELDS
                .iter()
                .map(|k| ss(self.t(&format!("bench.template.{k}"))))
                .collect(),
        ));
        om.set_template_values(model(
            TEMPLATE_FIELDS
                .iter()
                .map(|k| ss(b.field(&format!("text.{k}"))))
                .collect(),
        ));
        om.set_message(ss(&b.message));
        om.set_lines(model(b.display_text().split('\n').map(ss).collect()));
    }

    fn bench_apply(&mut self) {
        self.bench.profile_dirty = true;
        if self.bench.last.is_some() {
            self.bench_generate();
        }
    }

    /// Write the in-memory profile to the project; the only path that persists it.
    pub fn bench_commit_profile(&mut self, activate: bool) -> Result<(), CoreError> {
        let no_project = CoreError::invalid(self.t("bench.no_project"));
        let Some(project) = self.project.as_mut() else {
            self.bench.message = no_project.message.clone();
            return Err(no_project);
        };
        let id = self.bench.profile_id.clone();
        match project.upsert_output_profile(&id, &self.bench.profile, activate) {
            Ok(()) => {
                self.bench.profile_dirty = false;
                self.bench.message = tr_static(&self.lang, "bench.profile_saved");
                Ok(())
            }
            Err(e) => {
                self.bench.message = trf(
                    &self.lang,
                    "bench.profile_save_failed",
                    &[("error", e.message.clone())],
                );
                Err(e)
            }
        }
    }

    /// Point the project's active profile at the current selection (builtins allowed).
    pub fn bench_set_default(&mut self) -> Result<(), CoreError> {
        let no_project = CoreError::invalid(self.t("bench.no_project"));
        let Some(project) = self.project.as_mut() else {
            self.bench.message = no_project.message.clone();
            return Err(no_project);
        };
        let result = project.set_active_output_profile(&self.bench.profile_id);
        match result {
            Ok(()) => {
                self.bench.message = tr_static(&self.lang, "bench.profile_default_set");
                Ok(())
            }
            Err(e) => {
                self.bench.message = e.message.clone();
                Err(e)
            }
        }
    }

    pub fn bench_field(&mut self, key: &str, value: &str) {
        match self.bench.set_field(key, value) {
            Ok(()) => self.bench_apply(),
            Err(e) => self.bench.message = e.message,
        }
        self.refresh_bench();
    }

    pub fn bench_source(&mut self, index: i32) {
        self.bench.source = usize::try_from(index).unwrap_or(0).min(SOURCES.len() - 1);
        self.bench_generate();
        self.refresh_bench();
    }

    pub fn bench_profile(&mut self, index: i32) {
        let (_, saved) = self.saved_profiles();
        let merged = merged_profiles(&saved);
        let Some((id, profile)) = usize::try_from(index)
            .ok()
            .and_then(|i| merged.get(i))
            .map(|(id, profile)| (id.clone(), profile.clone()))
        else {
            self.refresh_bench();
            return;
        };
        if id == self.bench.profile_id {
            // Re-selecting the current entry must not drop an edited draft.
            self.refresh_bench();
            return;
        }
        if self.bench.profile_dirty && self.interactive {
            let answer = rfd::MessageDialog::new()
                .set_title(self.t("dialog.unsaved_title"))
                .set_description(self.t("bench.draft_switch_confirm"))
                .set_buttons(rfd::MessageButtons::YesNo)
                .show();
            if answer != rfd::MessageDialogResult::Yes {
                self.refresh_bench();
                return;
            }
        }
        self.bench.profile_id = id;
        self.bench.profile = profile;
        self.bench.profile_dirty = false;
        if self.bench.last.is_some() {
            self.bench_generate();
        }
        self.refresh_bench();
    }

    /// V1 regenerates on canvas edits when the source is the canvas/selection.
    pub fn bench_document_changed(&mut self) {
        if self.bench.last.is_some() && self.bench.source <= 1 {
            self.bench_generate();
            self.refresh_bench();
        }
    }

    fn bench_items(&mut self) -> Result<Vec<OutputItem>, CoreError> {
        let profile = self.bench.profile.clone();
        match self.bench.source_kind() {
            "canvas" => {
                let name = self
                    .pixel
                    .path
                    .as_deref()
                    .and_then(Path::file_stem)
                    .map_or_else(
                        || "oled_bitmap".into(),
                        |s| s.to_string_lossy().into_owned(),
                    );
                Ok(vec![bitmap_item(&name, &self.pixel.doc.rows(), &profile)?])
            }
            "selection" => {
                if self.pixel.selection.is_none() {
                    return Err(CoreError::invalid(self.t("bench.no_selection")));
                }
                Ok(vec![bitmap_item(
                    "selection",
                    &self.pixel.selection_rows(),
                    &profile,
                )?])
            }
            "scene" => {
                let name = self
                    .project
                    .as_ref()
                    .map(mono_project::project::ProjectWorkspace::active_screen)
                    .unwrap_or_else(|| "scene".into());
                let Some(fb) = self.current_framebuffer() else {
                    return Err(CoreError::invalid(self.t("bench.no_project")));
                };
                let rows: Vec<Vec<u8>> = fb.rows().map(<[u8]>::to_vec).collect();
                Ok(vec![bitmap_item(&name, &rows, &profile)?])
            }
            "font" => {
                let root = self
                    .project_root()
                    .ok_or_else(|| CoreError::invalid(self.t("bench.no_project")))?;
                let pack_id = self
                    .font_packs
                    .get(self.bench_font_index())
                    .cloned()
                    .ok_or_else(|| CoreError::invalid(self.t("pixel.font_missing")))?;
                let pack = load_font_pack(&root.join(pack_id))?;
                font_items(&pack, &self.bench.characters, &profile)
            }
            _ => {
                let path = PathBuf::from(self.bench.image_path.trim());
                let bytes = std::fs::read(&path)
                    .map_err(|e| mono_project::resources::io_error(&path, &e))?;
                let decoded = mono_project::image_io::decode_image(&bytes)?;
                let image = RgbaImage::new(decoded.width, decoded.height, decoded.rgba)?;
                let bitmap = rasterize(&image, &profile.raster, None)?;
                let rows: Vec<Vec<u8>> = bitmap.rows().map(<[u8]>::to_vec).collect();
                let name = path
                    .file_stem()
                    .map_or_else(|| "image".into(), |s| s.to_string_lossy().into_owned());
                Ok(vec![bitmap_item(&name, &rows, &profile)?])
            }
        }
    }

    fn bench_font_index(&self) -> usize {
        self.ui.upgrade().map_or(0, |ui| {
            OutputModel::get(&ui).get_font_pack().max(0) as usize
        })
    }

    pub fn bench_generate(&mut self) {
        let result = self.bench_items().and_then(|items| {
            let symbol = items.first().map(|i| i.name.clone()).unwrap_or_default();
            self.bench.generate(&items, &symbol)
        });
        match result {
            Ok(()) => self.bench.message.clear(),
            Err(e) => self.bench.message = e.message,
        }
    }

    pub fn bench_action(&mut self, action: &str) {
        if let Some(ui) = self.ui.upgrade() {
            let om = OutputModel::get(&ui);
            self.bench.characters = om.get_characters().to_string();
            self.bench.image_path = om.get_image_path().to_string();
        }
        match action {
            "generate" => self.bench_generate(),
            "clear" => {
                self.bench.last = None;
                self.bench.message.clear();
            }
            "copy" => {
                if let Some(text) = self.bench.copy_text() {
                    self.bench.message =
                        match arboard::Clipboard::new().and_then(|mut c| c.set_text(text)) {
                            Ok(()) => self.t("bench.copied"),
                            Err(e) => e.to_string(),
                        };
                }
            }
            "save" => {
                if self.bench.last.is_none() {
                    self.bench_generate();
                } else if let Err(e) = self.bench_save() {
                    self.bench.message = e.message;
                }
            }
            "commit-profile" => {
                let _ = self.bench_commit_profile(false);
            }
            "set-default-profile" => {
                let _ = self.bench_set_default();
            }
            "save-as" => {
                if self.project.is_some() {
                    let (title, label) = (self.t("bench.save_as"), self.t("bench.profile_id"));
                    self.show_prompt(Prompt::ProfileId, &title, &label, "");
                }
            }
            "delete-profile" => {
                let id = self.bench.profile_id.clone();
                let (_, saved) = self.saved_profiles();
                if !saved.iter().any(|(s, _)| *s == id) {
                    self.bench.message = self.t("bench.builtin_not_saved");
                } else if let Some(project) = self.project.as_mut() {
                    match project.delete_output_profile(&id) {
                        Ok(()) => self.bench_load_active(),
                        Err(e) => self.bench.message = e.message,
                    }
                }
            }
            "browse-image" => {
                if let Some(path) = pick_image() {
                    self.bench.image_path = posix(&path);
                    if let Some(ui) = self.ui.upgrade() {
                        OutputModel::get(&ui).set_image_path(ss(&self.bench.image_path));
                    }
                    self.bench_generate();
                }
            }
            _ => {}
        }
        self.refresh_bench();
    }

    fn bench_save(&mut self) -> Result<(), CoreError> {
        let Some((raw, sidecar)) = self.bench.save_payload() else {
            return Ok(());
        };
        let binary = self.bench.is_binary();
        let mut dialog =
            rfd::FileDialog::new().set_file_name(if binary { "bitmap.bin" } else { "bitmap.h" });
        dialog = if binary {
            dialog.add_filter("BIN", &["bin"])
        } else {
            dialog
                .add_filter("Header", &["h"])
                .add_filter("Text", &["txt"])
        };
        if let Some(root) = self.project_root() {
            dialog = dialog.set_directory(root);
        }
        let Some(path) = dialog.save_file() else {
            return Ok(());
        };
        atomic_write(&path, &raw)?;
        if let Some(text) = sidecar {
            let stem = path
                .file_stem()
                .map(|s| s.to_string_lossy().into_owned())
                .unwrap_or_default();
            atomic_write(
                &path.with_file_name(format!("{stem}_index.h")),
                text.as_bytes(),
            )?;
        }
        self.bench.message = trf(&self.lang, "bench.saved", &[("sha", hex_digest(&raw))]);
        Ok(())
    }
}

fn tr_static(lang: &str, key: &str) -> String {
    crate::i18n::tr(lang, key)
}

#[cfg(test)]
mod tests {
    #![allow(clippy::unwrap_used)]
    use super::*;
    use std::path::Path;

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
        let root = std::env::temp_dir().join(format!("mono-bench-{name}-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&root);
        let repo = Path::new(env!("CARGO_MANIFEST_DIR")).join("../..");
        copy_dir(&repo.join("test_assets/projects/curing_lite"), &root);
        let prefs = crate::prefs::Preferences::load_from(root.join("prefs.json"));
        let mut app = App::new(slint::Weak::default(), prefs);
        app.open_project(&root.join("project.oled.json")).unwrap();
        (app, root)
    }

    fn manifest_bytes(app: &App) -> Vec<u8> {
        let path = app.project.as_ref().unwrap().path.clone();
        std::fs::read(path).unwrap()
    }

    fn manifest_json(app: &App) -> Value {
        serde_json::from_slice(&manifest_bytes(app)).unwrap()
    }

    #[test]
    fn switching_profiles_discards_the_draft_without_writing() {
        let (mut app, root) = app("switch");
        app.bench_field("text.bytes_per_line", "8");
        assert!(app.bench.profile_dirty);
        let before = manifest_bytes(&app);
        app.bench_profile(1);
        assert_eq!(app.bench.profile_id, "row_msb_c51");
        assert!(!app.bench.profile_dirty);
        assert_eq!(app.bench.field("text.bytes_per_line"), "16");
        assert_eq!(manifest_bytes(&app), before);
        let _ = std::fs::remove_dir_all(&root);
    }

    #[test]
    fn builtin_selection_does_not_write_the_manifest() {
        let (mut app, root) = app("builtin");
        let before = manifest_bytes(&app);
        app.bench_profile(1);
        assert_eq!(app.bench.profile_id, "row_msb_c51");
        assert_eq!(manifest_bytes(&app), before);
        assert!(!app.bench.profile_dirty);
        let _ = std::fs::remove_dir_all(&root);
    }

    #[test]
    fn field_edits_stay_in_memory_until_commit() {
        let (mut app, root) = app("field");
        let before = manifest_bytes(&app);
        app.bench_field("text.bytes_per_line", "8");
        assert_eq!(app.bench.field("text.bytes_per_line"), "8");
        assert!(app.bench.profile_dirty);
        assert_eq!(manifest_bytes(&app), before);
        app.bench_commit_profile(true).unwrap();
        assert!(!app.bench.profile_dirty);
        let json = manifest_json(&app);
        assert_eq!(
            json.pointer("/output_workbench/profiles/ssd1306_vlsb_c/text/bytes_per_line"),
            Some(&Value::from(8))
        );
        assert_eq!(
            json.pointer("/output_workbench/active_profile"),
            Some(&Value::from("ssd1306_vlsb_c"))
        );
        let _ = std::fs::remove_dir_all(&root);
    }

    #[test]
    fn open_project_loads_the_active_profile() {
        let (mut app, root) = app("active");
        let path = app.project.as_ref().unwrap().path.clone();
        let mut project = mono_project::project::ProjectWorkspace::load(&path).unwrap();
        project.set_active_output_profile("row_msb_c51").unwrap();
        app.bench.profile_id = "ssd1306_vlsb_c".into();
        app.open_project(&path).unwrap();
        assert_eq!(app.bench.profile_id, "row_msb_c51");
        assert!(!app.bench.profile_dirty);
        let _ = std::fs::remove_dir_all(&root);
    }

    #[test]
    fn default_may_reference_a_builtin_without_copying_it() {
        let (mut app, root) = app("default");
        app.bench_profile(2);
        let id = app.bench.profile_id.clone();
        app.bench_set_default().unwrap();
        let json = manifest_json(&app);
        assert_eq!(
            json.pointer("/output_workbench/active_profile"),
            Some(&Value::from(id.as_str()))
        );
        assert!(
            json.pointer(&format!("/output_workbench/profiles/{id}"))
                .is_none(),
            "the default builtin must not be written as a project profile"
        );
        let _ = std::fs::remove_dir_all(&root);
    }

    #[test]
    fn legacy_manifest_without_workbench_opens_with_defaults() {
        let (mut app, root) = app("legacy");
        let path = app.project.as_ref().unwrap().path.clone();
        let mut json = manifest_json(&app);
        json.as_object_mut().unwrap().remove("output_workbench");
        std::fs::write(&path, serde_json::to_vec_pretty(&json).unwrap()).unwrap();
        app.open_project(&path).unwrap();
        let (active, saved) = app.saved_profiles();
        assert_eq!(active, "ssd1306_vlsb_c");
        assert_eq!(app.bench.profile_id, "ssd1306_vlsb_c");
        // `output_profiles` reports the builtin default when the key is absent.
        assert_eq!(saved.len(), 1);
        let _ = std::fs::remove_dir_all(&root);
    }

    #[test]
    fn open_scene_file_resets_the_workbench_to_the_builtin() {
        let (mut app, root) = app("scene-reset");
        app.bench_profile(2);
        app.bench_field("text.bytes_per_line", "8");
        assert!(app.bench.profile_dirty);
        app.open_scene_file(&root.join("scenes/123.json")).unwrap();
        assert!(app.project.is_none());
        assert_eq!(app.bench.profile_id, "ssd1306_vlsb_c");
        assert!(!app.bench.profile_dirty);
        let _ = std::fs::remove_dir_all(&root);
    }

    #[test]
    fn reselecting_the_current_profile_keeps_the_draft() {
        let (mut app, root) = app("reselect");
        app.bench_field("text.bytes_per_line", "8");
        assert!(app.bench.profile_dirty);
        let before = manifest_bytes(&app);
        app.bench_profile(0);
        assert!(app.bench.profile_dirty);
        assert_eq!(app.bench.field("text.bytes_per_line"), "8");
        assert_eq!(manifest_bytes(&app), before);
        let _ = std::fs::remove_dir_all(&root);
    }

    #[test]
    fn failed_save_as_keeps_the_previous_profile() {
        let (mut app, root) = app("save-as-fail");
        let before_id = app.bench.profile_id.clone();
        let before_name = app.bench.profile.name.clone();
        let before_manifest = manifest_bytes(&app);
        assert!(app.pixel_prompt(Prompt::ProfileName("Bad ID".into()), "Renamed"));
        assert_eq!(app.bench.profile_id, before_id);
        assert_eq!(app.bench.profile.name, before_name);
        assert!(!app.bench.profile_dirty);
        assert_eq!(manifest_bytes(&app), before_manifest);
        let _ = std::fs::remove_dir_all(&root);
    }

    #[test]
    fn glyph_dir_matches_v1_layout_and_prunes_stale_pngs() {
        let dir = std::env::temp_dir().join(format!("mono-glyphs-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&dir);
        let cells = mono_font::render_centered_cells("AB", None, 12, GLYPH_CELL, 128).unwrap();
        assert_eq!(write_glyph_dir(&cells, &dir, 12).unwrap(), 2);
        assert!(dir.join("U+0041.png").is_file());
        let header = std::fs::read_to_string(dir.join("glyphs.h")).unwrap();
        assert!(
            header.starts_with("#pragma once\n\nstatic const unsigned char glyph_0041[24] = {0x")
        );
        let manifest: Value =
            serde_json::from_slice(&std::fs::read(dir.join("glyph_manifest.json")).unwrap())
                .unwrap();
        assert_eq!(manifest["glyphs"]["B"]["file"], "U+0042.png");
        assert_eq!(manifest["cell"]["h"], 16);
        let cells = mono_font::render_centered_cells("A", None, 12, GLYPH_CELL, 128).unwrap();
        write_glyph_dir(&cells, &dir, 12).unwrap();
        assert!(!dir.join("U+0042.png").exists());
        let _ = std::fs::remove_dir_all(&dir);
    }

    #[test]
    fn vlsb_packs_pages_lsb_top() {
        let mut rows = vec![vec![0u8; 2]; 16];
        rows[0][0] = 1;
        rows[9][1] = 1;
        assert_eq!(vlsb(&rows, 2), vec![0x01, 0x00, 0x00, 0x02]);
    }
}
