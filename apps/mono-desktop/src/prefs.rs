//! Workspace preferences, file- and schema-compatible with V1 `preferences.py`
//! (same path, same keys), so existing users keep their settings.

use std::path::PathBuf;

use mono_project::atomic::atomic_write_json;
use serde_json::{Map, Value, json};

pub fn defaults() -> Value {
    json!({
        "schema_version": 1,
        "language": "zh_CN",
        "startup": {"reopen_last_project": false, "last_project": "", "recent_projects": []},
        "appearance": {"theme_mode": "light", "color_theme": "monooled-light", "density": "comfortable", "ui_scale": "100%", "reduced_motion": false},
        "input": {"wheel_action": "zoom", "middle_drag": "pan", "space_drag": "pan"},
        "canvas": {"grid": true, "bounds": true, "rulers": true, "zones": false, "snap": 0},
        "pixel_studio": {"left_button": "draw", "right_button": "erase", "brush_size": 1, "stroke_interpolation": true, "pixel_grid": true, "actual_preview": true, "rulers": true,
            "palette_mode": "auto",
            // V1 output workbench "显示" group.
            "canvas_background": "#000000", "grid_color": "#495028", "pixel_fill": "#FFFFFF", "pixel_border": "#FFFF00",
            "output_font": "", "output_font_size": 14},
        "autosave": {"enabled": true, "interval_minutes": 3, "snapshots": 10, "prompt_recovery": true},
        "performance": {"drag_preview": "fast", "validation_mode": "edit_complete", "undo_history": 200, "asset_cache_mb": 512, "overlay": false},
        "shortcuts": crate::commands::default_shortcuts()
    })
}

/// Default chord for a registered command, or `None` for an unknown id.
pub fn default_shortcut(command: &str) -> Option<String> {
    defaults()
        .get("shortcuts")
        .and_then(|shortcuts| shortcuts.get(command))
        .and_then(Value::as_str)
        .map(str::to_string)
}

/// V1 `preferences_path()`.
pub fn preferences_path() -> PathBuf {
    if cfg!(windows) {
        let base = std::env::var_os("LOCALAPPDATA")
            .map(PathBuf::from)
            .or_else(home)
            .unwrap_or_default();
        base.join("MonoOLEDStudio").join("preferences.json")
    } else {
        let base = std::env::var_os("XDG_CONFIG_HOME")
            .map(PathBuf::from)
            .or_else(|| home().map(|h| h.join(".config")))
            .unwrap_or_default();
        base.join("monooled-studio").join("preferences.json")
    }
}

fn home() -> Option<PathBuf> {
    std::env::var_os("HOME")
        .or_else(|| std::env::var_os("USERPROFILE"))
        .map(PathBuf::from)
}

fn merge(base: &mut Value, incoming: &Value) {
    match (base, incoming) {
        (Value::Object(b), Value::Object(i)) => {
            for (k, v) in i {
                match b.get_mut(k) {
                    Some(slot) if slot.is_object() && v.is_object() => merge(slot, v),
                    _ => {
                        b.insert(k.clone(), v.clone());
                    }
                }
            }
        }
        (b, i) => *b = i.clone(),
    }
}

fn valid(key: &str, value: &Value) -> bool {
    let one_of = |options: &[&str]| value.as_str().is_some_and(|v| options.contains(&v));
    let int_range = |lo: i64, hi: i64| value.as_i64().is_some_and(|v| (lo..=hi).contains(&v));
    match key {
        "language" => one_of(&["zh_CN", "en_US"]),
        "appearance.theme_mode" => one_of(&["system", "light", "dark", "high-contrast"]),
        "pixel_studio.palette_mode" => one_of(&["auto", "custom"]),
        "appearance.density" => one_of(&["compact", "comfortable", "spacious"]),
        "appearance.ui_scale" => value.as_str().is_some_and(|v| {
            v == "auto"
                || v.trim_end_matches('%')
                    .parse::<u32>()
                    .is_ok_and(|n| (75..=300).contains(&n))
        }),
        "canvas.snap" => value.as_i64().is_some_and(|v| [0, 1, 2, 4, 8].contains(&v)),
        "pixel_studio.brush_size" => int_range(1, 8),
        "pixel_studio.output_font_size" => int_range(8, 32),
        "pixel_studio.canvas_background"
        | "pixel_studio.grid_color"
        | "pixel_studio.pixel_fill"
        | "pixel_studio.pixel_border" => value
            .as_str()
            .is_some_and(|v| crate::canvas::parse_color(v).is_some()),
        "autosave.interval_minutes" => int_range(1, 60),
        "autosave.snapshots" => int_range(1, 100),
        "performance.undo_history" => int_range(10, 2000),
        "performance.asset_cache_mb" => int_range(32, 4096),
        "performance.validation_mode" => one_of(&["edit_complete", "idle", "continuous"]),
        "performance.drag_preview" => one_of(&["fast", "exact"]),
        "startup.recent_projects" => value
            .as_array()
            .is_some_and(|values| values.iter().all(Value::is_string)),
        k if k.starts_with("shortcuts.") => value.as_str().is_some_and(|v| {
            let trimmed = v.trim();
            trimmed.is_empty() || !["none", "null"].contains(&trimmed.to_lowercase().as_str())
        }),
        _ => match defaults().pointer(&format!("/{}", key.replace('.', "/"))) {
            Some(Value::Bool(_)) => value.is_boolean(),
            Some(Value::String(_)) => value.is_string(),
            Some(Value::Number(_)) => value.is_number(),
            _ => true,
        },
    }
}

