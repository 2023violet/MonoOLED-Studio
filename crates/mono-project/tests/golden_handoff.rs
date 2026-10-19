#![allow(clippy::unwrap_used, clippy::expect_used, clippy::panic)]

mod common;

use std::io::Read;
use std::path::{Path, PathBuf};

use common::{Report, cases};
use mono_core::render::posix;
use mono_core::state::{IntegerPolicy, build_export_states};
use mono_project::export::build_handoff_package;
use mono_project::image_io::decode_png;
use mono_project::project::py_resolve;
use mono_project::resources::hex_digest;
use serde_json::{Map, Value, json};

fn repo() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("../..")
        .canonicalize()
        .unwrap()
}

fn replace_root(text: &str, root: &Path) -> String {
    let root = py_resolve(root);
    text.replace(&posix(&root), "${PROJECT_ROOT}")
        .replace(&root.display().to_string(), "${PROJECT_ROOT}")
}

/// Handoff files V1 writes in platform text mode (documented G1 deviation: Rust always writes LF).
const V1_PLATFORM_NEWLINE: [&str; 3] = ["HANDOFF_README.md", "design_rules.md", "asset_health.md"];

#[test]
fn handoff_zip_entries_match_v1() {
    let repo = repo();
    let mut report = Report::default();
    for case in cases("handoff") {
        let id = case["id"].as_str().unwrap();
        let input = &case["input"];
        let scene_rel = input["scene"].as_str().unwrap();
        // The corpus input path is the V1 location; the frozen copy is used for builtin scenes.
        let (scene_path, root) = if scene_rel.starts_with("src/scenes/") {
            let base = repo.join("fixtures/golden/inputs/builtin");
            (base.join(scene_rel), base)
        } else {
            (
                repo.join(scene_rel),
                repo.join("test_assets/projects/curing_lite"),
            )
        };
        let root = py_resolve(&root);
        let scene: Map<String, Value> =
            serde_json::from_slice(&std::fs::read(&scene_path).unwrap()).unwrap();
        let wanted: Vec<String> = input["states"]
            .as_array()
            .unwrap()
            .iter()
            .map(|v| v.as_str().unwrap().to_string())
            .collect();
        let states: Vec<_> =
            build_export_states(&scene, IntegerPolicy::Representative, 5000, false)
                .unwrap()
                .into_iter()
                .filter(|(name, _)| wanted.contains(name))
                .collect();
        let policy = IntegerPolicy::parse(input["integer_policy"].as_str().unwrap()).unwrap();
        let target = std::env::temp_dir().join(format!(
            "mono-golden-handoff-{}-{id}.zip",
            std::process::id()
        ));
        build_handoff_package(&scene, &root, &target, &states, policy, &mut |_, _, _| true)
            .unwrap();
        let mut archive = zip::ZipArchive::new(std::fs::File::open(&target).unwrap()).unwrap();
        let mut got = Vec::new();
        let mut names: Vec<String> = archive
            .file_names()
            .map(|n| n.unwrap().into_owned())
            .collect();
        names.sort();
        for name in &names {
            let mut data = Vec::new();
            archive
                .by_name(name)
                .unwrap()
                .read_to_end(&mut data)
                .unwrap();
            got.push((name.clone(), data));
        }
        let expected = case["expected"]["entries"].as_array().unwrap();
        let expected_names: Vec<&str> = expected
            .iter()
            .map(|e| e["name"].as_str().unwrap())
            .collect();
        report.check(
            &format!("{id}:names"),
            expected_names == names.iter().map(String::as_str).collect::<Vec<_>>(),
            || format!("got {names:?}"),
        );
        for want in expected {
            let name = want["name"].as_str().unwrap();
            let Some((_, data)) = got.iter().find(|(n, _)| n == name) else {
                continue;
            };
            let ok = match want["kind"].as_str().unwrap() {
                "png" if name == "thumbnail_wall.png" => {
                    // Labels use V1's Pillow default font; only the canvas size is a contract.
                    let image = decode_png(data).unwrap();
                    want["size"] == json!([image.width, image.height])
                }
                "png" => {
                    let image = decode_png(data).unwrap();
                    let luma: Vec<u8> = image.rgba.chunks(4).map(|p| p[0]).collect();
                    want["size"] == json!([image.width, image.height])
                        && want["pixels_l_sha256"] == hex_digest(&luma)
                }
                "text" if V1_PLATFORM_NEWLINE.contains(&name) => {
                    // V1 writes these with Path.write_text, i.e. CRLF on Windows and LF elsewhere;
                    // Rust writes LF on every platform. Compare with V1's Windows bytes.
                    let text = replace_root(&String::from_utf8(data.clone()).unwrap(), &root)
                        .replace('\n', "\r\n");
                    want["sha256"] == hex_digest(text.as_bytes())
                }
                "text" => {
                    let text = replace_root(&String::from_utf8(data.clone()).unwrap(), &root);
                    want["sha256"] == hex_digest(text.as_bytes())
                }
                _ => want["sha256"] == hex_digest(data),
            };
            report.check(&format!("{id}:{name}"), ok, || {
                String::from_utf8(data.clone())
                    .map(|t| t.chars().take(1500).collect())
                    .unwrap_or_else(|_| "<binary>".into())
            });
        }
    }
    let expected: usize = cases("handoff")
        .iter()
        .map(|c| c["expected"]["entries"].as_array().map_or(0, Vec::len) + 1)
        .sum();
    report.finish_exact("handoff", expected);
}
