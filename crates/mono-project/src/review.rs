//! Review sidecar: `<project>/review/review.json`.
//!
//! Holds user annotations and named scenarios. It is deliberately outside
//! `project.oled.json` (no manifest fingerprint churn) and outside the export
//! contract (no Automation JSON change), and it is meant to be committed so a
//! review travels with the book.

use std::collections::BTreeMap;
use std::path::{Path, PathBuf};

use mono_core::{CoreError, CoreResult};
use serde_json::{Map, Value, json};

use crate::atomic::{atomic_write, python_json};
use crate::autosave::utc_stamps;
use crate::resources::hex_digest;

pub const REVIEW_DIR: &str = "review";
pub const REVIEW_FILE: &str = "review/review.json";
pub const SCHEMA_VERSION: i64 = 1;
const MAX_TITLE: usize = 120;
const MAX_BODY: usize = 4000;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum AnnotationKind {
    Defect,
    Decision,
    Explanation,
}

impl AnnotationKind {
    pub fn as_str(self) -> &'static str {
        match self {
            Self::Defect => "defect",
            Self::Decision => "decision",
            Self::Explanation => "explanation",
        }
    }

    pub fn parse(text: &str) -> Option<Self> {
        match text {
            "defect" => Some(Self::Defect),
            "decision" => Some(Self::Decision),
            "explanation" => Some(Self::Explanation),
            _ => None,
        }
    }
}

#[derive(Debug, Clone, Default, PartialEq, Eq)]
pub struct Evidence {
    pub sha256: String,
    pub lit_pixels: usize,
    pub frame: Option<String>,
    pub source: String,
}

#[derive(Debug, Clone, PartialEq)]
pub struct Annotation {
    pub id: String,
    pub kind: AnnotationKind,
    pub screen: String,
    pub state: Map<String, Value>,
    pub element: Option<String>,
    pub title: String,
    pub body: String,
    pub evidence: Evidence,
    pub created_utc: String,
    pub updated_utc: String,
}

#[derive(Debug, Clone, PartialEq)]
pub struct Scenario {
    pub id: String,
    pub label: String,
    pub set: Map<String, Value>,
    pub created_utc: String,
}

pub struct ReviewStore {
    pub path: PathBuf,
    data: Map<String, Value>,
    fingerprint: Option<String>,
}

fn empty() -> Map<String, Value> {
    let mut data = Map::new();
    data.insert("schema_version".into(), json!(SCHEMA_VERSION));
    data.insert("annotations".into(), json!([]));
    data.insert("scenarios".into(), json!([]));
    data
}

fn now() -> (String, String) {
    let duration = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .unwrap_or_default();
    utc_stamps(duration.as_secs() as i64, duration.subsec_micros())
}

fn hex64(text: &str) -> bool {
    text.len() == 64 && text.chars().all(|c| c.is_ascii_hexdigit())
}

impl Evidence {
    fn to_json(&self) -> Value {
        json!({
            "sha256": self.sha256,
            "lit_pixels": self.lit_pixels,
            "frame": self.frame,
            "source": self.source,
        })
    }

    fn from_json(value: &Value) -> Self {
        let field = |key: &str| {
            value
                .get(key)
                .and_then(Value::as_str)
                .unwrap_or_default()
                .to_string()
        };
        Self {
            sha256: field("sha256"),
            lit_pixels: value.get("lit_pixels").and_then(Value::as_u64).unwrap_or(0) as usize,
            frame: value
                .get("frame")
                .and_then(Value::as_str)
                .map(str::to_string),
            source: field("source"),
        }
    }
}

impl Annotation {
    fn to_json(&self) -> Value {
        json!({
            "id": self.id,
            "kind": self.kind.as_str(),
            "screen": self.screen,
            "state": self.state,
            "element": self.element,
            "title": self.title,
            "body": self.body,
            "evidence": self.evidence.to_json(),
            "created_utc": self.created_utc,
            "updated_utc": self.updated_utc,
        })
    }

    /// Lenient: a record with an unknown kind or a missing anchor is skipped
    /// instead of failing the whole review file.
    fn from_json(value: &Value) -> Option<Self> {
        let text = |key: &str| value.get(key).and_then(Value::as_str).map(str::to_string);
        let screen = text("screen")?;
        if screen.trim().is_empty() {
            return None;
        }
        Some(Self {
            id: text("id")?,
            kind: AnnotationKind::parse(&text("kind")?)?,
            screen,
            state: value
                .get("state")
                .and_then(Value::as_object)
                .cloned()
                .unwrap_or_default(),
            element: value
                .get("element")
                .and_then(Value::as_str)
                .filter(|e| !e.is_empty())
                .map(str::to_string),
            title: text("title")?,
            body: value
                .get("body")
                .and_then(Value::as_str)
                .unwrap_or_default()
                .to_string(),
            evidence: value
                .get("evidence")
                .map(Evidence::from_json)
                .unwrap_or_default(),
            created_utc: value
                .get("created_utc")
                .and_then(Value::as_str)
                .unwrap_or_default()
                .to_string(),
            updated_utc: value
                .get("updated_utc")
                .and_then(Value::as_str)
                .unwrap_or_default()
                .to_string(),
        })
    }
}