fn normalize(value: &mut Value, prefix: &str, defaults: &Value) {
    let Value::Object(map) = value else { return };
    let keys: Vec<String> = map.keys().cloned().collect();
    for key in keys {
        let full = if prefix.is_empty() {
            key.clone()
        } else {
            format!("{prefix}.{key}")
        };
        let default = defaults.get(&key).cloned().unwrap_or(Value::Null);
        let Some(slot) = map.get_mut(&key) else {
            continue;
        };
        if slot.is_object() && default.is_object() {
            normalize(slot, &full, &default);
        } else if !default.is_null() && !valid(&full, slot) {
            *slot = default;
        }
    }
}

/// Pre-`palette_mode` files with non-default colours keep their look as `custom`.
fn legacy_custom_palette(incoming: &Value) -> bool {
    if incoming.pointer("/pixel_studio/palette_mode").is_some() {
        return false;
    }
    let base = defaults();
    [
        "canvas_background",
        "grid_color",
        "pixel_fill",
        "pixel_border",
    ]
    .iter()
    .any(|key| {
        let saved = incoming
            .pointer(&format!("/pixel_studio/{key}"))
            .and_then(Value::as_str);
        let default = base
            .pointer(&format!("/pixel_studio/{key}"))
            .and_then(Value::as_str);
        saved.is_some_and(|saved| Some(saved) != default)
    })
}

pub struct Preferences {
    pub data: Value,
    path: PathBuf,
}

impl Preferences {
    pub fn load() -> Self {
        Self::load_from(preferences_path())
    }

    pub fn load_from(path: PathBuf) -> Self {
        let mut data = defaults();
        if let Ok(raw) = std::fs::read(&path) {
            if let Ok(incoming) = serde_json::from_slice::<Value>(&raw) {
                if incoming.is_object() {
                    let legacy_custom = legacy_custom_palette(&incoming);
                    merge(&mut data, &incoming);
                    if legacy_custom {
                        if let Some(Value::Object(map)) = data.get_mut("pixel_studio") {
                            map.insert("palette_mode".into(), json!("custom"));
                        }
                    }
                }
            }
        }
        let template = defaults();
        normalize(&mut data, "", &template);
        Self { data, path }
    }

    pub fn get(&self, key: &str) -> Value {
        // `shortcuts.*` is a flat namespace (the command id may itself contain
        // dots), unlike the dotted JSON paths used by every other preference.
        if let Some(command) = key.strip_prefix("shortcuts.") {
            return self
                .data
                .get("shortcuts")
                .and_then(|shortcuts| shortcuts.get(command))
                .cloned()
                .unwrap_or(Value::Null);
        }
        self.data
            .pointer(&format!("/{}", key.replace('.', "/")))
            .cloned()
            .unwrap_or(Value::Null)
    }

    pub fn str(&self, key: &str) -> String {
        self.get(key).as_str().unwrap_or_default().to_string()
    }

    pub fn bool(&self, key: &str) -> bool {
        self.get(key).as_bool().unwrap_or(false)
    }

    pub fn int(&self, key: &str) -> i64 {
        self.get(key).as_i64().unwrap_or(0)
    }

