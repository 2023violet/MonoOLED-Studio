//! Workspace preferences, file- and schema-compatible with V1 `preferences.py`
//! (same path, same keys), so existing users keep their settings.

use std::path::PathBuf;

use mono_project::atomic::atomic_write_json;
use serde_json::{Map, Value, json};

pub fn defaults() -> Value {
    json!({
        "schema_version": 1,
        "language": "zh_CN",
        "startup": {"reopen_last_project": false, "last_project": ""},
        "appearance": {"theme_mode": "light", "color_theme": "monooled-light", "density": "comfortable", "ui_scale": "100%", "reduced_motion": false},
        "input": {"wheel_action": "zoom", "middle_drag": "pan", "space_drag": "pan"},
        "canvas": {"grid": true, "bounds": true, "rulers": true, "zones": false, "snap": 0},
        "pixel_studio": {"left_button": "draw", "right_button": "erase", "brush_size": 1, "stroke_interpolation": true, "pixel_grid": true, "actual_preview": true, "rulers": true},
        "autosave": {"enabled": true, "interval_minutes": 3, "snapshots": 10, "prompt_recovery": true},
        "performance": {"drag_preview": "fast", "validation_mode": "edit_complete", "undo_history": 200, "asset_cache_mb": 512, "overlay": false},
        "shortcuts": {
            "preferences.open": "Ctrl+,", "workspace.canvas_only": "Ctrl+Space", "project.save": "Ctrl+S",
            "designer.undo": "Ctrl+Z", "designer.redo": "Ctrl+Y", "pixel.pencil": "B", "pixel.select": "M", "pixel.fill": "F"
        }
    })
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
        "appearance.theme_mode" => one_of(&["system", "light", "dark"]),
        "appearance.density" => one_of(&["compact", "comfortable", "spacious"]),
        "appearance.ui_scale" => value.as_str().is_some_and(|v| {
            v == "auto"
                || v.trim_end_matches('%')
                    .parse::<u32>()
                    .is_ok_and(|n| (75..=300).contains(&n))
        }),
        "canvas.snap" => value.as_i64().is_some_and(|v| [0, 1, 2, 4, 8].contains(&v)),
        "pixel_studio.brush_size" => int_range(1, 8),
        "autosave.interval_minutes" => int_range(1, 60),
        "autosave.snapshots" => int_range(1, 100),
        "performance.undo_history" => int_range(10, 2000),
        "performance.asset_cache_mb" => int_range(32, 4096),
        "performance.validation_mode" => one_of(&["edit_complete", "idle", "continuous"]),
        "performance.drag_preview" => one_of(&["fast", "exact"]),
        k if k.starts_with("shortcuts.") => value.as_str().is_some_and(|v| {
            !v.trim().is_empty() && !["none", "null"].contains(&v.trim().to_lowercase().as_str())
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
                    merge(&mut data, &incoming);
                }
            }
        }
        let template = defaults();
        normalize(&mut data, "", &template);
        Self { data, path }
    }

    pub fn get(&self, key: &str) -> Value {
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
}
