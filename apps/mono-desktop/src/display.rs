//! Pixel Studio display settings (V1 output workbench "显示" group): canvas
//! background, grid, pixel fill and pixel border colours, pixel size, and the
//! output text font. Display only — none of it changes exported bytes.

use serde_json::json;
use slint::{Global, Model, Rgba8Pixel};

use crate::app::{App, model, ss};
use crate::canvas::{
    CellWindow, DEFAULT_BACKGROUND, DEFAULT_BORDER, DEFAULT_FILL, DEFAULT_GRID, border_runs,
    clip_runs, parse_color, slint_color,
};
use crate::{BorderLine, OutputModel, PixelModel};

/// Preference keys in display order, with V1's labels for the invalid-colour message.
pub const COLOR_KEYS: [(&str, &str, &str); 4] = [
    (
        "canvas_background",
        DEFAULT_BACKGROUND,
        "bench.display.bg_short",
    ),
    ("grid_color", DEFAULT_GRID, "bench.display.grid_short"),
    ("pixel_fill", DEFAULT_FILL, "bench.display.fill_short"),
    ("pixel_border", DEFAULT_BORDER, "bench.display.border_short"),
];

/// Colours the canvas is drawn with.
#[derive(Debug, Clone, Copy)]
pub struct DisplayColors {
    pub background: Rgba8Pixel,
    pub grid: Rgba8Pixel,
    pub fill: Rgba8Pixel,
    pub border: Rgba8Pixel,
}

/// Pixel palette derived from the active theme (light / dark / high contrast).
pub fn theme_palette(mode: i32) -> DisplayColors {
    let (background, grid, border) = match mode {
        2 => ("#000000", "#505050", "#00D8FF"),
        1 => ("#000000", "#343438", "#12CCD8"),
        _ => ("#0B0D0E", "#343438", "#176B75"),
    };
    let color = |text: &str| parse_color(text).unwrap_or(crate::canvas::OFF);
    DisplayColors {
        background: color(background),
        grid: color(grid),
        fill: color("#FFFFFF"),
        border: color(border),
    }
}

fn hex_color(pixel: Rgba8Pixel) -> String {
    format!("#{:02X}{:02X}{:02X}", pixel.r, pixel.g, pixel.b)
}

