//! Autosave recovery points (V1 `autosave.AutoSaveManager`):
//! `<scene root>/.oled/autosave/<scene stem>/<UTC stamp>.autosave.json`.

use std::path::{Path, PathBuf};
use std::time::{SystemTime, UNIX_EPOCH};

use mono_core::pyvalue::py_int;
use mono_core::{CoreError, CoreResult};
use serde_json::{Map, Value, json};

use crate::atomic::atomic_write_json;
use crate::resources::io_error;

/// Proleptic Gregorian date from days since 1970-01-01 (Howard Hinnant).
fn civil_from_days(days: i64) -> (i64, u32, u32) {
    let z = days + 719_468;
    let era = z.div_euclid(146_097);
    let doe = z - era * 146_097;
    let yoe = (doe - doe / 1460 + doe / 36_524 - doe / 146_096) / 365;
    let doy = doe - (365 * yoe + yoe / 4 - yoe / 100);
    let mp = (5 * doy + 2) / 153;
    let day = (doy - (153 * mp + 2) / 5 + 1) as u32;
    let month = if mp < 10 { mp + 3 } else { mp - 9 } as u32;
    let year = yoe + era * 400 + i64::from(month <= 2);
    (year, month, day)
}

/// (`%Y%m%dT%H%M%S_%fZ`, ISO-8601 with `+00:00`) for a UNIX time.
pub fn utc_stamps(secs: i64, micros: u32) -> (String, String) {
    let (year, month, day) = civil_from_days(secs.div_euclid(86_400));
    let rem = secs.rem_euclid(86_400);
    let (h, m, s) = (rem / 3600, (rem / 60) % 60, rem % 60);
    (
        format!("{year:04}{month:02}{day:02}T{h:02}{m:02}{s:02}_{micros:06}Z"),
        format!("{year:04}-{month:02}-{day:02}T{h:02}:{m:02}:{s:02}.{micros:06}+00:00"),
    )
}

pub struct AutoSaveManager {
    pub directory: PathBuf,
    pub keep: usize,
    source: PathBuf,
}

impl AutoSaveManager {
    pub fn new(scene_path: &Path, scene_root: &Path, keep: usize) -> Self {
        let stem = scene_path
            .file_stem()
            .map(|s| s.to_string_lossy().into_owned())
            .unwrap_or_default();
        Self {
            directory: scene_root.join(".oled").join("autosave").join(stem),
            keep: keep.max(1),
            source: scene_path.to_path_buf(),
        }
    }

    pub fn set_keep(&mut self, keep: usize) {
        self.keep = keep.max(1);
        self.prune();
    }

    /// Snapshots, oldest first (sorted by file name = UTC stamp).
    pub fn snapshots(&self) -> Vec<PathBuf> {
        let Ok(entries) = std::fs::read_dir(&self.directory) else {
            return Vec::new();
        };
        let mut out: Vec<PathBuf> = entries
            .flatten()
            .map(|e| e.path())
            .filter(|p| {
                p.is_file()
                    && p.file_name()
                        .is_some_and(|n| n.to_string_lossy().ends_with(".autosave.json"))
            })
            .collect();
        out.sort_by_key(|p| p.file_name().map(|n| n.to_os_string()));
        out
    }

    /// Best-effort retention cleanup; never fails a fresh snapshot.
    fn prune(&self) {
        let snaps = self.snapshots();
        if snaps.len() > self.keep {
            for old in &snaps[..snaps.len() - self.keep] {
                let _ = std::fs::remove_file(old);
            }
        }
    }

    /// V1 `snapshot`: scene keys without `_` prefixes plus `_autosave` metadata.
    pub fn snapshot(&self, scene: &Map<String, Value>, reason: &str) -> CoreResult<PathBuf> {
        let now = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap_or_default();
        let (stamp, iso) = utc_stamps(now.as_secs() as i64, now.subsec_micros());
        let mut target = self.directory.join(format!("{stamp}.autosave.json"));
        let mut n = 1;
        while target.exists() {
            target = self.directory.join(format!("{stamp}.{n}.autosave.json"));
            n += 1;
        }
        let mut payload: Map<String, Value> = scene
            .iter()
            .filter(|(k, _)| !k.starts_with('_'))
            .map(|(k, v)| (k.clone(), v.clone()))
            .collect();
        let source = std::fs::canonicalize(&self.source).unwrap_or_else(|_| self.source.clone());
        payload.insert(
            "_autosave".into(),
            json!({"reason": reason, "source": source.display().to_string(), "created_utc": iso}),
        );
        atomic_write_json(&target, &Value::Object(payload))?;
        self.prune();
        Ok(target)
    }

