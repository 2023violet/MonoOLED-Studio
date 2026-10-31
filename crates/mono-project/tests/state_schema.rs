#![allow(clippy::unwrap_used, clippy::expect_used, clippy::panic)]
//! The state schema is scene data: editing it dirties the document, lands as
//! one undo step, and re-seeds the preview state the canvas renders.

use std::path::PathBuf;

use mono_core::state::{schema_from_scene, validate_state_schema};
use mono_project::editor::EditorSession;
use mono_project::scene_io::load_scene;
use serde_json::{Value, json};

fn session(name: &str) -> (EditorSession, PathBuf) {
    let root = std::env::temp_dir().join(format!("mono-schema-{name}-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&root);
    std::fs::create_dir_all(&root).unwrap();
    let path = root.join("scene.json");
    std::fs::write(
        &path,
        json!({
            "canvas": {"w": 64, "h": 16},
            "states": {},
            "elements": [{"id": "p", "type": "placeholder", "x": 0, "y": 0, "w": 8, "h": 8}]
        })
        .to_string(),
    )
    .unwrap();
    (
        EditorSession::new(load_scene(&path, None).unwrap()).unwrap(),
        root,
    )
}

/// What the desktop panel hands over: the schema the validator normalised.
fn normalized(raw: Value) -> Value {
    let checked = validate_state_schema(&raw);
    assert_eq!(checked["valid"], json!(true), "{checked}");
    checked["schema"].clone()
}

#[test]
fn adding_a_variable_dirties_the_scene_and_undo_restores_the_saved_file() {
    let (mut session, root) = session("add");
    let schema = normalized(json!({"variables": {
        "battery": {"type": "int", "init": 3, "min": 0, "max": 4}
    }}));

    assert!(session.set_state_schema(&schema));
    assert!(session.is_dirty());
    assert_eq!(session.doc.data["states"]["battery"]["init"], json!(3));
    assert_eq!(session.state["battery"], json!(3), "preview re-seeded");
    assert_eq!(session.undo_label(), Some("state_schema"));

    assert!(session.undo());
    assert!(
        !session.is_dirty(),
        "undo must return to the schema on disk"
    );
    assert_eq!(
        schema_from_scene(&session.doc.data),
        json!({"variables": {}, "relations": []})
    );
    let _ = std::fs::remove_dir_all(root);
}

#[test]
fn an_unchanged_schema_leaves_no_extra_undo_step() {
    let (mut session, root) = session("noop");
    let schema = normalized(json!({"variables": {
        "mode": {"type": "enum", "values": ["a", "b"], "init": "a"}
    }}));
    assert!(session.set_state_schema(&schema));
    session.save().unwrap();

    assert!(
        !session.set_state_schema(&schema),
        "second write changes nothing"
    );
    assert!(!session.is_dirty());
    assert!(session.undo());
    assert_eq!(
        schema_from_scene(&session.doc.data),
        json!({"variables": {}, "relations": []})
    );
    assert_eq!(session.undo_label(), None, "only one step was recorded");
    let _ = std::fs::remove_dir_all(root);
}

#[test]
fn changing_a_variable_type_reseeds_the_preview_and_keeps_relations_ordered() {
    let (mut session, root) = session("retype");
    let first = normalized(json!({
        "variables": {
            "battery": {"type": "int", "init": 3, "min": 0, "max": 4},
            "level": {"type": "int", "init": 4, "min": 0, "max": 4}
        },
        "relations": [{"left": "battery", "operator": "<=", "right": "level"}]
    }));
    assert!(session.set_state_schema(&first));
    assert_eq!(
        session.doc.data["state_relations"],
        json!([{"left": "battery", "operator": "<=", "right": "level"}])
    );

    let second = normalized(json!({
        "variables": {
            "battery": {"type": "enum", "values": ["low", "full"], "init": "low"},
            "level": {"type": "int", "init": 4, "min": 0, "max": 4}
        }
    }));
    assert!(session.set_state_schema(&second));
    assert_eq!(session.state["battery"], json!("low"));
    assert!(
        session.doc.data.get("state_relations").is_none(),
        "an empty relation list is removed, not written as []"
    );

    assert!(session.undo());
    assert_eq!(session.state["battery"], json!(3), "undo restores the int");
    assert!(session.doc.data.get("state_relations").is_some());
    let _ = std::fs::remove_dir_all(root);
}
