#![allow(clippy::unwrap_used, clippy::expect_used, clippy::panic)]
//! The release gate is shared by the desktop app, the CLI and the Automation
//! API: a scene with blocking findings must never leave a file behind, and the
//! report has to survive the handoff staging directory.

use std::path::{Path, PathBuf};

use mono_core::render::posix;
use mono_core::state::{IntegerPolicy, State};
use mono_project::export::{
    EXPORT_BLOCKED, build_handoff_package, export_scene, export_scene_with_report, preflight,
    write_validation_report,
};
use mono_project::resources::hex_digest;
use serde_json::{Map, Value, json};

fn temp(name: &str) -> PathBuf {
    let root = std::env::temp_dir().join(format!("mono-gate-{}-{name}", std::process::id()));
    let _ = std::fs::remove_dir_all(&root);
    root
}

fn blocked_scene() -> Map<String, Value> {
    serde_json::from_value(json!({
        "canvas": {"w": 64, "h": 16},
        "states": {},
        "elements": [{"id": "p", "type": "placeholder", "x": 0, "y": 0, "w": 8, "h": 8}]
    }))
    .unwrap()
}

fn states() -> Vec<(String, State)> {
    vec![("current".into(), State::new())]
}

#[test]
fn preflight_reports_blockers_without_writing_anything() {
    let root = Path::new(".");
    let findings = preflight(&blocked_scene(), root, &states()).unwrap();
    let current = findings.get("current").unwrap();
    assert!(
        current
            .iter()
            .any(|f| f.code == "DRAFT_PLACEHOLDER" && f.is_blocking())
    );
    assert!(findings.len() == 1);
}

#[test]
fn export_scene_keeps_its_contract_and_writes_the_sibling_report() {
    let out = temp("export");
    let error = export_scene(
        &blocked_scene(),
        Path::new("."),
        &out,
        &states(),
        &mut |_, _, _| true,
    )
    .unwrap_err();
    assert_eq!(error.code, EXPORT_BLOCKED);
    let report = out.join("validation_report.md");
    assert_eq!(
        error.message,
        format!("export blocked; see {}", report.display())
    );
    assert!(report.is_file());
}

#[test]
fn blocked_export_leaves_no_directories_behind() {
    let out = temp("no-debris");
    let error = export_scene(
        &blocked_scene(),
        Path::new("."),
        &out,
        &states(),
        &mut |_, _, _| true,
    )
    .unwrap_err();
    assert_eq!(error.code, EXPORT_BLOCKED);
    assert!(out.join("validation_report.md").is_file());
    assert!(
        !out.join("reference").exists() && !out.join("golden").exists(),
        "a refused export must not create the frame directories"
    );
}

#[test]
fn explicit_report_path_replaces_the_output_directory_default() {
    let out = temp("explicit-output");
    let report = temp("explicit-report").join("gate.md");
    let error = export_scene_with_report(
        &blocked_scene(),
        Path::new("."),
        &out,
        &states(),
        Some(&report),
        &mut |_, _, _| true,
    )
    .unwrap_err();
    assert_eq!(error.code, EXPORT_BLOCKED);
    assert!(report.is_file());
    assert!(!out.join("validation_report.md").exists());
}

#[test]
fn handoff_keeps_the_report_after_its_staging_directory_is_deleted() {
    let root = temp("handoff");
    std::fs::create_dir_all(&root).unwrap();
    let zip = root.join("handoff.zip");
    let error = build_handoff_package(
        &blocked_scene(),
        Path::new("."),
        &zip,
        &states(),
        IntegerPolicy::Representative,
        &mut |_, _, _| true,
    )
    .unwrap_err();
    assert_eq!(error.code, EXPORT_BLOCKED);
    let report = zip.with_extension("validation.md");
    assert!(
        report.is_file(),
        "report must outlive the staging directory"
    );
    assert!(!zip.exists(), "a blocked handoff must not produce a ZIP");
    let work = std::env::temp_dir().join(format!(
        "mono-handoff-{}-{}",
        std::process::id(),
        hex_digest(posix(&zip).as_bytes()).get(..12).unwrap()
    ));
    assert!(!work.exists(), "staging directory must be removed");
}

#[test]
fn write_validation_report_creates_missing_parents() {
    let report = temp("parents").join(".oled").join("validation_report.md");
    let findings = preflight(&blocked_scene(), Path::new("."), &states()).unwrap();
    write_validation_report(&report, &findings).unwrap();
    assert!(report.is_file());
}
