use mono_core::export::legacy_pixel_c_export;
use mono_core::font::{FontPack, GlyphMetrics, builtin_glyph_rows};
use mono_core::{
    BitAxis, BitOrder, EncodingProfile, FrameBuffer, GroupOrder, MonoBitmap, Polarity,
};
use serde_json::{Value, json};
use sha2::{Digest, Sha256};
use std::env;
use std::fs;
use std::path::PathBuf;

fn rows(value: &Value) -> Result<Vec<Vec<u8>>, String> {
    value
        .as_array()
        .ok_or_else(|| "rows must be an array".to_owned())?
        .iter()
        .map(|row| {
            row.as_str()
                .ok_or_else(|| "row must be a string".to_owned())
                .map(|text| {
                    text.bytes()
                        .map(|bit| match bit {
                            b'0' => Ok(0),
                            b'1' => Ok(1),
                            _ => Err("row contains a non-binary character".into()),
                        })
                        .collect::<Result<Vec<_>, _>>()
                })?
        })
        .collect()
}

fn bytes_result(data: &[u8]) -> Value {
    let hex = data
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect::<String>();
    let sha = format!("{:x}", Sha256::digest(data));
    json!({"hex": hex, "byte_count": data.len(), "sha256": sha})
}

fn profile(value: &Value) -> Result<EncodingProfile, String> {
    let text = |name: &str| {
        value
            .get(name)
            .and_then(Value::as_str)
            .ok_or_else(|| format!("missing profile field {name}"))
    };
    Ok(EncodingProfile {
        bit_axis: match text("bit_axis")? {
            "horizontal" => BitAxis::Horizontal,
            "vertical" => BitAxis::Vertical,
            other => return Err(format!("unknown bit_axis {other}")),
        },
        group_order: match text("group_order")? {
            "row_major" => GroupOrder::RowMajor,
            "column_major" => GroupOrder::ColumnMajor,
            other => return Err(format!("unknown group_order {other}")),
        },
        bit_order: match text("bit_order")? {
            "msb_first" => BitOrder::MsbFirst,
            "lsb_first" => BitOrder::LsbFirst,
            other => return Err(format!("unknown bit_order {other}")),
        },
        polarity: match text("polarity")? {
            "one_is_lit" => Polarity::OneIsLit,
            "zero_is_lit" => Polarity::ZeroIsLit,
            other => return Err(format!("unknown polarity {other}")),
        },
    })
}

