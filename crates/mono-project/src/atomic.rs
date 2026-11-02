//! Atomic writes and Python-compatible JSON serialisation (V1 `atomic_io.py`).

use std::fs;
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
    static COUNTER: std::sync::atomic::AtomicU64 = std::sync::atomic::AtomicU64::new(0);
    let unique = u128::from(COUNTER.fetch_add(1, std::sync::atomic::Ordering::Relaxed));
    let nonce = (std::process::id() as u128) << 64
        ^ unique
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
        // create_new: never reuse or follow an existing path (V1 uses mkstemp).
        let mut file = std::fs::OpenOptions::new()
            .write(true)
            .create_new(true)
            .open(&temp)?;
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

/// Incremental atomic write: bytes go to a sibling temp file and become visible
/// only when [`AtomicWriter::finish`] fsyncs and renames it. Dropping an
/// unfinished writer removes the temp file, so an aborted export leaves no
/// partial artefact.
pub struct AtomicWriter {
    target: PathBuf,
    temp: PathBuf,
    file: Option<std::io::BufWriter<fs::File>>,
    finished: bool,
}

impl AtomicWriter {
    pub fn create(target: &Path) -> CoreResult<Self> {
        if let Some(parent) = target.parent() {
            fs::create_dir_all(parent).map_err(|e| io_error(parent, &e))?;
        }
        let temp = temp_sibling(target);
        let file = fs::OpenOptions::new()
            .write(true)
            .create_new(true)
            .open(&temp)
            .map_err(|e| io_error(target, &e))?;
        Ok(Self {
            target: target.to_path_buf(),
            temp,
            file: Some(std::io::BufWriter::new(file)),
            finished: false,
        })
    }

    pub fn write_all(&mut self, data: &[u8]) -> CoreResult<()> {
        let file = self.file.as_mut().ok_or_else(|| {
            CoreError::new(
                "E-IO",
                format!("{}: writer is closed", self.target.display()),
            )
        })?;
        file.write_all(data).map_err(|e| io_error(&self.target, &e))
    }

    pub fn finish(mut self) -> CoreResult<()> {
        let mut buffered = self.file.take().ok_or_else(|| {
            CoreError::new(
                "E-IO",
                format!("{}: writer is closed", self.target.display()),
            )
        })?;
        buffered.flush().map_err(|e| io_error(&self.target, &e))?;
        let file = buffered
            .into_inner()
            .map_err(|e| io_error(&self.target, &e.into_error()))?;
        file.sync_all().map_err(|e| io_error(&self.target, &e))?;
        drop(file);
        fs::rename(&self.temp, &self.target).map_err(|e| io_error(&self.target, &e))?;
        self.finished = true;
        Ok(())
    }
}

impl Drop for AtomicWriter {
    fn drop(&mut self) {
        if !self.finished {
            self.file.take();
            let _ = fs::remove_file(&self.temp);
        }
    }
}

/// `atomic_write` for a batch of independent files. Each file keeps the full
/// temp + fsync + rename contract; files are written concurrently so the
/// per-file fsync latencies overlap. Returns the first error (by input order).
pub fn atomic_write_many(writes: &[(PathBuf, Vec<u8>)]) -> CoreResult<()> {
    if writes.len() <= 1 {
        return writes
            .iter()
            .try_for_each(|(path, data)| atomic_write(path, data));
    }
    let workers = writes.len().min(8);
    let next = std::sync::atomic::AtomicUsize::new(0);
    let mut results: Vec<Option<CoreResult<()>>> = (0..writes.len()).map(|_| None).collect();
    let slots = std::sync::Mutex::new(&mut results);
    std::thread::scope(|scope| {
        for _ in 0..workers {
            scope.spawn(|| {
                loop {
                    let index = next.fetch_add(1, std::sync::atomic::Ordering::Relaxed);
                    let Some((path, data)) = writes.get(index) else {
                        break;
                    };
                    let result = atomic_write(path, data);
                    if let Ok(mut slots) = slots.lock() {
                        slots[index] = Some(result);
                    }
                }
            });
        }
    });
    results
        .into_iter()
        .try_for_each(|r| r.unwrap_or_else(|| Err(CoreError::invalid("write worker did not run"))))
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

#[cfg(test)]
mod tests {
    #![allow(clippy::unwrap_used)]
    use super::*;

    fn dir(name: &str) -> PathBuf {
        let path = std::env::temp_dir().join(format!("mono-atomic-{name}-{}", std::process::id()));
        let _ = fs::remove_dir_all(&path);
        fs::create_dir_all(&path).unwrap();
        path
    }

    fn names(path: &Path) -> Vec<String> {
        let mut names: Vec<String> = fs::read_dir(path)
            .unwrap()
            .flatten()
            .map(|e| e.file_name().to_string_lossy().into_owned())
            .collect();
        names.sort();
        names
    }

    #[test]
    fn dropping_an_unfinished_writer_keeps_the_old_file_and_no_temp() {
        let root = dir("drop");
        let target = root.join("out.txt");
        fs::write(&target, b"old").unwrap();
        let mut writer = AtomicWriter::create(&target).unwrap();
        writer.write_all(b"new").unwrap();
        drop(writer);
        assert_eq!(fs::read(&target).unwrap(), b"old");
        assert_eq!(names(&root), ["out.txt"]);
        fs::remove_dir_all(&root).unwrap();
    }

    #[test]
    fn finish_replaces_an_existing_file() {
        let root = dir("finish");
        let target = root.join("out.txt");
        fs::write(&target, b"old").unwrap();
        let mut writer = AtomicWriter::create(&target).unwrap();
        writer.write_all(b"new").unwrap();
        writer.write_all(b" data").unwrap();
        writer.finish().unwrap();
        assert_eq!(fs::read(&target).unwrap(), b"new data");
        assert_eq!(names(&root), ["out.txt"]);
        fs::remove_dir_all(&root).unwrap();
    }

    #[test]
    fn a_failed_rename_reports_the_error_and_removes_the_temp() {
        let root = dir("rename");
        // A directory at the target makes the final rename fail on every OS.
        let target = root.join("taken");
        fs::create_dir(&target).unwrap();
        let mut writer = AtomicWriter::create(&target).unwrap();
        writer.write_all(b"data").unwrap();
        assert!(writer.finish().is_err());
        assert!(target.is_dir());
        assert_eq!(names(&root), ["taken"]);
        fs::remove_dir_all(&root).unwrap();
    }
}
