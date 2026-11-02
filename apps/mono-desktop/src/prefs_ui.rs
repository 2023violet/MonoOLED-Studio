//! Preferences window controller (V1 `preferences_qt.PreferencesView`) and the
//! configurable shortcut dispatcher (V1 command registry).

use serde_json::{Value, json};
use slint::Global;

use crate::app::{App, model, ss};
use crate::commands::{CONFIGURABLE as SHORTCUTS, normalize_shortcut};
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
                    ("high-contrast", "mode.high_contrast"),
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
            Combo(
                "pixel_studio.palette_mode",
                "label.palette_mode",
                Some("help.palette_mode"),
                &[("auto", "palette.auto"), ("custom", "palette.custom")],
            ),
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
            Spin(
                "performance.undo_history",
                "label.undo",
                Some("help.undo"),
                10,
                2000,
            ),
        ],
        _ => vec![
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

/// The command bound to a key chord, if any (`chord` like `Ctrl+S`).
pub fn command_for(shortcuts: &Value, chord: &str) -> Option<&'static str> {
    let wanted = normalize_shortcut(chord);
    if wanted.is_empty() {
        return None;
    }
    SHORTCUTS.iter().copied().find(|command| {
        shortcuts
            .get(*command)
            .and_then(Value::as_str)
            .is_some_and(|bound| !bound.trim().is_empty() && normalize_shortcut(bound) == wanted)
    })
}

/// The command already using `text`, ignoring empty (cleared) bindings.
pub fn shortcut_conflict(shortcuts: &Value, command: &str, text: &str) -> Option<&'static str> {
    let wanted = normalize_shortcut(text);
    if wanted.is_empty() {
        return None;
    }
    SHORTCUTS.iter().copied().find(|other| {
        *other != command
            && shortcuts
                .get(*other)
                .and_then(Value::as_str)
                .is_some_and(|bound| {
                    !bound.trim().is_empty() && normalize_shortcut(bound) == wanted
                })
    })
}

/// Command id from a `shortcut-reset:<PrefRow.key>` button action.
fn reset_command(action: &str) -> Option<&str> {
    let command = action.strip_prefix("shortcut-reset:")?;
    Some(command.strip_prefix("shortcuts.").unwrap_or(command))
}

/// Preference row labels live under the `pref.` namespace.
pub fn pref_key(key: &str) -> String {
    format!("pref.{key}")
}

