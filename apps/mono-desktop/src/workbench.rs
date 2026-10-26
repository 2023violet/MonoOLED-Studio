//! Output workbench (V1 `output_workbench_qt.OutputWorkbench`): pick a 1-bit
//! source, edit the output profile, generate the firmware array.
//!
//! The profile is edited as its V1 JSON form and re-validated through
//! `OutputProfile::from_json` after every change, so the UI can never hold a
//! profile the formatter would reject; a rejected edit leaves the last valid
//! profile in place.

use mono_core::bitmap::MonoBitmap;
use mono_core::encoding::encode_bitmap;
use mono_core::font::FontPack;
use mono_core::formatter::{DEFAULT_PREVIEW_LIMIT, FormattedOutput, OutputItem, format_output};
use mono_core::profiles::{OutputProfile, builtin_profiles};
use mono_core::{CoreError, CoreResult};
use serde_json::Value;

pub const SOURCES: [&str; 5] = ["canvas", "selection", "scene", "font", "image"];

/// V1 `_MODE_VALUES`: (label key, bit_axis, group_order).
pub const MODES: [(&str, &str, &str); 4] = [
    ("逐行式", "horizontal", "row_major"),
    ("行列式", "horizontal", "column_major"),
    ("逐列式", "vertical", "column_major"),
    ("列行式（SSD1306 VLSB）", "vertical", "row_major"),
];

/// Builtins followed by project profiles; a project id replaces the builtin in place.
pub fn merged_profiles(saved: &[(String, OutputProfile)]) -> Vec<(String, OutputProfile)> {
    let mut out: Vec<(String, OutputProfile)> = builtin_profiles()
        .into_iter()
        .map(|(id, p)| (id.to_string(), p))
        .collect();
    for (id, profile) in saved {
        match out.iter_mut().find(|(existing, _)| existing == id) {
            Some(slot) => slot.1 = profile.clone(),
            None => out.push((id.clone(), profile.clone())),
        }
    }
    out
}

pub struct Workbench {
    pub profile_id: String,
    pub profile: OutputProfile,
    /// The in-memory profile differs from what the project stores; only an
    /// explicit commit writes it to `project.oled.json`.
    pub profile_dirty: bool,
    pub source: usize,
    pub characters: String,
    pub image_path: String,
    pub last: Option<FormattedOutput>,
    pub message: String,
}

impl Default for Workbench {
    fn default() -> Self {
        let profile = mono_core::profiles::builtin_profile("ssd1306_vlsb_c").unwrap_or_default();
        Self {
            profile_id: "ssd1306_vlsb_c".into(),
            profile,
            profile_dirty: false,
            source: 0,
            characters: String::new(),
            image_path: String::new(),
            last: None,
            message: String::new(),
        }
    }
}

