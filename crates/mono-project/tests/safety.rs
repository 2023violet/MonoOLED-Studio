#![allow(clippy::unwrap_used, clippy::expect_used, clippy::panic)]
//! Rust-only hardening tests from the G1 agent review (no V1 corpus equivalent).

use std::path::{Path, PathBuf};

use mono_core::FrameBuffer;
use mono_core::render::{PATH_ESCAPE, joined_member, member_path, render_scene};
use mono_core::state::{State, eval_do};
use mono_project::editor::EditorSession;
use mono_project::export::validate_scene;
use mono_project::fontpack_io::{fontpack_fingerprint, load_font_pack};
use mono_project::image_io::decode_image;
use mono_project::resources::DiskResources;
use mono_project::scene_io::load_scene;
use serde_json::{Map, Value, json};

fn bmp_header(width: u32, height: u32, bpp: u16) -> Vec<u8> {
    let mut b = vec![0u8; 54];
    b[0] = b'B';
    b[1] = b'M';
    b[10..14].copy_from_slice(&54u32.to_le_bytes());
    b[14..18].copy_from_slice(&40u32.to_le_bytes());
    b[18..22].copy_from_slice(&width.to_le_bytes());
    b[22..26].copy_from_slice(&height.to_le_bytes());
    b[26..28].copy_from_slice(&1u16.to_le_bytes());
    b[28..30].copy_from_slice(&bpp.to_le_bytes());
    b
}

#[test]
fn hostile_bmp_headers_are_refused_without_allocating() {
    let huge = decode_image(&bmp_header(1 << 20, 1 << 20, 24)).unwrap_err();
    assert!(
        huge.message.contains("decompression bomb"),
        "{}",
        huge.message
    );
    let truncated = decode_image(&bmp_header(64, 64, 24)).unwrap_err();
    assert!(
        truncated.message.contains("truncated"),
        "{}",
        truncated.message
    );
    let mut palette = bmp_header(4, 4, 8);
    palette[46..50].copy_from_slice(&u32::MAX.to_le_bytes());
    assert!(decode_image(&palette).is_err());
}

#[test]
fn hostile_png_header_is_refused() {
    // Minimal PNG signature + IHDR claiming 100000 x 100000.
    let mut png = b"\x89PNG\r\n\x1a\n".to_vec();
    let mut ihdr = b"IHDR".to_vec();
    ihdr.extend(100_000u32.to_be_bytes());
    ihdr.extend(100_000u32.to_be_bytes());
    ihdr.extend([8, 6, 0, 0, 0]);
    png.extend(13u32.to_be_bytes());
    png.extend(&ihdr);
    let crc = crc32(&ihdr);
    png.extend(crc.to_be_bytes());
    // An empty IDAT lets the decoder return the header so our pixel cap is what refuses it.
    png.extend(0u32.to_be_bytes());
    png.extend(b"IDAT");
    png.extend(crc32(b"IDAT").to_be_bytes());
    let error = decode_image(&png).unwrap_err();
    assert!(
        error.message.contains("decompression bomb"),
        "{}",
        error.message
    );
}

fn crc32(data: &[u8]) -> u32 {
    let mut crc = 0xFFFF_FFFFu32;
    for byte in data {
        crc ^= u32::from(*byte);
        for _ in 0..8 {
            crc = if crc & 1 != 0 {
                (crc >> 1) ^ 0xEDB8_8320
            } else {
                crc >> 1
            };
        }
    }
    !crc
}

#[test]
fn oversized_framebuffer_is_an_error_not_an_abort() {
    assert!(FrameBuffer::new(1 << 32, 1 << 32).is_err());
    let scene: Map<String, Value> =
        serde_json::from_value(json!({"canvas": {"w": 1i64 << 40, "h": 8}, "elements": []}))
            .unwrap();
    assert!(
        render_scene(
            &scene,
            &PathBuf::from("."),
            &State::new(),
            &mut DiskResources::new()
        )
        .is_err()
    );
}

#[test]
fn validator_reports_out_of_bounds_for_extreme_coordinates() {
    let scene: Map<String, Value> = serde_json::from_value(json!({
        "canvas": {"w": 128, "h": 32},
        "states": {},
        "elements": [{"id": "p", "type": "placeholder", "x": i64::MAX - 1, "y": 0, "w": i64::MAX, "h": 4}]
    }))
    .unwrap();
    let findings = validate_scene(&scene, &PathBuf::from("."), None, &mut DiskResources::new());
    assert!(
        findings.iter().any(|f| f.code == "OUT_OF_BOUNDS"),
        "{findings:?}"
    );
}

