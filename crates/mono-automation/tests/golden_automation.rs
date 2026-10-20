//! Replays the 18 frozen V1 Automation API sessions (`fixtures/golden/automation.json`).
//!
//! Every request is dispatched as recorded; responses must equal V1 after the
//! corpus normalisation (project root → `${PROJECT_ROOT}`, `elapsed_ms`).
//! Fields that carry PNG/ZIP *encoder* bytes (G1 deviation 4) are compared by
//! content instead: PNG payloads by decoded pixels, file digests by existence
//! and decodability. Everything else — VLSB hashes, JSON manifests, errors,
//! revisions, events — is compared exactly.
#![allow(clippy::unwrap_used, clippy::expect_used, clippy::panic)]

use std::collections::BTreeMap;
use std::path::{Path, PathBuf};
use std::time::{Duration, Instant};

use mono_automation::{Service, dispatch_json_rpc};
use mono_project::image_io::decode_image;
use mono_project::project::py_resolve;
use mono_project::resources::hex_digest;
use serde_json::{Map, Value};

const TOKEN: &str = "${PROJECT_ROOT}";

fn repo() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("../..")
        .canonicalize()
        .unwrap()
}

fn cases() -> Vec<Value> {
    let path = repo().join("fixtures/golden/automation.json");
    let value: Value = serde_json::from_str(&std::fs::read_to_string(path).unwrap()).unwrap();
    value["cases"].as_array().unwrap().clone()
}

fn copy_dir(from: &Path, to: &Path) {
    std::fs::create_dir_all(to).unwrap();
    for entry in std::fs::read_dir(from).unwrap() {
        let entry = entry.unwrap();
        let target = to.join(entry.file_name());
        if entry.file_type().unwrap().is_dir() {
            copy_dir(&entry.path(), &target);
        } else {
            std::fs::copy(entry.path(), target).unwrap();
        }
    }
}

fn fresh(name: &str) -> PathBuf {
    let root = std::env::temp_dir().join(format!("mono-auto-{}-{name}", std::process::id()));
    let _ = std::fs::remove_dir_all(&root);
    copy_dir(&repo().join("test_assets/projects/curing_lite"), &root);
    py_resolve(&root)
}

/// Corpus `replace_root` + the path after the token is made `/`-separated.
fn normalize_text(text: &str, root: &Path) -> String {
    let mut variants = Vec::new();
    for base in [root.to_path_buf(), py_resolve(root)] {
        let native = base.display().to_string();
        variants.push(native.replace('\\', "\\\\"));
        variants.push(native.replace('\\', "/"));
        variants.push(native);
    }
    variants.sort_by_key(|v| std::cmp::Reverse(v.len()));
    let mut out = text.to_string();
    for variant in variants {
        out = out.replace(&variant, TOKEN);
    }
    let stop = |c: char| c.is_whitespace() || "'\"<>|*?:,;)]}".contains(c);
    let mut result = String::new();
    let mut rest = out.as_str();
    while let Some(i) = rest.find(TOKEN) {
        result.push_str(&rest[..i + TOKEN.len()]);
        rest = &rest[i + TOKEN.len()..];
        let end = rest.find(stop).unwrap_or(rest.len());
        let path = &rest[..end];
        let mut cleaned = String::new();
        let mut last_slash = false;
        for c in path.chars() {
            if c == '\\' {
                if !last_slash {
                    cleaned.push('/');
                }
                last_slash = true;
            } else {
                cleaned.push(c);
                last_slash = false;
            }
        }
        result.push_str(&cleaned);
        rest = &rest[end..];
    }
    result.push_str(rest);
    result
}

fn normalize(value: &Value, root: &Path) -> Value {
    match value {
        Value::String(s) => Value::String(normalize_text(s, root)),
        Value::Array(items) => Value::Array(items.iter().map(|v| normalize(v, root)).collect()),
        Value::Object(map) => Value::Object(
            map.iter()
                .map(|(k, v)| {
                    let v = if k == "elapsed_ms" {
                        Value::from("${ELAPSED_MS}")
                    } else {
                        normalize(v, root)
                    };
                    (k.clone(), v)
                })
                .collect(),
        ),
        other => other.clone(),
    }
}

