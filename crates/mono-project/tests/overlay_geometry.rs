#![allow(clippy::unwrap_used, clippy::expect_used, clippy::panic)]
//! The canvas overlay and hit-testing read the rects the renderer resolved,
//! instead of asking `geometry(id)` per element (which clones the element list
//! and re-renders text elements). The two only agree under the Inspector's own
//! precedence — a complete zone first, then a complete explicit rect, then the
//! renderer's own box — so this pins exactly that on the fixture scene, which
//! carries a zone element, a `digits` element, an `image_seq` and two `image` elements.

use std::path::{Path, PathBuf};

use mono_project::editor::{EditorSession, overlay_rect};
use mono_project::scene_io::load_scene;
use serde_json::json;

fn fixture(name: &str) -> (EditorSession, PathBuf) {
    let root = Path::new(env!("CARGO_MANIFEST_DIR")).join("../../test_assets/projects/curing_lite");
    let path = root.join("scenes").join(name);
    let doc = load_scene(&path, Some(&root)).unwrap();
    (EditorSession::new(doc).unwrap(), root)
}

#[test]
fn every_overlay_rect_equals_the_geometry_the_inspector_reports() {
    let (mut session, _root) = fixture("main_scene.json");
    let ids = session.element_ids();
    assert!(ids.len() > 2, "the fixture lost its elements: {ids:?}");
    let elements = session.scene()["elements"].as_array().unwrap().clone();
    let resolved = session.render().unwrap().resolved_elements;
    assert_eq!(
        resolved.len(),
        elements.len(),
        "the overlay indexes resolved elements by scene position, so it needs one entry per element"
    );
    for (index, element) in elements.iter().enumerate() {
        let id = ids[index].clone();
        assert_eq!(resolved[index]["id"], json!(id), "order drifted at {index}");
        let geometry = session.geometry(&id).unwrap();
        let expected = (geometry.x, geometry.y, geometry.w, geometry.h);
        // `None` would mean the overlay has to ask `geometry`.
        let drawn = overlay_rect(element, &resolved, index);
        assert!(
            drawn.is_some(),
            "element {id} has no resolvable overlay rect"
        );
        assert_eq!(
            drawn.unwrap(),
            expected,
            "element {id}: the overlay would draw {drawn:?}, the Inspector reports {expected:?}"
        );
    }
}

#[test]
fn a_hidden_element_without_coordinates_still_answers_geometry() {
    let root = std::env::temp_dir().join(format!("mono-overlay-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&root);
    std::fs::create_dir_all(&root).unwrap();
    let path = root.join("scene.json");
    std::fs::write(
        &path,
        json!({
            "canvas": {"w": 64, "h": 16},
            "states": {},
            "elements": [
                {"id": "zoned", "type": "placeholder", "hidden": true,
                 "zone": {"x": 4, "y": 2, "w": 8, "h": 6}},
                {"id": "bare", "type": "placeholder", "hidden": true}
            ]
        })
        .to_string(),
    )
    .unwrap();
    let doc = load_scene(&path, None).unwrap();
    let mut session = EditorSession::new(doc).unwrap();
    let resolved = session.render().unwrap().resolved_elements;
    assert_eq!(resolved.len(), 2);
    // A hidden element takes its box from its zone.
    let zoned = json!({"zone": {"x": 4, "y": 2, "w": 8, "h": 6}});
    assert_eq!(overlay_rect(&zoned, &resolved, 0), Some((4, 2, 8, 6)));
    // Without a zone the render result carries no rect, so the overlay falls
    // back to geometry — which reports a zero-sized box rather than an error.
    let bare = json!({"hidden": true});
    assert_eq!(overlay_rect(&bare, &resolved, 1), None);
    let geometry = session.geometry("bare").unwrap();
    assert_eq!(
        (geometry.x, geometry.y, geometry.w, geometry.h),
        (0, 0, 0, 0)
    );
    let _ = std::fs::remove_dir_all(&root);
}

#[test]
fn an_incomplete_zone_defers_to_the_element_like_the_inspector() {
    for extra in [
        json!({"zone": {"x": 1}, "x": 30, "y": 9, "w": 40, "h": 11}),
        json!({"zone": {"x": 1}, "x": 30, "y": 9}),
    ] {
        let root =
            Path::new(env!("CARGO_MANIFEST_DIR")).join("../../test_assets/projects/curing_lite");
        let mut doc = load_scene(&root.join("scenes/main_scene.json"), Some(&root)).unwrap();
        let elements = doc
            .data
            .get_mut("elements")
            .unwrap()
            .as_array_mut()
            .unwrap();
        let text = elements.iter_mut().find(|e| e["type"] == "text").unwrap();
        let object = text.as_object_mut().unwrap();
        object.remove("zone");
        for (key, value) in extra.as_object().unwrap() {
            object.insert(key.clone(), value.clone());
        }
        let id = object["id"].as_str().unwrap().to_string();
        let element = text.clone();
        let index = doc.data["elements"]
            .as_array()
            .unwrap()
            .iter()
            .position(|e| e["id"] == json!(id))
            .unwrap();
        let mut session = EditorSession::new(doc).unwrap();
        let resolved = session.render().unwrap().resolved_elements;
        let geometry = session.geometry(&id).unwrap();
        assert_eq!(
            overlay_rect(&element, &resolved, index),
            Some((geometry.x, geometry.y, geometry.w, geometry.h)),
            "{element}"
        );
    }
}

/// Hand-written scenes can hold what the editor never writes. The overlay still
/// has to agree with the Inspector, which decides by key presence, not by value.
#[test]
fn unusual_field_values_follow_the_inspector() {
    for extra in [
        json!({"x": 5, "y": 5, "w": null, "h": null}),
        json!({"x": 5, "y": 5, "w": null}),
        json!({"x": 5, "y": 5, "h": 9}),
        json!({"zone": {"x": 2.5, "y": 1, "w": 20, "h": 9}}),
        json!({"zone": {"x": null, "y": 1, "w": 20, "h": 9}}),
    ] {
        let root =
            Path::new(env!("CARGO_MANIFEST_DIR")).join("../../test_assets/projects/curing_lite");
        let mut doc = load_scene(&root.join("scenes/main_scene.json"), Some(&root)).unwrap();
        let elements = doc
            .data
            .get_mut("elements")
            .unwrap()
            .as_array_mut()
            .unwrap();
        let index = elements.iter().position(|e| e["type"] == "text").unwrap();
        let object = elements[index].as_object_mut().unwrap();
        object.remove("zone");
        for (key, value) in extra.as_object().unwrap() {
            object.insert(key.clone(), value.clone());
        }
        let id = object["id"].as_str().unwrap().to_string();
        let element = elements[index].clone();
        let mut session = EditorSession::new(doc).unwrap();
        // Some of these values fail the render; the overlay then has no resolved
        // rects and falls back to `geometry` itself, as `refresh_canvas` does.
        let resolved = session
            .render()
            .map(|r| r.resolved_elements)
            .unwrap_or_default();
        let Ok(geometry) = session.geometry(&id) else {
            continue;
        };
        let expected = (geometry.x, geometry.y, geometry.w, geometry.h);
        assert_eq!(
            overlay_rect(&element, &resolved, index).unwrap_or(expected),
            expected,
            "{element}"
        );
    }
}
