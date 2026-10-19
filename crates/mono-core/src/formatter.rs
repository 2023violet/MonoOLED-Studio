//! Text/binary output formatting (V1 `output_formatter.py`).

use serde::Serialize;

use crate::encoding::EncodedOutput;
use crate::error::{CoreError, CoreResult};
use crate::profiles::{Container, IndexMode, Radix, TextFormatProfile};

pub const DEFAULT_PREVIEW_LIMIT: usize = 256 * 1024;

#[derive(Debug, Clone)]
pub struct OutputItem {
    pub name: String,
    pub encoded: EncodedOutput,
    pub codepoint: Option<u32>,
    pub width: Option<usize>,
    pub height: Option<usize>,
    pub bearing_x: i32,
    pub bearing_y: i32,
    pub advance: i32,
}

impl OutputItem {
    pub fn bitmap(name: impl Into<String>, encoded: EncodedOutput) -> Self {
        Self {
            name: name.into(),
            encoded,
            codepoint: None,
            width: None,
            height: None,
            bearing_x: 0,
            bearing_y: 0,
            advance: 0,
        }
    }
}

/// Field order matches V1 `dataclasses.asdict(IndexEntry)`.
#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct IndexEntry {
    pub codepoint: u32,
    pub offset: usize,
    pub byte_length: usize,
    pub width: usize,
    pub height: usize,
    pub bearing_x: i32,
    pub bearing_y: i32,
    pub advance: i32,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct FormattedOutput {
    pub data: Vec<u8>,
    pub text: String,
    pub preview_text: String,
    pub preview_truncated: bool,
    pub index: Vec<IndexEntry>,
    pub sidecar_text: String,
}

/// Replace non-identifier runs with `_`, strip `_`, default and digit-prefix like V1.
pub fn sanitize_symbol(value: &str) -> String {
    let trimmed = crate::c_header::collapse_identifier(value);
    let mut symbol = if trimmed.is_empty() {
        "oled_bitmap".to_string()
    } else {
        trimmed
    };
    if symbol.as_bytes()[0].is_ascii_digit() {
        symbol = format!("bitmap_{symbol}");
    }
    symbol
}

#[derive(Clone)]
struct Values {
    symbol: String,
    name: String,
    codepoint: String,
    width: usize,
    height: usize,
    byte_count: usize,
    offset: usize,
}

/// Expand `${placeholder}`; templates were validated to only contain known names.
fn expand(template: &str, values: &Values) -> String {
    let mut out = String::with_capacity(template.len());
    let mut rest = template;
    while let Some(start) = rest.find("${") {
        let after = &rest[start + 2..];
        let Some(end) = after.find('}') else { break };
        out.push_str(&rest[..start]);
        match &after[..end] {
            "symbol" => out.push_str(&values.symbol),
            "name" => out.push_str(&values.name),
            "codepoint" => out.push_str(&values.codepoint),
            "width" => out.push_str(&values.width.to_string()),
            "height" => out.push_str(&values.height.to_string()),
            "byte_count" => out.push_str(&values.byte_count.to_string()),
            "offset" => out.push_str(&values.offset.to_string()),
            other => {
                out.push_str("${");
                out.push_str(other);
                out.push('}');
            }
        }
        rest = &after[end + 1..];
    }
    out.push_str(rest);
    out
}

fn number(value: u8, profile: &TextFormatProfile) -> String {
    match (profile.radix, profile.uppercase) {
        (Radix::Decimal, _) => value.to_string(),
        (Radix::Hex, true) => format!("{value:02X}"),
        (Radix::Hex, false) => format!("{value:02x}"),
    }
}

fn data_lines(data: &[u8], profile: &TextFormatProfile, minimal: bool) -> String {
    let separator = if profile.compact_spacing { "" } else { " " };
    let (prefix, suffix, ending) = if minimal {
        ("", "", "\n")
    } else {
        (
            profile.line_prefix.as_str(),
            profile.line_suffix.as_str(),
            profile.line_end.as_str(),
        )
    };
    let mut out = String::new();
    for chunk in data.chunks(usize::from(profile.bytes_per_line.max(1))) {
        let tokens: Vec<String> = chunk
            .iter()
            .map(|v| {
                format!(
                    "{}{}{}",
                    profile.data_prefix,
                    number(*v, profile),
                    profile.data_suffix
                )
            })
            .collect();
        out.push_str(prefix);
        out.push_str(&tokens.join(separator));
        out.push_str(suffix);
        out.push_str(ending);
    }
    out
}