impl Scenario {
    fn to_json(&self) -> Value {
        json!({
            "id": self.id,
            "label": self.label,
            "set": self.set,
            "created_utc": self.created_utc,
        })
    }

    fn from_json(value: &Value) -> Option<Self> {
        let label = value.get("label").and_then(Value::as_str)?.to_string();
        if label.trim().is_empty() {
            return None;
        }
        Some(Self {
            id: value
                .get("id")
                .and_then(Value::as_str)
                .unwrap_or_default()
                .to_string(),
            label,
            set: value
                .get("set")
                .and_then(Value::as_object)
                .cloned()
                .unwrap_or_default(),
            created_utc: value
                .get("created_utc")
                .and_then(Value::as_str)
                .unwrap_or_default()
                .to_string(),
        })
    }
}

impl ReviewStore {
    pub fn for_root(root: &Path) -> CoreResult<Self> {
        Self::load(&root.join(REVIEW_FILE))
    }

    /// A missing file is an empty review; a malformed one is quarantined and
    /// replaced by an empty review; an unknown schema version is an error and
    /// the file is left untouched.
    pub fn load(path: &Path) -> CoreResult<Self> {
        let raw = match std::fs::read(path) {
            Ok(raw) => raw,
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => {
                return Ok(Self {
                    path: path.to_path_buf(),
                    data: empty(),
                    fingerprint: None,
                });
            }
            Err(error) => {
                return Err(CoreError::new(
                    "E-REVIEW-IO",
                    format!("{}: {error}", path.display()),
                ));
            }
        };
        let Some(map) = serde_json::from_slice::<Value>(&raw)
            .ok()
            .and_then(|value| value.as_object().cloned())
        else {
            return Ok(Self::quarantine(path, &raw));
        };
        match map.get("schema_version").and_then(Value::as_i64) {
            Some(SCHEMA_VERSION) => {}
            Some(other) => {
                return Err(CoreError::new(
                    "E-REVIEW-SCHEMA",
                    format!("unsupported review schema_version {other}"),
                ));
            }
            None => {
                return Err(CoreError::new(
                    "E-REVIEW-SCHEMA",
                    "review file has no schema_version",
                ));
            }
        }
        Ok(Self {
            path: path.to_path_buf(),
            data: map,
            fingerprint: Some(hex_digest(&raw)),
        })
    }

    fn quarantine(path: &Path, raw: &[u8]) -> Self {
        let (stamp, _) = now();
        let preserved = match path.parent() {
            Some(parent) => {
                let target = parent
                    .join("quarantine")
                    .join(format!("review.corrupt.{stamp}.json"));
                atomic_write(&target, raw).is_ok()
            }
            None => false,
        };
        // The corrupt bytes are preserved in quarantine, so the next save may
        // replace the original instead of tripping the external-change guard.
        // If the copy failed, keep no fingerprint: the guard must protect it.
        Self {
            path: path.to_path_buf(),
            data: empty(),
            fingerprint: preserved.then(|| hex_digest(raw)),
        }
    }

    /// Read annotations without migrating, quarantining or rewriting the file
    /// (the CLI review pack must stay read-only).
    pub fn read_annotations(path: &Path) -> CoreResult<Vec<Annotation>> {
        let raw = match std::fs::read(path) {
            Ok(raw) => raw,
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => return Ok(Vec::new()),
            Err(error) => {
                return Err(CoreError::new(
                    "E-REVIEW",
                    format!("{}: {error}", mono_core::render::posix(path)),
                ));
            }
        };
        let value: Value = serde_json::from_slice(&raw)
            .map_err(|error| CoreError::new("E-REVIEW", error.to_string()))?;
        match value.get("schema_version").and_then(Value::as_i64) {
            Some(SCHEMA_VERSION) => {}
            Some(version) => {
                return Err(CoreError::new(
                    "E-REVIEW",
                    format!("unsupported review schema_version {version}"),
                ));
            }
            None => {
                return Err(CoreError::new(
                    "E-REVIEW",
                    "review file has no schema_version",
                ));
            }
        }
        Ok(value
            .get("annotations")
            .and_then(Value::as_array)
            .into_iter()
            .flatten()
            .filter_map(Annotation::from_json)
            .collect())
    }

