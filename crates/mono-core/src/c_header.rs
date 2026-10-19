//! Legacy `export.c_header` (V1 `c_export.framebuffer_to_c_header`).

use crate::error::CoreResult;
use crate::framebuffer::FrameBuffer;

/// Collapse runs outside `[A-Za-z0-9_]` to `_` and strip surrounding `_` (V1 regex rule).
pub(crate) fn collapse_identifier(value: &str) -> String {
    let mut out = String::new();
    let mut in_run = false;
    for ch in value.chars() {
        if ch.is_ascii_alphanumeric() || ch == '_' {
            out.push(ch);
            in_run = false;
        } else if !in_run {
            out.push('_');
            in_run = true;
        }
    }
    out.trim_matches('_').to_string()
}

/// V1 `_ident`: default `oled_frame`, digit-prefixed with `_`.
pub fn c_identifier(name: &str) -> String {
    let mut out = collapse_identifier(name);
    if out.is_empty() {
        out = "oled_frame".into();
    }
    if out.as_bytes()[0].is_ascii_digit() {
        out.insert(0, '_');
    }
    out
}

pub fn framebuffer_to_c_header(framebuffer: &FrameBuffer, name: &str) -> CoreResult<String> {
    let ident = c_identifier(name);
    let raw = framebuffer.to_vlsb()?;
    let lines: Vec<String> = raw
        .chunks(16)
        .map(|chunk| {
            format!(
                "    {},",
                chunk
                    .iter()
                    .map(|b| format!("0x{b:02X}"))
                    .collect::<Vec<_>>()
                    .join(", ")
            )
        })
        .collect();
    Ok(format!(
        "#pragma once\n#include <stdint.h>\n\nstatic const uint16_t {ident}_width = {};\nstatic const uint16_t {ident}_height = {};\nstatic const uint16_t {ident}_bytes = {};\nstatic const uint8_t {ident}[{}] = {{\n{}\n}};\n",
        framebuffer.width(),
        framebuffer.height(),
        raw.len(),
        raw.len(),
        lines.join("\n")
    ))
}
