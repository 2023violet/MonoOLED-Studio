#![allow(clippy::unwrap_used, clippy::expect_used, clippy::panic)]
//! C-header export must honour the same release gate as `export.current`:
//! blocking findings are an invalid request and no file is written.

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
    let root = std::env::temp_dir().join(format!("mono-gate-{name}-{}", std::process::id()));
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
fn blocked_c_header_export_writes_nothing() {
    let (mut service, root) = attached_service("c-header");
    call(
        &mut service,
        "scene.create_element",
        json!({"element": {"id": "stub", "type": "placeholder", "x": 0, "y": 0, "w": 8, "h": 8}}),
    );
    // A second, distinct problem: the response has to name both, or a caller
    // fixing one still gets refused with no way to see what is left.
    call(
        &mut service,
        "scene.create_element",
        json!({"element": {"id": "far", "type": "placeholder", "x": 4000, "y": 4000, "w": 8, "h": 8}}),
    );
    let response = dispatch_json_rpc(
        &mut service,
        &json!({
            "jsonrpc": "2.0",
            "id": 2,
            "method": "export.c_header",
            "params": {"path": "exports/blocked.h"}
        }),
    );
    assert_eq!(response["error"]["code"], "INVALID_REQUEST", "{response}");
    let message = response["error"]["message"].as_str().unwrap_or_default();
    assert!(message.contains("export blocked"), "{response}");
    assert!(message.contains("DRAFT_PLACEHOLDER"), "{response}");
    assert!(message.contains("OUT_OF_BOUNDS"), "{response}");
    assert!(!root.join("exports").join("blocked.h").exists());
}

#[test]
fn clean_scene_still_exports_a_c_header() {
    let (mut service, root) = attached_service("c-header-clean");
    call(
        &mut service,
        "export.c_header",
        json!({"path": "exports/clean.h"}),
    );
    assert!(root.join("exports").join("clean.h").is_file());
}
