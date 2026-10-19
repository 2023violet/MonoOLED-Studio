#![allow(clippy::unwrap_used, clippy::expect_used, clippy::panic)]

mod common;

use sha2::{Digest, Sha256};

/// The corpus files must be byte-identical to what the manifest pins, and every
/// category must still hold the recorded number of cases.
#[test]
fn corpus_manifest_is_intact() {
    let dir = common::golden_dir();
    let manifest: serde_json::Value =
        serde_json::from_slice(&std::fs::read(dir.join("manifest.json")).unwrap()).unwrap();
    let categories = manifest["categories"].as_object().unwrap();
    assert!(
        categories.len() >= 8,
        "manifest lists {} categories",
        categories.len()
    );
    for (name, entry) in categories {
        let bytes = std::fs::read(dir.join(entry["file"].as_str().unwrap())).unwrap();
        let digest: String = Sha256::digest(&bytes)
            .iter()
            .map(|b| format!("{b:02x}"))
            .collect();
        assert_eq!(
            entry["sha256"], digest,
            "{name}: file bytes differ from manifest"
        );
        assert_eq!(
            entry["case_count"],
            common::cases(name).len(),
            "{name}: case count differs from manifest"
        );
    }
}