    /// Set a dotted key (shortcuts stay flat: `shortcuts.designer.undo`).
    pub fn set(&mut self, key: &str, value: Value) -> bool {
        if !valid(key, &value) {
            return false;
        }
        let (section, leaf) = match key.strip_prefix("shortcuts.") {
            Some(command) => (vec!["shortcuts"], command.to_string()),
            None => {
                let mut parts: Vec<&str> = key.split('.').collect();
                let leaf = parts.pop().unwrap_or_default().to_string();
                (parts, leaf)
            }
        };
        let mut node = &mut self.data;
        for part in section {
            if !node.get(part).is_some_and(Value::is_object) {
                if let Value::Object(map) = node {
                    map.insert(part.into(), Value::Object(Map::new()));
                }
            }
            let Some(next) = node.get_mut(part) else {
                return false;
            };
            node = next;
        }
        if let Value::Object(map) = node {
            map.insert(leaf, value);
        }
        true
    }

    pub fn save(&self) -> bool {
        atomic_write_json(&self.path, &self.data).is_ok()
    }

    /// Restore a shortcut to its shipped default. Returns false for unknown ids.
    pub fn reset_shortcut(&mut self, command: &str) -> bool {
        let Some(value) = default_shortcut(command) else {
            return false;
        };
        self.set(&format!("shortcuts.{command}"), Value::String(value))
    }
}

#[cfg(test)]
mod tests {
    #![allow(clippy::unwrap_used)]
    use super::*;

    fn prefs() -> Preferences {
        Preferences {
            data: defaults(),
            path: PathBuf::new(),
        }
    }

    #[test]
    fn shortcuts_read_as_flat_keys() {
        let prefs = prefs();
        assert_eq!(prefs.str("shortcuts.project.save"), "Ctrl+S");
        assert_eq!(prefs.str("shortcuts.designer.undo"), "Ctrl+Z");
        assert_eq!(prefs.str("shortcuts.preferences.open"), "Ctrl+,");
    }

    #[test]
    fn dotted_paths_still_resolve() {
        let prefs = prefs();
        assert_eq!(prefs.str("appearance.theme_mode"), "light");
        assert_eq!(prefs.int("autosave.interval_minutes"), 3);
        assert!(prefs.bool("canvas.grid"));
    }

    #[test]
    fn set_then_get_shortcut_round_trips() {
        let mut prefs = prefs();
        assert!(prefs.set("shortcuts.project.save", json!("Ctrl+Alt+S")));
        assert_eq!(prefs.str("shortcuts.project.save"), "Ctrl+Alt+S");
    }

    #[test]
    fn empty_shortcut_clears_binding_and_resets() {
        let mut prefs = prefs();
        assert!(prefs.set("shortcuts.project.save", json!("")));
        assert_eq!(prefs.str("shortcuts.project.save"), "");
        assert!(prefs.reset_shortcut("project.save"));
        assert_eq!(prefs.str("shortcuts.project.save"), "Ctrl+S");
    }

    #[test]
    fn unknown_shortcut_reset_is_rejected() {
        let mut prefs = prefs();
        assert!(!prefs.reset_shortcut("designer.paste"));
    }

    #[test]
    fn recent_list_persists() {
        let path = std::env::temp_dir().join(format!(
            "mono-prefs-recent-{}/preferences.json",
            std::process::id()
        ));
        let _ = std::fs::remove_dir_all(path.parent().unwrap());
        let mut prefs = Preferences::load_from(path.clone());
        assert!(prefs.set(
            "startup.recent_projects",
            json!(["D:/a/project.oled.json", "D:/b/project.oled.json"])
        ));
        assert!(prefs.save());
        let reloaded = Preferences::load_from(path.clone());
        assert_eq!(
            reloaded.get("startup.recent_projects"),
            json!(["D:/a/project.oled.json", "D:/b/project.oled.json"])
        );
        let _ = std::fs::remove_dir_all(path.parent().unwrap());
    }

    #[test]
    fn invalid_recent_schema_falls_back() {
        let root = std::env::temp_dir().join(format!("mono-prefs-bad-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&root);
        std::fs::create_dir_all(&root).unwrap();
        let path = root.join("preferences.json");
        std::fs::write(&path, r#"{"startup":{"recent_projects":"not a list"}}"#).unwrap();
        let prefs = Preferences::load_from(path);
        assert_eq!(prefs.get("startup.recent_projects"), json!([]));
        let _ = std::fs::remove_dir_all(&root);
    }
}
