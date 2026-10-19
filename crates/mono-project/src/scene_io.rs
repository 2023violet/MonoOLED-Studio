//! Scene files, frame evidence and the JSONL session log (V1 `scene.py`, `evidence.py`, `session_log.py`).

use std::fs::OpenOptions;
use std::io::{BufRead, Write};
use std::path::{Path, PathBuf};

use mono_core::pyvalue::{py_repr, py_str};
use mono_core::render::{RenderResult, posix};
use mono_core::runtime::RuntimeLog;
use mono_core::state::State;
use mono_core::{CoreError, CoreResult};
use serde_json::{Map, Value, json};

use crate::atomic::{atomic_write, atomic_write_json};
use crate::project::{ProjectWorkspace, py_resolve};
use crate::resources::{hex_digest, io_error, read_file};

/// A loaded scene document plus V1's private bookkeeping fields.
#[derive(Debug, Clone)]
pub struct SceneDoc {
    pub data: Map<String, Value>,
    pub path: PathBuf,
    pub root: PathBuf,
    pub disk_sha256: String,
}

/// V1 `load_scene(path, project_root=...)`.
pub fn load_scene(path: &Path, project_root: Option<&Path>) -> CoreResult<SceneDoc> {
    let path = py_resolve(path);
    let raw = read_file(&path)?;
    let value: Value = serde_json::from_slice(&raw)
        .map_err(|e| CoreError::invalid(format!("{}: {e}", posix(&path))))?;
    let Value::Object(data) = value else {
        return Err(CoreError::invalid("scene file must contain a JSON object"));
    };
    let parent = path.parent().map(Path::to_path_buf).unwrap_or_default();
    let root = match (project_root, data.get("project_root")) {
        (Some(root), _) => py_resolve(root),
        (None, Some(raw)) if !raw.is_null() => {
            let rel = PathBuf::from(py_str(raw));
            py_resolve(&if rel.is_absolute() {
                rel
            } else {
                parent.join(rel)
            })
        }
        _ => parent,
    };
    Ok(SceneDoc {
        data,
        path,
        root,
        disk_sha256: hex_digest(&raw),
    })
}

/// Scene of a project's active (or given) screen, with project context fields V1 injects.
pub fn load_project_scene(
    project: &ProjectWorkspace,
    screen_id: Option<&str>,
) -> CoreResult<SceneDoc> {
    let screen = screen_id
        .map(str::to_string)
        .unwrap_or_else(|| project.active_screen());
    let mut scene = load_scene(&project.screen_path(&screen)?, Some(&project.root))?;
    scene
        .data
        .insert("_project_path".into(), json!(posix(&project.path)));
    scene
        .data
        .insert("_asset_dirs".into(), json!(project.asset_dirs()));
    scene.data.insert(
        "_design_rules".into(),
        project
            .data
            .get("design_rules")
            .cloned()
            .unwrap_or(json!({})),
    );
    Ok(scene)
}

/// V1 `save_scene`: private `_` keys dropped, indent 2, atomic.
pub fn save_scene(scene: &SceneDoc) -> CoreResult<()> {
    let data: Map<String, Value> = scene
        .data
        .iter()
        .filter(|(k, _)| !k.starts_with('_'))
        .map(|(k, v)| (k.clone(), v.clone()))
        .collect();
    atomic_write_json(&scene.path, &Value::Object(data))
}

fn relative_asset(path: &str, root: &Path) -> String {
    let p = py_resolve(Path::new(path));
    match p.strip_prefix(py_resolve(root)) {
        Ok(rel) => posix(rel),
        Err(_) => posix(&p),
    }
}

/// V1 `frame_evidence`.
pub fn frame_evidence(
    result: &RenderResult,
    state: &State,
    elapsed: i64,
    root: &Path,
) -> CoreResult<Value> {
    let raw = result.framebuffer.to_vlsb()?;
    let visible: Vec<Value> = result
        .resolved_elements
        .iter()
        .filter(|item| item.get("visible") == Some(&Value::Bool(true)))
        .map(|item| {
            let assets: Vec<Value> = item
                .get("assets")
                .and_then(Value::as_array)
                .into_iter()
                .flatten()
                .map(|p| json!(relative_asset(&py_str(p), root)))
                .collect();
            json!({
                "id": item.get("id"), "type": item.get("type"),
                "x": item.get("x"), "y": item.get("y"), "w": item.get("w"), "h": item.get("h"),
                "text": item.get("text"), "assets": assets,
                "placeholder": item.get("placeholder") == Some(&Value::Bool(true)),
            })
        })
        .collect();
    let mut sorted: Vec<(&String, &Value)> = state.iter().collect();
    sorted.sort_by(|a, b| a.0.cmp(b.0));
    Ok(json!({
        "elapsed": elapsed,
        "state": Value::Object(sorted.into_iter().map(|(k, v)| (k.clone(), v.clone())).collect()),
        "framebuffer_bytes": raw.len(),
        "sha256": hex_digest(&raw),
        "lit_pixels": result.framebuffer.pixels().iter().map(|v| usize::from(*v)).sum::<usize>(),
        "visible_elements": visible,
    }))
}

fn sort_keys(value: &Value) -> Value {
    match value {
        Value::Object(map) => {
            let mut keys: Vec<&String> = map.keys().collect();
            keys.sort();
            Value::Object(
                keys.into_iter()
                    .map(|k| (k.clone(), sort_keys(&map[k])))
                    .collect(),
            )
        }
        Value::Array(items) => Value::Array(items.iter().map(sort_keys).collect()),
        other => other.clone(),
    }
}

