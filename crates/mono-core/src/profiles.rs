//! Output profiles (V1 `output_profiles.py`): raster, encoding and text formatting.

use serde::{Deserialize, Serialize};

use crate::encoding::{BitAxis, BitOrder, EncodingProfile, GroupOrder};
use crate::error::{CoreError, CoreResult};

pub const PLACEHOLDERS: [&str; 7] = [
    "symbol",
    "name",
    "codepoint",
    "width",
    "height",
    "byte_count",
    "offset",
];

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum Alignment {
    FontSet,
    GlyphWidth,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum ThresholdMode {
    Luma,
    RgbAll,
}

/// Field order matches V1 `dataclasses.asdict(RasterProfile())`.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields, default)]
pub struct RasterProfile {
    pub alignment: Alignment,
    pub threshold_mode: ThresholdMode,
    pub luma_threshold: u8,
    pub red_threshold: u8,
    pub green_threshold: u8,
    pub blue_threshold: u8,
    pub invert_source: bool,
    pub antialias_scale: u8,
    pub offset_x: i32,
    pub offset_y: i32,
}

impl Default for RasterProfile {
    fn default() -> Self {
        Self {
            alignment: Alignment::GlyphWidth,
            threshold_mode: ThresholdMode::Luma,
            luma_threshold: 128,
            red_threshold: 255,
            green_threshold: 255,
            blue_threshold: 255,
            invert_source: false,
            antialias_scale: 1,
            offset_x: 0,
            offset_y: 0,
        }
    }
}

impl RasterProfile {
    pub fn validate(&self) -> CoreResult<()> {
        if !matches!(self.antialias_scale, 1 | 2 | 4) {
            return Err(CoreError::invalid("antialias_scale must be 1, 2, or 4"));
        }
        Ok(())
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum Container {
    Binary,
    Text,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum Radix {
    Hex,
    Decimal,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum IndexMode {
    None,
    Inline,
    Sidecar,
}

/// Field order matches V1 `dataclasses.asdict(TextFormatProfile())`.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields, default)]
pub struct TextFormatProfile {
    pub container: Container,
    pub radix: Radix,
    pub uppercase: bool,
    pub bytes_per_line: u16,
    pub index_entries_per_line: u16,
    pub index_mode: IndexMode,
    pub minimal_data: bool,
    pub compact_spacing: bool,
    pub segment_prefix: String,
    pub segment_suffix: String,
    pub comment_prefix: String,
    pub comment_suffix: String,
    pub data_prefix: String,
    pub data_suffix: String,
    pub line_prefix: String,
    pub line_suffix: String,
    pub line_end: String,
}

impl Default for TextFormatProfile {
    fn default() -> Self {
        Self {
            container: Container::Text,
            radix: Radix::Hex,
            uppercase: true,
            bytes_per_line: 16,
            index_entries_per_line: 16,
            index_mode: IndexMode::None,
            minimal_data: false,
            compact_spacing: false,
            segment_prefix:
                "#pragma once\n#include <stdint.h>\n\nstatic const uint8_t ${symbol}[] = {\n".into(),
            segment_suffix: "};\n".into(),
            comment_prefix: "    /* ".into(),
            comment_suffix: " */\n".into(),
            data_prefix: "0x".into(),
            data_suffix: ",".into(),
            line_prefix: "    ".into(),
            line_suffix: String::new(),
            line_end: "\n".into(),
        }
    }
}

/// Every `${name}` placeholder in `template`, in order.
pub fn placeholders(template: &str) -> Vec<&str> {
    let mut found = Vec::new();
    let mut rest = template;
    while let Some(start) = rest.find("${") {
        let after = &rest[start + 2..];
        let Some(end) = after.find('}') else { break };
        found.push(&after[..end]);
        rest = &after[end + 1..];
    }
    found
}

impl TextFormatProfile {
    pub fn templates(&self) -> [(&'static str, &str); 9] {
        [
            ("segment_prefix", &self.segment_prefix),
            ("segment_suffix", &self.segment_suffix),
            ("comment_prefix", &self.comment_prefix),
            ("comment_suffix", &self.comment_suffix),
            ("data_prefix", &self.data_prefix),
            ("data_suffix", &self.data_suffix),
            ("line_prefix", &self.line_prefix),
            ("line_suffix", &self.line_suffix),
            ("line_end", &self.line_end),
        ]
    }

    pub fn validate(&self) -> CoreResult<()> {
        for (name, value) in [
            ("bytes_per_line", self.bytes_per_line),
            ("index_entries_per_line", self.index_entries_per_line),
        ] {
            if !(1..=256).contains(&value) {
                return Err(CoreError::invalid(format!(
                    "{name} must be between 1 and 256"
                )));
            }
        }
        for (name, value) in self.templates() {
            if value.chars().count() > 1024 {
                return Err(CoreError::invalid(format!(
                    "{name} must not exceed 1024 characters"
                )));
            }
            for placeholder in placeholders(value) {
                if !PLACEHOLDERS.contains(&placeholder) {
                    return Err(CoreError::invalid(format!(
                        "unknown placeholder: {placeholder}"
                    )));
                }
            }
        }
        Ok(())
    }
}

/// Field order matches V1 `OutputProfile.to_dict()`.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct OutputProfile {
    pub name: String,
    #[serde(default)]
    pub raster: RasterProfile,
    #[serde(default)]
    pub encoding: EncodingProfile,
    #[serde(default)]
    pub text: TextFormatProfile,
}

impl Default for OutputProfile {
    fn default() -> Self {
        Self {
            name: "SSD1306 VLSB · C Header".into(),
            raster: RasterProfile::default(),
            encoding: EncodingProfile::default(),
            text: TextFormatProfile::default(),
        }
    }
}

impl OutputProfile {
    /// V1 `normalize_profile`: trims the name and validates every section.
    pub fn normalized(mut self) -> CoreResult<Self> {
        self.name = self.name.trim().to_string();
        let length = self.name.chars().count();
        if length == 0 || length > 64 {
            return Err(CoreError::invalid(
                "profile name must contain 1 to 64 characters",
            ));
        }
        self.raster.validate()?;
        self.text.validate()?;
        Ok(self)
    }
}

fn text(change: impl FnOnce(&mut TextFormatProfile)) -> TextFormatProfile {
    let mut value = TextFormatProfile::default();
    change(&mut value);
    value
}

/// Built-in profiles in V1 order.
pub fn builtin_profiles() -> Vec<(&'static str, OutputProfile)> {
    vec![
        ("ssd1306_vlsb_c", OutputProfile::default()),
        (
            "row_msb_c51",
            OutputProfile {
                name: "逐行 MSB · C51".into(),
                encoding: EncodingProfile {
                    bit_axis: BitAxis::Horizontal,
                    group_order: GroupOrder::RowMajor,
                    bit_order: BitOrder::MsbFirst,
                    ..EncodingProfile::default()
                },
                text: text(|t| {
                    t.segment_prefix = "const unsigned char code ${symbol}[] = {\n".into()
                }),
                ..OutputProfile::default()
            },
        ),
        (
            "raw_hex",
            OutputProfile {
                name: "Raw Hex".into(),
                text: text(|t| t.minimal_data = true),
                ..OutputProfile::default()
            },
        ),
        (
            "raw_decimal",
            OutputProfile {
                name: "Raw Decimal".into(),
                text: text(|t| {
                    t.radix = Radix::Decimal;
                    t.data_prefix = String::new();
                    t.minimal_data = true;
                }),
                ..OutputProfile::default()
            },
        ),
        (
            "legacy_pixel_c",
            OutputProfile {
                name: "Legacy Pixel C Header".into(),
                text: text(|t| {
                    t.bytes_per_line = 12;
                    t.segment_prefix = "#define ${symbol}_WIDTH ${width}\n#define ${symbol}_HEIGHT ${height}\n#define ${symbol}_BYTES ${byte_count}\n\nstatic const unsigned char ${symbol}[] = {\n".into();
                    t.comment_prefix = String::new();
                    t.comment_suffix = String::new();
                }),
                ..OutputProfile::default()
            },
        ),
    ]
}

pub fn builtin_profile(id: &str) -> Option<OutputProfile> {
    builtin_profiles()
        .into_iter()
        .find(|(key, _)| *key == id)
        .map(|(_, profile)| profile)
}

/// Profile ids: lowercase ASCII letter/digit first, then `[a-z0-9_-]`, at most 64.
pub fn validate_profile_id(id: &str) -> CoreResult<&str> {
    let bytes = id.as_bytes();
    let ok = !bytes.is_empty()
        && bytes.len() <= 64
        && (bytes[0].is_ascii_lowercase() || bytes[0].is_ascii_digit())
        && bytes
            .iter()
            .all(|b| b.is_ascii_lowercase() || b.is_ascii_digit() || *b == b'_' || *b == b'-');
    if ok {
        Ok(id)
    } else {
        Err(CoreError::invalid(
            "profile id must use lowercase ASCII letters, digits, underscore, or hyphen",
        ))
    }
}

// ---------------------------------------------------------------------------
// V1 `normalize_profile` with identical validation order and messages.

use serde_json::{Map, Value};

use crate::pyvalue::{py_int, py_repr, py_str};

fn type_error(class: &str, key: &str) -> CoreError {
    CoreError::new(
        "E-CORE-TYPE",
        format!("{class}.__init__() got an unexpected keyword argument '{key}'"),
    )
}

fn section(raw: &Map<String, Value>, key: &str) -> CoreResult<Map<String, Value>> {
    match raw.get(key) {
        None | Some(Value::Null) | Some(Value::Bool(false)) => Ok(Map::new()),
        Some(Value::Object(map)) => Ok(map.clone()),
        Some(Value::Array(items)) if items.is_empty() => Ok(Map::new()),
        Some(Value::String(s)) if s.is_empty() => Ok(Map::new()),
        Some(other) => Err(CoreError::new(
            "E-CORE-TYPE",
            format!(
                "cannot convert dictionary update sequence element #0 to a sequence: {}",
                py_repr(other)
            ),
        )),
    }
}

fn check_keys(map: &Map<String, Value>, class: &str, allowed: &[&str]) -> CoreResult<()> {
    match map.keys().find(|k| !allowed.contains(&k.as_str())) {
        Some(key) => Err(type_error(class, key)),
        None => Ok(()),
    }
}

fn choice<T: Copy>(
    map: &Map<String, Value>,
    key: &str,
    default: T,
    options: &[(&str, T)],
    message: &str,
) -> CoreResult<T> {
    match map.get(key) {
        None => Ok(default),
        Some(value) => options
            .iter()
            .find(|(name, _)| value.as_str() == Some(*name))
            .map(|(_, v)| *v)
            .ok_or_else(|| CoreError::invalid(message.to_string())),
    }
}

fn int_value(map: &Map<String, Value>, key: &str, default: i64) -> CoreResult<i64> {
    match map.get(key) {
        None => Ok(default),
        Some(value) => py_int(value).ok_or_else(|| {
            CoreError::invalid(format!(
                "invalid literal for int() with base 10: {}",
                py_repr(value)
            ))
        }),
    }
}

fn bool_value(map: &Map<String, Value>, key: &str, default: bool) -> bool {
    match map.get(key) {
        None => default,
        Some(Value::Bool(b)) => *b,
        Some(Value::Number(n)) => n.as_f64().is_some_and(|f| f != 0.0),
        Some(Value::String(s)) => !s.is_empty(),
        Some(Value::Null) => false,
        Some(Value::Array(a)) => !a.is_empty(),
        Some(Value::Object(o)) => !o.is_empty(),
    }
}

const RASTER_FIELDS: [&str; 10] = [
    "alignment",
    "threshold_mode",
    "luma_threshold",
    "red_threshold",
    "green_threshold",
    "blue_threshold",
    "invert_source",
    "antialias_scale",
    "offset_x",
    "offset_y",
];
const TEXT_FIELDS: [&str; 17] = [
    "container",
    "radix",
    "uppercase",
    "bytes_per_line",
    "index_entries_per_line",
    "index_mode",
    "minimal_data",
    "compact_spacing",
    "segment_prefix",
    "segment_suffix",
    "comment_prefix",
    "comment_suffix",
    "data_prefix",
    "data_suffix",
    "line_prefix",
    "line_suffix",
    "line_end",
];

impl RasterProfile {
    pub fn from_map(map: &Map<String, Value>) -> CoreResult<Self> {
        check_keys(map, "RasterProfile", &RASTER_FIELDS)?;
        let d = Self::default();
        let alignment = choice(
            map,
            "alignment",
            d.alignment,
            &[
                ("font_set", Alignment::FontSet),
                ("glyph_width", Alignment::GlyphWidth),
            ],
            "alignment must be font_set or glyph_width",
        )?;
        let threshold_mode = choice(
            map,
            "threshold_mode",
            d.threshold_mode,
            &[
                ("luma", ThresholdMode::Luma),
                ("rgb_all", ThresholdMode::RgbAll),
            ],
            "threshold_mode must be luma or rgb_all",
        )?;
        let mut thresholds = [0u8; 4];
        let names = [
            ("luma_threshold", 128),
            ("red_threshold", 255),
            ("green_threshold", 255),
            ("blue_threshold", 255),
        ];
        for (slot, (name, default)) in thresholds.iter_mut().zip(names) {
            let value = int_value(map, name, default)?;
            if !(0..=255).contains(&value) {
                return Err(CoreError::invalid(format!(
                    "{name} must be between 0 and 255"
                )));
            }
            *slot = value as u8;
        }
        let antialias = int_value(map, "antialias_scale", 1)?;
        if !matches!(antialias, 1 | 2 | 4) {
            return Err(CoreError::invalid("antialias_scale must be 1, 2, or 4"));
        }
        Ok(Self {
            alignment,
            threshold_mode,
            luma_threshold: thresholds[0],
            red_threshold: thresholds[1],
            green_threshold: thresholds[2],
            blue_threshold: thresholds[3],
            invert_source: bool_value(map, "invert_source", false),
            antialias_scale: antialias as u8,
            offset_x: int_value(map, "offset_x", 0)? as i32,
            offset_y: int_value(map, "offset_y", 0)? as i32,
        })
    }
}

impl EncodingProfile {
    pub fn from_map(map: &Map<String, Value>) -> CoreResult<Self> {
        use crate::encoding::Polarity;
        check_keys(
            map,
            "EncodingProfile",
            &["bit_axis", "group_order", "bit_order", "polarity"],
        )?;
        let d = Self::default();
        Ok(Self {
            bit_axis: choice(
                map,
                "bit_axis",
                d.bit_axis,
                &[
                    ("horizontal", BitAxis::Horizontal),
                    ("vertical", BitAxis::Vertical),
                ],
                "bit_axis must be one of ['horizontal', 'vertical']",
            )?,
            group_order: choice(
                map,
                "group_order",
                d.group_order,
                &[
                    ("column_major", GroupOrder::ColumnMajor),
                    ("row_major", GroupOrder::RowMajor),
                ],
                "group_order must be one of ['column_major', 'row_major']",
            )?,
            bit_order: choice(
                map,
                "bit_order",
                d.bit_order,
                &[
                    ("lsb_first", BitOrder::LsbFirst),
                    ("msb_first", BitOrder::MsbFirst),
                ],
                "bit_order must be one of ['lsb_first', 'msb_first']",
            )?,
            polarity: choice(
                map,
                "polarity",
                d.polarity,
                &[
                    ("one_is_lit", Polarity::OneIsLit),
                    ("zero_is_lit", Polarity::ZeroIsLit),
                ],
                "polarity must be one of ['one_is_lit', 'zero_is_lit']",
            )?,
        })
    }
}

impl TextFormatProfile {
    pub fn from_map(map: &Map<String, Value>) -> CoreResult<Self> {
        check_keys(map, "TextFormatProfile", &TEXT_FIELDS)?;
        let d = Self::default();
        let container = choice(
            map,
            "container",
            d.container,
            &[("binary", Container::Binary), ("text", Container::Text)],
            "container must be binary or text",
        )?;
        let radix = choice(
            map,
            "radix",
            d.radix,
            &[("hex", Radix::Hex), ("decimal", Radix::Decimal)],
            "radix must be hex or decimal",
        )?;
        let index_mode = choice(
            map,
            "index_mode",
            d.index_mode,
            &[
                ("none", IndexMode::None),
                ("inline", IndexMode::Inline),
                ("sidecar", IndexMode::Sidecar),
            ],
            "index_mode must be none, inline, or sidecar",
        )?;
        let mut counts = [0u16; 2];
        for (slot, name) in counts
            .iter_mut()
            .zip(["bytes_per_line", "index_entries_per_line"])
        {
            let value = int_value(map, name, 16)?;
            if !(1..=256).contains(&value) {
                return Err(CoreError::invalid(format!(
                    "{name} must be between 1 and 256"
                )));
            }
            *slot = value as u16;
        }
        let mut profile = Self {
            container,
            radix,
            uppercase: bool_value(map, "uppercase", true),
            bytes_per_line: counts[0],
            index_entries_per_line: counts[1],
            index_mode,
            minimal_data: bool_value(map, "minimal_data", false),
            compact_spacing: bool_value(map, "compact_spacing", false),
            ..d
        };
        for name in &TEXT_FIELDS[8..] {
            if let Some(value) = map.get(*name) {
                let Value::String(text) = value else {
                    return Err(CoreError::invalid(format!("{name} must be text")));
                };
                let slot = match *name {
                    "segment_prefix" => &mut profile.segment_prefix,
                    "segment_suffix" => &mut profile.segment_suffix,
                    "comment_prefix" => &mut profile.comment_prefix,
                    "comment_suffix" => &mut profile.comment_suffix,
                    "data_prefix" => &mut profile.data_prefix,
                    "data_suffix" => &mut profile.data_suffix,
                    "line_prefix" => &mut profile.line_prefix,
                    "line_suffix" => &mut profile.line_suffix,
                    _ => &mut profile.line_end,
                };
                *slot = text.clone();
            }
        }
        profile.validate()?;
        Ok(profile)
    }
}

impl OutputProfile {
    /// V1 `normalize_profile(raw_dict)`.
    pub fn from_json(raw: &Value) -> CoreResult<Self> {
        let Value::Object(map) = raw else {
            return Err(CoreError::invalid("output profile must be an object"));
        };
        let name = map
            .get("name")
            .map(py_str)
            .unwrap_or_default()
            .trim()
            .to_string();
        let length = name.chars().count();
        if length == 0 || length > 64 {
            return Err(CoreError::invalid(
                "profile name must contain 1 to 64 characters",
            ));
        }
        Ok(Self {
            name,
            raster: RasterProfile::from_map(&section(map, "raster")?)?,
            encoding: EncodingProfile::from_map(&section(map, "encoding")?)?,
            text: TextFormatProfile::from_map(&section(map, "text")?)?,
        })
    }

    /// V1 `OutputProfile.to_dict()`.
    pub fn to_json(&self) -> Value {
        serde_json::to_value(self).unwrap_or(Value::Null)
    }
}