fn index_text(entries: &[IndexEntry], symbol: &str, per_line: usize) -> String {
    if entries.is_empty() {
        return String::new();
    }
    let records: Vec<String> = entries
        .iter()
        .map(|e| {
            format!(
                "{{ 0x{:08X}, {}, {}, {}, {}, {}, {}, {} }},",
                e.codepoint,
                e.offset,
                e.byte_length,
                e.width,
                e.height,
                e.bearing_x,
                e.bearing_y,
                e.advance
            )
        })
        .collect();
    let rows: String = records
        .chunks(per_line.max(1))
        .map(|chunk| format!("    {}\n", chunk.join(" ")))
        .collect();
    format!(
        "\ntypedef struct {{ uint32_t codepoint, offset, byte_length; uint16_t width, height; int16_t bearing_x, bearing_y; uint16_t advance; }} MonoGlyphIndex;\nstatic const MonoGlyphIndex {symbol}_index[] = {{\n{rows}}};\n"
    )
}

/// Truncate to at most `limit` UTF-8 bytes, dropping a split trailing character.
pub fn preview(text: &str, limit: usize) -> (String, bool) {
    if text.len() <= limit {
        return (text.to_string(), false);
    }
    let mut end = limit;
    while end > 0 && !text.is_char_boundary(end) {
        end -= 1;
    }
    (text[..end].to_string(), true)
}

pub fn format_output(
    items: &[OutputItem],
    profile: &TextFormatProfile,
    symbol: &str,
    preview_limit: usize,
) -> CoreResult<FormattedOutput> {
    let Some(first) = items.first() else {
        return Err(CoreError::invalid("output requires at least one item"));
    };
    let symbol = sanitize_symbol(symbol);
    let data: Vec<u8> = items
        .iter()
        .flat_map(|item| item.encoded.data.iter().copied())
        .collect();
    let mut index = Vec::new();
    let mut offset = 0;
    for item in items {
        if let Some(codepoint) = item.codepoint {
            index.push(IndexEntry {
                codepoint,
                offset,
                byte_length: item.encoded.data.len(),
                width: item.width.unwrap_or(item.encoded.width),
                height: item.height.unwrap_or(item.encoded.height),
                bearing_x: item.bearing_x,
                bearing_y: item.bearing_y,
                advance: item.advance,
            });
        }
        offset += item.encoded.data.len();
    }

    if profile.container == Container::Binary {
        return Ok(FormattedOutput {
            data,
            text: String::new(),
            preview_text: String::new(),
            preview_truncated: false,
            index,
            sidecar_text: String::new(),
        });
    }

    let common = Values {
        symbol: symbol.clone(),
        name: first.name.clone(),
        codepoint: first.codepoint.map(|c| c.to_string()).unwrap_or_default(),
        width: first.encoded.width,
        height: first.encoded.height,
        byte_count: data.len(),
        offset: 0,
    };
    let mut text = if profile.minimal_data {
        data_lines(&data, profile, true)
    } else {
        let mut chunks = expand(&profile.segment_prefix, &common);
        let mut running = 0;
        for item in items {
            let values = Values {
                name: item.name.clone(),
                codepoint: item.codepoint.map(|c| c.to_string()).unwrap_or_default(),
                width: item.encoded.width,
                height: item.encoded.height,
                byte_count: item.encoded.data.len(),
                offset: running,
                ..common.clone()
            };
            if !profile.comment_prefix.is_empty() || !profile.comment_suffix.is_empty() {
                chunks.push_str(&expand(&profile.comment_prefix, &values));
                chunks.push_str(&values.name);
                chunks.push_str(&expand(&profile.comment_suffix, &values));
            }
            chunks.push_str(&data_lines(&item.encoded.data, profile, false));
            running += item.encoded.data.len();
        }
        chunks.push_str(&expand(&profile.segment_suffix, &common));
        chunks
    };
    let index_block = if profile.index_mode == IndexMode::None {
        String::new()
    } else {
        index_text(&index, &symbol, usize::from(profile.index_entries_per_line))
    };
    let sidecar_text = if profile.index_mode == IndexMode::Sidecar {
        index_block.clone()
    } else {
        String::new()
    };
    if profile.index_mode == IndexMode::Inline {
        text.push_str(&index_block);
    }
    let (preview_text, preview_truncated) = preview(&text, preview_limit);
    Ok(FormattedOutput {
        data,
        text,
        preview_text,
        preview_truncated,
        index,
        sidecar_text,
    })
}