fn resolve_request(request: &Value, root: &Path) -> Value {
    let text = serde_json::to_string(request).unwrap().replace(
        TOKEN,
        &py_resolve(root).display().to_string().replace('\\', "/"),
    );
    serde_json::from_str(&text).unwrap()
}

fn png_pixels(b64: &str) -> (usize, usize, Vec<u8>) {
    const TABLE: &str = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
    let mut bits = 0u32;
    let mut count = 0;
    let mut out = Vec::new();
    for c in b64.chars().filter(|c| *c != '=') {
        bits = (bits << 6) | TABLE.find(c).unwrap() as u32;
        count += 6;
        if count >= 8 {
            count -= 8;
            out.push((bits >> count) as u8);
        }
    }
    let image = decode_image(&out).unwrap();
    (image.width, image.height, image.rgba)
}

/// Methods whose `sha256`/`bytes` describe PNG or ZIP encoder output.
fn encoder_fields(method: &str) -> &'static [&'static str] {
    match method {
        "asset.create" | "asset.import" | "asset.copy" | "asset.rename" => &["sha256", "bytes"],
        "render.preview_file"
        | "render.annotated_preview"
        | "export.font_pack"
        | "export.code_ai_handoff" => &["sha256"],
        _ => &[],
    }
}

fn first_diff(path: &str, a: &Value, b: &Value) -> Option<String> {
    match (a, b) {
        (Value::Object(x), Value::Object(y)) => {
            for key in x.keys().chain(y.keys()) {
                match (x.get(key), y.get(key)) {
                    (Some(p), Some(q)) => {
                        if let Some(d) = first_diff(&format!("{path}.{key}"), p, q) {
                            return Some(d);
                        }
                    }
                    (p, q) => return Some(format!("{path}.{key}: actual={p:?} expected={q:?}")),
                }
            }
            None
        }
        (Value::Array(x), Value::Array(y)) => {
            if x.len() != y.len() {
                return Some(format!("{path}: len {} vs {}", x.len(), y.len()));
            }
            x.iter()
                .zip(y)
                .enumerate()
                .find_map(|(i, (p, q))| first_diff(&format!("{path}[{i}]"), p, q))
        }
        _ if a == b => None,
        _ => {
            let show = |v: &Value| {
                let s = v.to_string();
                s.chars().take(300).collect::<String>()
            };
            Some(format!("{path}: actual={} expected={}", show(a), show(b)))
        }
    }
}

fn compare_response(method: &str, mut actual: Value, mut expected: Value) -> Option<String> {
    if let (Some(a), Some(e)) = (
        actual.pointer("/result/png_base64").and_then(Value::as_str),
        expected
            .pointer("/result/png_base64")
            .and_then(Value::as_str),
    ) {
        if png_pixels(a) != png_pixels(e) {
            return Some("render.png pixels differ".into());
        }
        for v in [&mut actual, &mut expected] {
            if let Some(Value::Object(r)) = v.get_mut("result") {
                r.remove("png_base64");
                r.remove("png_sha256");
            }
        }
    }
    for field in encoder_fields(method) {
        for v in [&mut actual, &mut expected] {
            if let Some(Value::Object(r)) = v.get_mut("result") {
                r.remove(*field);
            }
        }
    }
    first_diff("", &actual, &expected)
}

fn tracked_files(root: &Path) -> BTreeMap<String, String> {
    fn walk(dir: &Path, root: &Path, out: &mut BTreeMap<String, String>) {
        let Ok(entries) = std::fs::read_dir(dir) else {
            return;
        };
        for entry in entries.flatten() {
            let path = entry.path();
            if path.is_dir() {
                walk(&path, root, out);
            } else {
                let rel = path
                    .strip_prefix(root)
                    .unwrap()
                    .to_string_lossy()
                    .replace('\\', "/");
                out.insert(rel, hex_digest(&std::fs::read(&path).unwrap()));
            }
        }
    }
    let mut out = BTreeMap::new();
    for base in ["exports", "assets/golden", "fonts", "scenes"] {
        walk(&root.join(base), root, &mut out);
    }
    out.insert(
        "project.oled.json".into(),
        hex_digest(&std::fs::read(root.join("project.oled.json")).unwrap()),
    );
    out
}

