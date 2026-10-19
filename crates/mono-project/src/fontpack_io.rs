//! Font Pack persistence: `fontpack.json` plus one 1-bit PNG per glyph (V1 `FontPack.save/load`).

use std::path::Path;

use mono_core::font::{FontPack, GlyphMetrics};
use mono_core::render::posix;
use mono_core::{CoreError, CoreResult};
use serde_json::{Map, Value, json};

use crate::atomic::{atomic_write, atomic_write_json};
use crate::image_io::{decode_image, encode_bitmap_png};
use crate::resources::{hex_digest, read_file};

pub const MANIFEST: &str = "fontpack.json";

fn glyph_file(ch: char) -> String {
    format!("U+{:04X}.png", ch as u32)
}

/// Content fingerprint of the manifest and every referenced glyph file.
pub fn fontpack_fingerprint(root: &Path) -> CoreResult<String> {
    let manifest = read_file(&root.join(MANIFEST))?;
    let mut combined = hex_digest(&manifest);
    if let Ok(Value::Object(data)) = serde_json::from_slice::<Value>(&manifest) {
        if let Some(Value::Object(glyphs)) = data.get("glyphs") {
            for meta in glyphs.values() {
                if let Some(asset) = meta.get("asset").and_then(Value::as_str) {
                    if let Ok(bytes) = std::fs::read(root.join(asset)) {
                        combined.push_str(&hex_digest(&bytes));
                    }
                }
            }
        }
    }
    Ok(hex_digest(combined.as_bytes()))
}

/// V1 `int(meta.get(key, default))`: Python int() semantics, errors are reported.
fn int(value: Option<&Value>, default: i64) -> CoreResult<i64> {
    match value {
        None => Ok(default),
        Some(v) => mono_core::pyvalue::py_int(v)
            .filter(|n| n.unsigned_abs() <= i64::from(i32::MAX) as u64)
            .ok_or_else(|| {
                CoreError::invalid(format!(
                    "invalid literal for int() with base 10: {}",
                    mono_core::pyvalue::py_repr(v)
                ))
            }),
    }
}

/// V1 `FontPack.load`.
pub fn load_font_pack(root: &Path) -> CoreResult<FontPack> {
    let raw = read_file(&root.join(MANIFEST))?;
    let data: Map<String, Value> = serde_json::from_slice(&raw)
        .map_err(|e| CoreError::invalid(format!("{}: {e}", posix(&root.join(MANIFEST)))))?;
    let schema = int(data.get("schema"), 1)?;
    if schema != 1 {
        return Err(CoreError::invalid(format!(
            "unsupported font pack schema: {}",
            data.get("schema")
                .map(mono_core::pyvalue::py_str)
                .unwrap_or_default()
        )));
    }
    let cell = data
        .get("cell")
        .ok_or_else(|| CoreError::new("E-CORE-KEY", "'cell'"))?;
    let (w, h) = (int(cell.get("w"), 0)?, int(cell.get("h"), 0)?);
    let name = data
        .get("name")
        .map(mono_core::pyvalue::py_str)
        .ok_or_else(|| CoreError::new("E-CORE-KEY", "'name'"))?;
    let mut pack = FontPack::new(
        name,
        (w, h),
        int(data.get("baseline"), h - 1)?,
        int(data.get("advance"), w)?,
    )?;
    if let Some(Value::Object(glyphs)) = data.get("glyphs") {
        for (key, meta) in glyphs {
            let mut chars = key.chars();
            let (Some(ch), None) = (chars.next(), chars.next()) else {
                return Err(CoreError::invalid(
                    "glyph key must be one Unicode character",
                ));
            };
            let asset_rel = meta
                .get("asset")
                .and_then(Value::as_str)
                .unwrap_or_default();
            // Resolve links like V1 `.resolve().relative_to(root)`.
            let asset = crate::project::py_resolve(&root.join(asset_rel));
            if !asset.starts_with(crate::project::py_resolve(root)) {
                return Err(CoreError::invalid("glyph asset must stay inside font pack"));
            }
            if !asset.is_file() {
                return Err(CoreError::invalid(format!(
                    "missing glyph asset: {asset_rel}"
                )));
            }
            let image = decode_image(&read_file(&asset)?)?;
            // Pillow `convert('1')`; glyph PNGs are already bilevel, so a 128 luma cut is exact.
            let rows = image
                .rgba
                .chunks(image.width * 4)
                .map(|row| {
                    row.chunks(4)
                        .map(|p| {
                            let luma = (u32::from(p[0]) * 299
                                + u32::from(p[1]) * 587
                                + u32::from(p[2]) * 114)
                                / 1000;
                            u8::from(luma >= 128)
                        })
                        .collect()
                })
                .collect();
            let metrics = GlyphMetrics {
                bearing_x: int(meta.get("bearing_x"), 0)? as i32,
                bearing_y: int(meta.get("bearing_y"), 0)? as i32,
                advance: int(meta.get("advance"), i64::from(pack.advance))? as i32,
            };
            pack.set_glyph(ch, rows, Some(metrics))?;
        }
    }
    Ok(pack)
}

/// V1 `FontPack.manifest` dictionary, in V1 key order.
pub fn manifest_value(pack: &FontPack) -> Value {
    let mut glyphs = Map::new();
    for glyph in pack.glyphs() {
        glyphs.insert(
            glyph.ch.to_string(),
            json!({
                "asset": format!("glyphs/{}", glyph_file(glyph.ch)),
                "bearing_x": glyph.metrics.bearing_x,
                "bearing_y": glyph.metrics.bearing_y,
                "advance": glyph.metrics.advance,
            }),
        );
    }
    json!({
        "schema": 1,
        "name": pack.name,
        "cell": {"w": pack.cell.0, "h": pack.cell.1},
        "baseline": pack.baseline,
        "advance": pack.advance,
        "glyphs": glyphs,
    })
}

/// V1 `FontPack.save`: rewrites changed glyph PNGs (all when `changed` is `None`),
/// removes stale glyph files, then commits the manifest once.
pub fn save_font_pack(root: &Path, pack: &FontPack, changed: Option<&[char]>) -> CoreResult<()> {
    let glyph_dir = root.join("glyphs");
    std::fs::create_dir_all(&glyph_dir).map_err(|e| crate::resources::io_error(&glyph_dir, &e))?;
    let expected: Vec<String> = pack.characters().map(glyph_file).collect();
    if let Ok(entries) = std::fs::read_dir(&glyph_dir) {
        for entry in entries.flatten() {
            let name = entry.file_name().to_string_lossy().into_owned();
            if name.starts_with("U+") && name.ends_with(".png") && !expected.contains(&name) {
                let _ = std::fs::remove_file(entry.path());
            }
        }
    }
    for glyph in pack.glyphs() {
        let asset = glyph_dir.join(glyph_file(glyph.ch));
        let rewrite = changed.is_none_or(|list| list.contains(&glyph.ch)) || !asset.is_file();
        if rewrite {
            atomic_write(
                &asset,
                &encode_bitmap_png(pack.cell.0, pack.cell.1, &glyph.rows)?,
            )?;
        }
    }
    atomic_write_json(&root.join(MANIFEST), &manifest_value(pack))
}
