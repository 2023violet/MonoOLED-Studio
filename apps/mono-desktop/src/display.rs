//! Pixel Studio display settings (V1 output workbench "显示" group): canvas
//! background, grid, pixel fill and pixel border colours, pixel size, and the
//! output text font. Display only — none of it changes exported bytes.

use serde_json::json;
use slint::{Global, Rgba8Pixel};

use crate::app::{App, model, ss};
use crate::canvas::{
    DEFAULT_BACKGROUND, DEFAULT_BORDER, DEFAULT_FILL, DEFAULT_GRID, Viewport, border_overlay,
    parse_color, slint_color,
};
use crate::{OutputModel, PixelModel};

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

impl App {
    /// Saved display colours; an unreadable value falls back to V1's default.
    pub fn display_colors(&self) -> DisplayColors {
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

    /// Initial editor texts (the saved colours).
    pub fn load_display_draft(&mut self) {
        for (slot, (key, _, _)) in self.display_draft.iter_mut().zip(COLOR_KEYS) {
            *slot = self.prefs.str(&format!("pixel_studio.{key}"));
        }
    }

    /// The canvas reports which cells are visible and its zoom.
    pub fn pixel_viewport(&mut self, x0: i32, y0: i32, cols: i32, rows: i32, zoom: i32) {
        let clamp = |v: i32| usize::try_from(v).unwrap_or(0);
        let view = Viewport {
            x0: clamp(x0),
            y0: clamp(y0),
            cols: clamp(cols),
            rows: clamp(rows),
            zoom: clamp(zoom),
        };
        if view != self.viewport {
            self.viewport = view;
            let pixels = self.studio().display_pixels();
            self.refresh_overlay(&pixels);
        }
    }

    /// V1 pixel border: outline every lit pixel of the visible window.
    pub fn refresh_overlay(&self, pixels: &[u8]) {
        let Some(ui) = self.ui.upgrade() else { return };
        let pm = PixelModel::get(&ui);
        let p = self.studio();
        let colors = self.display_colors();
        match border_overlay(p.width(), p.height(), pixels, self.viewport, colors.border) {
            Some(image) => {
                pm.set_border_overlay(image);
                pm.set_overlay_x(self.viewport.x0 as i32);
                pm.set_overlay_y(self.viewport.y0 as i32);
                pm.set_has_overlay(true);
            }
            None => pm.set_has_overlay(false),
        }
    }

    /// Push colours, font and the editor texts to the UI.
    pub fn refresh_display_model(&self) {
        let Some(ui) = self.ui.upgrade() else { return };
        let colors = self.display_colors();
        let pm = PixelModel::get(&ui);
        pm.set_canvas_background(slint_color(colors.background));
        pm.set_grid_color(slint_color(colors.grid));
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
    }

    /// One edit in the display group (V1 `_canvas_display_changed`,
    /// `_display_changed`, `_pixel_size_changed`, `_reset_display`).
    pub fn bench_display(&mut self, key: &str, value: &str) {
        match key {
            "reset" => {
                // V1 resets colours, pixel size 10 and font size 14 (not the family).
                for (slot, (_, default, _)) in self.display_draft.iter_mut().zip(COLOR_KEYS) {
                    *slot = default.to_string();
                }
                self.prefs.set("pixel_studio.output_font_size", json!(14));
                self.apply_display_colors();
                self.set_pixel_size(10);
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
