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

#[test]
fn undo_follows_the_element_id_when_the_list_moved_underneath() {
    // An open Automation transaction changes the list without recording a step
    // (`changed()` records only outside a transaction). A geometry edit recorded
    // meanwhile must still restore its own element, never the one that now sits
    // at its old index.
    let (mut session, root) = session("shifted");
    assert!(session.set_geometry("b", &[("x", 30)], false).unwrap());
    if let Some(Value::Array(list)) = session.doc.data.get_mut("elements") {
        list.insert(
            0,
            json!({"id": "c", "type": "placeholder", "x": 0, "y": 20, "w": 4, "h": 4}),
        );
    }
    assert!(session.undo());
    let ids: Vec<String> = elements(&session)
        .iter()
        .map(|e| e["id"].as_str().unwrap().to_string())
        .collect();
    assert_eq!(
        ids,
        ["c", "a", "b", "z"],
        "no element is lost or duplicated"
    );
    assert_eq!(
        elements(&session)[2]["x"],
        json!(10),
        "b is back where it was"
    );
    assert!(session.redo());
    assert_eq!(elements(&session)[2]["x"], json!(30));
    assert_eq!(elements(&session)[1]["x"], json!(0), "a is untouched");

    // An element that is gone is left alone instead of overwriting a neighbour.
    assert!(session.undo());
    if let Some(Value::Array(list)) = session.doc.data.get_mut("elements") {
        list.retain(|e| e["id"] != json!("b"));
    }
    assert!(session.redo());
    let ids: Vec<String> = elements(&session)
        .iter()
        .map(|e| e["id"].as_str().unwrap().to_string())
        .collect();
    assert_eq!(ids, ["c", "a", "z"]);
    let _ = std::fs::remove_dir_all(&root);
}

#[test]
fn a_coalesced_drag_follows_the_element_id_when_the_list_moves_mid_drag() {
    fn insert_front(session: &mut EditorSession, id: &str) {
        if let Some(Value::Array(list)) = session.doc.data.get_mut("elements") {
            list.insert(
                0,
                json!({"id": id, "type": "placeholder", "x": 0, "y": 20, "w": 4, "h": 4}),
            );
        }
    }
    fn ids(session: &EditorSession) -> Vec<String> {
        elements(session)
            .iter()
            .map(|e| e["id"].as_str().unwrap().to_string())
            .collect()
    }

    let new_session = session;
    // A multi-select drag: the list shifts between two coalesced batches.
    let (mut session, root) = new_session("mid-drag-multi");
    let pair = ["a".to_string(), "b".to_string()];
    assert!(session.batch_move(&pair, 1, 0, true).unwrap());
    insert_front(&mut session, "c");
    assert!(session.batch_move(&pair, 1, 0, true).unwrap());
    session.end_coalesced_edit();
    assert!(session.undo(), "the drag is one step");
    assert_eq!(ids(&session), ["c", "a", "b", "z"]);
    assert_eq!(
        elements(&session)[1]["x"],
        json!(0),
        "a is back at its start"
    );
    assert_eq!(
        elements(&session)[2]["x"],
        json!(10),
        "b is back at its start"
    );
    assert!(session.redo());
    assert_eq!(ids(&session), ["c", "a", "b", "z"], "redo loses nothing");
    assert_eq!(elements(&session)[1]["x"], json!(2));
    assert_eq!(elements(&session)[2]["x"], json!(12));
    let _ = std::fs::remove_dir_all(&root);

    // A single-element drag: one element must not get two entries.
    let (mut session, root) = new_session("mid-drag-single");
    assert!(session.set_geometry("b", &[("x", 20)], true).unwrap());
    insert_front(&mut session, "c");
    assert!(session.set_geometry("b", &[("x", 30)], true).unwrap());
    session.end_coalesced_edit();
    assert!(session.undo());
    assert_eq!(
        elements(&session)[2]["x"],
        json!(10),
        "undo reaches the start"
    );
    assert!(session.redo());
    assert_eq!(elements(&session)[2]["x"], json!(30));
    let _ = std::fs::remove_dir_all(&root);
}