impl App {
    /// `auto` follows the theme; `custom` keeps the four saved colours.
    pub fn palette_mode(&self) -> &'static str {
        if self.prefs.str("pixel_studio.palette_mode") == "custom" {
            "custom"
        } else {
            "auto"
        }
    }

    /// Saved display colours; an unreadable value falls back to V1's default.
    pub fn display_colors(&self) -> DisplayColors {
        if self.palette_mode() == "auto" {
            return theme_palette(crate::theme_mode(&self.prefs, None));
        }
        let pick = |index: usize| {
            let (key, default, _) = COLOR_KEYS[index];
            parse_color(&self.prefs.str(&format!("pixel_studio.{key}")))
                .or_else(|| parse_color(default))
                .unwrap_or(crate::canvas::OFF)
        };
        DisplayColors {
            background: pick(0),
            grid: pick(1),
            fill: pick(2),
            border: pick(3),
        }
    }

    /// Initial editor texts: the theme colours in auto mode, else the saved ones.
    pub fn load_display_draft(&mut self) {
        if self.palette_mode() == "auto" {
            let colors = self.display_colors();
            let values = [colors.background, colors.grid, colors.fill, colors.border];
            for (slot, pixel) in self.display_draft.iter_mut().zip(values) {
                *slot = hex_color(pixel);
            }
            return;
        }
        for (slot, (key, _, _)) in self.display_draft.iter_mut().zip(COLOR_KEYS) {
            *slot = self.prefs.str(&format!("pixel_studio.{key}"));
        }
    }

    /// The canvas reports which cells are visible (scroll, zoom, resize).
    pub fn pixel_cell_window(&mut self, x0: i32, y0: i32, x1: i32, y1: i32) {
        let cell = |v: i32| usize::try_from(v).unwrap_or(0);
        let window = CellWindow {
            x0: cell(x0),
            y0: cell(y0),
            x1: cell(x1),
            y1: cell(y1),
        };
        if window != self.cell_window {
            self.cell_window = window;
            let pixels = self.studio().display_pixels();
            self.refresh_overlay(&pixels);
        }
    }

    /// V1 pixel border: outline every lit pixel of the visible window, as
    /// merged edge runs (see `canvas.rs`). The model is updated row by row; a
    /// stroke changes a few runs, and a new model would rebuild every item.
    pub fn refresh_overlay(&self, pixels: &[u8]) {
        let Some(ui) = self.ui.upgrade() else { return };
        let p = self.studio();
        let runs = clip_runs(
            &border_runs(p.width(), p.height(), pixels),
            self.cell_window,
        );
        let lines = &self.border_lines;
        if lines.row_count() == 0 {
            PixelModel::get(&ui).set_border_lines(slint::ModelRc::from(lines.clone()));
        }
        for (i, r) in runs.iter().enumerate() {
            let line = BorderLine {
                x: r.x as i32,
                y: r.y as i32,
                len: r.len as i32,
                vertical: r.vertical,
            };
            if i < lines.row_count() {
                if lines.row_data(i).as_ref() != Some(&line) {
                    lines.set_row_data(i, line);
                }
            } else {
                lines.push(line);
            }
        }
        while lines.row_count() > runs.len() {
            lines.remove(lines.row_count() - 1);
        }
    }

    /// Push colours, font and the editor texts to the UI.
    pub fn refresh_display_model(&self) {
        let Some(ui) = self.ui.upgrade() else { return };
        let colors = self.display_colors();
        let pm = PixelModel::get(&ui);
        pm.set_canvas_background(slint_color(colors.background));
        pm.set_grid_color(slint_color(colors.grid));
        pm.set_border_color(slint_color(colors.border));
        let om = OutputModel::get(&ui);
        om.set_display_hex(model(self.display_draft.iter().map(ss).collect()));
        om.set_display_colors(model(
            self.display_draft
                .iter()
                .map(|t| parse_color(t).map_or(slint::Color::default(), slint_color))
                .collect(),
        ));
        om.set_display_invalid(model(
            self.display_draft
                .iter()
                .map(|t| parse_color(t).is_none())
                .collect(),
        ));
        om.set_output_font(ss(self.prefs.str("pixel_studio.output_font")));
        om.set_output_font_size(self.prefs.int("pixel_studio.output_font_size").clamp(8, 32) as i32);
        om.set_follow_theme(self.palette_mode() == "auto");
    }

    /// One edit in the display group (V1 `_canvas_display_changed`,
    /// `_display_changed`, `_pixel_size_changed`, `_reset_display`).
    pub fn bench_display(&mut self, key: &str, value: &str) {
        match key {
            "reset" => {
                // V1 resets colours, pixel size 10 and font size 14 (not the family).
                for (key, default, _) in COLOR_KEYS {
                    self.prefs
                        .set(&format!("pixel_studio.{key}"), json!(default));
                }
                self.prefs.set("pixel_studio.palette_mode", json!("auto"));
                self.prefs.set("pixel_studio.output_font_size", json!(14));
                let _ = self.prefs.save();
                self.load_display_draft();
                self.refresh_pixel();
                self.set_pixel_size(10);
            }
            "palette_mode" => {
                let mode = if value == "custom" { "custom" } else { "auto" };
                self.prefs.set("pixel_studio.palette_mode", json!(mode));
                let _ = self.prefs.save();
                self.load_display_draft();
                self.refresh_pixel();
            }
            "output_font" => {
                self.prefs
                    .set("pixel_studio.output_font", json!(value.trim()));
                let _ = self.prefs.save();
            }
            "output_font_size" => {
                if let Ok(size) = value.parse::<i64>() {
                    self.prefs
                        .set("pixel_studio.output_font_size", json!(size.clamp(8, 32)));
                    let _ = self.prefs.save();
                }
            }
            "pixel_size" => {
                if let Ok(size) = value.parse::<i32>() {
                    self.set_pixel_size(size);
                }
            }
            _ => {
                if let Some(index) = COLOR_KEYS.iter().position(|(k, _, _)| *k == key) {
                    self.display_draft[index] = value.trim().to_string();
                    self.apply_display_colors();
                }
            }
        }
        self.refresh_display_model();
    }

    /// Save and apply the edited colours, unless one of them is invalid.
    fn apply_display_colors(&mut self) {
        let invalid: Vec<String> = COLOR_KEYS
            .iter()
            .zip(&self.display_draft)
            .filter(|(_, text)| parse_color(text).is_none())
            .map(|((_, _, label), _)| self.t(label))
            .collect();
        let message = if invalid.is_empty() {
            for ((key, _, _), text) in COLOR_KEYS.iter().zip(&self.display_draft) {
                self.prefs.set(&format!("pixel_studio.{key}"), json!(text));
            }
            // Editing a colour is an explicit choice: stop following the theme.
            self.prefs.set("pixel_studio.palette_mode", json!("custom"));
            let _ = self.prefs.save();
            self.refresh_pixel();
            String::new()
        } else {
            format!("{}{}", self.t("bench.display.invalid"), invalid.join("、"))
        };
        if let Some(ui) = self.ui.upgrade() {
            OutputModel::get(&ui).set_display_error(ss(message));
        }
    }

    /// V1 `set_zoom(value)`: an exact zoom of 1..40 px per pixel.
    pub fn set_pixel_size(&mut self, size: i32) {
        let Some(ui) = self.ui.upgrade() else { return };
        let size = size.clamp(1, 40);
        let pm = PixelModel::get(&ui);
        pm.set_zoom(size as f32);
        let index = crate::pixel::ZOOMS
            .iter()
            .position(|z| *z == size)
            .map_or(0, |i| i as i32 + 1);
        pm.set_zoom_index(index);
    }
}