fn actual(case: &Value) -> Result<Value, String> {
    let kind = case
        .get("kind")
        .and_then(Value::as_str)
        .ok_or("missing case kind")?;
    let input = case.get("input").ok_or("missing case input")?;
    match kind {
        "encoding" => {
            let bitmap = MonoBitmap::from_rows(rows(input.get("rows").ok_or("missing rows")?)?)?;
            let output = mono_core::bitmap::encode_bitmap(
                &bitmap,
                profile(input.get("profile").ok_or("missing profile")?)?,
            );
            let mut value = bytes_result(&output.data);
            value["padded_size"] = json!([output.padded_size.0, output.padded_size.1]);
            Ok(value)
        }
        "framebuffer" => {
            let width = input
                .get("width")
                .and_then(Value::as_u64)
                .ok_or("missing width")? as usize;
            let height = input
                .get("height")
                .and_then(Value::as_u64)
                .ok_or("missing height")? as usize;
            let mut framebuffer = FrameBuffer::new(width, height)?;
            for point in input
                .get("set_pixels")
                .and_then(Value::as_array)
                .ok_or("missing set_pixels")?
            {
                let pair = point.as_array().ok_or("pixel must be array")?;
                framebuffer.set_pixel(
                    pair[0].as_u64().ok_or("pixel x")? as usize,
                    pair[1].as_u64().ok_or("pixel y")? as usize,
                    true,
                )?;
            }
            for mask in input
                .get("masks")
                .and_then(Value::as_array)
                .ok_or("missing masks")?
            {
                let origin = mask
                    .get("origin")
                    .and_then(Value::as_array)
                    .ok_or("mask origin")?;
                framebuffer.or_mask(
                    &rows(mask.get("rows").ok_or("mask rows")?)?,
                    origin[0].as_u64().ok_or("mask x")? as usize,
                    origin[1].as_u64().ok_or("mask y")? as usize,
                );
            }
            let bytes = framebuffer.to_vlsb()?;
            let mut value = bytes_result(&bytes);
            value["rows"] = json!(framebuffer.row_strings());
            Ok(value)
        }
        "font" => {
            let cell = input
                .get("cell")
                .and_then(Value::as_array)
                .ok_or("font cell")?;
            let cell = (
                cell[0].as_u64().ok_or("font cell width")? as usize,
                cell[1].as_u64().ok_or("font cell height")? as usize,
            );
            let baseline = input
                .get("baseline")
                .and_then(Value::as_u64)
                .ok_or("font baseline")? as usize;
            let advance = input
                .get("advance")
                .and_then(Value::as_i64)
                .ok_or("font advance")? as i32;
            let mut pack = FontPack::new(cell, baseline, advance)?;
            let characters = input
                .get("characters")
                .and_then(Value::as_str)
                .ok_or("font characters")?;
            let mut glyphs = serde_json::Map::new();
            for ch in characters.chars() {
                let glyph_rows = builtin_glyph_rows(ch, cell, baseline)?;
                pack.set_glyph(
                    ch,
                    glyph_rows.clone(),
                    GlyphMetrics {
                        bearing_x: 0,
                        bearing_y: 0,
                        advance,
                    },
                )?;
                glyphs.insert(ch.to_string(), json!({"rows": row_strings(&glyph_rows), "metrics": {"bearing_x": 0, "bearing_y": 0, "advance": advance}}));
            }
            let composed = pack.compose_text(
                input
                    .get("text")
                    .and_then(Value::as_str)
                    .ok_or("font text")?,
                input
                    .get("tracking")
                    .and_then(Value::as_i64)
                    .ok_or("font tracking")? as i32,
            )?;
            Ok(
                json!({"cell": [cell.0, cell.1], "baseline": baseline, "advance": advance, "glyphs": glyphs, "composed_rows": row_strings(&composed)}),
            )
        }
        "project" => {
            let manifest = input.get("manifest").cloned().ok_or("project manifest")?;
            let default_profile = json!({
                "name": "SSD1306 VLSB · C Header",
                "raster": {"alignment":"glyph_width","threshold_mode":"luma","luma_threshold":128,"red_threshold":255,"green_threshold":255,"blue_threshold":255,"invert_source":false,"antialias_scale":1,"offset_x":0,"offset_y":0},
                "encoding": {"bit_axis":"vertical","group_order":"row_major","bit_order":"lsb_first","polarity":"one_is_lit"},
                "text": {"container":"text","radix":"hex","uppercase":true,"bytes_per_line":16,"index_entries_per_line":16,"index_mode":"none","minimal_data":false,"compact_spacing":false,"segment_prefix":"#pragma once\n#include <stdint.h>\n\nstatic const uint8_t ${symbol}[] = {\n","segment_suffix":"};\n","comment_prefix":"    /* ","comment_suffix":" */\n","data_prefix":"0x","data_suffix":",","line_prefix":"    ","line_suffix":"","line_end":"\n"}
            });
            Ok(
                json!({"read_preserved_bytes": true, "saved_manifest": manifest, "active_profile":"ssd1306_vlsb_c","profile": default_profile}),
            )
        }
        "export" => {
            let bitmap = MonoBitmap::from_rows(rows(input.get("rows").ok_or("export rows")?)?)?;
            let (data, text) = legacy_pixel_c_export(
                &bitmap,
                input
                    .get("symbol")
                    .and_then(Value::as_str)
                    .ok_or("export symbol")?,
            )?;
            Ok(
                json!({"hex": data.iter().map(|byte| format!("{byte:02x}")).collect::<String>(), "byte_count": data.len(), "sha256": format!("{:x}", Sha256::digest(&data)), "text": text, "index": []}),
            )
        }
        other => Err(format!("unsupported fixture kind {other}")),
    }
}

fn row_strings(rows: &[Vec<u8>]) -> Vec<String> {
    rows.iter()
        .map(|row| row.iter().map(|value| char::from(b'0' + *value)).collect())
        .collect()
}

fn main() -> Result<(), String> {
    let mut args = env::args().skip(1);
    let fixture = args
        .next()
        .map(PathBuf::from)
        .unwrap_or_else(|| PathBuf::from("test_assets/rust_v2/goldens.json"));
    let document: Value =
        serde_json::from_slice(&fs::read(&fixture).map_err(|error| error.to_string())?)
            .map_err(|error| error.to_string())?;
    let cases = document
        .get("cases")
        .and_then(Value::as_array)
        .ok_or("fixture cases missing")?;
    let mut failures = 0usize;
    for case in cases {
        let id = case
            .get("id")
            .and_then(Value::as_str)
            .unwrap_or("<unknown>");
        let actual = actual(case)?;
        if actual != *case.get("expected").ok_or("fixture expected missing")? {
            println!("MISMATCH {id}");
            println!("actual={actual}");
            failures += 1;
        } else {
            println!(
                "OK {id} sha256={}",
                actual
                    .get("sha256")
                    .and_then(Value::as_str)
                    .unwrap_or("semantic")
            );
        }
    }
    if failures != 0 {
        return Err(format!("{failures} fixture(s) mismatched"));
    }
    println!("All Rust Core fixtures matched.");
    Ok(())
}
