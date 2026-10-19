//! Atomic writes and Python-compatible JSON serialisation (V1 `atomic_io.py`).

use std::fs::{self, File};
use std::io::Write;
use std::path::{Path, PathBuf};

use mono_core::{CoreError, CoreResult};
use serde_json::Value;
use serde_json::ser::{PrettyFormatter, Serializer};

use crate::resources::io_error;

fn temp_sibling(target: &Path) -> PathBuf {
    let name = target
        .file_name()
        .map(|n| n.to_string_lossy().into_owned())
        .unwrap_or_default();
    let nonce = std::process::id() as u128
        ^ std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .map(|d| d.as_nanos())
            .unwrap_or(0);
    target.with_file_name(format!(".{name}.{nonce:x}.tmp"))
}

/// Write to a sibling temp file, fsync, then rename over `target`. The target is
/// either the old or the new content, never a partial file.
pub fn atomic_write(target: &Path, data: &[u8]) -> CoreResult<()> {
    if let Some(parent) = target.parent() {
        fs::create_dir_all(parent).map_err(|e| io_error(parent, &e))?;
    }
    let temp = temp_sibling(target);
    let result = (|| -> std::io::Result<()> {
        let mut file = File::create(&temp)?;
        file.write_all(data)?;
        file.sync_all()?;
        drop(file);
        fs::rename(&temp, target)
    })();
    if result.is_err() {
        let _ = fs::remove_file(&temp);
    }
    result.map_err(|e| io_error(target, &e))
}

/// `json.dumps(value, ensure_ascii=False, indent=2)` byte-compatible output.
pub fn python_json(value: &Value) -> CoreResult<String> {
    let mut out = Vec::new();
    let formatter = PrettyFormatter::with_indent(b"  ");
    let mut serializer = Serializer::with_formatter(&mut out, formatter);
    serde::Serialize::serialize(value, &mut serializer)
        .map_err(|e| CoreError::invalid(e.to_string()))?;
    String::from_utf8(out).map_err(|e| CoreError::invalid(e.to_string()))
}

/// V1 `atomic_write_json`: indent 2, non-ASCII kept, trailing newline.
pub fn atomic_write_json(target: &Path, value: &Value) -> CoreResult<()> {
    let mut text = python_json(value)?;
    text.push('\n');
    atomic_write(target, text.as_bytes())
}
