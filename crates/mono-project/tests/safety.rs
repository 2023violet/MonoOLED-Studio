#![allow(clippy::unwrap_used, clippy::expect_used, clippy::panic)]
//! Rust-only hardening tests from the G1 agent review (no V1 corpus equivalent).

use std::path::PathBuf;

use mono_core::FrameBuffer;
use mono_core::render::render_scene;
use mono_core::state::{State, eval_do};
use mono_project::export::validate_scene;
use mono_project::image_io::decode_image;
use mono_project::resources::DiskResources;
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
