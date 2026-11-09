#![allow(clippy::unwrap_used, clippy::expect_used, clippy::panic)]
//! A geometry edit records only the elements it changed (TASK-018). Undo and
//! redo must still restore the exact element list, coalescing must still make
//! one step of a drag, and the Inspector's frame geometry must equal
//! `geometry()` without the scratch render.

use std::path::{Path, PathBuf};

use mono_project::editor::EditorSession;
use mono_project::scene_io::load_scene;
use serde_json::{Value, json};

fn session(name: &str) -> (EditorSession, PathBuf) {
    let root = std::env::temp_dir().join(format!("mono-patch-{name}-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&root);
    std::fs::create_dir_all(&root).unwrap();
    let path = root.join("scene.json");
    std::fs::write(
        &path,
        json!({
            "canvas": {"w": 64, "h": 32},
            "states": {},
            "elements": [
                {"id": "a", "type": "placeholder", "x": 0, "y": 0, "w": 8, "h": 8},
                {"id": "b", "type": "placeholder", "x": 10, "y": 0, "w": 8, "h": 8},
                {"id": "z", "type": "placeholder", "y": 3,
                 "zone": {"x": 20, "y": 1, "w": 8, "h": 8}}
            ]
        })
        .to_string(),
    )
    .unwrap();
    let doc = load_scene(&path, None).unwrap();
    (EditorSession::new(doc).unwrap(), root)
}

fn elements(session: &EditorSession) -> Vec<Value> {
    session.scene()["elements"].as_array().unwrap().clone()
}

#[test]
fn undo_and_redo_restore_the_exact_list_after_a_coalesced_drag() {
    let (mut session, root) = session("drag");
    let original = elements(&session);
    // One drag: three coalesced batches over two elements, one of them zoned.
    let ids = ["a".to_string(), "z".to_string()];
    assert!(session.batch_move(&ids, 1, 0, true).unwrap());
    assert!(session.batch_move(&ids, 1, 1, true).unwrap());
    assert!(session.batch_move(&ids, 0, 1, true).unwrap());
    session.end_coalesced_edit();
    let moved = elements(&session);
    assert_eq!(moved[0]["x"], json!(2));
    assert_eq!(moved[0]["y"], json!(2));
    assert_eq!(moved[2]["zone"]["x"], json!(22));
    assert_eq!(
        moved[1], original[1],
        "an untouched element must not change"
    );
    assert!(session.undo(), "the drag must be one undo step");
    assert_eq!(elements(&session), original);
    assert!(!session.can_undo());
    assert!(session.redo());
    assert_eq!(elements(&session), moved);
    let _ = std::fs::remove_dir_all(&root);
}

#[test]
fn an_edit_that_changes_nothing_records_no_step() {
    let (mut session, root) = session("noop");
    assert!(!session.set_geometry("a", &[("x", 0)], false).unwrap());
    assert!(!session.can_undo());
    assert!(session.set_geometry("a", &[("x", 4)], false).unwrap());
    assert_eq!(session.undo_label(), Some("geometry:a"));
    let _ = std::fs::remove_dir_all(&root);
}

#[test]
fn separate_edits_stay_separate_steps_after_another_command() {
    let (mut session, root) = session("steps");
    let original = elements(&session);
    session.set_geometry("a", &[("x", 4)], false).unwrap();
    let after_first = elements(&session);
    session.set_geometry("b", &[("w", 12)], false).unwrap();
    session
        .add_elements(
            vec![json!({"id": "c", "type": "placeholder", "x": 0, "y": 20, "w": 4, "h": 4})],
            "add",
        )
        .unwrap();
    assert!(session.undo());
    assert!(session.undo());
    assert_eq!(elements(&session), after_first);
    assert!(session.undo());
    assert_eq!(elements(&session), original);
    let _ = std::fs::remove_dir_all(&root);
}

#[test]
fn frame_geometry_equals_inspector_geometry_on_the_fixture() {
    // The fixture carries a zoned element, a digits element (the scratch-render
    // path), an image_seq and two images.
    let root = Path::new(env!("CARGO_MANIFEST_DIR")).join("../../test_assets/projects/curing_lite");
    let doc = load_scene(&root.join("scenes/main_scene.json"), Some(&root)).unwrap();
    let mut session = EditorSession::new(doc).unwrap();
    let resolved = session.render().unwrap().resolved_elements;
    let ids = session.element_ids();
    assert!(ids.iter().any(|id| id == "hero_digits"));
    for id in ids {
        let from_frame = session
            .geometry_from_frame(&id, &resolved)
            .unwrap_or_else(|| panic!("{id} has no frame geometry"));
        assert_eq!(from_frame, session.geometry(&id).unwrap(), "element {id}");
    }
    // A frame that does not line up with the scene is never used.
    assert_eq!(session.geometry_from_frame("battery", &resolved[1..]), None);
}
