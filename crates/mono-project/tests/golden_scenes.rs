#![allow(
    clippy::unwrap_used,
    clippy::expect_used,
    clippy::panic,
    clippy::type_complexity
)]

mod common;

use std::path::{Path, PathBuf};

use common::{Report, cases, hex};
use mono_core::render::{posix, render_scene};
use mono_core::state::{IntegerPolicy, build_export_states};
use mono_project::resources::DiskResources;
use serde_json::{Map, Value, json};

fn repo() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("../..")
        .canonicalize()
        .unwrap()
}

/// Mirror of the corpus `${PROJECT_ROOT}` rule: replace the root, then use `/` in the path after it.
fn replace_root(value: &Value, root: &Path) -> Value {
    match value {
        Value::String(s) => {
            let root_posix = posix(root);
            let text = s
                .replace(&root_posix, "${PROJECT_ROOT}")
                .replace(&root.display().to_string(), "${PROJECT_ROOT}");
            Value::String(text)
        }
        Value::Array(items) => Value::Array(items.iter().map(|v| replace_root(v, root)).collect()),
        Value::Object(map) => Value::Object(
            map.iter()
                .map(|(k, v)| (k.clone(), replace_root(v, root)))
                .collect(),
        ),
        other => other.clone(),
    }
}

fn error_kind(code: &str) -> &'static str {
    match code {
        "E-IO-NOT-FOUND" => "FileNotFoundError",
        "E-ASSET-FORMAT" => "AssetFormatError",
        _ => "ValueError",
    }
}

#[test]
fn scene_cases_match_v1() {
    let repo = repo();
    let mut report = Report::default();
    let mut matrices: std::collections::HashMap<
        String,
        (
            Map<String, Value>,
            PathBuf,
            Result<Vec<(String, Map<String, Value>)>, String>,
        ),
    > = Default::default();
    let mut resources = DiskResources::new();
    for case in cases("scenes") {
        let id = case["id"].as_str().unwrap().to_string();
        let input = &case["input"];
        let expected = &case["expected"];
        let scene_rel = input["scene"].as_str().unwrap().to_string();
        let entry = matrices.entry(scene_rel.clone()).or_insert_with(|| {
            let scene: Map<String, Value> =
                serde_json::from_slice(&std::fs::read(repo.join(&scene_rel)).unwrap()).unwrap();
            let root = repo
                .join(input["project_root"].as_str().unwrap())
                .canonicalize()
                .unwrap();
            let states = build_export_states(&scene, IntegerPolicy::Representative, 5000, false)
                .map_err(|e| e.message);
            (scene, root, states)
        });
        let (scene, root, states) = (&entry.0, &entry.1, &entry.2);
        if id.ends_with("-matrix") {
            let ok = matches!(states, Err(message) if expected["error"] == "ValueError" && expected["message"] == *message);
            report.check(&id, ok, || format!("matrix {states:?}"));
            continue;
        }
        let Ok(states) = states else {
            report.check(&id, false, || "matrix unexpectedly failed".into());
            continue;
        };
        let state = input["state"].as_object().unwrap();
        let in_matrix = states
            .iter()
            .any(|(name, s)| id.ends_with(name.as_str()) && s == state);
        let result = render_scene(scene, root, state, &mut resources);
        let ok = match (&result, expected.get("error")) {
            (Ok(r), None) => {
                let vlsb = r.framebuffer.to_vlsb().unwrap();
                let used: Vec<Value> = r.used_files.iter().map(|p| Value::from(posix(p))).collect();
                expected["vlsb"]["hex"] == hex(&vlsb)
                    && replace_root(&Value::Array(r.resolved_elements.clone()), root)
                        == expected["resolved_elements"]
                    && replace_root(&Value::Array(used), root) == expected["used_files"]
            }
            (Err(e), Some(kind)) => *kind == json!(error_kind(e.code)),
            _ => false,
        };
        report.check(&id, ok && in_matrix, || match &result {
            Ok(r) => {
                let got = replace_root(&Value::Array(r.resolved_elements.clone()), root);
                let diff: Vec<String> = got
                    .as_array()
                    .unwrap()
                    .iter()
                    .zip(
                        expected["resolved_elements"]
                            .as_array()
                            .into_iter()
                            .flatten(),
                    )
                    .filter(|(a, b)| a != b)
                    .map(|(a, b)| format!("got {a} want {b}"))
                    .take(2)
                    .collect();
                let used: Vec<Value> = r.used_files.iter().map(|p| Value::from(posix(p))).collect();
                format!(
                    "in_matrix={in_matrix} vlsb_ok={} used_ok={} diff={diff:?} used={}",
                    expected["vlsb"]["hex"] == hex(&r.framebuffer.to_vlsb().unwrap()),
                    replace_root(&Value::Array(used.clone()), root) == expected["used_files"],
                    replace_root(&Value::Array(used), root)
                )
            }
            Err(e) => format!("in_matrix={in_matrix} error {} {}", e.code, e.message),
        });
    }
    report.finish_exact("scenes", common::count_cases("scenes", |_| true));
}