    pub fn annotations(&self) -> Vec<Annotation> {
        self.data
            .get("annotations")
            .and_then(Value::as_array)
            .into_iter()
            .flatten()
            .filter_map(Annotation::from_json)
            .collect()
    }

    pub fn scenarios(&self) -> Vec<Scenario> {
        self.data
            .get("scenarios")
            .and_then(Value::as_array)
            .into_iter()
            .flatten()
            .filter_map(Scenario::from_json)
            .collect()
    }

    pub fn annotations_for(&self, screen: &str) -> Vec<Annotation> {
        self.annotations()
            .into_iter()
            .filter(|a| a.screen == screen)
            .collect()
    }

    pub fn counts(&self) -> (usize, usize, usize) {
        let mut counts = (0, 0, 0);
        for annotation in self.annotations() {
            match annotation.kind {
                AnnotationKind::Defect => counts.0 += 1,
                AnnotationKind::Decision => counts.1 += 1,
                AnnotationKind::Explanation => counts.2 += 1,
            }
        }
        counts
    }

    pub fn counts_by_screen(&self) -> BTreeMap<String, usize> {
        let mut counts: BTreeMap<String, usize> = BTreeMap::new();
        for annotation in self.annotations() {
            *counts.entry(annotation.screen).or_default() += 1;
        }
        counts
    }

    /// Insert or replace by id; an empty id is generated. Returns the id.
    pub fn upsert_annotation(&mut self, mut annotation: Annotation) -> CoreResult<String> {
        let (compact, iso) = now();
        if annotation.id.is_empty() {
            let existing: Vec<String> = self.annotations().into_iter().map(|a| a.id).collect();
            let mut id = format!("n_{compact}");
            let mut suffix = 1;
            while existing.contains(&id) {
                id = format!("n_{compact}_{suffix}");
                suffix += 1;
            }
            annotation.id = id;
        }
        if annotation.created_utc.is_empty() {
            annotation.created_utc = iso.clone();
        }
        annotation.updated_utc = iso;
        validate_annotation(&annotation)?;
        let id = annotation.id.clone();
        let before = self.data.clone();
        let list = self.data.entry("annotations").or_insert_with(|| json!([]));
        let Some(items) = list.as_array_mut() else {
            self.data = before;
            return Err(CoreError::new(
                "E-REVIEW-SCHEMA",
                "annotations is not an array",
            ));
        };
        match items
            .iter_mut()
            .find(|item| item.get("id").and_then(Value::as_str) == Some(id.as_str()))
        {
            Some(slot) => *slot = annotation.to_json(),
            None => items.push(annotation.to_json()),
        }
        if let Err(error) = self.save() {
            self.data = before;
            return Err(error);
        }
        Ok(id)
    }

    pub fn remove_annotation(&mut self, id: &str) -> CoreResult<bool> {
        let before = self.data.clone();
        let Some(items) = self
            .data
            .get_mut("annotations")
            .and_then(Value::as_array_mut)
        else {
            return Ok(false);
        };
        let len = items.len();
        items.retain(|item| item.get("id").and_then(Value::as_str) != Some(id));
        if items.len() == len {
            return Ok(false);
        }
        if let Err(error) = self.save() {
            self.data = before;
            return Err(error);
        }
        Ok(true)
    }

    /// Insert or replace a scenario by id; an empty id is generated.
    pub fn upsert_scenario(&mut self, mut scenario: Scenario) -> CoreResult<String> {
        let (compact, iso) = now();
        if scenario.id.is_empty() {
            let existing: Vec<String> = self.scenarios().into_iter().map(|s| s.id).collect();
            let mut id = format!("s_{compact}");
            let mut suffix = 1;
            while existing.contains(&id) {
                id = format!("s_{compact}_{suffix}");
                suffix += 1;
            }
            scenario.id = id;
        }
        if scenario.created_utc.is_empty() {
            scenario.created_utc = iso;
        }
        validate_scenario(&scenario)?;
        let id = scenario.id.clone();
        let before = self.data.clone();
        let list = self.data.entry("scenarios").or_insert_with(|| json!([]));
        let Some(items) = list.as_array_mut() else {
            self.data = before;
            return Err(CoreError::new(
                "E-REVIEW-SCHEMA",
                "scenarios is not an array",
            ));
        };
        match items
            .iter_mut()
            .find(|item| item.get("id").and_then(Value::as_str) == Some(id.as_str()))
        {
            Some(slot) => *slot = scenario.to_json(),
            None => items.push(scenario.to_json()),
        }
        if let Err(error) = self.save() {
            self.data = before;
            return Err(error);
        }
        Ok(id)
    }

