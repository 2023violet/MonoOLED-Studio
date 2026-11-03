//! Regressions from the G4 agent review: switching screens and rolling back a
//! transaction must rebind the live editor session (V1 `reset_scene`).
#![allow(clippy::unwrap_used, clippy::expect_used, clippy::panic)]

use std::path::{Path, PathBuf};

use mono_automation::{Service, dispatch_json_rpc};
use serde_json::{Value, json};

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

fn attached_service(name: &str) -> (Service, PathBuf) {
    let root = std::env::temp_dir().join(format!("mono-reset-{name}-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&root);
    let repo = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../..");
    copy_dir(&repo.join("test_assets/projects/curing_lite"), &root);
    let mut service =
        Service::for_project(&root.join("project.oled.json"), Some("main"), "edit").unwrap();
    service.editor_attached = true;
    (service, root)
}

fn call(service: &mut Service, method: &str, params: Value) -> Value {
    let response = dispatch_json_rpc(
        service,
        &json!({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}),
    );
    assert!(response.get("error").is_none(), "{method}: {response}");
    response
}

#[test]
fn opening_another_screen_drops_the_previous_screens_history_and_fingerprint() {
    let (mut service, root) = attached_service("open");
    call(
        &mut service,
        "scene.update_element",
        json!({"id": "mode_label", "changes": {"x": 80}}),
    );
    call(&mut service, "project.save", json!({}));
    call(
        &mut service,
        "project.create_screen",
        json!({"screen_id": "second", "open": true}),
    );
    assert!(
        !service.session.can_undo(),
        "undo history leaked across screens"
    );
    assert!(service.session.element_ids().is_empty());
    service
        .session
        .save()
        .expect("save on the new screen must not see a stale fingerprint");
    let _ = std::fs::remove_dir_all(&root);
}

#[test]
fn rollback_restores_a_renderable_runtime_state() {
    let (mut service, root) = attached_service("rollback");
    let tx =
        call(&mut service, "history.begin_transaction", json!({}))["result"]["transaction"].clone();
    call(
        &mut service,
        "state.set_schema",
        json!({"_transaction": tx, "schema": {"variables": {"only": {"type": "int", "min": 0, "max": 5, "init": 3}}}}),
    );
    call(&mut service, "history.rollback", json!({"transaction": tx}));
    assert!(service.session.state.contains_key("battery"));
    service.session.render().expect("render after rollback");
    let _ = std::fs::remove_dir_all(&root);
}

#[test]
fn renaming_a_screen_moves_its_annotations() {
    let (mut service, root) = attached_service("rename-notes");
    let review = root.join("review/review.json");
    std::fs::create_dir_all(review.parent().unwrap()).unwrap();
    std::fs::write(
        &review,
        r#"{"schema_version":1,"annotations":[{"id":"n1","kind":"defect","screen":"main","state":{},"title":"t","body":"","evidence":{"sha256":"","lit_pixels":0,"source":"designer"},"created_utc":"","updated_utc":""}],"scenarios":[]}"#,
    )
    .unwrap();
    call(
        &mut service,
        "project.rename_screen",
        json!({"screen_id": "main", "new_id": "renamed"}),
    );
    let store = mono_project::review::ReviewStore::for_root(&root).unwrap();
    assert_eq!(store.annotations_for("renamed").len(), 1);
    assert!(store.annotations_for("main").is_empty());
    let _ = std::fs::remove_dir_all(&root);
}

#[test]
fn a_failed_annotation_move_still_rebinds_the_session_to_the_renamed_file() {
    let (mut service, root) = attached_service("rename-notes-fail");
    let review = root.join("review/review.json");
    std::fs::create_dir_all(review.parent().unwrap()).unwrap();
    // A newer schema the store refuses to load: the annotation move fails.
    std::fs::write(
        &review,
        r#"{"schema_version":99,"annotations":[],"scenarios":[]}"#,
    )
    .unwrap();
    let old_path = service.session.doc.path.clone();
    let response = dispatch_json_rpc(
        &mut service,
        &json!({"jsonrpc": "2.0", "id": 1, "method": "project.rename_screen",
                "params": {"screen_id": "main", "new_id": "renamed"}}),
    );
    assert!(response.get("error").is_some(), "{response}");
    assert!(!old_path.exists(), "the rename moved the scene file");
    assert_ne!(service.session.doc.path, old_path);
    assert!(service.session.doc.path.ends_with("renamed.json"));
    call(&mut service, "project.save", json!({}));
    assert!(
        !old_path.exists(),
        "a save after the failed move must not recreate the old file"
    );
    let _ = std::fs::remove_dir_all(&root);
}

#[test]
fn renaming_another_screen_leaves_the_session_on_its_own_file() {
    // The fixture's manifest marks `123` active while this session edits `main`.
    let (mut service, root) = attached_service("rename-other");
    let own = service.session.doc.path.clone();
    let main_before = std::fs::read(&own).unwrap();
    call(
        &mut service,
        "project.rename_screen",
        json!({"screen_id": "123", "new_id": "renamed"}),
    );
    assert_eq!(service.session.doc.path, own);
    call(&mut service, "project.save", json!({}));
    assert_eq!(std::fs::read(&own).unwrap().len(), main_before.len());
    let renamed = service
        .require_project()
        .unwrap()
        .screen_path("renamed")
        .unwrap();
    assert_ne!(std::fs::read(renamed).unwrap(), main_before);
    let _ = std::fs::remove_dir_all(&root);
}
