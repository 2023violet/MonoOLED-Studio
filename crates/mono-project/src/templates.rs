//! Component template library (V1 `component_templates.TemplateLibrary`),
//! stored at `<scene root>/.oled/templates.json`.

use std::path::{Path, PathBuf};

use mono_core::pyvalue::{py_int, py_str};
use mono_core::{CoreError, CoreResult};
use serde_json::{Map, Value, json};

use crate::atomic::{atomic_write, atomic_write_json};

pub struct TemplateLibrary {
    pub path: PathBuf,
    pub data: Map<String, Value>,
}

fn empty() -> Map<String, Value> {
    let mut data = Map::new();
    data.insert("schema_version".into(), json!(1));
    data.insert("templates".into(), json!({}));
    data
}

fn utc_stamp() -> String {
    let now = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .unwrap_or_default();
    format!("{}_{:06}Z", now.as_secs(), now.subsec_micros())
}

impl TemplateLibrary {
    pub fn for_root(scene_root: &Path) -> Self {
        Self::load(&scene_root.join(".oled").join("templates.json"))
    }

    /// Load the library; an unreadable or malformed file is quarantined and
    /// replaced by an empty library (V1 `_quarantine_corrupt`).
    pub fn load(path: &Path) -> Self {
        let mut library = Self {
            path: path.to_path_buf(),
            data: empty(),
        };
        let Ok(raw) = std::fs::read(path) else {
            return library;
        };
        let valid = serde_json::from_slice::<Value>(&raw)
            .ok()
            .and_then(|v| match v {
                Value::Object(map) => Some(map),
                _ => None,
            })
            .filter(|map| {
                map.get("schema_version").map_or(Some(1), py_int) == Some(1)
                    && map.get("templates").is_none_or(Value::is_object)
            });
        match valid {
            Some(map) => library.data = map,
            None => {
                if let Some(parent) = path.parent() {
                    let target = parent
                        .join("quarantine")
                        .join(format!("templates.corrupt.{}.json", utc_stamp()));
                    let _ = atomic_write(&target, &raw);
                }
            }
        }
        library
    }

    fn templates(&self) -> Option<&Map<String, Value>> {
        self.data.get("templates").and_then(Value::as_object)
    }

    /// Template names, sorted (V1 `names`).
    pub fn names(&self) -> Vec<String> {
        let mut names: Vec<String> = self
            .templates()
            .map(|t| t.keys().cloned().collect())
            .unwrap_or_default();
        names.sort();
        names
    }

    pub fn save_template(&mut self, name: &str, elements: &[Value]) -> CoreResult<()> {
        if name.trim().is_empty() {
            return Err(CoreError::invalid("template name must not be empty"));
        }
        if elements.is_empty() {
            return Err(CoreError::invalid(
                "template must contain at least one element",
            ));
        }
        let before = self.data.clone();
        let templates = self.data.entry("templates").or_insert_with(|| json!({}));
        if let Value::Object(map) = templates {
            map.insert(name.to_string(), Value::Array(elements.to_vec()));
        }
        if let Err(e) = atomic_write_json(&self.path, &Value::Object(self.data.clone())) {
            self.data = before;
            return Err(e);
        }
        Ok(())
    }

    /// V1 `instantiate`: prefix ids and offset `x`/`y` (and zone `x`/`y`).
    pub fn instantiate(
        &self,
        name: &str,
        prefix: &str,
        offset: (i64, i64),
    ) -> CoreResult<Vec<Value>> {
        let source = self
            .templates()
            .and_then(|t| t.get(name))
            .and_then(Value::as_array)
            .ok_or_else(|| CoreError::new("E-CORE-KEY", format!("'unknown template: {name}'")))?;
        let (dx, dy) = offset;
        let shift = |map: &mut Map<String, Value>| -> CoreResult<()> {
            for (key, delta) in [("x", dx), ("y", dy)] {
                if let Some(value) = map.get(key) {
                    let base = py_int(value)
                        .ok_or_else(|| CoreError::new("ValueError", format!("invalid {key}")))?;
                    map.insert(key.into(), json!(base + delta));
                }
            }
            Ok(())
        };
        let mut out = Vec::new();
        for item in source {
            let Value::Object(mut map) = item.clone() else {
                return Err(CoreError::new(
                    "TypeError",
                    "template element must be an object",
                ));
            };
            let id = map
                .get("id")
                .map(py_str)
                .ok_or_else(|| CoreError::new("E-CORE-KEY", "'id'"))?;
            map.insert("id".into(), json!(format!("{prefix}{id}")));
            shift(&mut map)?;
            if let Some(Value::Object(zone)) = map.get_mut("zone") {
                shift(zone)?;
            }
            out.push(Value::Object(map));
        }
        Ok(out)
    }
}

#[cfg(test)]
mod tests {
    #![allow(clippy::unwrap_used)]
    use super::*;

    fn temp(name: &str) -> PathBuf {
        let dir =
            std::env::temp_dir().join(format!("mono-templates-{name}-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&dir);
        dir
    }

    #[test]
    fn save_and_instantiate_round_trip() {
        let root = temp("rt");
        let mut lib = TemplateLibrary::for_root(&root);
        assert!(lib.names().is_empty());
        let elements = vec![
            json!({"id": "icon", "type": "image", "x": 2, "y": 3, "zone": {"x": 1, "y": 1, "w": 4, "h": 4}}),
        ];
        lib.save_template("badge", &elements).unwrap();
        let reloaded = TemplateLibrary::for_root(&root);
        assert_eq!(reloaded.names(), vec!["badge".to_string()]);
        let items = reloaded.instantiate("badge", "b_", (10, 20)).unwrap();
        assert_eq!(items[0]["id"], "b_icon");
        assert_eq!(
            (items[0]["x"].clone(), items[0]["y"].clone()),
            (json!(12), json!(23))
        );
        assert_eq!(items[0]["zone"]["x"], json!(11));
        assert!(reloaded.instantiate("missing", "", (0, 0)).is_err());
        let _ = std::fs::remove_dir_all(&root);
    }

    #[test]
    fn invalid_input_is_rejected_and_corrupt_file_quarantined() {
        let root = temp("bad");
        let mut lib = TemplateLibrary::for_root(&root);
        assert!(lib.save_template(" ", &[json!({"id": "a"})]).is_err());
        assert!(lib.save_template("x", &[]).is_err());
        let path = root.join(".oled").join("templates.json");
        std::fs::create_dir_all(path.parent().unwrap()).unwrap();
        std::fs::write(&path, b"{not json").unwrap();
        let lib = TemplateLibrary::for_root(&root);
        assert!(lib.names().is_empty());
        let quarantine = root.join(".oled").join("quarantine");
        assert_eq!(std::fs::read_dir(quarantine).unwrap().count(), 1);
        let _ = std::fs::remove_dir_all(&root);
    }
}