    fn save(&mut self) -> CoreResult<()> {
        let mut text = python_json(&Value::Object(self.data.clone()))?;
        text.push('\n');
        // Serialize first, then re-read, so the external-change window is only
        // the atomic write itself. The check stays best-effort: a writer that
        // lands between this read and the rename is not detected.
        let current = std::fs::read(&self.path).ok().map(|b| hex_digest(&b));
        let unchanged = match (&self.fingerprint, &current) {
            (None, None) => true,
            (Some(expected), Some(actual)) => expected == actual,
            _ => false,
        };
        if !unchanged {
            return Err(CoreError::new(
                "E-REVIEW-EXTERNAL",
                "review.json changed outside the editor; reopen the project",
            ));
        }
        atomic_write(&self.path, text.as_bytes())?;
        self.fingerprint = Some(hex_digest(text.as_bytes()));
        Ok(())
    }
}

fn validate_annotation(annotation: &Annotation) -> CoreResult<()> {
    if annotation.screen.trim().is_empty() {
        return Err(CoreError::invalid("annotation screen must not be empty"));
    }
    if annotation.title.trim().is_empty() {
        return Err(CoreError::invalid("annotation title must not be empty"));
    }
    if annotation.title.chars().count() > MAX_TITLE {
        return Err(CoreError::invalid(format!(
            "annotation title exceeds {MAX_TITLE} characters"
        )));
    }
    if annotation.body.chars().count() > MAX_BODY {
        return Err(CoreError::invalid(format!(
            "annotation body exceeds {MAX_BODY} characters"
        )));
    }
    let sha = &annotation.evidence.sha256;
    if !sha.is_empty() && !hex64(sha) {
        return Err(CoreError::invalid(
            "annotation evidence sha256 must be 64 hex characters",
        ));
    }
    Ok(())
}

