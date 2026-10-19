#![allow(clippy::unwrap_used, clippy::expect_used, clippy::panic)]

mod common;

use common::{Report, cases, hex, row_strings, rows};
use mono_core::c_header::framebuffer_to_c_header;
use mono_core::formatter::{OutputItem, format_output};
use mono_core::profiles::TextFormatProfile;
use mono_core::{EncodingProfile, FrameBuffer, MonoBitmap, encode_bitmap};
use serde_json::{Value, json};

fn profile(value: &Value) -> EncodingProfile {
    serde_json::from_value(value.clone()).expect("encoding profile")
}

#[test]
fn encoding_and_framebuffer_cases_match_v1() {
    let mut report = Report::default();
    for case in cases("encoding") {
        let id = case["id"].as_str().unwrap();
        let input = &case["input"];
        let expected = &case["expected"];
        match case["kind"].as_str().unwrap() {
            "encoding" => {
                let bitmap = MonoBitmap::from_rows(rows(&input["rows"])).unwrap();
                let encoded = encode_bitmap(&bitmap, &profile(&input["profile"]));
                let trace: Vec<Value> = expected["trace"]
                    .as_array()
                    .unwrap()
                    .iter()
                    .map(|sample| {
                        let step = encoded.trace_step(&bitmap, sample["index"].as_u64().unwrap() as usize).unwrap();
                        json!({
                            "index": step.index,
                            "value": step.value,
                            "coordinates": step.coordinates.iter().map(|c| c.map(|(x, y)| json!([x, y])).unwrap_or(Value::Null)).collect::<Vec<_>>(),
                            "source_bits": step.source_bits.to_vec(),
                        })
                    })
                    .collect();
                let ok = hex(&encoded.data) == expected["hex"]
                    && json!([encoded.padded_size.0, encoded.padded_size.1])
                        == expected["padded_size"]
                    && Value::Array(trace) == expected["trace"];
                report.check(id, ok, || format!("got {}", hex(&encoded.data)));
            }
            "framebuffer" => {
                let width = input["width"].as_u64().unwrap() as usize;
                let height = input["height"].as_u64().unwrap() as usize;
                let mut fb = FrameBuffer::new(width, height).unwrap();
                for pixel in input["set_pixels"].as_array().unwrap() {
                    fb.set_pixel(pixel[0].as_i64().unwrap(), pixel[1].as_i64().unwrap(), true)
                        .unwrap();
                }
                for mask in input["masks"].as_array().unwrap() {
                    fb.or_mask(
                        &rows(&mask["rows"]),
                        mask["origin"][0].as_i64().unwrap(),
                        mask["origin"][1].as_i64().unwrap(),
                    );
                }
                let ok = match fb.to_vlsb() {
                    Ok(data) => {
                        hex(&data) == expected["hex"]
                            && json!(row_strings(fb.rows())) == expected["rows"]
                    }
                    Err(error) => {
                        expected["error"] == "ValueError"
                            && json!(error.message) == expected["message"]
                    }
                };
                report.check(id, ok, || "framebuffer mismatch".into());
            }
            other => panic!("unknown kind {other}"),
        }
    }
    report.finish("encoding");
}

#[test]
fn formatting_and_legacy_header_cases_match_v1() {
    let mut report = Report::default();
    for case in cases("formatting") {
        let id = case["id"].as_str().unwrap();
        let input = &case["input"];
        let expected = &case["expected"];
        if case["kind"] == "legacy_c_header" {
            let width = input["width"].as_u64().unwrap() as usize;
            let height = input["height"].as_u64().unwrap() as usize;
            let mut fb = FrameBuffer::new(width, height).unwrap();
            for (y, row) in rows(&input["rows"]).iter().enumerate() {
                for (x, v) in row.iter().enumerate() {
                    if *v != 0 {
                        fb.set_pixel(x as i64, y as i64, true).unwrap();
                    }
                }
            }
            let text = framebuffer_to_c_header(&fb, input["name"].as_str().unwrap()).unwrap();
            report.check(id, json!(text) == expected["text"]["text"], || {
                format!("got {text:?}")
            });
            continue;
        }
        let Some(items_spec) = input["items"].as_array() else {
            continue;
        };
        if items_spec.iter().any(|item| item.get("rows").is_none()) {
            // Large preview cases store a pattern reference instead of rows.
            let items: Vec<OutputItem> = items_spec
                .iter()
                .map(|item| {
                    let bitmap = pattern(256, 128);
                    OutputItem::bitmap(
                        item["name"].as_str().unwrap(),
                        encode_bitmap(&bitmap, &profile(&input["encoding"])),
                    )
                })
                .collect();
            check_format(&mut report, id, &items, input, expected);
            continue;
        }
        let items: Vec<OutputItem> = items_spec
            .iter()
            .map(|item| {
                let bitmap = MonoBitmap::from_rows(rows(&item["rows"])).unwrap();
                OutputItem {
                    name: item["name"].as_str().unwrap().to_string(),
                    encoded: encode_bitmap(&bitmap, &profile(&input["encoding"])),
                    codepoint: item
                        .get("codepoint")
                        .and_then(Value::as_u64)
                        .map(|v| v as u32),
                    width: item
                        .get("width")
                        .and_then(Value::as_u64)
                        .map(|v| v as usize),
                    height: item
                        .get("height")
                        .and_then(Value::as_u64)
                        .map(|v| v as usize),
                    bearing_x: item.get("bearing_x").and_then(Value::as_i64).unwrap_or(0) as i32,
                    bearing_y: item.get("bearing_y").and_then(Value::as_i64).unwrap_or(0) as i32,
                    advance: item.get("advance").and_then(Value::as_i64).unwrap_or(0) as i32,
                }
            })
            .collect();
        check_format(&mut report, id, &items, input, expected);
    }
    report.finish("formatting");
}

fn pattern(width: usize, height: usize) -> MonoBitmap {
    MonoBitmap::from_rows((0..height).map(|y| {
        (0..width)
            .map(move |x| u8::from((x * 7 + y * 13 + x * y) % 5 < 2))
            .collect::<Vec<_>>()
    }))
    .unwrap()
}

fn text_matches(got: &str, expected: &Value) -> bool {
    let mut ok =
        expected["sha256"] == sha256_hex(got.as_bytes()) && expected["byte_count"] == got.len();
    if let Some(text) = expected.get("text") {
        ok &= text == got;
    }
    ok
}

fn check_format(
    report: &mut Report,
    id: &str,
    items: &[OutputItem],
    input: &Value,
    expected: &Value,
) {
    let text_profile: TextFormatProfile =
        serde_json::from_value(input["text"].clone()).expect("text profile");
    let limit = input["preview_limit"].as_u64().unwrap() as usize;
    let result = format_output(
        items,
        &text_profile,
        input["symbol"].as_str().unwrap(),
        limit,
    )
    .unwrap();
    let index: Vec<Value> = result
        .index
        .iter()
        .map(|e| serde_json::to_value(e).unwrap())
        .collect();
    let ok = hex(&result.data) == expected["data"]["hex"]
        && text_matches(&result.text, &expected["text"])
        && text_matches(&result.preview_text, &expected["preview_text"])
        && json!(result.preview_truncated) == expected["preview_truncated"]
        && Value::Array(index) == expected["index"]
        && text_matches(&result.sidecar_text, &expected["sidecar_text"]);
    report.check(id, ok, || {
        format!(
            "text={:?}",
            result.text.chars().take(200).collect::<String>()
        )
    });
}

fn sha256_hex(data: &[u8]) -> String {
    use sha2::{Digest, Sha256};
    hex(&Sha256::digest(data))
}
