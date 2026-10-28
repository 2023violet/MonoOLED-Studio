//! `mono --json` contract: one parseable object, exit codes unchanged.
#![allow(clippy::unwrap_used, clippy::expect_used)]

use std::path::Path;
use std::process::Command;

use serde_json::Value;

fn fixture() -> String {
    Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../../test_assets/projects/curing_lite/project.oled.json")
        .to_string_lossy()
        .into_owned()
}

fn run(args: &[&str]) -> (i32, String, String) {
    let output = Command::new(env!("CARGO_BIN_EXE_mono"))
        .args(args)
        .output()
        .expect("mono binary runs");
    (
        output.status.code().unwrap_or(-1),
        String::from_utf8_lossy(&output.stdout).into_owned(),
        String::from_utf8_lossy(&output.stderr).into_owned(),
    )
}

fn json_of(stdout: &str) -> Value {
    serde_json::from_str(stdout.trim()).expect("stdout is one JSON object")
}

#[test]
fn validate_json_matches_exit_code_and_totals() {
    let project = fixture();
    let (code, stdout, stderr) = run(&["validate", "--project", &project, "--json"]);
    assert_eq!(code, 0, "stderr: {stderr}");
    let value = json_of(&stdout);
    assert_eq!(value["command"], "validate");
    assert_eq!(value["ok"], true);
    assert_eq!(value["exit_code"], 0);

    let findings = value["findings"].as_array().expect("findings array");
    assert_eq!(findings.len() as u64, value["total"].as_u64().unwrap());
    for finding in findings {
        assert!(finding["severity"].is_string());
        assert!(!finding["code"].as_str().unwrap().is_empty());
        assert!(finding["message"].is_string());
        assert!(finding["blocking"].is_boolean());
    }
    let blocking = findings.iter().filter(|f| f["blocking"] == true).count();
    assert_eq!(blocking as u64, value["blocking"].as_u64().unwrap());
}

#[test]
fn export_json_reports_frames_and_hashes() {
    let root = std::env::temp_dir().join(format!("mono-cli-export-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&root);
    let project = fixture();
    let output = root.to_string_lossy().into_owned();
    let (code, stdout, stderr) = run(&[
        "export",
        "--project",
        &project,
        "--output",
        &output,
        "--json",
    ]);
    assert_eq!(code, 0, "stderr: {stderr}");
    let value = json_of(&stdout);
    assert_eq!(value["command"], "export");
    assert_eq!(value["ok"], true);
    assert!(!value["output_dir"].as_str().unwrap().is_empty());
    assert!(value["frame_count"].as_u64().unwrap() >= 1);

    let frames = value["frames"].as_array().expect("frames array");
    assert!(!frames.is_empty());
    for frame in frames {
        assert!(frame["name"].is_string());
        let digest = frame["sha256"].as_str().expect("sha256 string");
        assert_eq!(digest.len(), 64);
        assert!(digest.chars().all(|c| c.is_ascii_hexdigit()));
    }
    assert!(root.is_dir(), "export wrote the requested directory");
    let _ = std::fs::remove_dir_all(&root);
}

#[test]
fn asset_audit_json_has_every_section() {
    let project = fixture();
    let (code, stdout, stderr) = run(&["asset-audit", "--project", &project, "--json"]);
    assert!(code == 0 || code == 1, "stderr: {stderr}");
    let value = json_of(&stdout);
    assert_eq!(value["command"], "asset-audit");
    assert_eq!(value["ok"], code == 0);
    assert!(value["duplicates"].is_array());
    assert!(value["unused"].is_array());
    let invalid = value["invalid"].as_array().expect("invalid array");
    assert_eq!(invalid.is_empty(), code == 0);
}

#[test]
fn json_errors_stay_exit_two_and_parseable() {
    let missing = std::env::temp_dir()
        .join("mono-cli-missing-project.oled.json")
        .to_string_lossy()
        .into_owned();
    let (code, stdout, stderr) = run(&["validate", "--project", &missing, "--json"]);
    assert_eq!(code, 2);
    let value = json_of(&stdout);
    assert_eq!(value["command"], "validate");
    assert_eq!(value["ok"], false);
    assert_eq!(value["exit_code"], 2);
    assert!(!value["error"]["code"].as_str().unwrap().is_empty());
    assert!(!value["error"]["message"].as_str().unwrap().is_empty());
    assert!(stderr.contains("ERROR:"));
}

#[test]
fn text_mode_keeps_the_human_summary() {
    let project = fixture();
    let (code, stdout, _) = run(&["validate", "--project", &project]);
    assert_eq!(code, 0);
    assert!(stdout.contains("PASS:"));
    assert!(!stdout.trim_start().starts_with('{'));
}

#[test]
fn review_pack_writes_html_and_json() {
    let root = std::env::temp_dir().join(format!("mono-cli-pack-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&root);
    std::fs::create_dir_all(&root).expect("temp dir");
    let project = fixture();
    let output = root.join("review.html");
    let (code, stdout, stderr) = run(&[
        "review-pack",
        "--project",
        &project,
        "--output",
        &output.to_string_lossy(),
        "--json",
    ]);
    assert_eq!(code, 0, "stderr: {stderr}");
    let value = json_of(&stdout);
    assert_eq!(value["command"], "review-pack");
    assert_eq!(value["ok"], true);
    assert_eq!(value["exit_code"], 0);
    assert!(value["screens"].as_u64().unwrap() >= 1);
    assert!(value["frames"].as_u64().unwrap() >= value["screens"].as_u64().unwrap());
    assert_eq!(value["sha256"].as_str().unwrap().len(), 64);
    assert!(value["bytes"].as_u64().unwrap() > 0);
    assert!(output.is_file());
    let html = std::fs::read_to_string(&output).unwrap();
    assert!(html.starts_with("<!DOCTYPE html>"));
    assert!(html.contains("id=\"pack-data\""));
    assert!(html.contains("\"renderer\""));
    let _ = std::fs::remove_dir_all(&root);
}

#[test]
fn review_pack_is_deterministic() {
    let root = std::env::temp_dir().join(format!("mono-cli-pack-det-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&root);
    std::fs::create_dir_all(&root).expect("temp dir");
    let project = fixture();
    let first = root.join("a.html");
    let second = root.join("b.html");
    let (code, stdout, _) = run(&[
        "review-pack",
        "--project",
        &project,
        "--output",
        &first.to_string_lossy(),
        "--json",
    ]);
    assert_eq!(code, 0);
    let first_hash = json_of(&stdout)["sha256"].as_str().unwrap().to_string();
    let (code, stdout, _) = run(&[
        "review-pack",
        "--project",
        &project,
        "--output",
        &second.to_string_lossy(),
        "--json",
    ]);
    assert_eq!(code, 0);
    assert_eq!(first_hash, json_of(&stdout)["sha256"].as_str().unwrap());
    assert_eq!(
        std::fs::read(&first).unwrap(),
        std::fs::read(&second).unwrap()
    );
    let _ = std::fs::remove_dir_all(&root);
}
