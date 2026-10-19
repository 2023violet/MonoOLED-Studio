//! `project.oled.json` workspace (V1 `project_workspace.py`).
//!
//! Contracts kept from V1: schema 1, member paths resolve inside the project
//! root (following links, like `Path.resolve`), atomic manifest writes, an
//! external-modification fingerprint, case-insensitive collision checks, and
//! in-memory rollback when a save fails.

use std::path::{Path, PathBuf};

use mono_core::profiles::{OutputProfile, builtin_profile, validate_profile_id};
use mono_core::pyvalue::{py_int, py_str};
use mono_core::render::{normalize_path, posix};
use mono_core::{CoreError, CoreResult};
use serde_json::{Map, Value, json};

use crate::atomic::{atomic_write_json, python_json};
use crate::resources::{hex_digest, io_error};

pub const PROJECT_FILENAME: &str = "project.oled.json";
pub const PROJECT_SCHEMA_VERSION: i64 = 1;
const WINDOWS_RESERVED: [&str; 22] = [
    "CON", "PRN", "AUX", "NUL", "COM1", "COM2", "COM3", "COM4", "COM5", "COM6", "COM7", "COM8",
    "COM9", "LPT1", "LPT2", "LPT3", "LPT4", "LPT5", "LPT6", "LPT7", "LPT8", "LPT9",
];

pub const INVALID_PATH: &str = "E-PROJ-PATH";
pub const EXTERNAL_MODIFICATION: &str = "E-PROJ-EXTERNAL";
pub const KEY: &str = "E-CORE-KEY";
pub const EXISTS: &str = "E-IO-EXISTS";

fn invalid_path(message: impl Into<String>) -> CoreError {
    CoreError::new(INVALID_PATH, message)
}

fn key_error(message: impl Into<String>) -> CoreError {
    CoreError::new(KEY, format!("'{}'", message.into()))
}

/// Remove the Windows verbatim prefix that `canonicalize` adds.
fn strip_verbatim(path: PathBuf) -> PathBuf {
    let text = path.to_string_lossy();
    if let Some(rest) = text.strip_prefix(r"\\?\UNC\") {
        return PathBuf::from(format!(r"\\{rest}"));
    }
    if let Some(rest) = text.strip_prefix(r"\\?\") {
        return PathBuf::from(rest);
    }
    path
}

/// Python `Path.resolve()` (non-strict): canonicalise the longest existing prefix.
pub fn py_resolve(path: &Path) -> PathBuf {
    let absolute = if path.is_absolute() {
        normalize_path(path)
    } else {
        normalize_path(&std::env::current_dir().unwrap_or_default().join(path))
    };
    let mut existing = absolute.clone();
    let mut tail = Vec::new();
    loop {
        if let Ok(canonical) = std::fs::canonicalize(&existing) {
            let mut out = strip_verbatim(canonical);
            for part in tail.iter().rev() {
                out.push(part);
            }
            return normalize_path(&out);
        }
        match (
            existing.file_name().map(|n| n.to_os_string()),
            existing.parent().map(Path::to_path_buf),
        ) {
            (Some(name), Some(parent)) => {
                tail.push(name);
                existing = parent;
            }
            _ => return absolute,
        }
    }
}

/// V1 `resolve_under_root`.
pub fn resolve_under_root(root: &Path, member: &str, label: &str) -> CoreResult<PathBuf> {
    let root_path = py_resolve(root);
    let rel = Path::new(member);
    if rel.is_absolute() || rel.has_root() {
        return Err(invalid_path(format!("{label} must be relative: {member}")));
    }
    let resolved = py_resolve(&root_path.join(rel));
    if resolved != root_path && !resolved.starts_with(&root_path) {
        return Err(invalid_path(format!(
            "{label} escapes project root: {member}"
        )));
    }
    Ok(resolved)
}

/// V1 `validate_screen_id`.
pub fn validate_screen_id(value: &str) -> CoreResult<&str> {
    if value.is_empty() || value == "." || value == ".." {
        return Err(invalid_path("screen id must not be empty or dot path"));
    }
    if value != value.trim() || value.ends_with('.') || value.ends_with(' ') {
        return Err(invalid_path(format!("unsafe screen id: {value}")));
    }
    if value
        .chars()
        .any(|c| (c as u32) < 32 || "<>:\"/\\|?*".contains(c))
    {
        return Err(invalid_path(format!("unsafe screen id: {value}")));
    }
    let stem = value.split('.').next().unwrap_or("").to_uppercase();
    if WINDOWS_RESERVED.contains(&stem.as_str()) {
        return Err(invalid_path(format!("Windows-reserved screen id: {value}")));
    }
    if value.chars().count() > 96 {
        return Err(invalid_path("screen id is too long"));
    }
    Ok(value)
}