#[cfg(test)]
mod tests {
    #![allow(clippy::unwrap_used)]
    use super::*;

    fn app(name: &str) -> (App, std::path::PathBuf) {
        let dir = std::env::temp_dir().join(format!("mono-display-{name}-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&dir);
        std::fs::create_dir_all(&dir).unwrap();
        let prefs = crate::prefs::Preferences::load_from(dir.join("prefs.json"));
        let mut app = App::new(slint::Weak::default(), prefs);
        app.load_display_draft();
        (app, dir)
    }

    #[test]
    fn invalid_colour_is_not_saved_and_valid_ones_are() {
        let (mut app, dir) = app("colours");
        app.prefs.set("pixel_studio.palette_mode", json!("custom"));
        assert_eq!(
            app.display_colors().border,
            parse_color(DEFAULT_BORDER).unwrap()
        );
        app.bench_display("pixel_border", "#12");
        assert_eq!(app.prefs.str("pixel_studio.pixel_border"), DEFAULT_BORDER);
        app.bench_display("pixel_border", "#00FF00");
        assert_eq!(app.prefs.str("pixel_studio.pixel_border"), "#00FF00");
        // While another field is invalid, nothing is saved (V1 `_canvas_display_changed`).
        app.bench_display("grid_color", "nope");
        app.bench_display("pixel_fill", "#FF0000");
        assert_eq!(app.prefs.str("pixel_studio.pixel_fill"), DEFAULT_FILL);
        let saved = crate::prefs::Preferences::load_from(dir.join("prefs.json"));
        assert_eq!(saved.str("pixel_studio.pixel_border"), "#00FF00");
        let _ = std::fs::remove_dir_all(&dir);
    }

    #[test]
    fn auto_palette_follows_theme() {
        let (mut app, dir) = app("auto");
        assert_eq!(app.palette_mode(), "auto");
        let light = app.display_colors();
        assert_eq!(light.border, parse_color("#176B75").unwrap());
        assert_eq!(light.fill, parse_color("#FFFFFF").unwrap());
        app.prefs.set("appearance.theme_mode", json!("dark"));
        assert_eq!(app.display_colors().border, parse_color("#12CCD8").unwrap());
        app.prefs
            .set("appearance.theme_mode", json!("high-contrast"));
        assert_eq!(app.display_colors().border, parse_color("#00D8FF").unwrap());
        assert_eq!(app.display_colors().grid, parse_color("#505050").unwrap());
        let _ = std::fs::remove_dir_all(&dir);
    }

    #[test]
    fn custom_palette_keeps_user_colors() {
        let (mut app, dir) = app("custom");
        app.bench_display("pixel_border", "#00FF00");
        assert_eq!(app.palette_mode(), "custom");
        app.prefs.set("appearance.theme_mode", json!("dark"));
        assert_eq!(app.display_colors().border, parse_color("#00FF00").unwrap());
        app.bench_display("reset", "");
        assert_eq!(app.palette_mode(), "auto");
        assert_eq!(app.display_colors().border, parse_color("#12CCD8").unwrap());
        let _ = std::fs::remove_dir_all(&dir);
    }

    #[test]
    fn legacy_palette_migrates_to_custom() {
        let dir = std::env::temp_dir().join(format!("mono-display-legacy-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&dir);
        std::fs::create_dir_all(&dir).unwrap();
        let path = dir.join("prefs.json");
        std::fs::write(
            &path,
            r##"{"appearance":{"theme_mode":"light"},"pixel_studio":{"pixel_border":"#00FF00"}}"##,
        )
        .unwrap();
        let prefs = crate::prefs::Preferences::load_from(path);
        assert_eq!(prefs.str("pixel_studio.palette_mode"), "custom");
        let app = App::new(slint::Weak::default(), prefs);
        assert_eq!(app.display_colors().border, parse_color("#00FF00").unwrap());
        let _ = std::fs::remove_dir_all(&dir);
    }

    #[test]
    fn missing_palette_defaults_to_auto() {
        let dir = std::env::temp_dir().join(format!("mono-display-missing-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&dir);
        std::fs::create_dir_all(&dir).unwrap();
        let path = dir.join("prefs.json");
        std::fs::write(&path, r#"{"language":"en_US"}"#).unwrap();
        let prefs = crate::prefs::Preferences::load_from(path);
        assert_eq!(prefs.str("pixel_studio.palette_mode"), "auto");
        let _ = std::fs::remove_dir_all(&dir);
    }

    #[test]
    fn high_contrast_is_valid_pref() {
        let dir =
            std::env::temp_dir().join(format!("mono-display-contrast-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&dir);
        std::fs::create_dir_all(&dir).unwrap();
        let path = dir.join("prefs.json");
        std::fs::write(&path, r#"{"appearance":{"theme_mode":"high-contrast"}}"#).unwrap();
        let prefs = crate::prefs::Preferences::load_from(path);
        assert_eq!(prefs.str("appearance.theme_mode"), "high-contrast");
        let _ = std::fs::remove_dir_all(&dir);
    }

    #[test]
    fn reset_restores_v1_defaults_but_keeps_the_font_family() {
        let (mut app, dir) = app("reset");
        app.bench_display("pixel_fill", "#FF0000");
        app.bench_display("output_font", "Cascadia Mono");
        app.bench_display("output_font_size", "99");
        assert_eq!(app.prefs.int("pixel_studio.output_font_size"), 32);
        app.bench_display("reset", "");
        assert_eq!(app.prefs.str("pixel_studio.pixel_fill"), DEFAULT_FILL);
        assert_eq!(app.prefs.int("pixel_studio.output_font_size"), 14);
        assert_eq!(app.prefs.str("pixel_studio.output_font"), "Cascadia Mono");
        let _ = std::fs::remove_dir_all(&dir);
    }

    #[test]
    fn a_saved_unreadable_colour_falls_back_to_the_default() {
        let (dir, path) = {
            let (_, dir) = app("fallback");
            let path = dir.join("prefs.json");
            std::fs::write(&path, r#"{"pixel_studio": {"pixel_border": "red"}}"#).unwrap();
            (dir, path)
        };
        let prefs = crate::prefs::Preferences::load_from(path);
        let app = App::new(slint::Weak::default(), prefs);
        assert_eq!(
            app.display_colors().border,
            parse_color(DEFAULT_BORDER).unwrap()
        );
        let _ = std::fs::remove_dir_all(&dir);
    }
}