/// Python `json.dumps(record, ensure_ascii=False, sort_keys=True)` (default separators).
pub fn python_compact_json(value: &Value) -> String {
    match value {
        Value::Object(map) => format!(
            "{{{}}}",
            map.iter()
                .map(|(k, v)| format!("{}: {}", Value::from(k.as_str()), python_compact_json(v)))
                .collect::<Vec<_>>()
                .join(", ")
        ),
        Value::Array(items) => format!(
            "[{}]",
            items
                .iter()
                .map(python_compact_json)
                .collect::<Vec<_>>()
                .join(", ")
        ),
        other => other.to_string(),
    }
}

/// Append-only JSONL session log (V1 `SessionLogger`). A write failure degrades the
/// log instead of failing the caller.
pub struct SessionLogger {
    path: PathBuf,
    seq: u64,
    pub degraded: bool,
    pub last_error: String,
}

fn utc_now_iso() -> String {
    let now = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .unwrap_or_default();
    let secs = now.as_secs() as i64;
    let millis = now.subsec_millis();
    let days = secs.div_euclid(86_400);
    let rem = secs.rem_euclid(86_400);
    // Civil-from-days (Howard Hinnant).
    let z = days + 719_468;
    let era = z.div_euclid(146_097);
    let doe = z - era * 146_097;
    let yoe = (doe - doe / 1460 + doe / 36_524 - doe / 146_096) / 365;
    let y = yoe + era * 400;
    let doy = doe - (365 * yoe + yoe / 4 - yoe / 100);
    let mp = (5 * doy + 2) / 153;
    let d = doy - (153 * mp + 2) / 5 + 1;
    let m = if mp < 10 { mp + 3 } else { mp - 9 };
    let y = if m <= 2 { y + 1 } else { y };
    format!(
        "{y:04}-{m:02}-{d:02}T{:02}:{:02}:{:02}.{millis:03}+00:00",
        rem / 3600,
        (rem % 3600) / 60,
        rem % 60
    )
}

impl SessionLogger {
    pub fn new(path: &Path) -> CoreResult<Self> {
        if let Some(parent) = path.parent() {
            std::fs::create_dir_all(parent).map_err(|e| io_error(parent, &e))?;
        }
        let mut seq = 0u64;
        if let Ok(file) = std::fs::File::open(path) {
            let mut count = 0u64;
            for line in std::io::BufReader::new(file).lines().map_while(Result::ok) {
                if line.trim().is_empty() {
                    continue;
                }
                count += 1;
                let item = serde_json::from_str::<Value>(&line)
                    .ok()
                    .and_then(|v| v.get("seq").and_then(Value::as_u64));
                seq = seq.max(item.unwrap_or(count));
            }
        }
        Ok(Self {
            path: path.to_path_buf(),
            seq,
            degraded: false,
            last_error: String::new(),
        })
    }

    pub fn log(&mut self, event: &str, payload: Map<String, Value>) -> Value {
        self.seq += 1;
        let mut record = Map::new();
        record.insert("ts".into(), json!(utc_now_iso()));
        record.insert("seq".into(), json!(self.seq));
        record.insert("event".into(), json!(event));
        record.extend(payload);
        let record = Value::Object(record);
        let line = format!("{}\n", python_compact_json(&sort_keys(&record)));
        let result = OpenOptions::new()
            .create(true)
            .append(true)
            .open(&self.path)
            .and_then(|mut f| f.write_all(line.as_bytes()).and_then(|()| f.flush()));
        if let Err(error) = result {
            self.degraded = true;
            self.last_error = error.to_string();
        }
        record
    }

    /// V1 `write_markdown`.
    pub fn write_markdown(&self, out: &Path) -> CoreResult<()> {
        let mut text = String::from("# OLED UI Session Log\n\n");
        let file = std::fs::File::open(&self.path).map_err(|e| io_error(&self.path, &e))?;
        for (index, line) in std::io::BufReader::new(file)
            .lines()
            .map_while(Result::ok)
            .enumerate()
        {
            let line = line.trim_end_matches(['\r', '\n']);
            if line.trim().is_empty() {
                continue;
            }
            let Ok(Value::Object(item)) = serde_json::from_str::<Value>(line) else {
                text.push_str(&format!(
                    "- ⚠ skipped corrupt JSONL record at line {}\n",
                    index + 1
                ));
                continue;
            };
            let field = |k: &str| item.get(k).map(py_str).unwrap_or_default();
            let seq = item
                .get("seq")
                .map(py_repr)
                .unwrap_or_else(|| "None".into());
            let mut core = format!("- `{}` **{}** seq={seq}", field("ts"), field("event"));
            let payload: Vec<String> = item
                .iter()
                .filter(|(k, _)| !["ts", "seq", "event"].contains(&k.as_str()))
                .map(|(k, v)| format!("{k}={}", py_repr(v)))
                .collect();
            if !payload.is_empty() {
                core.push_str(" — ");
                core.push_str(&payload.join(", "));
            }
            text.push_str(&core);
            text.push('\n');
        }
        atomic_write(out, text.as_bytes())
    }
}

impl RuntimeLog for SessionLogger {
    fn log(&mut self, event: &str, payload: Map<String, Value>) {
        let _ = SessionLogger::log(self, event, payload);
    }
}