impl Workbench {
    pub fn source_kind(&self) -> &'static str {
        SOURCES.get(self.source).copied().unwrap_or("canvas")
    }

    pub fn mode_index(&self) -> usize {
        let json = self.profile.to_json();
        let axis = json.pointer("/encoding/bit_axis").and_then(Value::as_str);
        let order = json
            .pointer("/encoding/group_order")
            .and_then(Value::as_str);
        MODES
            .iter()
            .position(|(_, a, o)| Some(*a) == axis && Some(*o) == order)
            .unwrap_or(3)
    }

    /// Read one dotted field (`text.bytes_per_line`) as display text; template
    /// fields show newlines escaped as `\n` like V1.
    pub fn field(&self, key: &str) -> String {
        let json = self.profile.to_json();
        match json.pointer(&format!("/{}", key.replace('.', "/"))) {
            Some(Value::String(s)) => s.replace('\n', "\\n"),
            Some(Value::Bool(b)) => b.to_string(),
            Some(Value::Number(n)) => n.to_string(),
            _ => String::new(),
        }
    }

    /// Apply one edit; on rejection the previous profile stays and the error returns.
    pub fn set_field(&mut self, key: &str, value: &str) -> CoreResult<()> {
        let mut json = self.profile.to_json();
        if key == "mode" {
            let index: usize = value.parse().unwrap_or(3);
            let (_, axis, order) = MODES.get(index).copied().unwrap_or(MODES[3]);
            set_pointer(&mut json, "encoding.bit_axis", Value::from(axis))?;
            set_pointer(&mut json, "encoding.group_order", Value::from(order))?;
        } else {
            let pointer = format!("/{}", key.replace('.', "/"));
            let typed = match json.pointer(&pointer) {
                Some(Value::Bool(_)) => Value::Bool(value == "true"),
                Some(Value::Number(_)) => value
                    .trim()
                    .parse::<i64>()
                    .map(Value::from)
                    .map_err(|_| CoreError::invalid(format!("{key} must be an integer")))?,
                Some(Value::String(_)) => Value::from(value.replace("\\n", "\n")),
                _ => return Err(CoreError::invalid(format!("unknown profile field: {key}"))),
            };
            set_pointer(&mut json, key, typed)?;
        }
        self.profile = OutputProfile::from_json(&json)?;
        Ok(())
    }

    pub fn generate(&mut self, items: &[OutputItem], symbol: &str) -> CoreResult<()> {
        if items.is_empty() {
            return Err(CoreError::invalid("当前来源没有可输出内容"));
        }
        let formatted = format_output(items, &self.profile.text, symbol, DEFAULT_PREVIEW_LIMIT)?;
        self.last = Some(formatted);
        Ok(())
    }

    /// Text shown in the output panel (V1 `_generation_completed`).
    pub fn display_text(&self) -> String {
        let Some(out) = &self.last else {
            return String::new();
        };
        let mut text = out.preview_text.clone();
        if out.preview_truncated {
            text.push_str("\n\n[预览已截断；保存仍会写入完整结果]");
        }
        if text.is_empty() && !out.data.is_empty() {
            text = hex_spaced(&out.data);
        }
        text
    }

    /// What "copy" puts on the clipboard (full text, or hex for binary).
    pub fn copy_text(&self) -> Option<String> {
        let out = self.last.as_ref()?;
        Some(if out.text.is_empty() {
            hex_spaced(&out.data)
        } else {
            out.text.clone()
        })
    }

    pub fn is_binary(&self) -> bool {
        self.field("text.container") == "binary"
    }

    /// Bytes for "save" plus the optional `_index.h` sidecar.
    pub fn save_payload(&self) -> Option<(Vec<u8>, Option<String>)> {
        let out = self.last.as_ref()?;
        let raw = if self.is_binary() {
            out.data.clone()
        } else {
            out.text.clone().into_bytes()
        };
        let sidecar = (self.field("text.index_mode") == "sidecar" && !out.sidecar_text.is_empty())
            .then(|| out.sidecar_text.clone());
        Some((raw, sidecar))
    }
}

fn set_pointer(json: &mut Value, key: &str, value: Value) -> CoreResult<()> {
    let mut node = json;
    let parts: Vec<&str> = key.split('.').collect();
    let Some((leaf, sections)) = parts.split_last() else {
        return Err(CoreError::invalid("empty profile field"));
    };
    for part in sections {
        node = node
            .get_mut(*part)
            .ok_or_else(|| CoreError::invalid(format!("unknown profile field: {key}")))?;
    }
    match node {
        Value::Object(map) => {
            map.insert((*leaf).to_string(), value);
            Ok(())
        }
        _ => Err(CoreError::invalid(format!("unknown profile field: {key}"))),
    }
}

/// Python `bytes.hex(' ')`.
pub fn hex_spaced(data: &[u8]) -> String {
    data.iter()
        .map(|b| format!("{b:02x}"))
        .collect::<Vec<_>>()
        .join(" ")
}

pub fn bitmap_item(
    name: &str,
    rows: &[Vec<u8>],
    profile: &OutputProfile,
) -> CoreResult<OutputItem> {
    let bitmap = MonoBitmap::from_rows(rows.iter().cloned())?;
    Ok(OutputItem::bitmap(
        name,
        encode_bitmap(&bitmap, &profile.encoding),
    ))
}