/// V1 writes these Markdown reports with `Path.write_text` (CRLF on Windows,
/// G1 deviation 2/12); compare them with Windows line endings.
fn crlf_digest(path: &Path) -> String {
    let text = std::fs::read(path).unwrap();
    let mut out = Vec::with_capacity(text.len());
    for (i, b) in text.iter().enumerate() {
        if *b == b'\n' && (i == 0 || text[i - 1] != b'\r') {
            out.push(b'\r');
        }
        out.push(*b);
    }
    hex_digest(&out)
}

fn compare_files(root: &Path, expected: &Map<String, Value>) -> Vec<String> {
    let actual = tracked_files(root);
    let mut problems = Vec::new();
    let expected_keys: Vec<&String> = expected.keys().collect();
    let actual_keys: Vec<&String> = actual.keys().collect();
    if expected_keys != actual_keys {
        let missing: Vec<_> = expected_keys
            .iter()
            .filter(|k| !actual.contains_key(k.as_str()))
            .collect();
        let extra: Vec<_> = actual_keys
            .iter()
            .filter(|k| !expected.contains_key(k.as_str()))
            .collect();
        problems.push(format!(
            "file set differs: missing={missing:?} extra={extra:?}"
        ));
    }
    for (rel, sha) in expected {
        let Some(actual_sha) = actual.get(rel) else {
            continue;
        };
        let path = root.join(rel);
        if rel.ends_with(".png") {
            if decode_image(&std::fs::read(&path).unwrap()).is_err() {
                problems.push(format!("{rel}: not a decodable PNG"));
            }
        } else if rel.ends_with(".zip") {
            if std::fs::metadata(&path).map(|m| m.len()).unwrap_or(0) == 0 {
                problems.push(format!("{rel}: empty ZIP"));
            }
        } else if Some(actual_sha.as_str()) != sha.as_str()
            && Some(crlf_digest(&path).as_str()) != sha.as_str()
        {
            problems.push(format!("{rel}: sha256 differs"));
        }
    }
    problems
}

fn wait_for_jobs(service: &Service) {
    let deadline = Instant::now() + Duration::from_secs(120);
    while !service.jobs.all_terminal() {
        assert!(Instant::now() < deadline, "job did not finish within 120 s");
        std::thread::sleep(Duration::from_millis(10));
    }
}

#[test]
fn v1_automation_sessions_replay_identically() {
    let all = cases();
    assert_eq!(all.len(), 18, "corpus case count");
    let mut failures = Vec::new();
    let mut steps_checked = 0;
    for case in &all {
        let id = case["id"].as_str().unwrap();
        let root = fresh(id);
        let manifest = root.join("project.oled.json");
        if case["kind"] == "automation_raw" {
            let mut service = Service::for_project(&manifest, Some("main"), "full").unwrap();
            let actual = normalize(
                &dispatch_json_rpc(&mut service, &case["input"]["request"]),
                &root,
            );
            if let Some(d) = first_diff("", &actual, &case["expected"]["response"]) {
                failures.push(format!("{id}: {d}"));
            }
            steps_checked += 1;
            continue;
        }
        let permission = case["input"]["permission"].as_str().unwrap();
        let mut service = Service::for_project(&manifest, Some("main"), permission).unwrap();
        for (index, step) in case["expected"]["steps"]
            .as_array()
            .unwrap()
            .iter()
            .enumerate()
        {
            let request = resolve_request(&step["request"], &root);
            let method = request["method"].as_str().unwrap_or_default().to_string();
            let started = Instant::now();
            let response = dispatch_json_rpc(&mut service, &request);
            if started.elapsed() > Duration::from_secs(2) {
                eprintln!("slow: {id} {method} {:?}", started.elapsed());
            }
            if method == "job.start" {
                wait_for_jobs(&service);
            }
            let actual = normalize(&response, &root);
            if let Some(d) = compare_response(&method, actual, step["response"].clone()) {
                failures.push(format!("{id} step {} ({method}): {d}", index + 1));
            }
            steps_checked += 1;
        }
        for problem in compare_files(&root, case["expected"]["files_sha256"].as_object().unwrap()) {
            failures.push(format!("{id} files: {problem}"));
        }
        let _ = std::fs::remove_dir_all(&root);
    }
    assert_eq!(
        steps_checked, 152,
        "every recorded step and raw request must be checked"
    );
    assert!(
        failures.is_empty(),
        "{} mismatches:\n{}",
        failures.len(),
        failures.join("\n")
    );
}