#[test]
fn scene_members_cannot_escape_the_project_root() {
    let base = std::env::temp_dir().join(format!("mono-escape-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&base);
    let root = base.join("project");
    std::fs::create_dir_all(&root).unwrap();
    // A decodable 2x2 image declared as 1x1. Reading it would add a size finding,
    // so the absence of one below proves the file was never opened.
    let outside = base.join("outside.bmp");
    let mut bmp = bmp_header(2, 2, 24);
    bmp.extend([0; 16]);
    std::fs::write(&outside, &bmp).unwrap();
    std::fs::write(root.join("inside.bmp"), &bmp).unwrap();
    let inside: Map<String, Value> = serde_json::from_value(json!({
        "canvas": {"w": 8, "h": 8},
        "states": {},
        "elements": [{
            "id": "probe", "type": "image", "asset": "inside.bmp",
            "x": 0, "y": 0, "w": 1, "h": 1
        }]
    }))
    .unwrap();
    let control = validate_scene(&inside, &root, None, &mut DiskResources::new());
    assert!(
        control.iter().any(|f| f.code == "ASSET_SIZE_MISMATCH"),
        "the same file inside the root must decode and mismatch: {control:?}"
    );

    let mut element = json!({
        "id": "probe", "type": "image", "asset": "../outside.bmp",
        "x": 0, "y": 0, "w": 1, "h": 1
    });
    let scene: Map<String, Value> = serde_json::from_value(json!({
        "canvas": {"w": 8, "h": 8},
        "states": {},
        "elements": [element.clone()]
    }))
    .unwrap();
    let findings = validate_scene(&scene, &root, None, &mut DiskResources::new());
    assert!(
        findings
            .iter()
            .any(|f| f.code == "ASSET_PATH_ESCAPE" && f.is_blocking()),
        "{findings:?}"
    );
    assert!(
        !findings
            .iter()
            .any(|f| f.code == "ASSET_SIZE_MISMATCH" || f.code == "NON_BINARY_ASSET"),
        "an escaping asset must not be opened: {findings:?}"
    );
    let error = render_scene(&scene, &root, &State::new(), &mut DiskResources::new()).unwrap_err();
    assert_eq!(error.code, PATH_ESCAPE);

    element["asset"] = json!(outside.to_string_lossy());
    let scene: Map<String, Value> = serde_json::from_value(json!({
        "canvas": {"w": 8, "h": 8},
        "states": {},
        "elements": [element]
    }))
    .unwrap();
    let findings = validate_scene(&scene, &root, None, &mut DiskResources::new());
    assert!(
        findings.iter().any(|f| f.code == "ASSET_PATH_ESCAPE"),
        "{findings:?}"
    );
    let _ = std::fs::remove_dir_all(&base);
}

/// `outside` is a decodable 2x2 image declared as 1x1 by every scene below, so a
/// size finding would mean it was opened.
fn assert_escape_is_refused_unopened(element: Value, root: &Path) {
    let scene: Map<String, Value> = serde_json::from_value(json!({
        "canvas": {"w": 8, "h": 8},
        "states": {"n": {"type": "int", "min": 0, "max": 0, "init": 0}},
        "elements": [element]
    }))
    .unwrap();
    let findings = validate_scene(&scene, root, None, &mut DiskResources::new());
    assert!(
        findings
            .iter()
            .any(|f| f.code == "ASSET_PATH_ESCAPE" && f.is_blocking()),
        "{findings:?}"
    );
    assert!(
        !findings
            .iter()
            .any(|f| f.code == "ASSET_SIZE_MISMATCH" || f.code == "NON_BINARY_ASSET"),
        "an escaping member must not be opened: {findings:?}"
    );
    let state: State = serde_json::from_value(json!({"n": 0})).unwrap();
    let error = render_scene(&scene, root, &state, &mut DiskResources::new());
    assert_eq!(error.unwrap_err().code, PATH_ESCAPE);
}

#[test]
fn sequence_and_digit_members_cannot_escape_the_project_root() {
    let base = std::env::temp_dir().join(format!("mono-pattern-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&base);
    let root = base.join("project");
    std::fs::create_dir_all(root.join("assets")).unwrap();
    std::fs::create_dir_all(base.join("outside")).unwrap();
    let mut bmp = bmp_header(2, 2, 24);
    bmp.extend([0; 16]);
    std::fs::write(base.join("outside.bmp"), &bmp).unwrap();
    for n in 0..10 {
        std::fs::write(base.join("outside").join(format!("d{n}.bmp")), &bmp).unwrap();
    }

    let sequence = |dir: &str, pattern: &str| {
        json!({
            "id": "seq", "type": "image_seq", "dir": dir, "pattern": pattern,
            "bind": "n", "count": 1, "x": 0, "y": 0, "w": 1, "h": 1
        })
    };
    let digits = |dir: &str, pattern: &str| {
        json!({
            "id": "digits", "type": "digits", "dir": dir, "pattern": pattern,
            "digit_w": 1, "digit_h": 1, "bind": "n", "x": 0, "y": 0
        })
    };
    for element in [
        sequence("assets", "../../outside.bmp"),
        sequence("../outside", "d{n}.bmp"),
        digits("assets", "../../outside/d{d}.bmp"),
        digits("../outside", "d{d}.bmp"),
    ] {
        assert_escape_is_refused_unopened(element, &root);
    }
    let _ = std::fs::remove_dir_all(&base);
}

#[test]
fn font_members_cannot_escape_the_project_root() {
    let base = std::env::temp_dir().join(format!("mono-font-escape-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&base);
    let root = base.join("project");
    std::fs::create_dir_all(&root).unwrap();
    for element in [
        json!({"id": "header", "type": "text", "text": "A",
               "font_header": "../outside.h", "x": 0, "y": 0}),
        json!({"id": "pack", "type": "bitmap_text", "text": "A",
               "font_pack": "../outside-pack", "x": 0, "y": 0}),
    ] {
        let scene: Map<String, Value> = serde_json::from_value(json!({
            "canvas": {"w": 8, "h": 8},
            "states": {},
            "elements": [element]
        }))
        .unwrap();
        let findings = validate_scene(&scene, &root, None, &mut DiskResources::new());
        assert!(
            findings
                .iter()
                .any(|f| f.code == "ASSET_PATH_ESCAPE" && f.is_blocking()),
            "{findings:?}"
        );
        let error =
            render_scene(&scene, &root, &State::new(), &mut DiskResources::new()).unwrap_err();
        assert_eq!(error.code, PATH_ESCAPE);
    }
    let _ = std::fs::remove_dir_all(&base);
}

/// The fingerprint runs before the load, so it must apply the same containment:
/// a file outside the pack may not influence it, which means it was not read.
#[test]
fn a_font_pack_fingerprint_never_reads_outside_the_pack() {
    let base = std::env::temp_dir().join(format!("mono-pack-print-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&base);
    let pack = base.join("project").join("pack");
    std::fs::create_dir_all(&pack).unwrap();
    let outside = base.join("outside.bin");
    std::fs::write(&outside, b"one").unwrap();
    std::fs::write(pack.join("inside.bin"), b"one").unwrap();
    std::fs::write(
        pack.join("fontpack.json"),
        json!({
            "schema": 1, "name": "x", "cell": {"w": 5, "h": 8},
            "glyphs": {
                "A": {"asset": "../../outside.bin"},
                "B": {"asset": "inside.bin"}
            }
        })
        .to_string(),
    )
    .unwrap();

    let first = fontpack_fingerprint(&pack).unwrap();
    std::fs::write(&outside, b"two").unwrap();
    assert_eq!(
        fontpack_fingerprint(&pack).unwrap(),
        first,
        "the fingerprint followed a glyph asset outside the pack"
    );
    std::fs::write(pack.join("inside.bin"), b"two").unwrap();
    assert_ne!(fontpack_fingerprint(&pack).unwrap(), first);
    assert!(load_font_pack(&pack).is_err());
    let _ = std::fs::remove_dir_all(&base);
}

#[test]
fn an_unanchored_root_still_contains_its_members() {
    let root = Path::new(".");
    assert_eq!(
        member_path(root, Path::new("assets/a.png")).unwrap(),
        Path::new("assets/a.png")
    );
    for climbing in ["../a.png", "../../a.png", "assets/../../a.png"] {
        assert_eq!(
            member_path(root, Path::new(climbing)).unwrap_err().code,
            PATH_ESCAPE,
            "{climbing}"
        );
    }
    let absolute = std::env::temp_dir().join("a.png");
    assert_eq!(member_path(root, &absolute).unwrap_err().code, PATH_ESCAPE);
}

#[cfg(windows)]
#[test]
fn windows_containment_ignores_case_and_the_verbatim_prefix() {
    let root = Path::new(r"C:\Project\Scene");
    for inside in [
        r"C:\PROJECT\SCENE\a.png",
        r"c:\project\scene\assets\a.png",
        r"\\?\C:\Project\Scene\a.png",
    ] {
        assert!(member_path(root, Path::new(inside)).is_ok(), "{inside}");
    }
    for outside in [
        r"C:\Project\Scene2\a.png",
        r"C:\Project\a.png",
        r"\\?\C:\Project\a.png",
        r"D:\Project\Scene\a.png",
    ] {
        assert_eq!(
            member_path(root, Path::new(outside)).unwrap_err().code,
            PATH_ESCAPE,
            "{outside}"
        );
    }
}

/// NTFS names are not Unicode-folded: `\u{212A}it` (KELVIN SIGN) and `kit` are two
/// directories, though `to_lowercase` makes them equal. A relative member keeps
/// the root's own spelling, so a sibling can never compare as the root.
#[cfg(windows)]
#[test]
fn windows_containment_does_not_fold_unicode_or_relative_members() {
    let root = Path::new(r"C:\ws\kit");
    for outside in [
        "../\u{212A}it/secret.png",
        r"C:\ws\\u{212A}it\secret.png",
        r"C:\ws\KIT\..\\u{212A}it\secret.png",
        "../KIT/a.png",
    ] {
        assert_eq!(
            member_path(root, Path::new(outside)).unwrap_err().code,
            PATH_ESCAPE,
            "{outside}"
        );
    }
}

/// A `dir` and its `pattern` are one relative member: they keep the root's own
/// spelling, so a climb back in through another case is a climb out, as it is for
/// `image`. A folder can be case-sensitive, so `KIT` may be a sibling of `kit`.
#[cfg(windows)]
#[test]
fn windows_sequence_members_are_compared_exactly_like_other_relative_members() {
    let base = std::env::temp_dir().join(format!("mono-seq-case-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&base);
    let root = base.join("kit");
    std::fs::create_dir_all(root.join("assets/sub")).unwrap();
    let mut bmp = bmp_header(2, 2, 24);
    bmp.extend([0; 16]);
    std::fs::write(root.join("assets/sub/0.bmp"), &bmp).unwrap();
    for d in 0..10 {
        std::fs::write(root.join(format!("assets/sub/d{d}.bmp")), &bmp).unwrap();
    }

    assert_escape_is_refused_unopened(
        json!({"id": "seq", "type": "image_seq", "dir": "assets",
               "pattern": "../../KIT/assets/sub/{n}.bmp",
               "bind": "n", "count": 1, "x": 0, "y": 0, "w": 1, "h": 1}),
        &root,
    );
    assert_escape_is_refused_unopened(
        json!({"id": "digits", "type": "digits", "dir": "assets",
               "pattern": "../../KIT/assets/sub/d{d}.bmp",
               "digit_w": 1, "digit_h": 1, "bind": "n", "x": 0, "y": 0}),
        &root,
    );

    // The Inspector's geometry resolves the sequence on its own path. No `w`/`h`
    // here: an explicit rect would answer without touching the member.
    let path = root.join("scene.json");
    std::fs::write(
        &path,
        json!({
            "canvas": {"w": 8, "h": 8},
            "states": {"n": {"type": "int", "min": 0, "max": 0, "init": 0}},
            "elements": [{"id": "seq", "type": "image_seq", "dir": "assets",
                          "pattern": "../../KIT/assets/sub/{n}.bmp",
                          "bind": "n", "count": 1, "x": 0, "y": 0}]
        })
        .to_string(),
    )
    .unwrap();
    let doc = load_scene(&path, Some(&root)).unwrap();
    let mut session = EditorSession::new(doc).unwrap();
    assert_eq!(session.geometry("seq").unwrap_err().code, PATH_ESCAPE);
    let _ = std::fs::remove_dir_all(&base);
}

/// The `dir` is checked on its own: a pattern cannot bring an escaped `dir` back in.
#[test]
fn a_pattern_cannot_rescue_a_dir_outside_the_project() {
    let root = Path::new("/ws/kit");
    assert!(joined_member(root, "assets", "sub/0.png").is_ok());
    assert_eq!(
        joined_member(root, "../other", "../kit/a.png")
            .unwrap_err()
            .code,
        PATH_ESCAPE
    );
}

/// Nothing is joined when there is nothing to draw, so the `dir` has to be refused
/// before the loop: an escape stays visible while the value or count is empty. The
/// validator's own render would report it too, but without the element to jump to.
#[test]
fn an_escaped_dir_is_refused_even_when_no_file_is_joined() {
    let root = Path::new("/ws/kit");
    let scene: Map<String, Value> = serde_json::from_value(json!({
        "canvas": {"w": 8, "h": 8},
        "states": {"n": {"type": "int", "min": 0, "max": 0, "init": 0}},
        "elements": [{"id": "seq", "type": "image_seq", "dir": "../outside",
                      "pattern": "{n}.bmp", "bind": "n", "count": 0, "x": 0, "y": 0}]
    }))
    .unwrap();
    let findings = validate_scene(&scene, root, None, &mut DiskResources::new());
    assert!(
        findings.iter().any(|f| f.code == "ASSET_PATH_ESCAPE"
            && f.is_blocking()
            && f.element_id.as_deref() == Some("seq")),
        "{findings:?}"
    );

    let scene: Map<String, Value> = serde_json::from_value(json!({
        "canvas": {"w": 8, "h": 8},
        "elements": [{"id": "digits", "type": "digits", "dir": "../outside",
                      "pattern": "{d}.bmp", "digit_w": 1, "digit_h": 1,
                      "bind": "n", "x": 0, "y": 0}]
    }))
    .unwrap();
    let state: State = serde_json::from_value(json!({"n": ""})).unwrap();
    let error = render_scene(&scene, root, &state, &mut DiskResources::new());
    assert_eq!(error.unwrap_err().code, PATH_ESCAPE);
}

#[test]
fn timeline_arithmetic_overflow_and_type_errors_are_reported() {
    let mut state: State = serde_json::from_value(json!({"n": i64::MAX, "s": "text"})).unwrap();
    assert!(eval_do("n += 1", &mut state).is_err());
    let error = eval_do("s += 1", &mut state).unwrap_err();
    assert_eq!(error.code, "E-CORE-TYPE");
}

#[test]
fn empty_text_zone_falls_back_to_element_position() {
    let root =
        PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../fixtures/golden/inputs/synthetic");
    let scene: Map<String, Value> = serde_json::from_value(json!({
        "canvas": {"w": 64, "h": 16},
        "elements": [{"id": "t", "type": "text", "text": "AB", "font_header": "assets/mode_font_5x7.h", "zone": {}, "x": 3, "y": 2}]
    }))
    .unwrap();
    let result = render_scene(&scene, &root, &State::new(), &mut DiskResources::new()).unwrap();
    assert_eq!(result.resolved_elements[0]["x"], 3);
}

#[cfg(windows)]
#[test]
fn export_prune_does_not_delete_through_junctions() {
    use std::process::Command;
    let base = std::env::temp_dir().join(format!("mono-prune-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&base);
    let outside = base.join("outside");
    std::fs::create_dir_all(&outside).unwrap();
    std::fs::write(outside.join("victim.bin"), b"keep").unwrap();
    let out = base.join("export");
    std::fs::create_dir_all(out.join("golden")).unwrap();
    let link = out.join("golden").join("link");
    let made = Command::new("cmd")
        .args(["/c", "mklink", "/J"])
        .arg(&link)
        .arg(&outside)
        .status()
        .unwrap();
    if !made.success() {
        return;
    }
    let scene: Map<String, Value> =
        serde_json::from_value(json!({"canvas": {"w": 8, "h": 8}, "states": {}, "elements": []}))
            .unwrap();
    mono_project::export::export_scene(
        &scene,
        &base,
        &out,
        &[("case_0000".into(), State::new())],
        &mut |_, _, _| true,
    )
    .unwrap();
    assert!(
        outside.join("victim.bin").exists(),
        "prune followed a junction"
    );
    let _ = std::fs::remove_dir_all(&base);
}
