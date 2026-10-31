#![allow(clippy::unwrap_used, clippy::expect_used, clippy::panic)]
//! Design rules are manifest data, not scene data: editing them writes
//! `project.oled.json` immediately, and a project whose rules nobody touched
//! must not gain the key (the schema_version 1 shape stays as it was written).

use std::path::{Path, PathBuf};

use mono_project::project::ProjectWorkspace;
use serde_json::{Value, json};

fn copy_dir(from: &Path, to: &Path) {
    std::fs::create_dir_all(to).unwrap();
    for entry in std::fs::read_dir(from).unwrap() {
        let entry = entry.unwrap();
        let target = to.join(entry.file_name());
        if entry.file_type().unwrap().is_dir() {
            copy_dir(&entry.path(), &target);
        } else {
            std::fs::copy(entry.path(), &target).unwrap();
        }
    }
}

/// A copy of the shipped project with `design_rules` removed, so "nothing was
/// written" is observable rather than assumed.
fn temp_project(name: &str) -> (PathBuf, PathBuf) {
    let root = std::env::temp_dir().join(format!("mono-rules-{name}-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&root);
    let source =
        PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../test_assets/projects/curing_lite");
    copy_dir(&source, &root);
    let manifest = root.join("project.oled.json");
    let mut data: Value =
        serde_json::from_str(&std::fs::read_to_string(&manifest).unwrap()).unwrap();
    data.as_object_mut().unwrap().shift_remove("design_rules");
    std::fs::write(&manifest, serde_json::to_string_pretty(&data).unwrap()).unwrap();
    (manifest, root)
}

fn keys(path: &Path) -> Vec<String> {
    let text = std::fs::read_to_string(path).unwrap();
    serde_json::from_str::<Value>(&text)
        .unwrap()
        .as_object()
        .unwrap()
        .keys()
        .cloned()
        .collect()
}

#[test]
fn saving_an_untouched_project_does_not_backfill_design_rules() {
    let (manifest, root) = temp_project("untouched");
    let before = keys(&manifest);
    let mut project = ProjectWorkspace::load(&manifest).unwrap();
    project.save().unwrap();
    assert_eq!(
        keys(&manifest),
        before,
        "save reordered or added manifest keys"
    );
    assert!(
        !keys(&manifest).contains(&"design_rules".to_string()),
        "a project nobody edited gained a design_rules block"
    );
    let _ = std::fs::remove_dir_all(&root);
}

#[test]
fn editing_rules_writes_at_once_and_keeps_the_other_keys_in_place() {
    let (manifest, root) = temp_project("edit");
    let before = keys(&manifest);
    let rules = json!({
        "required_elements": ["battery"],
        "zones": {"battery": {"x": 0, "y": 0, "w": 20, "h": 32}},
        "baseline_groups": [],
    });
    ProjectWorkspace::load(&manifest)
        .unwrap()
        .set_design_rules(rules.clone())
        .unwrap();
    // No reload, no second save: the write is the point of `transact`.
    let on_disk: Value =
        serde_json::from_str(&std::fs::read_to_string(&manifest).unwrap()).unwrap();
    assert_eq!(on_disk["design_rules"], rules);
    let after = keys(&manifest);
    let without_rules = |list: Vec<String>| {
        list.into_iter()
            .filter(|key| key != "design_rules")
            .collect::<Vec<_>>()
    };
    assert_eq!(without_rules(after.clone()), without_rules(before));
    assert_eq!(
        after.last().map(String::as_str),
        Some("design_rules"),
        "the new block was inserted in the middle of the manifest"
    );

    // A second edit replaces it in place; it does not append a second key or
    // move the block.
    let edited = json!({"required_elements": [], "zones": {}, "baseline_groups": []});
    ProjectWorkspace::load(&manifest)
        .unwrap()
        .set_design_rules(edited.clone())
        .unwrap();
    let on_disk: Value =
        serde_json::from_str(&std::fs::read_to_string(&manifest).unwrap()).unwrap();
    assert_eq!(on_disk["design_rules"], edited);
    assert_eq!(keys(&manifest), after);
    let _ = std::fs::remove_dir_all(&root);
}

#[test]
fn a_narrowed_zone_reaches_the_findings_without_a_reopen() {
    let (manifest, root) = temp_project("findings");
    let mut project = ProjectWorkspace::load(&manifest).unwrap();
    // `main` is the screen that carries the elements; the fixture's other screen
    // is deliberately empty.
    let scene_path = project.screen_path("main").unwrap();
    let scene: Value =
        serde_json::from_str(&std::fs::read_to_string(&scene_path).unwrap()).unwrap();
    let rules = json!({
        "required_elements": ["battery", "hero_digits", "mode_label"],
        // `battery` spans x=5..16, y=2..30: a 4px-wide column cannot contain it.
        "zones": {"battery": {"x": 0, "y": 0, "w": 4, "h": 32}},
        "baseline_groups": [],
    });
    project.set_design_rules(rules.clone()).unwrap();
    // The desktop hands the manifest's own block straight to the checker, so a
    // rules edit shows up in the next findings pass with no reload in between.
    let findings = mono_project::export::check_design_rules(scene.as_object().unwrap(), &rules);
    let outside: Vec<_> = findings
        .iter()
        .filter(|finding| finding.code == "ELEMENT_OUTSIDE_ZONE")
        .collect();
    assert!(
        outside
            .iter()
            .any(|finding| finding.element_id.as_deref() == Some("battery")),
        "the narrowed zone produced no finding: {findings:?}"
    );
    assert!(
        findings
            .iter()
            .all(|finding| finding.code != "REQUIRED_ELEMENT_MISSING"),
        "the fixture screen is missing elements this test assumes: {findings:?}"
    );
    let _ = std::fs::remove_dir_all(&root);
}