/// Python `str.casefold()` for the cases that matter in file names (adds ß→ss etc.).
pub fn casefold(value: &str) -> String {
    value.to_lowercase().replace('ß', "ss").replace('ς', "σ")
}

/// Python `Path(p).as_posix()` normalisation used for collision checks:
/// backslash to `/`, empty and `.` segments dropped, trailing `/` removed.
fn posix_key(path: &str) -> String {
    let segments: Vec<&str> = path
        .split(['/', '\\'])
        .filter(|s| !s.is_empty() && *s != ".")
        .collect();
    let prefix = if path.starts_with(['/', '\\']) {
        "/"
    } else {
        ""
    };
    casefold(&format!("{prefix}{}", segments.join("/")))
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ScreenRef {
    pub id: String,
    pub label: String,
    pub path: String,
}

#[derive(Debug, Clone)]
pub struct ProjectWorkspace {
    pub path: PathBuf,
    pub root: PathBuf,
    pub data: Map<String, Value>,
    disk_fingerprint: Option<String>,
}

pub fn blank_scene(product: &str, width: i64, height: i64) -> CoreResult<Value> {
    if width <= 0 || height <= 0 || height % 8 != 0 {
        return Err(CoreError::invalid(
            "monochrome VLSB canvas height must be a positive multiple of 8",
        ));
    }
    Ok(json!({
        "schema_version": 1,
        "product": product,
        "canvas": {"w": width, "h": height, "preview_scale": 6},
        "storage": {"layout": "VLSB column-page (SSD1306)", "bytes_per_frame": width * (height / 8), "polarity": "1 = lit"},
        "states": {},
        "elements": [],
        "timeline": [],
    }))
}

pub fn default_output_workbench() -> Value {
    let default = builtin_profile("ssd1306_vlsb_c").unwrap_or_default();
    json!({"schema": 1, "active_profile": "ssd1306_vlsb_c", "profiles": {"ssd1306_vlsb_c": default.to_json()}})
}

fn fingerprint(path: &Path) -> Option<String> {
    std::fs::read(path).ok().map(|bytes| hex_digest(&bytes))
}

impl ProjectWorkspace {
    fn new(path: &Path, data: Map<String, Value>) -> CoreResult<Self> {
        let path = py_resolve(path);
        let root = path.parent().map(Path::to_path_buf).unwrap_or_default();
        let disk_fingerprint = fingerprint(&path);
        let project = Self {
            path,
            root,
            data,
            disk_fingerprint,
        };
        project.validate_members()?;
        Ok(project)
    }

    /// V1 `ProjectWorkspace.load`.
    pub fn load(path: &Path) -> CoreResult<Self> {
        let resolved = py_resolve(path);
        let raw = std::fs::read(&resolved).map_err(|e| io_error(&resolved, &e))?;
        let value: Value =
            serde_json::from_slice(&raw).map_err(|e| CoreError::invalid(e.to_string()))?;
        let Value::Object(data) = value else {
            return Err(CoreError::invalid(
                "project file must contain a JSON object",
            ));
        };
        let schema = data
            .get("schema_version")
            .cloned()
            .unwrap_or(Value::from(0));
        if py_int(&schema) != Some(PROJECT_SCHEMA_VERSION) {
            return Err(CoreError::invalid(format!(
                "unsupported project schema: {}",
                py_str(&schema)
            )));
        }
        let mut project = Self::new(&resolved, data)?;
        project.disk_fingerprint = Some(hex_digest(&raw));
        Ok(project)
    }

    fn validate_members(&self) -> CoreResult<()> {
        let screens = match self.data.get("screens") {
            None => Vec::new(),
            Some(Value::Array(items)) => items.clone(),
            Some(_) => return Err(CoreError::invalid("project screens must be a list")),
        };
        let mut seen: Vec<String> = Vec::new();
        let mut seen_folded: Vec<String> = Vec::new();
        let mut seen_paths: Vec<String> = Vec::new();
        for raw in &screens {
            let Some(entry) = raw
                .as_object()
                .filter(|m| m.contains_key("id") && m.contains_key("path"))
            else {
                return Err(CoreError::invalid("invalid project screen entry"));
            };
            let sid = py_str(&entry["id"]);
            validate_screen_id(&sid)?;
            if seen.contains(&sid) {
                return Err(CoreError::invalid(format!("duplicate screen id: {sid}")));
            }
            let folded = casefold(&sid);
            if seen_folded.contains(&folded) {
                return Err(CoreError::invalid(format!(
                    "case-insensitive screen id collision: {sid}"
                )));
            }
            seen.push(sid.clone());
            seen_folded.push(folded);
            let path = py_str(&entry["path"]);
            let resolved = resolve_under_root(&self.root, &path, &format!("screen {sid} path"))?;
            if resolved == py_resolve(&self.root) {
                return Err(invalid_path(format!(
                    "screen {sid} path must identify a file"
                )));
            }
            let folded_path = posix_key(&path);
            if seen_paths.contains(&folded_path) {
                return Err(CoreError::invalid(format!(
                    "case-insensitive screen path collision: {path}"
                )));
            }
            seen_paths.push(folded_path);
        }
        match self.data.get("asset_dirs") {
            None => {}
            Some(Value::Array(values)) => {
                for value in values {
                    resolve_under_root(&self.root, &py_str(value), "asset directory")?;
                }
            }
            Some(_) => return Err(CoreError::invalid("asset_dirs must be a list")),
        }
        let active = self
            .data
            .get("active_screen")
            .map(py_str)
            .unwrap_or_default();
        if !active.is_empty() && !screens.is_empty() && !seen.contains(&active) {
            return Err(CoreError::invalid(format!(
                "active_screen does not exist: {active}"
            )));
        }
        if let Some(workbench) = self.data.get("output_workbench") {
            let schema_ok = workbench
                .as_object()
                .is_some_and(|w| w.get("schema").and_then(py_int) == Some(1));
            if !schema_ok {
                return Err(CoreError::invalid("unsupported output workbench schema"));
            }
            let profiles = workbench
                .get("profiles")
                .and_then(Value::as_object)
                .filter(|p| !p.is_empty());
            let Some(profiles) = profiles else {
                return Err(CoreError::invalid(
                    "output workbench profiles must be a non-empty object",
                ));
            };
            for (id, raw) in profiles {
                validate_profile_id(id)?;
                OutputProfile::from_json(raw)?;
            }
            let active_profile = workbench
                .get("active_profile")
                .map(py_str)
                .unwrap_or_default();
            if !profiles.contains_key(&active_profile) {
                return Err(CoreError::invalid("active output profile does not exist"));
            }
        }
        Ok(())
    }

    pub fn name(&self) -> String {
        self.data.get("name").map(py_str).unwrap_or_else(|| {
            self.root
                .file_name()
                .map(|n| n.to_string_lossy().into_owned())
                .unwrap_or_default()
        })
    }

    pub fn screens(&self) -> Vec<ScreenRef> {
        self.data
            .get("screens")
            .and_then(Value::as_array)
            .map(|items| {
                items
                    .iter()
                    .map(|x| ScreenRef {
                        id: py_str(&x["id"]),
                        label: x
                            .get("label")
                            .map(py_str)
                            .unwrap_or_else(|| py_str(&x["id"])),
                        path: py_str(&x["path"]),
                    })
                    .collect()
            })
            .unwrap_or_default()
    }

    pub fn active_screen(&self) -> String {
        self.data
            .get("active_screen")
            .map(py_str)
            .unwrap_or_else(|| {
                self.screens()
                    .first()
                    .map(|s| s.id.clone())
                    .unwrap_or_default()
            })
    }

    pub fn asset_dirs(&self) -> Vec<String> {
        self.data
            .get("asset_dirs")
            .and_then(Value::as_array)
            .map(|v| v.iter().map(py_str).collect())
            .unwrap_or_else(|| vec!["assets".into()])
    }

    pub fn resolve_member(&self, member: &str, label: &str) -> CoreResult<PathBuf> {
        resolve_under_root(&self.root, member, label)
    }

    pub fn screen(&self, screen_id: &str) -> CoreResult<ScreenRef> {
        self.screens()
            .into_iter()
            .find(|s| s.id == screen_id)
            .ok_or_else(|| key_error(format!("unknown screen id: {screen_id}")))
    }

    pub fn screen_path(&self, screen_id: &str) -> CoreResult<PathBuf> {
        let screen = self.screen(screen_id)?;
        resolve_under_root(
            &self.root,
            &screen.path,
            &format!("screen {screen_id} path"),
        )
    }

    /// `(active profile id, profiles in manifest order)`.
    pub fn output_profiles(&self) -> CoreResult<(String, Vec<(String, OutputProfile)>)> {
        let Some(workbench) = self.data.get("output_workbench") else {
            let default = builtin_profile("ssd1306_vlsb_c").unwrap_or_default();
            return Ok((
                "ssd1306_vlsb_c".into(),
                vec![("ssd1306_vlsb_c".into(), default)],
            ));
        };
        let mut profiles = Vec::new();
        if let Some(map) = workbench.get("profiles").and_then(Value::as_object) {
            for (id, raw) in map {
                profiles.push((id.clone(), OutputProfile::from_json(raw)?));
            }
        }
        Ok((
            workbench
                .get("active_profile")
                .map(py_str)
                .unwrap_or_default(),
            profiles,
        ))
    }

    fn manifest_text(&self) -> CoreResult<String> {
        python_json(&Value::Object(self.data.clone()))
    }

    /// V1 `save`: validate, refuse external modifications, atomic write.
    pub fn save(&mut self) -> CoreResult<PathBuf> {
        self.validate_members()?;
        let current = fingerprint(&self.path);
        match (&self.disk_fingerprint, &current) {
            (Some(expected), actual) if actual.as_ref() != Some(expected) => {
                return Err(CoreError::new(
                    EXTERNAL_MODIFICATION,
                    format!(
                        "project manifest was externally modified: {}",
                        posix(&self.path)
                    ),
                ));
            }
            (None, Some(_)) => {
                return Err(CoreError::new(
                    EXTERNAL_MODIFICATION,
                    format!(
                        "project manifest appeared externally: {}",
                        posix(&self.path)
                    ),
                ));
            }
            _ => {}
        }
        let _ = self.manifest_text()?;
        atomic_write_json(&self.path, &Value::Object(self.data.clone()))?;
        self.disk_fingerprint = fingerprint(&self.path);
        Ok(self.path.clone())
    }

    /// Run `change`, save, and restore the previous data if either step fails.
    fn transact(
        &mut self,
        change: impl FnOnce(&mut Map<String, Value>) -> CoreResult<()>,
    ) -> CoreResult<()> {
        let previous = self.data.clone();
        let result = change(&mut self.data).and_then(|()| self.save().map(|_| ()));
        if result.is_err() {
            self.data = previous;
        }
        result
    }

    pub fn set_active_screen(&mut self, screen_id: &str) -> CoreResult<()> {
        self.screen(screen_id)?;
        self.data
            .insert("active_screen".into(), Value::from(screen_id));
        Ok(())
    }

    pub fn set_asset_dirs(&mut self, values: &[String]) -> CoreResult<()> {
        for value in values {
            resolve_under_root(&self.root, value, "asset directory")?;
        }
        let checked: Vec<Value> = values.iter().map(|v| Value::from(v.as_str())).collect();
        self.transact(|data| {
            data.insert("asset_dirs".into(), Value::Array(checked));
            Ok(())
        })
    }

    fn workbench(data: &mut Map<String, Value>) -> CoreResult<&mut Map<String, Value>> {
        if !data.get("output_workbench").is_some_and(Value::is_object) {
            data.insert("output_workbench".into(), default_output_workbench());
        }
        data.get_mut("output_workbench")
            .and_then(Value::as_object_mut)
            .ok_or_else(|| CoreError::invalid("unsupported output workbench schema"))
    }

    pub fn upsert_output_profile(
        &mut self,
        profile_id: &str,
        profile: &OutputProfile,
        activate: bool,
    ) -> CoreResult<()> {
        validate_profile_id(profile_id)?;
        let normalized = profile.clone().normalized()?;
        let id = profile_id.to_string();
        self.transact(|data| {
            let workbench = Self::workbench(data)?;
            let profiles = workbench.entry("profiles").or_insert_with(|| json!({}));
            if let Value::Object(map) = profiles {
                map.insert(id.clone(), normalized.to_json());
            }
            if activate {
                workbench.insert("active_profile".into(), Value::from(id));
            }
            Ok(())
        })
    }

    pub fn set_active_output_profile(&mut self, profile_id: &str) -> CoreResult<()> {
        validate_profile_id(profile_id)?;
        let id = profile_id.to_string();
        self.transact(|data| {
            let workbench = Self::workbench(data)?;
            if !workbench
                .get("profiles")
                .and_then(Value::as_object)
                .is_some_and(|p| p.contains_key(&id))
            {
                return Err(key_error(format!("unknown output profile: {id}")));
            }
            workbench.insert("active_profile".into(), Value::from(id));
            Ok(())
        })
    }

    pub fn delete_output_profile(&mut self, profile_id: &str) -> CoreResult<()> {
        validate_profile_id(profile_id)?;
        let id = profile_id.to_string();
        self.transact(|data| {
            let workbench = Self::workbench(data)?;
            let Some(Value::Object(profiles)) = workbench.get_mut("profiles") else {
                return Err(key_error(format!("unknown output profile: {id}")));
            };
            if !profiles.contains_key(&id) {
                return Err(key_error(format!("unknown output profile: {id}")));
            }
            if profiles.len() <= 1 {
                return Err(CoreError::invalid(
                    "project must keep at least one output profile",
                ));
            }
            profiles.shift_remove(&id);
            let mut remaining: Vec<String> = profiles.keys().cloned().collect();
            remaining.sort();
            if workbench.get("active_profile").map(py_str).as_deref() == Some(id.as_str()) {
                workbench.insert("active_profile".into(), Value::from(remaining[0].clone()));
            }
            Ok(())
        })
    }

    /// V1 `add_screen` (blank scene or a copy of `source`).
    pub fn add_screen(
        &mut self,
        screen_id: &str,
        label: Option<&str>,
        source: Option<&Path>,
        canvas: Option<(i64, i64)>,
    ) -> CoreResult<ScreenRef> {
        validate_screen_id(screen_id)?;
        let folded = casefold(screen_id);
        if self.screens().iter().any(|s| casefold(&s.id) == folded) {
            return Err(CoreError::invalid(format!(
                "duplicate screen id: {screen_id}"
            )));
        }
        let rel = format!("scenes/{screen_id}.json");
        let target = resolve_under_root(&self.root, &rel, "new screen path")?;
        if target.exists() {
            return Err(CoreError::new(EXISTS, posix(&target)));
        }
        let payload = match source {
            Some(source) => {
                let source = py_resolve(source);
                if !source.is_file() {
                    return Err(io_error(
                        &source,
                        &std::io::Error::from(std::io::ErrorKind::NotFound),
                    ));
                }
                let raw = std::fs::read(&source).map_err(|e| io_error(&source, &e))?;
                let mut value: Value =
                    serde_json::from_slice(&raw).map_err(|e| CoreError::invalid(e.to_string()))?;
                let Some(map) = value.as_object_mut() else {
                    return Err(CoreError::invalid(
                        "source scene must contain a JSON object",
                    ));
                };
                map.shift_remove("project_root");
                value
            }
            None => {
                let (w, h) = canvas.unwrap_or_else(|| {
                    let c = self.data.get("default_canvas").and_then(Value::as_array);
                    (
                        c.and_then(|c| c.first()).and_then(py_int).unwrap_or(128),
                        c.and_then(|c| c.get(1)).and_then(py_int).unwrap_or(32),
                    )
                });
                blank_scene(&self.name(), w, h)?
            }
        };
        atomic_write_json(&target, &payload)?;
        let label = label
            .filter(|l| !l.is_empty())
            .unwrap_or(screen_id)
            .to_string();
        let item = json!({"id": screen_id, "label": label, "path": rel});
        let result = self.transact(|data| {
            match data.entry("screens").or_insert_with(|| json!([])) {
                Value::Array(items) => items.push(item),
                _ => return Err(CoreError::invalid("project screens must be a list")),
            }
            Ok(())
        });
        if let Err(error) = result {
            let _ = std::fs::remove_file(&target);
            return Err(error);
        }
        Ok(ScreenRef {
            id: screen_id.into(),
            label,
            path: rel,
        })
    }

    pub fn duplicate_screen(
        &mut self,
        screen_id: &str,
        new_id: &str,
        label: Option<&str>,
    ) -> CoreResult<ScreenRef> {
        let source = self.screen_path(screen_id)?;
        self.add_screen(
            new_id,
            Some(label.filter(|l| !l.is_empty()).unwrap_or(new_id)),
            Some(&source),
            None,
        )
    }

    pub fn rename_screen(
        &mut self,
        screen_id: &str,
        new_id: &str,
        label: Option<&str>,
    ) -> CoreResult<ScreenRef> {
        self.screen(screen_id)?;
        validate_screen_id(new_id)?;
        if casefold(new_id) != casefold(screen_id)
            && self
                .screens()
                .iter()
                .any(|s| casefold(&s.id) == casefold(new_id))
        {
            return Err(CoreError::invalid(format!("duplicate screen id: {new_id}")));
        }
        let old_path = self.screen_path(screen_id)?;
        if new_id == screen_id {
            let label = label.map(str::to_string);
            self.transact(|data| {
                if let Some(Value::Array(items)) = data.get_mut("screens") {
                    if let Some(item) = items.iter_mut().find(|i| py_str(&i["id"]) == screen_id) {
                        let current = item
                            .get("label")
                            .map(py_str)
                            .filter(|l| !l.is_empty())
                            .unwrap_or_else(|| new_id.to_string());
                        item["label"] =
                            Value::from(label.filter(|l| !l.is_empty()).unwrap_or(current));
                    }
                }
                Ok(())
            })?;
            return self.screen(screen_id);
        }
        let new_rel = format!("scenes/{new_id}.json");
        let new_path = resolve_under_root(&self.root, &new_rel, "renamed screen path")?;
        if new_path.exists() {
            return Err(CoreError::new(EXISTS, posix(&new_path)));
        }
        if let Some(parent) = new_path.parent() {
            std::fs::create_dir_all(parent).map_err(|e| io_error(parent, &e))?;
        }
        std::fs::rename(&old_path, &new_path).map_err(|e| io_error(&old_path, &e))?;
        let active = self.active_screen();
        let label = label
            .filter(|l| !l.is_empty())
            .unwrap_or(new_id)
            .to_string();
        let result = self.transact(|data| {
            if let Some(Value::Array(items)) = data.get_mut("screens") {
                if let Some(item) = items.iter_mut().find(|i| py_str(&i["id"]) == screen_id) {
                    item["id"] = Value::from(new_id);
                    item["label"] = Value::from(label.as_str());
                    item["path"] = Value::from(new_rel.as_str());
                }
            }
            if active == screen_id {
                data.insert("active_screen".into(), Value::from(new_id));
            }
            Ok(())
        });
        if let Err(error) = result {
            if new_path.exists() && !old_path.exists() {
                let _ = std::fs::rename(&new_path, &old_path);
            }
            return Err(error);
        }
        self.screen(new_id)
    }

    pub fn remove_screen(&mut self, screen_id: &str, delete_file: bool) -> CoreResult<()> {
        if self.screens().len() <= 1 {
            return Err(CoreError::invalid("project must keep at least one screen"));
        }
        let screen = self.screen(screen_id)?;
        let active = self.active_screen();
        self.transact(|data| {
            if let Some(Value::Array(items)) = data.get_mut("screens") {
                items.retain(|x| py_str(&x["id"]) != screen_id);
                if active == screen_id {
                    let first = items.first().map(|x| py_str(&x["id"])).unwrap_or_default();
                    data.insert("active_screen".into(), Value::from(first));
                }
            }
            Ok(())
        })?;
        if delete_file {
            let path = resolve_under_root(
                &self.root,
                &screen.path,
                &format!("screen {screen_id} path"),
            )?;
            let _ = std::fs::remove_file(path);
        }
        Ok(())
    }
}

/// V1 `create_project`.
pub fn create_project(root: &Path, name: &str, canvas: (i64, i64)) -> CoreResult<ProjectWorkspace> {
    let root = py_resolve(root);
    let manifest = root.join(PROJECT_FILENAME);
    let main_scene = root.join("scenes").join("main.json");
    for path in [&manifest, &main_scene] {
        if path.exists() {
            return Err(CoreError::new(EXISTS, posix(path)));
        }
    }
    for dir in [root.clone(), root.join("assets"), root.join("exports")] {
        std::fs::create_dir_all(&dir).map_err(|e| io_error(&dir, &e))?;
    }
    let data = json!({
        "schema_version": PROJECT_SCHEMA_VERSION,
        "name": name,
        "default_canvas": [canvas.0, canvas.1],
        "active_screen": "main",
        "asset_dirs": ["assets"],
        "output_workbench": default_output_workbench(),
        "screens": [],
    });
    let Value::Object(map) = data else {
        return Err(CoreError::invalid("project data"));
    };
    let mut project = ProjectWorkspace {
        path: manifest,
        root,
        data: map,
        disk_fingerprint: None,
    };
    project.add_screen("main", Some("Main"), None, Some(canvas))?;
    project.set_active_screen("main")?;
    project.save()?;
    Ok(project)
}
