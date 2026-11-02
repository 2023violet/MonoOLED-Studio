#![allow(clippy::unwrap_used, clippy::expect_used, clippy::panic)]
//! Dirty tracking must describe the file on disk: undoing back to the saved
//! scene is clean, redo is dirty, and runtime `_` keys never count.

use std::path::PathBuf;

use mono_project::editor::EditorSession;
use mono_project::scene_io::load_scene;
use serde_json::json;

fn session(name: &str) -> (EditorSession, PathBuf) {
    let root = std::env::temp_dir().join(format!("mono-dirty-{name}-{}", std::process::id()));
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
    let doc = load_scene(&path, None).unwrap();
    (EditorSession::new(doc).unwrap(), root)
}

#[test]
fn undo_back_to_the_saved_scene_is_clean_and_redo_is_dirty() {
    let (mut session, root) = session("undo");
    assert!(!session.is_dirty());
    session.batch_move(&["p".to_string()], 1, 0, false).unwrap();
    assert!(session.is_dirty());
    assert!(session.undo());
    assert!(
        !session.is_dirty(),
        "undo must return to the saved baseline"
    );
    assert!(session.redo());
    assert!(session.is_dirty());
    let _ = std::fs::remove_dir_all(root);
}

#[test]
fn runtime_private_keys_do_not_count_as_edits() {
    let (mut session, root) = session("runtime");
    session
        .doc
        .data
        .insert("_asset_dirs".into(), json!(["assets"]));
    assert!(!session.is_dirty());
    let _ = std::fs::remove_dir_all(root);
}

#[test]
fn saving_rebaselines_and_recovery_can_force_dirty() {
    let (mut session, root) = session("save");
    session.batch_move(&["p".to_string()], 0, 1, false).unwrap();
    assert!(session.is_dirty());
    session.save().unwrap();
    assert!(!session.is_dirty());

    session.mark_dirty();
    assert!(session.is_dirty(), "restored snapshots are not on disk");
    session.mark_clean();
    assert!(!session.is_dirty());
    let _ = std::fs::remove_dir_all(root);
}
