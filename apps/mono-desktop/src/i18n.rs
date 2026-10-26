//! Key-based translations generated from V1 `i18n.py` (+ preferences copy) and
//! desktop-only additions; `zh_CN` is the default, `en_US` the alternative.

use std::collections::HashMap;
use std::sync::OnceLock;

use serde_json::Value;

const STRINGS: &str = include_str!("../i18n/strings.json");

fn tables() -> &'static HashMap<String, HashMap<String, String>> {
    static TABLES: OnceLock<HashMap<String, HashMap<String, String>>> = OnceLock::new();
    TABLES.get_or_init(|| {
        let parsed: Value = serde_json::from_str(STRINGS).unwrap_or(Value::Null);
        let mut out = HashMap::new();
        if let Value::Object(langs) = parsed {
            for (lang, table) in langs {
                let map = table
                    .as_object()
                    .map(|t| {
                        t.iter()
                            .map(|(k, v)| (k.clone(), v.as_str().unwrap_or_default().to_string()))
                            .collect()
                    })
                    .unwrap_or_default();
                out.insert(lang, map);
            }
        }
        out
    })
}

/// Translate `key`; unknown keys fall back to English, then to the key itself.
pub fn tr(lang: &str, key: &str) -> String {
    let tables = tables();
    tables
        .get(lang)
        .and_then(|t| t.get(key))
        .or_else(|| tables.get("en_US").and_then(|t| t.get(key)))
        .cloned()
        .unwrap_or_else(|| key.to_string())
}

/// Translate and substitute `{name}` placeholders (V1 `str.format(**values)`).
pub fn trf(lang: &str, key: &str, values: &[(&str, String)]) -> String {
    let mut text = tr(lang, key);
    for (name, value) in values {
        text = text.replace(&format!("{{{name}}}"), value);
        // `{name:.2f}`-style specs: callers pass the already formatted value.
        let open = format!("{{{name}:");
        while let Some(start) = text.find(&open) {
            let Some(len) = text[start..].find('}') else {
                break;
            };
            text.replace_range(start..start + len + 1, value);
        }
    }
    text
}

/// Readable label for a validation finding; unknown codes stay as the code.
pub fn finding_label(lang: &str, code: &str) -> String {
    let key = format!("finding.{code}");
    let label = tr(lang, &key);
    if label == key {
        code.to_string()
    } else {
        label
    }
}

#[cfg(test)]
mod tests {
    #![allow(clippy::unwrap_used)]
    use super::*;

    const LANGUAGES: [&str; 2] = ["zh_CN", "en_US"];

    fn has_key(key: &str) -> bool {
        LANGUAGES
            .iter()
            .all(|lang| tables().get(*lang).is_some_and(|t| t.contains_key(key)))
    }

    /// Every literal key the UI asks for exists in both languages.
    #[test]
    fn ui_and_controller_keys_are_translated() {
        let root = std::path::Path::new(env!("CARGO_MANIFEST_DIR"));
        let mut missing = Vec::new();
        for dir in ["ui", "src"] {
            for entry in std::fs::read_dir(root.join(dir)).unwrap() {
                let path = entry.unwrap().path();
                let text = std::fs::read_to_string(&path).unwrap();
                for marker in ["I18n.tr(I18n.lang, \"", "t(\"", "trf(&self.lang, \""] {
                    for (at, _) in text.match_indices(marker) {
                        // `t("` must be the whole identifier (not `int("` / `set("`).
                        let before = text[..at].chars().next_back().unwrap_or(' ');
                        if marker == "t(\"" && (before.is_ascii_alphanumeric() || before == '_') {
                            continue;
                        }
                        let rest = &text[at + marker.len()..];
                        let key = rest.split('"').next().unwrap_or_default();
                        let plausible = key.contains('.')
                            && key
                                .chars()
                                .all(|c| c.is_ascii_alphanumeric() || "._".contains(c));
                        if plausible && !has_key(key) {
                            missing.push(format!("{}: {key}", path.display()));
                        }
                    }
                }
            }
        }
        missing.sort();
        missing.dedup();
        assert!(missing.is_empty(), "untranslated keys: {missing:#?}");
    }

    #[test]
    fn unknown_keys_fall_back_and_placeholders_substitute() {
        assert_eq!(tr("zh_CN", "no.such.key"), "no.such.key");
        assert_eq!(
            trf(
                "en_US",
                "pixel.cursor",
                &[("x", "3".into()), ("y", "4".into())]
            ),
            tr("en_US", "pixel.cursor")
                .replace("{x}", "3")
                .replace("{y}", "4")
        );
    }

    #[test]
    fn every_finding_code_has_label() {
        for code in mono_project::export::FINDING_CODES {
            for lang in LANGUAGES {
                let key = format!("finding.{code}");
                assert!(
                    tables()
                        .get(lang)
                        .is_some_and(|table| table.contains_key(&key)),
                    "{lang} is missing {key}"
                );
                assert_ne!(tr(lang, &key), key, "{lang} {key}");
            }
        }
    }

    #[test]
    fn unknown_finding_falls_back_to_code() {
        assert_eq!(finding_label("zh_CN", "NO_SUCH_FINDING"), "NO_SUCH_FINDING");
        assert_eq!(
            finding_label("zh_CN", "REQUIRED_ELEMENT_MISSING"),
            tr("zh_CN", "finding.REQUIRED_ELEMENT_MISSING")
        );
    }
}
