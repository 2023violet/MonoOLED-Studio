#![allow(dead_code, clippy::unwrap_used, clippy::expect_used, clippy::panic)]

use std::path::PathBuf;

use serde_json::Value;

pub fn golden_dir() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../fixtures/golden")
}

pub fn cases(category: &str) -> Vec<Value> {
    let path = golden_dir().join(format!("{category}.json"));
    let text =
        std::fs::read_to_string(&path).unwrap_or_else(|e| panic!("read {}: {e}", path.display()));
    let value: Value = serde_json::from_str(&text).expect("corpus json");
    value["cases"].as_array().expect("cases array").clone()
}

pub fn rows(value: &Value) -> Vec<Vec<u8>> {
    value
        .as_array()
        .expect("rows")
        .iter()
        .map(|row| {
            row.as_str()
                .expect("row string")
                .bytes()
                .map(|b| u8::from(b == b'1'))
                .collect()
        })
        .collect()
}

pub fn row_strings<'a>(rows: impl Iterator<Item = &'a [u8]>) -> Vec<String> {
    rows.map(|row| {
        row.iter()
            .map(|v| if *v != 0 { '1' } else { '0' })
            .collect()
    })
    .collect()
}

pub fn hex(data: &[u8]) -> String {
    data.iter().map(|b| format!("{b:02x}")).collect()
}

/// Collects mismatching case ids so one run reports every failure.
#[derive(Default)]
pub struct Report {
    pub checked: usize,
    pub failures: Vec<String>,
}

impl Report {
    pub fn check(&mut self, id: &str, ok: bool, detail: impl FnOnce() -> String) {
        self.checked += 1;
        if !ok {
            self.failures.push(format!("{id}: {}", detail()));
        }
    }

    /// Like `finish`, but also proves no case was skipped.
    pub fn finish_exact(self, label: &str, expected: usize) {
        assert_eq!(
            self.checked, expected,
            "{label}: checked {} cases, corpus has {expected}",
            self.checked
        );
        self.finish(label);
    }

    pub fn finish(self, label: &str) {
        assert!(self.checked > 0, "{label}: no cases checked");
        assert!(
            self.failures.is_empty(),
            "{label}: {} of {} cases failed:\n{}",
            self.failures.len(),
            self.checked,
            self.failures.join("\n")
        );
    }
}

/// Number of corpus cases whose `kind` satisfies `keep`.
pub fn count_cases(category: &str, keep: impl Fn(&str) -> bool) -> usize {
    cases(category)
        .iter()
        .filter(|c| keep(c["kind"].as_str().unwrap_or("")))
        .count()
}