/// V1 font source: requested characters de-duplicated in order, else all by code point.
pub fn font_items(
    pack: &FontPack,
    characters: &str,
    profile: &OutputProfile,
) -> CoreResult<Vec<OutputItem>> {
    let mut chars: Vec<char> = Vec::new();
    if characters.is_empty() {
        chars = pack.characters().collect();
        chars.sort_unstable();
    } else {
        for ch in characters.chars() {
            if !chars.contains(&ch) {
                chars.push(ch);
            }
        }
    }
    let mut items = Vec::new();
    for ch in chars {
        let glyph = pack
            .glyph(ch)
            .ok_or_else(|| CoreError::new("KeyError", format!("{ch:?}")))?;
        let mut item = bitmap_item(&ch.to_string(), &glyph.rows, profile)?;
        item.codepoint = Some(u32::from(ch));
        item.bearing_x = glyph.metrics.bearing_x;
        item.bearing_y = glyph.metrics.bearing_y;
        item.advance = glyph.metrics.advance;
        items.push(item);
    }
    Ok(items)
}

#[cfg(test)]
mod tests {
    #![allow(clippy::unwrap_used)]
    use super::*;

    #[test]
    fn rejected_edit_keeps_last_valid_profile() {
        let mut bench = Workbench::default();
        let before = bench.profile.clone();
        assert!(bench.set_field("text.bytes_per_line", "0").is_err());
        assert_eq!(bench.profile, before);
        bench.set_field("text.bytes_per_line", "8").unwrap();
        assert_eq!(bench.field("text.bytes_per_line"), "8");
    }

    #[test]
    fn mode_sets_axis_and_order_together() {
        let mut bench = Workbench::default();
        assert_eq!(bench.mode_index(), 3);
        bench.set_field("mode", "0").unwrap();
        assert_eq!(bench.field("encoding.bit_axis"), "horizontal");
        assert_eq!(bench.field("encoding.group_order"), "row_major");
        assert_eq!(bench.mode_index(), 0);
    }

    #[test]
    fn template_newlines_round_trip_escaped() {
        let mut bench = Workbench::default();
        bench.set_field("text.line_end", "\\n").unwrap();
        assert_eq!(bench.field("text.line_end"), "\\n");
        assert_eq!(bench.profile.text.line_end, "\n");
    }

    #[test]
    fn generate_canvas_matches_formatter_and_binary_copy_is_hex() {
        let mut bench = Workbench::default();
        let rows = vec![vec![1u8; 8]; 8];
        let item = bitmap_item("logo", &rows, &bench.profile).unwrap();
        bench.generate(&[item], "logo").unwrap();
        assert!(bench.display_text().contains("0xFF") || bench.display_text().contains("0xff"));
        bench.set_field("text.container", "binary").unwrap();
        let item = bitmap_item("logo", &rows, &bench.profile).unwrap();
        bench.generate(&[item], "logo").unwrap();
        assert!(bench.is_binary());
        assert_eq!(bench.copy_text().unwrap(), "ff ff ff ff ff ff ff ff");
        assert_eq!(bench.save_payload().unwrap().0, vec![0xff; 8]);
    }

    #[test]
    fn empty_source_is_rejected() {
        let mut bench = Workbench::default();
        assert!(bench.generate(&[], "x").is_err());
    }

    #[test]
    fn project_profiles_override_builtins_in_place() {
        let builtin = builtin_profiles();
        let (first_id, mut first) = (builtin[0].0.to_string(), builtin[0].1.clone());
        first.name = "Custom".into();
        let merged = merged_profiles(&[
            (first_id.clone(), first),
            ("mine".into(), OutputProfile::default()),
        ]);
        assert_eq!(merged[0].0, first_id);
        assert_eq!(merged[0].1.name, "Custom");
        assert_eq!(merged.last().unwrap().0, "mine");
        assert_eq!(merged.len(), builtin.len() + 1);
    }
}