impl App {
    fn pt(&self, key: &str) -> String {
        tr(&self.lang, &pref_key(key))
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
                row.kind = "shortcut".into();
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

    /// One preference edit: validate, apply live, buffer for the debounced
    /// write. Rows are not rebuilt, so typing into a shortcut field is stable.
    pub fn pref_draft(&mut self, key: &str, value: &str) {
        let typed = self.typed_value(key, value);
        let mut error = String::new();
        if let (Some(command), Some(text)) = (key.strip_prefix("shortcuts."), typed.as_str()) {
            if let Some(other) = shortcut_conflict(&self.prefs.get("shortcuts"), command, text) {
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
        if let Some(ui) = self.ui.upgrade() {
            let pm = PrefsModel::get(&ui);
            pm.set_error(ss(&error));
            pm.set_save_state(ss(self.pt(if error.is_empty() {
                "status.pending"
            } else {
                "status.failed"
            })));
        }
        if !error.is_empty() {
            return;
        }
        self.prefs_pending = true;
        self.prefs_edit_at = Some(std::time::Instant::now());
        self.apply_live(key);
    }

    /// Explicit confirmation (Enter, combo, spin, checkbox): draft then write now.
    pub fn pref_changed(&mut self, key: &str, value: &str) {
        self.pref_draft(key, value);
        self.flush_prefs();
        self.refresh_prefs();
    }

    /// Write buffered preference edits; safe to call when nothing is pending.
    pub fn flush_prefs(&mut self) {
        if !self.prefs_pending {
            return;
        }
        let saved = self.prefs.save();
        // A failed write stays pending with a fresh timestamp, so the idle tick
        // retries on its own half-second rhythm: clearing the flag here would
        // leave the row showing a value the file never received, and nothing
        // would ever try again until an unrelated edit happened.
        self.prefs_pending = !saved;
        self.prefs_edit_at = if saved {
            None
        } else {
            Some(std::time::Instant::now())
        };
        if let Some(ui) = self.ui.upgrade() {
            PrefsModel::get(&ui).set_save_state(ss(self.pt(if saved {
                "status.saved"
            } else {
                "status.failed"
            })));
        }
    }

    /// 60 ms UI tick: persist once typing has been idle for half a second.
    pub fn flush_prefs_if_idle(&mut self) {
        if self.prefs_pending
            && self
                .prefs_edit_at
                .is_some_and(|at| at.elapsed() >= std::time::Duration::from_millis(500))
        {
            self.flush_prefs();
        }
    }

    /// Persisted canvas overlay flags → designer model. Called at startup and
    /// whenever a `canvas.*` preference changes; without it a saved preference
    /// only takes effect after the user touches the row again.
    pub fn apply_canvas_preferences(&mut self) {
        let Some(ui) = self.ui.upgrade() else {
            return;
        };
        let dm = DesignerModel::get(&ui);
        dm.set_show_grid(self.prefs.bool("canvas.grid"));
        dm.set_show_bounds(self.prefs.bool("canvas.bounds"));
        dm.set_show_rulers(self.prefs.bool("canvas.rulers"));
        dm.set_show_zones(self.prefs.bool("canvas.zones"));
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
                self.apply_canvas_preferences();
            }
        }
        if key.starts_with("pixel_studio.")
            || key.starts_with("input.")
            || key.starts_with("performance.")
        {
            self.apply_pixel_preferences();
        }
        if key == "appearance.theme_mode" {
            self.load_display_draft();
            self.refresh_display_model();
            self.refresh_pixel();
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
            _ if action.starts_with("shortcut-reset:") => {
                let saved = reset_command(action)
                    .is_some_and(|command| self.prefs.reset_shortcut(command) && self.prefs.save());
                if let Some(ui) = self.ui.upgrade() {
                    let pm = PrefsModel::get(&ui);
                    pm.set_error(ss(""));
                    pm.set_save_state(ss(self.pt(if saved {
                        "status.saved"
                    } else {
                        "status.failed"
                    })));
                }
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
    #![allow(clippy::unwrap_used, clippy::panic)]
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

    #[test]
    fn empty_binding_does_not_resolve() {
        let mut shortcuts = defaults()["shortcuts"].clone();
        shortcuts["project.save"] = json!("");
        assert_eq!(command_for(&shortcuts, "Ctrl+S"), None);
        assert_eq!(command_for(&shortcuts, ""), None);
    }

    #[test]
    fn cleared_binding_does_not_conflict() {
        let mut shortcuts = defaults()["shortcuts"].clone();
        shortcuts["project.save"] = json!("");
        assert_eq!(shortcut_conflict(&shortcuts, "project.save", ""), None);
        assert_eq!(
            shortcut_conflict(&shortcuts, "project.save", "Ctrl+Z"),
            Some("designer.undo")
        );
    }

    #[test]
    fn reset_action_accepts_pref_row_keys() {
        assert_eq!(
            reset_command("shortcut-reset:shortcuts.project.save"),
            Some("project.save")
        );
        assert_eq!(
            reset_command("shortcut-reset:project.save"),
            Some("project.save")
        );
        assert_eq!(reset_command("reset_all"), None);
    }

    /// Preference rows assemble their strings at run time from the `pref.`
    /// namespace, so the literal `"t(\"…\")"` scan in `i18n.rs` cannot see them
    /// and a missing key renders as raw text. Resolve every row string here.
    #[test]
    fn every_preference_string_translates() {
        use crate::i18n::has_key;

        fn check(missing: &mut Vec<String>, key: &str, where_: &str) {
            // `=Auto`-style literals are shown verbatim by `option_label`.
            if key.starts_with('=') {
                return;
            }
            let full = pref_key(key);
            if !has_key(&full) {
                missing.push(format!("{where_} -> {full}"));
            }
        }

        fn check_opt(missing: &mut Vec<String>, key: &Option<&str>, where_: &str) {
            if let Some(key) = key {
                check(missing, key, where_);
            }
        }

        let mut missing = Vec::new();
        for section in SECTIONS {
            let at = format!("section {section}");
            check(&mut missing, &format!("section.{section}"), &at);
            for spec in specs(section) {
                match spec {
                    Spec::Group(label, h) => {
                        check(&mut missing, label, &at);
                        check_opt(&mut missing, &h, &at);
                    }
                    Spec::Check(_, label, h) | Spec::Spin(_, label, h, _, _) => {
                        check(&mut missing, label, &at);
                        check_opt(&mut missing, &h, &at);
                    }
                    Spec::Combo(_, label, h, options) => {
                        check(&mut missing, label, &at);
                        check_opt(&mut missing, &h, &at);
                        for (_, option) in options {
                            check(&mut missing, option, &at);
                        }
                    }
                    Spec::Value(label, value) => {
                        check(&mut missing, label, &at);
                        check(&mut missing, value, &at);
                    }
                    Spec::Button(_, text, h) | Spec::Danger(_, text, h) => {
                        check(&mut missing, text, &at);
                        check_opt(&mut missing, &h, &at);
                    }
                    Spec::Shortcut(command) => {
                        check(&mut missing, &format!("shortcut.{command}"), &at);
                    }
                }
            }
        }
        missing.sort();
        missing.dedup();
        assert!(
            missing.is_empty(),
            "untranslated preference strings: {missing:#?}"
        );
    }

    /// `text` with the region from `from` up to `to` removed, panicking if either
    /// anchor moves so a scan can never silently start seeing everything.
    fn cut(text: &str, from: &str, to: &str) -> String {
        let start = text
            .find(from)
            .unwrap_or_else(|| panic!("anchor moved: {from}"));
        let end = text[start..].find(to).map_or(text.len(), |at| start + at);
        format!("{}{}", &text[..start], &text[end..])
    }

    /// A row that stores a preference nothing reads is a control that lies: the
    /// user flips it, it is written to disk, and the app behaves as before (this
    /// is how `appearance.reduced_motion` and `performance.overlay` shipped, and
    /// what `performance.drag_preview` / `validation_mode` / `asset_cache_mb`
    /// still were when this scan first ran). Every Check/Combo/Spin key must
    /// therefore reach an accessor call — `.bool("k")`, `.str("k")`, `.int("k")`,
    /// `.get("k")` — outside the row table that lists it.
    ///
    /// Deliberately narrow, in the loud direction: naming an accessor means
    /// `prefs.rs` cannot satisfy a row with its `valid()` schema or `defaults()`
    /// (both files are out of the corpus), a key used only through a run-time
    /// built path (`format!("pixel_studio.{key}")`) fails until it is listed
    /// here, and so does a call rustfmt has wrapped across lines. Each of those
    /// shows up as a failing test, not as a silent pass.
    #[test]
    fn every_preference_row_is_consumed() {
        const ACCESSORS: [&str; 4] = [".bool(", ".str(", ".int(", ".get("];
        let root = std::path::Path::new(env!("CARGO_MANIFEST_DIR"));
        let mut readers = String::new();
        for dir in ["src", "ui"] {
            for entry in std::fs::read_dir(root.join(dir)).unwrap() {
                let path = entry.unwrap().path();
                // `prefs.rs` stores and validates keys; storing one is not reading it.
                if path.file_name().and_then(|n| n.to_str()) == Some("prefs.rs") {
                    continue;
                }
                let text = std::fs::read_to_string(&path).unwrap();
                readers.push_str(&match path.file_name().and_then(|n| n.to_str()) {
                    // Declaring a row is not the same as acting on its key.
                    Some("prefs_ui.rs") => {
                        cut(&text, "fn specs(", "/// The command bound to a key chord")
                    }
                    _ => text,
                });
            }
        }
        let mut unread = Vec::new();
        for section in SECTIONS {
            for spec in specs(section) {
                let key = match spec {
                    Spec::Check(key, _, _)
                    | Spec::Combo(key, _, _, _)
                    | Spec::Spin(key, _, _, _, _) => key,
                    _ => continue,
                };
                let read = ACCESSORS
                    .iter()
                    .any(|accessor| readers.contains(&format!("{accessor}\"{key}\")")));
                if !read {
                    unread.push(format!("{section}: {key}"));
                }
            }
        }
        unread.sort();
        assert!(
            unread.is_empty(),
            "preference rows nothing reads: {unread:#?}"
        );
    }
}