fn validate_scenario(scenario: &Scenario) -> CoreResult<()> {
    if scenario.label.trim().is_empty() {
        return Err(CoreError::invalid("scenario label must not be empty"));
    }
    if scenario.label.chars().count() > MAX_TITLE {
        return Err(CoreError::invalid(format!(
            "scenario label exceeds {MAX_TITLE} characters"
        )));
    }
    if scenario.set.is_empty() {
        return Err(CoreError::invalid("scenario must set at least one state"));
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    #![allow(clippy::unwrap_used)]

    use super::*;

    fn root(name: &str) -> PathBuf {
        let root = std::env::temp_dir().join(format!("mono-review-{name}-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&root);
        std::fs::create_dir_all(&root).unwrap();
        root
    }

    fn annotation(screen: &str, kind: AnnotationKind, title: &str) -> Annotation {
        Annotation {
            id: String::new(),
            kind,
            screen: screen.into(),
            state: json!({"battery": 0}).as_object().cloned().unwrap(),
            element: Some("running_icon".into()),
            title: title.into(),
            body: "body".into(),
            evidence: Evidence {
                sha256: "a".repeat(64),
                lit_pixels: 42,
                frame: Some("main__init".into()),
                source: "designer".into(),
            },
            created_utc: String::new(),
            updated_utc: String::new(),
        }
    }

    #[test]
    fn round_trip_preserves_anchor_and_evidence() {
        let root = root("roundtrip");
        let mut store = ReviewStore::for_root(&root).unwrap();
        let id = store
            .upsert_annotation(annotation("main", AnnotationKind::Defect, "clips"))
            .unwrap();
        let reloaded = ReviewStore::for_root(&root).unwrap();
        let items = reloaded.annotations();
        assert_eq!(items.len(), 1);
        assert_eq!(items[0].id, id);
        assert_eq!(items[0].kind, AnnotationKind::Defect);
        assert_eq!(items[0].screen, "main");
        assert_eq!(items[0].state["battery"], 0);
        assert_eq!(items[0].element.as_deref(), Some("running_icon"));
        assert_eq!(items[0].evidence.lit_pixels, 42);
        assert_eq!(items[0].evidence.sha256.len(), 64);
        assert!(!items[0].created_utc.is_empty());
        let _ = std::fs::remove_dir_all(&root);
    }

    #[test]
    fn unknown_kind_is_skipped_not_fatal() {
        let root = root("kind");
        let path = root.join(REVIEW_FILE);
        std::fs::create_dir_all(path.parent().unwrap()).unwrap();
        std::fs::write(
            &path,
            br#"{"schema_version":1,"annotations":[{"id":"a","kind":"oops","screen":"main","title":"t"}],"scenarios":[]}"#,
        )
        .unwrap();
        let store = ReviewStore::load(&path).unwrap();
        assert!(store.annotations().is_empty());
        let _ = std::fs::remove_dir_all(&root);
    }

    #[test]
    fn corrupt_file_is_quarantined_and_replaced() {
        let root = root("corrupt");
        let path = root.join(REVIEW_FILE);
        std::fs::create_dir_all(path.parent().unwrap()).unwrap();
        std::fs::write(&path, b"{not json").unwrap();
        let mut store = ReviewStore::load(&path).unwrap();
        assert!(store.annotations().is_empty());
        let quarantine = root.join(REVIEW_DIR).join("quarantine");
        assert_eq!(std::fs::read_dir(&quarantine).unwrap().count(), 1);
        store
            .upsert_annotation(annotation("main", AnnotationKind::Explanation, "x"))
            .unwrap();
        assert_eq!(ReviewStore::load(&path).unwrap().annotations().len(), 1);
        let _ = std::fs::remove_dir_all(&root);
    }

    #[test]
    fn a_failed_quarantine_leaves_the_corrupt_file_guarded() {
        let root = root("quarantine-fail");
        let path = root.join(REVIEW_FILE);
        std::fs::create_dir_all(path.parent().unwrap()).unwrap();
        // A file where the quarantine directory belongs makes the copy fail, so
        // the corrupt bytes exist nowhere else and must not be overwritten.
        std::fs::write(root.join(REVIEW_DIR).join("quarantine"), b"").unwrap();
        std::fs::write(&path, b"{not json").unwrap();
        let mut store = ReviewStore::load(&path).unwrap();
        let error = store
            .upsert_annotation(annotation("main", AnnotationKind::Defect, "x"))
            .unwrap_err();
        assert_eq!(error.code, "E-REVIEW-EXTERNAL");
        assert_eq!(std::fs::read(&path).unwrap(), b"{not json");
        let _ = std::fs::remove_dir_all(&root);
    }

    #[test]
    fn external_change_is_refused() {
        let root = root("external");
        let mut store = ReviewStore::for_root(&root).unwrap();
        store
            .upsert_annotation(annotation("main", AnnotationKind::Defect, "first"))
            .unwrap();
        let path = root.join(REVIEW_FILE);
        let external = br#"{"schema_version":1,"annotations":[],"scenarios":[]}"#;
        std::fs::write(&path, external).unwrap();
        let error = store
            .upsert_annotation(annotation("main", AnnotationKind::Defect, "second"))
            .unwrap_err();
        assert_eq!(error.code, "E-REVIEW-EXTERNAL");
        assert_eq!(std::fs::read(&path).unwrap(), external);
        let _ = std::fs::remove_dir_all(&root);
    }

    #[test]
    fn counts_group_by_kind_and_screen() {
        let root = root("counts");
        let mut store = ReviewStore::for_root(&root).unwrap();
        store
            .upsert_annotation(annotation("main", AnnotationKind::Defect, "a"))
            .unwrap();
        store
            .upsert_annotation(annotation("main", AnnotationKind::Decision, "b"))
            .unwrap();
        store
            .upsert_annotation(annotation("main", AnnotationKind::Explanation, "c"))
            .unwrap();
        store
            .upsert_annotation(annotation("other", AnnotationKind::Defect, "d"))
            .unwrap();
        assert_eq!(store.counts(), (2, 1, 1));
        assert_eq!(store.counts_by_screen()["main"], 3);
        assert_eq!(store.counts_by_screen()["other"], 1);
        assert_eq!(store.annotations_for("main").len(), 3);
        let _ = std::fs::remove_dir_all(&root);
    }

    #[test]
    fn scenario_round_trip_and_validation() {
        let root = root("scenario");
        let mut store = ReviewStore::for_root(&root).unwrap();
        let id = store
            .upsert_scenario(Scenario {
                id: String::new(),
                label: "Low battery".into(),
                set: json!({"battery": 0}).as_object().cloned().unwrap(),
                created_utc: String::new(),
            })
            .unwrap();
        let reloaded = ReviewStore::for_root(&root).unwrap();
        assert_eq!(reloaded.scenarios()[0].id, id);
        assert_eq!(reloaded.scenarios()[0].set["battery"], 0);
        let empty = store.upsert_scenario(Scenario {
            id: String::new(),
            label: "Nothing".into(),
            set: Map::new(),
            created_utc: String::new(),
        });
        assert!(empty.is_err());
        let _ = std::fs::remove_dir_all(&root);
    }
}
