//! Preferences window controller (V1 `preferences_qt.PreferencesView`) and the
//! configurable shortcut dispatcher (V1 command registry).

use serde_json::{Value, json};
use slint::Global;

use crate::app::{App, model, ss};
use crate::i18n::tr;
use crate::prefs::defaults;
use crate::{DesignerModel, PrefRow, PrefsModel};

pub const SECTIONS: [&str; 7] = [
    "general",
    "appearance",
    "canvas",
    "pixel",
    "keyboard",
    "recovery",
    "advanced",
];

/// V1 shortcut command ids, in registry order.
pub const SHORTCUTS: [&str; 8] = [
    "preferences.open",
    "workspace.canvas_only",
    "project.save",
    "designer.undo",
    "designer.redo",
    "pixel.pencil",
    "pixel.select",
    "pixel.fill",
];

enum Spec {
    Group(&'static str, Option<&'static str>),
    Check(&'static str, &'static str, Option<&'static str>),
    /// key, label, help, (stored value, option label key or literal)
    Combo(
        &'static str,
        &'static str,
        Option<&'static str>,
        &'static [(&'static str, &'static str)],
    ),
    Spin(&'static str, &'static str, Option<&'static str>, i32, i32),
    Value(&'static str, &'static str),
    Button(&'static str, &'static str, Option<&'static str>),
    Danger(&'static str, &'static str, Option<&'static str>),
    Shortcut(&'static str),
}

fn specs(section: &str) -> Vec<Spec> {
    use Spec::*;
    match section {
        "general" => vec![
            Group("group.general", None),
            Combo(
                "language",
                "label.language",
                Some("help.language"),
                &[("zh_CN", "=简体中文"), ("en_US", "=English")],
            ),
            Check(
                "startup.reopen_last_project",
                "check.reopen",
                Some("help.startup"),
            ),
        ],
        "appearance" => vec![
            Group("group.appearance", None),
            Combo(
                "appearance.theme_mode",
                "label.theme_mode",
                Some("help.theme_mode"),
                &[
                    ("system", "mode.system"),
                    ("light", "mode.light"),
                    ("dark", "mode.dark"),
                ],
            ),
            Combo(
                "appearance.density",
                "label.density",
                Some("help.density"),
                &[
                    ("compact", "density.compact"),
                    ("comfortable", "density.comfortable"),
                    ("spacious", "density.spacious"),
                ],
            ),
            Combo(
                "appearance.ui_scale",
                "label.ui_scale",
                Some("help.ui_scale"),
                &[
                    ("auto", "=Auto"),
                    ("90%", "=90%"),
                    ("100%", "=100%"),
                    ("110%", "=110%"),
                    ("125%", "=125%"),
                    ("150%", "=150%"),
                ],
            ),
            Check(
                "appearance.reduced_motion",
                "check.reduced_motion",
                Some("help.reduced_motion"),
            ),
        ],
        "canvas" => vec![
            Group("group.input", None),
            Combo(
                "input.wheel_action",
                "label.wheel",
                Some("help.input"),
                &[("zoom", "wheel.zoom"), ("none", "wheel.none")],
            ),
            Combo(
                "input.middle_drag",
                "label.middle",
                None,
                &[("pan", "pan.pan"), ("none", "pan.none")],
            ),
            Check("input.space_drag", "check.space_pan", None),
            Group("group.canvas", None),
            Check("canvas.grid", "check.grid", Some("help.canvas_grid")),
            Check("canvas.bounds", "check.bounds", None),
            Check("canvas.rulers", "check.rulers", None),
            Check("canvas.zones", "check.zones", None),
            Combo(
                "canvas.snap",
                "label.snap",
                Some("help.snap"),
                &[
                    ("0", "snap.off"),
                    ("1", "=1 px"),
                    ("2", "=2 px"),
                    ("4", "=4 px"),
                    ("8", "=8 px"),
                ],
            ),
        ],
        "pixel" => vec![
            Group("group.pixel_behavior", Some("help.pixel_behavior")),
            Value("label.left", "value.draw"),
            Value("label.right", "value.erase"),
            Spin("pixel_studio.brush_size", "label.brush", None, 1, 8),
            Check(
                "pixel_studio.stroke_interpolation",
                "check.interpolation",
                None,
            ),
            Group("group.pixel_view", Some("help.pixel_view")),
            Check("pixel_studio.pixel_grid", "check.pixel_grid", None),
            Check("pixel_studio.actual_preview", "check.actual_preview", None),
            Check("pixel_studio.rulers", "check.pixel_rulers", None),
        ],
        "keyboard" => {
            let mut rows = vec![Group("group.shortcuts", Some("help.shortcuts"))];
            rows.extend(SHORTCUTS.iter().map(|c| Shortcut(c)));
            rows
        }
        "recovery" => vec![
            Group("group.autosave", None),
            Check("autosave.enabled", "check.autosave", Some("help.autosave")),
            Spin(
                "autosave.interval_minutes",
                "label.autosave_interval",
                None,
                1,
                60,
            ),
            Spin(
                "autosave.snapshots",
                "label.snapshots",
                Some("help.snapshots"),
                1,
                100,
            ),
            Check("autosave.prompt_recovery", "check.prompt_recovery", None),
            Group("group.recovery", None),
            Combo(
                "performance.validation_mode",
                "label.validation",
                Some("help.validation"),
                &[
                    ("edit_complete", "validation.edit_complete"),
                    ("idle", "validation.idle"),
                    ("continuous", "validation.continuous"),
                ],
            ),
            Spin(
                "performance.undo_history",
                "label.undo",
                Some("help.undo"),
                10,
                2000,
            ),
        ],
        _ => vec![
            Group("group.performance", None),
            Combo(
                "performance.drag_preview",
                "label.drag_preview",
                None,
                &[("fast", "perf.fast"), ("exact", "perf.exact")],
            ),
            Spin(
                "performance.asset_cache_mb",
                "label.cache",
                Some("help.asset_cache"),
                32,
                4096,
            ),
            Check("performance.overlay", "check.overlay", Some("help.overlay")),
            Group("group.maintenance", None),
            Button(
                "clear_cache",
                "button.clear_cache",
                Some("help.maintenance"),
            ),
            Button("reset_workspace", "button.reset_workspace", None),
            Group("group.danger", None),
            Danger("reset_all", "button.reset_all", Some("help.reset_all")),
        ],
    }
}

/// Normalised shortcut text for conflict checks (`ctrl+s` == `Ctrl+S`).
pub fn normalize_shortcut(text: &str) -> String {
    text.split('+')
        .map(|part| part.trim().to_lowercase())
        .collect::<Vec<_>>()
        .join("+")
}

/// The command bound to a key chord, if any (`chord` like `Ctrl+S`).
pub fn command_for(shortcuts: &Value, chord: &str) -> Option<&'static str> {
    let wanted = normalize_shortcut(chord);
    SHORTCUTS.iter().copied().find(|command| {
        shortcuts
            .get(*command)
            .and_then(Value::as_str)
            .is_some_and(|bound| normalize_shortcut(bound) == wanted)
    })
}

impl App {
    fn pt(&self, key: &str) -> String {
        tr(&self.lang, &format!("pref.{key}"))
    }

    fn option_label(&self, label: &str) -> String {
        label
            .strip_prefix('=')
            .map_or_else(|| self.pt(label), str::to_string)
    }

    fn build_row(&self, spec: &Spec) -> PrefRow {
        let mut row = PrefRow::default();
        let help = |h: &Option<&str>| h.map(|k| self.pt(k)).unwrap_or_default();
        match spec {
            Spec::Group(title, h) => {
                row.kind = "group".into();
                row.label = ss(self.pt(title));
                row.help = ss(help(h));
            }
            Spec::Check(key, label, h) => {
                row.kind = "check".into();
                row.key = ss(key);
                row.label = ss(self.pt(label));
                row.help = ss(help(h));
                row.checked = if *key == "input.space_drag" {
                    self.prefs.str(key) == "pan"
                } else {
                    self.prefs.bool(key)
                };
            }
            Spec::Combo(key, label, h, options) => {
                row.kind = "combo".into();
                row.key = ss(key);
                row.label = ss(self.pt(label));
                row.help = ss(help(h));
                row.options = model(
                    options
                        .iter()
                        .map(|(_, l)| ss(self.option_label(l)))
                        .collect(),
                );
                let current = match self.prefs.get(key) {
                    Value::String(s) => s,
                    other => other.to_string(),
                };
                row.index = options.iter().position(|(v, _)| *v == current).unwrap_or(0) as i32;
            }
            Spec::Spin(key, label, h, minimum, maximum) => {
                row.kind = "spin".into();
                row.key = ss(key);
                row.label = ss(self.pt(label));
                row.help = ss(help(h));
                row.value = self.prefs.int(key) as i32;
                row.minimum = *minimum;
                row.maximum = *maximum;
            }
            Spec::Value(label, value) => {
                row.kind = "value".into();
                row.label = ss(self.pt(label));
                row.text = ss(self.pt(value));
            }
            Spec::Button(action, text, h) | Spec::Danger(action, text, h) => {
                row.kind = if matches!(spec, Spec::Danger(..)) {
                    "danger"
                } else {
                    "button"
                }
                .into();
                row.key = ss(action);
                row.label = ss(self.pt(match *action {
                    "clear_cache" => "label.cache_action",
                    "reset_workspace" => "label.workspace_action",
                    _ => "label.danger",
                }));
                row.text = ss(self.pt(text));
                row.help = ss(help(h));
            }
            Spec::Shortcut(command) => {
                row.kind = "text".into();
                row.key = ss(format!("shortcuts.{command}"));
                row.label = ss(self.pt(&format!("shortcut.{command}")));
                row.text = ss(self.prefs.str(&format!("shortcuts.{command}")));
            }
        }
        row
    }

    fn row_matches(row: &PrefRow, needle: &str) -> bool {
        let haystack = format!("{} {} {}", row.label, row.help, row.key).to_lowercase();
        row.kind != "group" && haystack.contains(needle)
    }

    pub fn refresh_prefs(&mut self) {
        let Some(ui) = self.ui.upgrade() else { return };
        let pm = PrefsModel::get(&ui);
        pm.set_sections(model(
            SECTIONS
                .iter()
                .map(|s| ss(self.pt(&format!("section.{s}"))))
                .collect(),
        ));
        pm.set_version(ss(env!("CARGO_PKG_VERSION")));
        let search = pm.get_search().trim().to_lowercase();
        let rows: Vec<PrefRow> = if search.is_empty() {
            let section = SECTIONS
                .get(pm.get_section().max(0) as usize)
                .copied()
                .unwrap_or("general");
            pm.set_page_title(ss(self.pt(&format!("page.{section}.title"))));
            pm.set_page_desc(ss(self.pt(&format!("page.{section}.desc"))));
            specs(section).iter().map(|s| self.build_row(s)).collect()
        } else {
            pm.set_page_title(ss(self.pt("title")));
            pm.set_page_desc(ss(""));
            SECTIONS
                .iter()
                .flat_map(|section| specs(section))
                .map(|s| self.build_row(&s))
                .filter(|r| Self::row_matches(r, &search))
                .collect()
        };
        pm.set_rows(model(rows));
    }

    pub fn open_preferences(&mut self) {
        if let Some(ui) = self.ui.upgrade() {
            let pm = PrefsModel::get(&ui);
            pm.set_error(ss(""));
            pm.set_save_state(ss(""));
            pm.set_search(ss(""));
            crate::AppModel::get(&ui).set_preferences_visible(true);
        }
        self.refresh_prefs();
    }

    fn typed_value(&self, key: &str, value: &str) -> Value {
        let spec = SECTIONS
            .iter()
            .flat_map(|s| specs(s))
            .find(|s| matches!(s, Spec::Combo(k, ..) if *k == key));
        let raw = match spec {
            Some(Spec::Combo(_, _, _, options)) => value
                .parse::<usize>()
                .ok()
                .and_then(|i| options.get(i))
                .map_or(value, |(v, _)| *v)
                .to_string(),
            _ => value.to_string(),
        };
        if key == "input.space_drag" {
            return json!(if raw == "true" { "pan" } else { "none" });
        }
        let default = defaults()
            .pointer(&format!("/{}", key.replace('.', "/")))
            .cloned()
            .unwrap_or(Value::Null);
        match default {
            Value::Bool(_) => json!(raw == "true"),
            Value::Number(_) => raw.trim().parse::<i64>().map_or(json!(raw), |n| json!(n)),
            _ => json!(raw),
        }
    }

    /// One preference edit: validate, persist, apply live (V1 `_controls_changed`).
    pub fn pref_changed(&mut self, key: &str, value: &str) {
        let typed = self.typed_value(key, value);
        let mut error = String::new();
        if let (Some(command), Some(text)) = (key.strip_prefix("shortcuts."), typed.as_str()) {
            let wanted = normalize_shortcut(text);
            let clash = SHORTCUTS.iter().find(|other| {
                **other != command
                    && normalize_shortcut(&self.prefs.str(&format!("shortcuts.{other}"))) == wanted
            });
            if let Some(other) = clash {
                error = crate::i18n::trf(
                    &self.lang,
                    "pref.shortcut.conflict",
                    &[(
                        "error",
                        format!("{text} → {}", self.pt(&format!("shortcut.{other}"))),
                    )],
                );
            }
        }
        if error.is_empty() && !self.prefs.set(key, typed) {
            error = format!("{}: {value}", self.pt("status.failed"));
        }
        let saved = error.is_empty() && self.prefs.save();
        if let Some(ui) = self.ui.upgrade() {
            let pm = PrefsModel::get(&ui);
            pm.set_error(ss(&error));
            pm.set_save_state(ss(self.pt(if saved {
                "status.saved"
            } else {
                "status.failed"
            })));
        }
        if error.is_empty() {
            self.apply_live(key);
        }
        self.refresh_prefs();
    }

    fn apply_live(&mut self, key: &str) {
        if key == "language" {
            self.lang = self.prefs.str("language");
        }
        if let Some(ui) = self.ui.upgrade() {
            if key == "language" || key.starts_with("appearance.") {
                crate::apply_appearance(&ui, self, None);
            }
            if key.starts_with("canvas.") {
                let dm = DesignerModel::get(&ui);
                dm.set_show_grid(self.prefs.bool("canvas.grid"));
                dm.set_show_bounds(self.prefs.bool("canvas.bounds"));
                dm.set_show_rulers(self.prefs.bool("canvas.rulers"));
                dm.set_show_zones(self.prefs.bool("canvas.zones"));
            }
        }
        if key.starts_with("pixel_studio.")
            || key.starts_with("input.")
            || key.starts_with("performance.")
        {
            self.apply_pixel_preferences();
        }
        if key == "performance.undo_history" {
            let limit = usize::try_from(self.prefs.int(key)).unwrap_or(200);
            if let Some(session) = self.session.as_mut() {
                session.set_max_undo(limit);
            }
        }
        if key == "language" {
            self.refresh_all();
            self.refresh_pixel();
            self.refresh_bench();
            self.refresh_font();
        }
    }

    pub fn pref_button(&mut self, action: &str) {
        match action {
            "reset_all" => {
                let answer = rfd::MessageDialog::new()
                    .set_title(self.pt("confirm.reset_all.title"))
                    .set_description(self.pt("confirm.reset_all.body"))
                    .set_buttons(rfd::MessageButtons::YesNo)
                    .show();
                if answer != rfd::MessageDialogResult::Yes {
                    return;
                }
                self.prefs.data = defaults();
                let saved = self.prefs.save();
                self.lang = self.prefs.str("language");
                for key in [
                    "language",
                    "canvas.grid",
                    "pixel_studio.brush_size",
                    "performance.undo_history",
                ] {
                    self.apply_live(key);
                }
                if let Some(ui) = self.ui.upgrade() {
                    PrefsModel::get(&ui).set_save_state(ss(self.pt(if saved {
                        "status.saved"
                    } else {
                        "status.failed"
                    })));
                }
            }
            "clear_cache" => {
                if let Some(session) = self.session.as_mut() {
                    session.clear_resource_cache();
                }
                self.set_status(self.pt("status.saved"));
            }
            // Slint panels have fixed geometry; there is no saved layout to restore.
            _ => self.set_status(self.pt("status.saved")),
        }
        self.refresh_prefs();
    }

    /// Global key chord from the window (`Ctrl+S`, `B`, …) → registered command.
    pub fn shortcut(&mut self, chord: &str) -> Option<&'static str> {
        command_for(&self.prefs.get("shortcuts"), chord)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn default_shortcuts_resolve_case_insensitively() {
        let shortcuts = defaults()["shortcuts"].clone();
        assert_eq!(command_for(&shortcuts, "ctrl+s"), Some("project.save"));
        assert_eq!(command_for(&shortcuts, "Ctrl+,"), Some("preferences.open"));
        assert_eq!(command_for(&shortcuts, "B"), Some("pixel.pencil"));
        assert_eq!(command_for(&shortcuts, "Ctrl+Q"), None);
    }

    #[test]
    fn every_section_has_rows_and_registry_matches_defaults() {
        for section in SECTIONS {
            assert!(!specs(section).is_empty(), "{section}");
        }
        let defaults = defaults();
        let keys: Vec<&str> = defaults["shortcuts"]
            .as_object()
            .map(|m| m.keys().map(String::as_str).collect())
            .unwrap_or_default();
        assert_eq!(keys, SHORTCUTS.to_vec());
    }
}