    /// V1 `_validate_snapshot_payload` + `load_snapshot`.
    pub fn load_snapshot(path: &Path) -> CoreResult<Map<String, Value>> {
        let raw = std::fs::read(path).map_err(|e| io_error(path, &e))?;
        let value: Value = serde_json::from_slice(&raw)
            .map_err(|e| CoreError::new("JSONDecodeError", e.to_string()))?;
        let Value::Object(mut payload) = value else {
            return Err(CoreError::invalid(
                "autosave snapshot must contain a JSON object",
            ));
        };
        let Some(Value::Object(canvas)) = payload.get("canvas") else {
            return Err(CoreError::invalid("autosave snapshot missing canvas"));
        };
        let dim = |key: &str| canvas.get(key).map_or(Some(0), py_int);
        let (Some(width), Some(height)) = (dim("w"), dim("h")) else {
            return Err(CoreError::invalid("autosave snapshot has invalid canvas"));
        };
        if width <= 0 || height <= 0 || height % 8 != 0 {
            return Err(CoreError::invalid(
                "autosave snapshot has invalid canvas dimensions",
            ));
        }
        for (key, ok) in [
            (
                "elements",
                payload.get("elements").is_none_or(Value::is_array),
            ),
            ("states", payload.get("states").is_none_or(Value::is_object)),
            (
                "timeline",
                payload.get("timeline").is_none_or(Value::is_array),
            ),
        ] {
            if !ok {
                let kind = if key == "states" {
                    "an object"
                } else {
                    "a list"
                };
                return Err(CoreError::invalid(format!(
                    "autosave snapshot {key} must be {kind}"
                )));
            }
        }
        payload.remove("_autosave");
        Ok(payload)
    }

    fn quarantine(&self, path: &Path) {
        let dir = self.directory.join("quarantine");
        if std::fs::create_dir_all(&dir).is_err() {
            return;
        }
        let name = path
            .file_name()
            .map(|n| n.to_string_lossy().into_owned())
            .unwrap_or_default();
        let mut target = dir.join(format!("{name}.invalid"));
        let mut n = 1;
        while target.exists() {
            target = dir.join(format!("{name}.invalid.{n}"));
            n += 1;
        }
        let _ = std::fs::rename(path, target);
    }

    /// Newest valid snapshot; invalid ones are moved to `quarantine/`.
    pub fn latest_recovery(&self) -> Option<PathBuf> {
        for candidate in self.snapshots().into_iter().rev() {
            if Self::load_snapshot(&candidate).is_ok() {
                return Some(candidate);
            }
            self.quarantine(&candidate);
        }
        None
    }

    /// The newest valid snapshot only when it is newer than the scene on disk.
    pub fn recovery_candidate(&self) -> Option<PathBuf> {
        let latest = self.latest_recovery()?;
        let modified = |p: &Path| std::fs::metadata(p).and_then(|m| m.modified()).ok();
        match (modified(&latest), modified(&self.source)) {
            (Some(snap), Some(disk)) => (snap > disk).then_some(latest),
            _ => Some(latest),
        }
    }
}

#[cfg(test)]
mod tests {
    #![allow(clippy::unwrap_used)]
    use super::*;

    fn scene() -> Map<String, Value> {
        json!({"canvas": {"w": 128, "h": 32}, "elements": [], "_path": "x"})
            .as_object()
            .unwrap()
            .clone()
    }

    #[test]
    fn stamps_match_python_strftime() {
        let (stamp, iso) = utc_stamps(1_760_918_400, 42);
        assert_eq!(stamp, "20251020T000000_000042Z");
        assert_eq!(iso, "2025-10-20T00:00:00.000042+00:00");
        assert_eq!(utc_stamps(951_782_400, 0).0, "20000229T000000_000000Z");
    }

    #[test]
    fn snapshot_retention_and_validation() {
        let root = std::env::temp_dir().join(format!("mono-autosave-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&root);
        std::fs::create_dir_all(&root).unwrap();
        let scene_path = root.join("main.json");
        std::fs::write(&scene_path, b"{}").unwrap();
        let manager = AutoSaveManager::new(&scene_path, &root, 2);
        for _ in 0..3 {
            manager.snapshot(&scene(), "timer").unwrap();
        }
        assert_eq!(manager.snapshots().len(), 2);
        let latest = manager.latest_recovery().unwrap();
        let payload = AutoSaveManager::load_snapshot(&latest).unwrap();
        assert!(!payload.contains_key("_autosave") && !payload.contains_key("_path"));
        std::fs::write(
            manager
                .directory
                .join("99999999T000000_000000Z.autosave.json"),
            b"{\"canvas\":{\"w\":1,\"h\":3}}",
        )
        .unwrap();
        assert_eq!(manager.latest_recovery().unwrap(), latest);
        assert!(manager.directory.join("quarantine").is_dir());
        let _ = std::fs::remove_dir_all(&root);
    }
}
