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
