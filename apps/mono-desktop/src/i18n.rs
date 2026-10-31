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

/// Every language the app ships.
#[cfg(test)]
pub const LANGUAGES: [&str; 2] = ["zh_CN", "en_US"];

/// True when `key` resolves in every language. `tr` falls back to the key
/// itself, so a missing key is rendered as raw text rather than blank — this is
/// how a table-driven label (preferences rows, palette entries) goes unnoticed.
#[cfg(test)]
pub fn has_key(key: &str) -> bool {
    LANGUAGES
        .iter()
        .all(|lang| tables().get(*lang).is_some_and(|t| t.contains_key(key)))
}

#[cfg(test)]
mod tests {
    #![allow(clippy::unwrap_used)]
    use super::*;

    /// Every literal key the UI asks for exists in both languages.
    #[test]
    fn ui_and_controller_keys_are_translated() {
        let root = std::path::Path::new(env!("CARGO_MANIFEST_DIR"));
        let mut missing = Vec::new();
        for dir in ["ui", "src"] {
            for entry in std::fs::read_dir(root.join(dir)).unwrap() {
                let path = entry.unwrap().path();
                let text = std::fs::read_to_string(&path).unwrap();
                for marker in [
                    "I18n.tr(I18n.lang, \"",
                    "t(\"",
                    "tr(&self.lang, \"",
                    "tr(&lang, \"",
                    "tr(lang, \"",
                    "trf(&self.lang, \"",
                    "trf(&lang, \"",
                ] {
                    // `pt("…")` is deliberately not a marker: it takes a `pref.`
                    // suffix, not a full key, and `every_preference_string_translates`
                    // resolves those.
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
                "pixel.status",
                &[("x", "3".into()), ("y", "4".into())]
            ),
            tr("en_US", "pixel.status")
                .replace("{x}", "3")
                .replace("{y}", "4")
        );
    }

    /// Every `src/*.rs` and `ui/*.slint` file the app ships, minus its test
    /// module and minus whole-line comments: both hold literals nothing ever
    /// shows the user.
    fn shipped_text() -> Vec<(String, String)> {
        let root = std::path::Path::new(env!("CARGO_MANIFEST_DIR"));
        let mut out = Vec::new();
        for dir in ["ui", "src"] {
            for entry in std::fs::read_dir(root.join(dir)).unwrap() {
                let path = entry.unwrap().path();
                let ext = path.extension().and_then(|e| e.to_str()).unwrap_or("");
                if !matches!(ext, "rs" | "slint") {
                    continue;
                }
                let mut text = std::fs::read_to_string(&path).unwrap();
                // The test module is always the last block in these files; its
                // literals are assertions, not user-facing copy. `main.rs` names
                // its module `ui_source_tests`, so both anchors are needed.
                for anchor in ["mod tests {", "mod ui_source_tests {"] {
                    if let Some(at) = text.find(anchor) {
                        text.truncate(at);
                    }
                }
                // A key that survives only in a prose comment is still orphaned,
                // so whole-line comments are dropped before the search. Trailing
                // comments are left in place: cutting at `//` would also cut
                // through literals such as a documentation URL.
                let body = text
                    .lines()
                    .filter(|line| !line.trim_start().starts_with("//"))
                    .collect::<Vec<_>>()
                    .join("\n");
                out.push((path.display().to_string(), body));
            }
        }
        out.sort();
        out
    }

    /// The keys `strings.json` must carry: the two language tables have to be
    /// identical in content *and* order (the file is diffed by hand), no key may
    /// appear twice inside one language, and no key may sit unused. `ui_and_controller_keys_are_translated`
    /// proves the other direction (a used key exists); this one catches copy that
    /// only looks maintained.
    #[test]
    fn strings_json_is_exactly_paired_and_used() {
        // Keys named from an engine token never appear as a literal, so they
        // cannot be checked here: `undo.<token>` is built in `undo_phrase`,
        // `bench.source.<kind>` and `bench.template.<field>` in `refresh_bench`.
        // Their other half is `known_undo_tokens_have_copy` and the `SOURCES` /
        // `TEMPLATE_FIELDS` tables, which enumerate the tokens themselves.
        const CONSTRUCTED: [&str; 3] = ["undo.", "bench.source.", "bench.template."];
        let mut tables: Vec<Vec<String>> = Vec::new();
        for line in STRINGS.lines() {
            let line = line.trim();
            let Some(rest) = line.strip_prefix('"') else {
                continue;
            };
            let Some((name, tail)) = rest.split_once("\":") else {
                continue;
            };
            if tail.trim() == "{" {
                tables.push(Vec::new());
            } else if let Some(list) = tables.last_mut() {
                list.push(name.to_string());
            }
        }
        assert_eq!(
            tables.len(),
            LANGUAGES.len(),
            "strings.json must hold exactly {:?}, in that order",
            LANGUAGES
        );
        let keys = &tables[0];
        for (index, list) in tables.iter().enumerate().skip(1) {
            assert_eq!(
                list, keys,
                "{} must list the same keys as {} in the same order",
                LANGUAGES[index], LANGUAGES[0]
            );
        }
        let repeated: Vec<&String> = keys
            .iter()
            .filter(|key| keys.iter().filter(|other| other == key).count() > 1)
            .collect();
        assert!(repeated.is_empty(), "repeated keys: {repeated:?}");
        let text = shipped_text();
        let asks = |key: &str| {
            text.iter()
                .any(|(_, body)| body.contains(&format!("\"{key}\"")))
        };
        let unused: Vec<&String> = keys
            .iter()
            .filter(|key| {
                // Preference rows look up `pref.<suffix>`, so their source literal
                // is the suffix: matching the full key here would call every one of
                // them orphaned, and blanket-exempting `pref.` instead let a row that
                // was later deleted keep its copy forever.
                if let Some(suffix) = key.strip_prefix("pref.") {
                    if ["section.", "page.", "shortcut."]
                        .iter()
                        .any(|built| suffix.starts_with(built))
                    {
                        return false;
                    }
                    // Rows resolve `pref_key(suffix)`; the view chrome asks for
                    // the full key. Either one counts as a use.
                    return !(asks(suffix) || asks(key));
                }
                // Undo steps and workbench fields name themselves from engine tokens.
                if CONSTRUCTED.iter().any(|prefix| key.starts_with(prefix)) {
                    return false;
                }
                !asks(key)
            })
            .collect();
        assert!(
            unused.is_empty(),
            "{unused:#?} exist in strings.json but no code or view asks for them"
        );
    }

    /// Copy that skips `strings.json` cannot be translated, and the key-coverage
    /// tests above cannot see it. User-facing Chinese (or any other non-ASCII
    /// word) written straight into a view or controller is therefore rejected,
    /// with the one listed exception: the language picker names each language in
    /// its own tongue, which is the point of that row.
    #[test]
    fn no_user_facing_copy_bypasses_i18n() {
        // The language picker names each language in its own tongue; the leading
        // `=` is the preference rows' marker for "show this text, do not look it
        // up", so that row is the one literal the translator must not own.
        const ALLOWED: [&str; 1] = ["简体中文"];
        let mut bypassed = Vec::new();
        for (file, body) in shipped_text() {
            for literal in string_literals(&body) {
                if literal.is_ascii() || ALLOWED.contains(&literal.trim_start_matches('=')) {
                    continue;
                }
                if literal.chars().all(|c| !c.is_alphabetic() || c.is_ascii()) {
                    // Symbols such as `×`, `·` and `•` are language-neutral.
                    continue;
                }
                bypassed.push(format!("{file}: {literal}"));
            }
        }
        assert!(
            bypassed.is_empty(),
            "copy that bypasses i18n: {bypassed:#?}"
        );
    }

    /// Double-quoted literals in `text`, ignoring comments and escapes.
    fn string_literals(text: &str) -> Vec<String> {
        let mut out = Vec::new();
        for line in text.lines() {
            if line.trim_start().starts_with("//") {
                continue;
            }
            let mut current = String::new();
            let mut in_string = false;
            let mut escaped = false;
            for ch in line.chars() {
                if !in_string {
                    in_string = ch == '"';
                    continue;
                }
                if escaped {
                    escaped = false;
                } else if ch == '\\' {
                    escaped = true;
                } else if ch == '"' {
                    out.push(std::mem::take(&mut current));
                    in_string = false;
                } else {
                    current.push(ch);
                }
            }
        }
        out
    }
}
