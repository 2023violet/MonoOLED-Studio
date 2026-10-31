#![allow(clippy::unwrap_used, clippy::expect_used, clippy::panic)]
//! One element yields one diagnostic per distinct problem. `validate_scene`
//! checks declared geometry and rendered geometry separately; a box reported by
//! both passes must not surface twice.

use std::path::PathBuf;

use mono_project::export::validate_scene;
use mono_project::resources::DiskResources;
use serde_json::{Map, Value, json};

fn scene(value: Value) -> Map<String, Value> {
    serde_json::from_value(value).unwrap()
}

#[test]
fn out_of_bounds_placeholder_is_reported_once() {
    let root = PathBuf::from(".");
    let scene = scene(json!({
        "canvas": {"w": 128, "h": 32},
        "states": {},
        "elements": [{"id": "p", "type": "placeholder", "x": 126, "y": 0, "w": 4, "h": 4}]
    }));
    let findings = validate_scene(&scene, &root, None, &mut DiskResources::new());
    let bounds: Vec<_> = findings
        .iter()
        .filter(|f| f.code == "OUT_OF_BOUNDS")
        .collect();
    assert_eq!(bounds.len(), 1, "{findings:?}");
    assert_eq!(bounds[0].element_id.as_deref(), Some("p"));
}

#[test]
fn measured_text_keeps_its_distinct_diagnostic() {
    let root =
        PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../fixtures/golden/inputs/synthetic");
    // Declared width is 1px (text elements declare a single cell column), while
    // the rendered run is 11px wide: both overflow, with different messages.
    let scene = scene(json!({
        "canvas": {"w": 64, "h": 16},
        "states": {},
        "elements": [{
            "id": "t",
            "type": "text",
            "text": "AB",
            "font_header": "assets/mode_font_5x7.h",
            "x": 64,
            "y": 0
        }]
    }));
    let findings = validate_scene(&scene, &root, None, &mut DiskResources::new());
    let bounds: Vec<_> = findings
        .iter()
        .filter(|f| f.code == "OUT_OF_BOUNDS")
        .collect();
    assert_eq!(bounds.len(), 2, "{findings:?}");
    assert_ne!(bounds[0].message, bounds[1].message);
    assert!(bounds.iter().all(|f| f.element_id.as_deref() == Some("t")));
}
