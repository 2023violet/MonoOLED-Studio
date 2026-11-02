#![allow(clippy::unwrap_used, clippy::expect_used, clippy::panic)]
//! The release gate is shared by the desktop app, the CLI and the Automation
//! API: a scene with blocking findings must never leave a file behind, and the
//! report has to survive the handoff staging directory.

use std::path::{Path, PathBuf};

use mono_core::render::posix;
use mono_core::state::{IntegerPolicy, State};
use mono_project::export::{
    CANCELLED, EXPORT_BLOCKED, build_handoff_package, export_scene, export_scene_with_report,
    preflight, write_validation_report,
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
fn the_gate_stops_at_the_first_blocking_frame() {
    let root = temp("gate-stop-root");
    std::fs::create_dir_all(root.join("assets")).unwrap();
    let png = mono_project::image_io::encode_rgba_png(1, 1, &[0, 0, 0, 255]).unwrap();
    std::fs::write(root.join("assets").join("0.png"), png).unwrap();
    let scene: Map<String, Value> = serde_json::from_value(json!({
        "canvas": {"w": 8, "h": 8},
        "states": {"n": {"type": "int", "min": 0, "max": 3, "init": 0}},
        "elements": [{
            "id": "icon", "type": "image", "asset": "assets/{n}.png",
            "x": 0, "y": 0, "w": 1, "h": 1
        }]
    }))
    .unwrap();
    let states: Vec<(String, State)> = (0..4)
        .map(|n| {
            (
                format!("case_{n:04}"),
                serde_json::from_value(json!({"n": n})).unwrap(),
            )
        })
        .collect();

    let early = preflight(&scene, &root, &states).unwrap();
    assert_eq!(
        early.len(),
        2,
        "preflight must stop at the first blocking frame"
    );
    assert!(
        early
            .get("case_0001")
            .unwrap()
            .iter()
            .any(|f| f.code == "ASSET_NOT_FOUND")
    );

    let out = temp("gate-stop-out");
    let error = export_scene(&scene, &root, &out, &states, &mut |_, _, _| true).unwrap_err();
    assert_eq!(error.code, EXPORT_BLOCKED);
    let report = std::fs::read_to_string(out.join("validation_report.md")).unwrap();
    assert!(
        report.contains("Frames checked: **2** of **4** (stopped at the first blocking frame)\n"),
        "{report}"
    );
    assert!(report.contains("## case_0001"), "{report}");
    assert!(!report.contains("## case_0002"), "{report}");
    assert!(!out.join("golden").exists());
    let _ = std::fs::remove_dir_all(&root);
    let _ = std::fs::remove_dir_all(&out);
}

fn clean_scene() -> Map<String, Value> {
    serde_json::from_value(json!({"canvas": {"w": 8, "h": 8}, "states": {}, "elements": []}))
        .unwrap()
}

fn leftovers(dir: &Path) -> Vec<String> {
    std::fs::read_dir(dir)
        .map(|entries| {
            entries
                .flatten()
                .map(|e| e.file_name().to_string_lossy().into_owned())
                .filter(|name| name.ends_with(".tmp"))
                .collect()
        })
        .unwrap_or_default()
}

#[test]
fn a_blocked_export_leaves_an_earlier_successful_one_alone() {
    let out = temp("keep-earlier");
    export_scene(
        &clean_scene(),
        Path::new("."),
        &out,
        &states(),
        &mut |_, _, _| true,
    )
    .unwrap();
    let contract = std::fs::read(out.join("ui_contract.json")).unwrap();
    let golden = std::fs::read(out.join("golden/current.bin")).unwrap();

    let error = export_scene(
        &blocked_scene(),
        Path::new("."),
        &out,
        &states(),
        &mut |_, _, _| true,
    )
    .unwrap_err();
    assert_eq!(error.code, EXPORT_BLOCKED);
    assert_eq!(
        std::fs::read(out.join("ui_contract.json")).unwrap(),
        contract
    );
    assert_eq!(
        std::fs::read(out.join("golden/current.bin")).unwrap(),
        golden
    );
    let _ = std::fs::remove_dir_all(&out);
}

#[test]
fn a_zero_frame_export_writes_a_parseable_contract() {
    let out = temp("zero-frames");
    let summary = export_scene(&clean_scene(), Path::new("."), &out, &[], &mut |_, _, _| {
        true
    })
    .unwrap();
    assert_eq!(summary.frame_count, 0);
    let contract: Value =
        serde_json::from_slice(&std::fs::read(out.join("ui_contract.json")).unwrap()).unwrap();
    assert_eq!(contract["frames"], json!({}));
    let text = std::fs::read_to_string(out.join("ui_contract.json")).unwrap();
    assert!(text.contains("\"frames\": {},\n  \"product\""), "{text}");
    let _ = std::fs::remove_dir_all(&out);
}

#[test]
fn cancelling_during_the_render_stage_leaves_no_partial_artefact() {
    let out = temp("cancel-render");
    let error = export_scene(
        &clean_scene(),
        Path::new("."),
        &out,
        &states(),
        &mut |stage, _, _| stage != "export.render",
    )
    .unwrap_err();
    assert_eq!(error.code, CANCELLED);
    assert!(!out.join("ui_contract.json").exists());
    assert!(!out.join("UI_SPEC.md").exists());
    assert_eq!(leftovers(&out), Vec::<String>::new());
    let _ = std::fs::remove_dir_all(&out);
}

#[test]
fn a_repeated_frame_name_is_refused_before_anything_is_written() {
    let out = temp("repeat-frame");
    let repeated = [
        ("same".to_string(), State::new()),
        ("same".to_string(), State::new()),
    ];
    let error = export_scene(
        &clean_scene(),
        Path::new("."),
        &out,
        &repeated,
        &mut |_, _, _| true,
    )
    .unwrap_err();
    assert!(error.message.contains("same"), "{}", error.message);
    assert!(!out.exists());
}

#[test]
fn write_validation_report_creates_missing_parents() {
    let report = temp("parents").join(".oled").join("validation_report.md");
    let findings = preflight(&blocked_scene(), Path::new("."), &states()).unwrap();
    write_validation_report(&report, &findings).unwrap();
    assert!(report.is_file());
}
