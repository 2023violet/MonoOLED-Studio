//! Scene validation, export and Code AI handoff (V1 `validate.py`, `design_rules.py`,
//! `batch_validate.py`, `exporter.py`, `thumbnail_wall.py`, `asset_library.py`, `handoff.py`).

use std::collections::{BTreeMap, BTreeSet};
use std::io::Write;
use std::path::{Path, PathBuf};

use mono_core::c_header::framebuffer_to_c_header;
use mono_core::font::{builtin_glyph_rows, has_builtin_glyph};
use mono_core::pyvalue::{is_py_int, py_in, py_int, py_repr, py_str};
use mono_core::render::{Resources, normalize_path, posix, render_scene, resolve};
use mono_core::state::{IntegerPolicy, State, build_state_matrix, case_name, init_state, subst};
use mono_core::{CoreError, CoreResult};
use serde_json::{Map, Value, json};

use crate::atomic::{atomic_write, atomic_write_many, python_json};
use crate::image_io::{decode_image, encode_bitmap_png, encode_rgba_png};
use crate::project::{py_resolve, resolve_under_root};
use crate::resources::{DiskResources, hex_digest, read_file};

pub const EXPORT_BLOCKED: &str = "E-EXPORT-BLOCKED";
pub const CANCELLED: &str = "E-CANCELLED";

/// Progress callback: `(stage, completed, total)`; return `false` to cancel.
pub type Progress<'a> = &'a mut dyn FnMut(&str, usize, usize) -> bool;

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Finding {
    pub severity: String,
    pub code: String,
    pub message: String,
    pub element_id: Option<String>,
}

/// Every finding code the validator can emit (localized labels live in the UI).
pub const FINDING_CODES: [&str; 23] = [
    "NON_INTEGER_COORDINATE",
    "INVALID_SIZE",
    "OUT_OF_BOUNDS",
    "ASSET_NOT_FOUND",
    "NON_BINARY_ASSET",
    "ASSET_SIZE_MISMATCH",
    "INVALID_CANVAS_SIZE",
    "CANVAS_HEIGHT_NOT_PAGE_ALIGNED",
    "FRAMEBUFFER_SIZE_CONTRACT",
    "MISSING_STATE",
    "INVALID_STATE",
    "UNKNOWN_ELEMENT_TYPE",
    "INVALID_BINDING",
    "DRAFT_PLACEHOLDER",
    "INVALID_SEQUENCE",
    "FONT_INVALID",
    "FONT_MISSING_GLYPH",
    "UNRESOLVED_VARIABLE",
    "FRAMEBUFFER_SIZE",
    "RENDER_FAILED",
    "REQUIRED_ELEMENT_MISSING",
    "ELEMENT_OUTSIDE_ZONE",
    "BASELINE_MISMATCH",
];

impl Finding {
    fn new(
        severity: &str,
        code: &str,
        message: impl Into<String>,
        element_id: Option<&str>,
    ) -> Self {
        Self {
            severity: severity.into(),
            code: code.into(),
            message: message.into(),
            element_id: element_id.map(str::to_string),
        }
    }

    pub fn is_blocking(&self) -> bool {
        self.severity == "ERROR" || self.severity == "BLOCKER"
    }

    pub fn to_json(&self) -> Value {
        json!({"severity": self.severity, "code": self.code, "message": self.message, "element_id": self.element_id})
    }
}

pub fn has_blockers(findings: &[Finding]) -> bool {
    findings.iter().any(Finding::is_blocking)
}

const SUPPORTED_TYPES: [&str; 6] = [
    "image",
    "image_seq",
    "digits",
    "text",
    "bitmap_text",
    "placeholder",
];

fn check_box(
    findings: &mut Vec<Finding>,
    eid: &str,
    values: [Option<&Value>; 4],
    cw: i64,
    ch: i64,
) {
    if !values.iter().all(|v| v.is_some_and(is_py_int)) {
        findings.push(Finding::new(
            "BLOCKER",
            "NON_INTEGER_COORDINATE",
            format!("{eid}: X/Y/W/H must be integers"),
            Some(eid),
        ));
        return;
    }
    // i128 so huge JSON integers cannot wrap past the OUT_OF_BOUNDS gate.
    let [x, y, w, h] = values.map(|v| i128::from(v.and_then(Value::as_i64).unwrap_or(0)));
    let (cw, ch) = (i128::from(cw), i128::from(ch));
    if w <= 0 || h <= 0 {
        findings.push(Finding::new(
            "BLOCKER",
            "INVALID_SIZE",
            format!("{eid}: W/H must be > 0"),
            Some(eid),
        ));
        return;
    }
    if x < 0 || y < 0 || x + w > cw || y + h > ch {
        findings.push(Finding::new(
            "BLOCKER",
            "OUT_OF_BOUNDS",
            format!("{eid}: ({x},{y},{w},{h}) outside {cw}x{ch}"),
            Some(eid),
        ));
    }
}

fn template_keys(template: &str) -> Vec<String> {
    let mut keys = Vec::new();
    let mut rest = template;
    while let Some(start) = rest.find('{') {
        let after = &rest[start + 1..];
        match after.find('}') {
            Some(end)
                if end > 0
                    && after[..end]
                        .chars()
                        .all(|c| c.is_alphanumeric() || c == '_') =>
            {
                keys.push(after[..end].to_string());
                rest = &after[end + 1..];
            }
            _ => rest = after,
        }
    }
    keys
}

fn missing_key(key: &str) -> CoreError {
    CoreError::new("E-CORE-KEY", key.to_string())
}

fn enum_template_paths(
    template: &str,
    scene: &Map<String, Value>,
    root: &Path,
    state: &State,
    lower: bool,
) -> CoreResult<Vec<PathBuf>> {
    let keys = template_keys(template);
    if keys.is_empty() {
        return Ok(vec![py_resolve(&resolve(root, template))]);
    }
    let states = scene
        .get("states")
        .and_then(Value::as_object)
        .cloned()
        .unwrap_or_default();
    let mut domains = Vec::new();
    for key in &keys {
        let spec = states.get(key).ok_or_else(|| missing_key(key))?;
        if spec.get("type").and_then(Value::as_str) == Some("enum") {
            domains.push(
                spec.get("values")
                    .and_then(Value::as_array)
                    .cloned()
                    .unwrap_or_default(),
            );
        } else {
            domains.push(vec![
                state.get(key).cloned().ok_or_else(|| missing_key(key))?,
            ]);
        }
    }
    let mut paths = Vec::new();
    if domains.iter().any(Vec::is_empty) {
        return Ok(paths);
    }
    let mut idx = vec![0usize; domains.len()];
    loop {
        let mut local = state.clone();
        for (i, key) in keys.iter().enumerate() {
            local.insert(key.clone(), domains[i][idx[i]].clone());
        }
        paths.push(py_resolve(&resolve(root, &subst(template, &local, lower)?)));
        let mut p = domains.len();
        loop {
            if p == 0 {
                return Ok(paths);
            }
            p -= 1;
            idx[p] += 1;
            if idx[p] < domains[p].len() {
                break;
            }
            idx[p] = 0;
        }
    }
}

fn display(path: &Path) -> String {
    path.display().to_string()
}

fn validate_bitmap_path(
    findings: &mut Vec<Finding>,
    path: &Path,
    element: &Map<String, Value>,
    resources: &mut DiskResources,
    expected: Option<(&Value, &Value)>,
) {
    let eid = py_str(element.get("id").unwrap_or(&Value::Null));
    if !path.exists() {
        findings.push(Finding::new(
            "BLOCKER",
            "ASSET_NOT_FOUND",
            format!("{eid}: {}", display(path)),
            Some(&eid),
        ));
        return;
    }
    let asset = match resources.bitmap(path) {
        Ok(asset) => asset,
        Err(error) => {
            findings.push(Finding::new(
                "BLOCKER",
                "NON_BINARY_ASSET",
                format!("{eid}: {}", error.message),
                Some(&eid),
            ));
            return;
        }
    };
    let policy = element
        .get("resize_policy")
        .map(py_str)
        .unwrap_or_else(|| "native_only".into());
    if let (true, Some((w, h))) = (policy == "native_only", expected) {
        if w.is_null() || h.is_null() {
            return;
        }
        let (ew, eh) = (py_int(w).unwrap_or(-1), py_int(h).unwrap_or(-1));
        if (asset.width as i64, asset.height as i64) != (ew, eh) {
            findings.push(Finding::new(
                "BLOCKER",
                "ASSET_SIZE_MISMATCH",
                format!(
                    "{eid}: declared {}x{}, native {}x{}: {}",
                    py_str(w),
                    py_str(h),
                    asset.width,
                    asset.height,
                    display(path)
                ),
                Some(&eid),
            ));
        }
    }
}

/// V1 `validate_scene`.
pub fn validate_scene(
    scene: &Map<String, Value>,
    root: &Path,
    state: Option<&State>,
    resources: &mut DiskResources,
) -> Vec<Finding> {
    let mut findings = Vec::new();
    let state = state.cloned().unwrap_or_else(|| init_state(scene));
    let empty = Map::new();
    let canvas = scene
        .get("canvas")
        .and_then(Value::as_object)
        .unwrap_or(&empty);
    let (cwv, chv) = (
        canvas.get("w").cloned().unwrap_or(Value::Null),
        canvas.get("h").cloned().unwrap_or(Value::Null),
    );
    if !is_py_int(&cwv)
        || !is_py_int(&chv)
        || cwv.as_i64().unwrap_or(0) <= 0
        || chv.as_i64().unwrap_or(0) <= 0
    {
        let show = |v: &Value| {
            if v.is_null() {
                "None".to_string()
            } else {
                py_str(v)
            }
        };
        findings.push(Finding::new(
            "BLOCKER",
            "INVALID_CANVAS_SIZE",
            format!(
                "canvas must use positive integer dimensions, got {}x{}",
                show(&cwv),
                show(&chv)
            ),
            None,
        ));
        return findings;
    }
    let (cw, ch) = (cwv.as_i64().unwrap_or(0), chv.as_i64().unwrap_or(0));
    if ch % 8 != 0 {
        findings.push(Finding::new(
            "BLOCKER",
            "CANVAS_HEIGHT_NOT_PAGE_ALIGNED",
            format!("VLSB canvas height must be divisible by 8, got {ch}"),
            None,
        ));
        return findings;
    }
    let expected_bytes = cw.saturating_mul(ch / 8);
    if let Some(declared) = scene
        .get("storage")
        .and_then(|s| s.get("bytes_per_frame"))
        .filter(|v| !v.is_null())
    {
        if py_int(declared) != Some(expected_bytes) {
            findings.push(Finding::new(
                "BLOCKER",
                "FRAMEBUFFER_SIZE_CONTRACT",
                format!(
                    "storage.bytes_per_frame={}, expected {expected_bytes} for {cw}x{ch}",
                    py_str(declared)
                ),
                None,
            ));
        }
    }
    let states = scene
        .get("states")
        .and_then(Value::as_object)
        .cloned()
        .unwrap_or_default();
    for (key, spec) in &states {
        match state.get(key) {
            None => findings.push(Finding::new(
                "BLOCKER",
                "MISSING_STATE",
                format!("missing state value: {key}"),
                None,
            )),
            Some(value) => {
                let kind = spec.get("type").and_then(Value::as_str);
                if kind == Some("enum")
                    && !py_in(
                        value,
                        spec.get("values")
                            .and_then(Value::as_array)
                            .map(Vec::as_slice)
                            .unwrap_or(&[]),
                    )
                {
                    findings.push(Finding::new(
                        "BLOCKER",
                        "INVALID_STATE",
                        format!("{key}={} not in enum", py_repr(value)),
                        None,
                    ));
                } else if kind == Some("int") && !(is_py_int(value) || value.is_boolean()) {
                    findings.push(Finding::new(
                        "BLOCKER",
                        "INVALID_STATE",
                        format!("{key} must be int"),
                        None,
                    ));
                }
            }
        }
    }
    let elements = scene
        .get("elements")
        .and_then(Value::as_array)
        .cloned()
        .unwrap_or_default();
    for raw in &elements {
        let element = raw.as_object().cloned().unwrap_or_default();
        let eid = element
            .get("id")
            .map(py_str)
            .unwrap_or_else(|| "<missing-id>".into());
        let kind_value = element.get("type").cloned().unwrap_or(Value::Null);
        let kind = kind_value.as_str().unwrap_or("").to_string();
        if !SUPPORTED_TYPES.contains(&kind.as_str()) || !kind_value.is_string() {
            findings.push(Finding::new(
                "BLOCKER",
                "UNKNOWN_ELEMENT_TYPE",
                format!("{eid}: {}", py_repr(&kind_value)),
                Some(&eid),
            ));
            continue;
        }
        let bind = element.get("bind").map(py_str).filter(|b| !b.is_empty());
        if let Some(bind) = &bind {
            if !states.contains_key(bind) {
                findings.push(Finding::new(
                    "BLOCKER",
                    "INVALID_BINDING",
                    format!("{eid}: unknown state {bind}"),
                    Some(&eid),
                ));
                continue;
            }
        }
        let get = |k: &str| element.get(k);
        match kind.as_str() {
            "image" | "image_seq" | "placeholder" => {
                check_box(
                    &mut findings,
                    &eid,
                    [get("x"), get("y"), get("w"), get("h")],
                    cw,
                    ch,
                );
                if kind == "placeholder" {
                    findings.push(Finding::new("BLOCKER", "DRAFT_PLACEHOLDER", format!("{eid}: editor placeholder must be replaced by a production asset before export"), Some(&eid)));
                }
            }
            "digits" => {
                let zero = Value::from(0);
                let tracking = get("tracking").unwrap_or(&zero);
                let all_int = [
                    get("x"),
                    get("y"),
                    get("digit_w"),
                    get("digit_h"),
                    Some(tracking),
                ]
                .iter()
                .all(|v| v.is_some_and(is_py_int));
                if !all_int {
                    findings.push(Finding::new(
                        "BLOCKER",
                        "NON_INTEGER_COORDINATE",
                        format!("{eid}: digit geometry must be integer"),
                        Some(&eid),
                    ));
                } else {
                    let spec = bind
                        .as_ref()
                        .and_then(|b| states.get(b))
                        .cloned()
                        .unwrap_or(json!({}));
                    let max_text = spec.get("max").map(py_str).unwrap_or_else(|| {
                        bind.as_ref()
                            .and_then(|b| state.get(b))
                            .map(py_str)
                            .unwrap_or_else(|| "0".into())
                    });
                    let min_digits = get("min_digits").and_then(py_int).unwrap_or(1);
                    let digits = (max_text.chars().count() as i64).max(min_digits);
                    let (dw, dh, tr) = (
                        get("digit_w").and_then(Value::as_i64).unwrap_or(0),
                        get("digit_h").and_then(Value::as_i64).unwrap_or(0),
                        tracking.as_i64().unwrap_or(0),
                    );
                    let width = Value::from(
                        digits
                            .saturating_mul(dw)
                            .saturating_add((digits - 1).max(0).saturating_mul(tr)),
                    );
                    check_box(
                        &mut findings,
                        &eid,
                        [get("x"), get("y"), Some(&width), get("digit_h")],
                        cw,
                        ch,
                    );
                    let _ = dh;
                }
            }
            _ => {
                if let Some(zone) = get("zone")
                    .and_then(Value::as_object)
                    .filter(|z| !z.is_empty())
                {
                    check_box(
                        &mut findings,
                        &eid,
                        [zone.get("x"), zone.get("y"), zone.get("w"), zone.get("h")],
                        cw,
                        ch,
                    );
                } else {
                    let one = Value::from(1);
                    let cell_h = Value::from(get("cell_h").and_then(py_int).unwrap_or(7));
                    check_box(
                        &mut findings,
                        &eid,
                        [get("x"), get("y"), Some(&one), Some(&cell_h)],
                        cw,
                        ch,
                    );
                }
            }
        }
        let result = (|| -> CoreResult<()> {
            match kind.as_str() {
                "image" => {
                    let template = py_str(get("asset").ok_or_else(|| missing_key("asset"))?);
                    let lower = get("var_lower").is_some_and(|v| {
                        !matches!(v, Value::Bool(false) | Value::Null)
                            && v != &json!(0)
                            && v != &json!("")
                    });
                    for path in enum_template_paths(&template, scene, root, &state, lower)? {
                        validate_bitmap_path(
                            &mut findings,
                            &path,
                            &element,
                            resources,
                            Some((
                                get("w").unwrap_or(&Value::Null),
                                get("h").unwrap_or(&Value::Null),
                            )),
                        );
                    }
                }
                "image_seq" => {
                    let count = get("count").and_then(py_int).unwrap_or(0);
                    if count <= 0 {
                        findings.push(Finding::new(
                            "BLOCKER",
                            "INVALID_SEQUENCE",
                            format!("{eid}: count must be > 0"),
                            Some(&eid),
                        ));
                    }
                    let pattern = py_str(get("pattern").ok_or_else(|| missing_key("pattern"))?);
                    let dir = resolve(root, &py_str(get("dir").ok_or_else(|| missing_key("dir"))?));
                    for n in 0..count.max(0) {
                        let path = py_resolve(&normalize_path(
                            &dir.join(pattern.replace("{n}", &n.to_string())),
                        ));
                        validate_bitmap_path(
                            &mut findings,
                            &path,
                            &element,
                            resources,
                            Some((
                                get("w").unwrap_or(&Value::Null),
                                get("h").unwrap_or(&Value::Null),
                            )),
                        );
                    }
                }
                "digits" => {
                    let pattern = py_str(get("pattern").ok_or_else(|| missing_key("pattern"))?);
                    let dir = resolve(root, &py_str(get("dir").ok_or_else(|| missing_key("dir"))?));
                    for d in '0'..='9' {
                        let path = py_resolve(&normalize_path(
                            &dir.join(pattern.replace("{d}", &d.to_string())),
                        ));
                        validate_bitmap_path(
                            &mut findings,
                            &path,
                            &element,
                            resources,
                            Some((
                                get("digit_w").unwrap_or(&Value::Null),
                                get("digit_h").unwrap_or(&Value::Null),
                            )),
                        );
                    }
                }
                "text" => {
                    let header = py_resolve(&resolve(
                        root,
                        &py_str(get("font_header").ok_or_else(|| missing_key("font_header"))?),
                    ));
                    if !header.exists() {
                        findings.push(Finding::new(
                            "BLOCKER",
                            "ASSET_NOT_FOUND",
                            format!("{eid}: {}", display(&header)),
                            Some(&eid),
                        ));
                    } else if let Err(error) = resources.mode_font(&header) {
                        findings.push(Finding::new(
                            "BLOCKER",
                            "FONT_INVALID",
                            format!("{eid}: {}", error.message),
                            Some(&eid),
                        ));
                    }
                }
                "bitmap_text" => {
                    let pack_root = py_resolve(&resolve(
                        root,
                        &py_str(get("font_pack").ok_or_else(|| missing_key("font_pack"))?),
                    ));
                    if !pack_root.join("fontpack.json").exists() {
                        findings.push(Finding::new(
                            "BLOCKER",
                            "ASSET_NOT_FOUND",
                            format!("{eid}: {}/fontpack.json", display(&pack_root)),
                            Some(&eid),
                        ));
                    } else {
                        match resources.font_pack(&pack_root).and_then(|pack| {
                            let text =
                                subst(&get("text").map(py_str).unwrap_or_default(), &state, false)?;
                            Ok(text
                                .chars()
                                .filter(|c| pack.glyph(*c).is_none())
                                .collect::<Vec<_>>())
                        }) {
                            Ok(missing) if !missing.is_empty() => {
                                let list = Value::Array(
                                    missing.iter().map(|c| Value::from(c.to_string())).collect(),
                                );
                                findings.push(Finding::new(
                                    "BLOCKER",
                                    "FONT_MISSING_GLYPH",
                                    format!("{eid}: missing {}", py_repr(&list)),
                                    Some(&eid),
                                ));
                            }
                            Ok(_) => {}
                            Err(error) => findings.push(Finding::new(
                                "BLOCKER",
                                "FONT_INVALID",
                                format!("{eid}: {}", error.message),
                                Some(&eid),
                            )),
                        }
                    }
                }
                _ => {}
            }
            Ok(())
        })();
        if let Err(error) = result {
            let key = error.message.trim_matches('\'').to_string();
            findings.push(Finding::new(
                "BLOCKER",
                "UNRESOLVED_VARIABLE",
                format!("{eid}: unresolved template/state {key}"),
                Some(&eid),
            ));
        }
    }
    match render_scene(scene, root, &state, resources) {
        Ok(result) => {
            if result
                .framebuffer
                .to_vlsb()
                .map(|v| v.len() as i64)
                .unwrap_or(-1)
                != expected_bytes
            {
                findings.push(Finding::new(
                    "BLOCKER",
                    "FRAMEBUFFER_SIZE",
                    format!("rendered framebuffer is not {expected_bytes} bytes"),
                    None,
                ));
            }
            for item in &result.resolved_elements {
                let visible = item.get("visible").is_some_and(|v| v == &Value::Bool(true));
                let fields = ["x", "y", "w", "h"].map(|k| item.get(k).filter(|v| !v.is_null()));
                if visible && fields.iter().all(Option::is_some) {
                    let id = item.get("id").map(py_str).unwrap_or_default();
                    check_box(&mut findings, &id, fields, cw, ch);
                }
            }
        }
        Err(error) => findings.push(Finding::new(
            "BLOCKER",
            "RENDER_FAILED",
            error.message,
            None,
        )),
    }
    findings
}

fn rect(element: &Map<String, Value>) -> Option<(i64, i64, i64, i64)> {
    let src = element
        .get("zone")
        .and_then(Value::as_object)
        .unwrap_or(element);
    Some((
        py_int(src.get("x")?)?,
        py_int(src.get("y")?)?,
        py_int(src.get("w")?)?,
        py_int(src.get("h")?)?,
    ))
}

/// V1 `check_design_rules`.
pub fn check_design_rules(scene: &Map<String, Value>, rules: &Value) -> Vec<Finding> {
    let mut findings = Vec::new();
    let mut by_id: BTreeMap<String, Map<String, Value>> = BTreeMap::new();
    for e in scene
        .get("elements")
        .and_then(Value::as_array)
        .into_iter()
        .flatten()
    {
        if let Some(map) = e.as_object() {
            if let Some(id) = map.get("id").filter(|v| !v.is_null() && v != &&json!("")) {
                by_id.insert(py_str(id), map.clone());
            }
        }
    }
    for id in rules
        .get("required_elements")
        .and_then(Value::as_array)
        .into_iter()
        .flatten()
    {
        let id = py_str(id);
        if !by_id.contains_key(&id) {
            findings.push(Finding::new(
                "WARNING",
                "REQUIRED_ELEMENT_MISSING",
                format!(
                    "required design element {} is missing",
                    py_repr(&Value::from(id.as_str()))
                ),
                Some(&id),
            ));
        }
    }
    for (id, zone) in rules
        .get("zones")
        .and_then(Value::as_object)
        .into_iter()
        .flatten()
    {
        let Some((x, y, w, h)) = by_id.get(id).and_then(rect) else {
            continue;
        };
        let z = |k: &str| zone.get(k).and_then(py_int).unwrap_or(0);
        let (zx, zy, zw, zh) = (z("x"), z("y"), z("w"), z("h"));
        if x < zx || y < zy || x + w > zx + zw || y + h > zy + zh {
            findings.push(Finding::new(
                "WARNING",
                "ELEMENT_OUTSIDE_ZONE",
                format!("{id} lies outside configured design zone"),
                Some(id),
            ));
        }
    }
    for group in rules
        .get("baseline_groups")
        .and_then(Value::as_array)
        .into_iter()
        .flatten()
    {
        let axis = group.get("axis").map(py_str).unwrap_or_else(|| "y".into());
        let mut values = Vec::new();
        for id in group
            .get("ids")
            .and_then(Value::as_array)
            .into_iter()
            .flatten()
        {
            let id = py_str(id);
            if let Some(r) = by_id.get(&id).and_then(rect) {
                values.push((id, if axis == "y" { r.1 } else { r.0 }));
            }
        }
        let distinct: BTreeSet<i64> = values.iter().map(|(_, v)| *v).collect();
        if distinct.len() > 1 {
            let text = values
                .iter()
                .map(|(id, v)| format!("({}, {v})", py_repr(&Value::from(id.as_str()))))
                .collect::<Vec<_>>()
                .join(", ");
            findings.push(Finding::new(
                "WARNING",
                "BASELINE_MISMATCH",
                format!("{axis}-baseline mismatch: [{text}]"),
                None,
            ));
        }
    }
    findings
}

pub struct MatrixSummary {
    pub cases: usize,
    pub findings: usize,
    pub blockers: usize,
    pub by_case: Vec<(String, Vec<Finding>)>,
}

/// V1 `validate_matrix`.
pub fn validate_matrix(
    scene: &Map<String, Value>,
    root: &Path,
    matrix: &[State],
    progress: Progress<'_>,
) -> CoreResult<MatrixSummary> {
    let mut resources = DiskResources::frozen();
    let mut by_case = Vec::new();
    let (mut total, mut blockers) = (0, 0);
    for (index, state) in matrix.iter().enumerate() {
        let findings = validate_scene(scene, root, Some(state), &mut resources);
        total += findings.len();
        blockers += findings.iter().filter(|f| f.is_blocking()).count();
        by_case.push((case_name(index, state), findings));
        if !progress("validation", index + 1, matrix.len()) {
            return Err(CoreError::new(CANCELLED, "operation cancelled"));
        }
    }
    Ok(MatrixSummary {
        cases: matrix.len(),
        findings: total,
        blockers,
        by_case,
    })
}

pub fn matrix_report(summary: &MatrixSummary) -> String {
    let mut lines = vec![
        "# Batch Validation Matrix".to_string(),
        String::new(),
        format!("- Cases: **{}**", summary.cases),
        format!("- Findings: **{}**", summary.findings),
        format!("- Blockers: **{}**", summary.blockers),
        String::new(),
    ];
    for (name, findings) in &summary.by_case {
        if !findings.is_empty() {
            lines.push(format!("## {name}"));
            for f in findings {
                lines.push(format!("- **{}/{}**: {}", f.severity, f.code, f.message));
            }
            lines.push(String::new());
        }
    }
    if summary.findings == 0 {
        lines.push("PASS — all state combinations have zero findings.".into());
    }
    format!("{}\n", lines.join("\n").trim_end())
}

fn validate_frame_name(name: &str) -> CoreResult<String> {
    let bad = name.is_empty()
        || name == "."
        || name == ".."
        || name.trim_end_matches([' ', '.']) != name
        || name
            .chars()
            .any(|c| "/\\:*?\"<>|\0".contains(c) || (c as u32) < 32)
        || [
            "CON", "PRN", "AUX", "NUL", "COM1", "COM2", "COM3", "COM4", "COM5", "COM6", "COM7",
            "COM8", "COM9", "LPT1", "LPT2", "LPT3", "LPT4", "LPT5", "LPT6", "LPT7", "LPT8", "LPT9",
        ]
        .contains(&name.split('.').next().unwrap_or("").to_uppercase().as_str());
    if bad {
        return Err(CoreError::invalid(format!(
            "unsafe frame name: {}",
            py_repr(&Value::from(name))
        )));
    }
    Ok(name.to_string())
}

fn relative(path: &Path, root: &Path) -> String {
    let p = py_resolve(path);
    let base = py_resolve(root);
    match p.strip_prefix(&base) {
        Ok(rel) => posix(rel),
        Err(_) => posix(&p),
    }
}

/// `json.dumps(..., sort_keys=True, indent=2)`.
fn sorted_value(value: &Value) -> Value {
    match value {
        Value::Object(map) => {
            let mut keys: Vec<&String> = map.keys().collect();
            keys.sort_by(|a, b| a.chars().cmp(b.chars()));
            Value::Object(
                keys.into_iter()
                    .map(|k| (k.clone(), sorted_value(&map[k])))
                    .collect(),
            )
        }
        Value::Array(items) => Value::Array(items.iter().map(sorted_value).collect()),
        other => other.clone(),
    }
}

fn sorted_json_bytes(value: &Value) -> CoreResult<Vec<u8>> {
    let mut text = python_json(&sorted_value(value))?;
    text.push('\n');
    Ok(text.into_bytes())
}

/// Frames are written in concurrent batches of this many files.
const WRITE_BATCH: usize = 64;

fn element_contract(item: &Value, root: &Path) -> Value {
    let mut out = Map::new();
    for key in ["id", "type"] {
        out.insert(key.into(), item.get(key).cloned().unwrap_or(Value::Null));
    }
    out.insert(
        "visible".into(),
        Value::Bool(item.get("visible") == Some(&Value::Bool(true))),
    );
    for key in ["x", "y", "w", "h"] {
        out.insert(key.into(), item.get(key).cloned().unwrap_or(Value::Null));
    }
    let assets: Vec<Value> = item
        .get("assets")
        .and_then(Value::as_array)
        .into_iter()
        .flatten()
        .map(|p| Value::from(relative(Path::new(&py_str(p)), root)))
        .collect();
    out.insert("assets".into(), Value::Array(assets));
    for key in [
        "bind",
        "value",
        "text",
        "blend",
        "resize_policy",
        "native_w",
        "native_h",
    ] {
        if let Some(v) = item.get(key) {
            out.insert(key.into(), v.clone());
        }
    }
    Value::Object(out)
}

fn asset_entry(path: &Path, root: &Path, resources: &mut DiskResources) -> CoreResult<Value> {
    let raw = read_file(path)?;
    let mut entry =
        json!({"path": relative(path, root), "sha256": hex_digest(&raw), "bytes": raw.len()});
    let suffix = path
        .extension()
        .map(|e| e.to_string_lossy().to_lowercase())
        .unwrap_or_default();
    if ["png", "bmp", "jpg", "jpeg"].contains(&suffix.as_str()) {
        let asset = resources.bitmap(path)?;
        if let Value::Object(map) = &mut entry {
            map.insert("kind".into(), json!("bitmap"));
            map.insert("width".into(), json!(asset.width));
            map.insert("height".into(), json!(asset.height));
            map.insert("mode".into(), json!(asset.source_mode));
            map.insert("source_polarity".into(), json!(asset.source_polarity));
            map.insert("inverted_for_oled".into(), json!(asset.inverted));
            map.insert(
                "normalized_semantics".into(),
                json!("0=background, 1=OLED lit"),
            );
        }
    } else if let Value::Object(map) = &mut entry {
        map.insert("kind".into(), json!("file"));
    }
    Ok(entry)
}

fn cell(value: Option<&Value>) -> String {
    value.map(py_str).unwrap_or_default()
}

fn markdown_spec(scene: &Map<String, Value>, frames: &BTreeMap<String, Value>) -> String {
    let product = scene
        .get("product")
        .map(py_str)
        .filter(|s| !s.is_empty())
        .or_else(|| scene.get("name").map(py_str).filter(|s| !s.is_empty()));
    let name = product
        .unwrap_or_else(|| "MonoOLED Project".into())
        .trim()
        .to_string();
    let canvas = scene.get("canvas").cloned().unwrap_or(json!({}));
    let (w, h) = (
        py_int(&canvas["w"]).unwrap_or(0),
        py_int(&canvas["h"]).unwrap_or(0),
    );
    let mut lines: Vec<String> = vec![
        format!("# {name} OLED UI Specification"),
        String::new(),
        "> Generated from scene JSON. Do not edit this document as the layout source of truth.".into(),
        String::new(),
        "## Global Contract".into(),
        String::new(),
        format!("- Canvas: **{}×{}**, monochrome 1-bit.", py_str(&canvas["w"]), py_str(&canvas["h"])),
        "- Origin: `(0,0)` at top-left; X increases right, Y increases down.".into(),
        "- Bounds: `[x, x+w) × [y, y+h)`.".into(),
        format!("- Storage: **{}-byte VLSB**, {} pages × {} columns; bit0 is the top pixel of each 8-pixel page.", w * (h / 8), h / 8, py_str(&canvas["w"])),
        "- Polarity: `1 = OLED lit`, `0 = background`.".into(),
        "- Bitmap resize policy: `native_only` unless explicitly stated otherwise.".into(),
        "- Bitmap source polarity is normalized at load time: opaque black-on-white assets are inverted in memory; source files are not rewritten.".into(),
        String::new(),
        "## Scene Element Definitions".into(),
        String::new(),
        "| ID | Type | X | Y | W | H | Binding / Text |".into(),
        "|---|---|---:|---:|---:|---:|---|".into(),
    ];
    for e in scene
        .get("elements")
        .and_then(Value::as_array)
        .into_iter()
        .flatten()
    {
        let zone = e.get("zone").cloned().unwrap_or(json!({}));
        let pick = |k: &str| {
            e.get(k)
                .or_else(|| zone.get(k))
                .map(py_str)
                .unwrap_or_default()
        };
        let desc = e
            .get("bind")
            .filter(|v| truthy(v))
            .or_else(|| e.get("text").filter(|v| truthy(v)))
            .map(py_str)
            .unwrap_or_default();
        lines.push(format!(
            "| {} | {} | {} | {} | {} | {} | {} |",
            cell(e.get("id")),
            cell(e.get("type")),
            pick("x"),
            pick("y"),
            pick("w"),
            pick("h"),
            desc
        ));
    }
    lines.push(String::new());
    for (frame_name, frame) in frames {
        let mut state: Vec<(&String, &Value)> =
            frame["state"].as_object().into_iter().flatten().collect();
        state.sort_by(|a, b| a.0.cmp(b.0));
        lines.extend([
            format!("## {}", frame_name.to_uppercase()),
            String::new(),
            format!(
                "State: `{}`",
                state
                    .iter()
                    .map(|(k, v)| format!("{k}={}", py_str(v)))
                    .collect::<Vec<_>>()
                    .join(", ")
            ),
            String::new(),
            format!("Golden BIN: `golden/{frame_name}.bin`  "),
            format!("Reference PNG: `reference/{frame_name}.png`  "),
            format!("SHA-256: `{}`", py_str(&frame["golden_sha256"])),
            String::new(),
            "| ID | Type | X | Y | W | H | Asset / Text |".into(),
            "|---|---|---:|---:|---:|---:|---|".into(),
        ]);
        for item in frame["elements"].as_array().into_iter().flatten() {
            if item["visible"] != Value::Bool(true) {
                continue;
            }
            let asset_or_text = item
                .get("text")
                .filter(|v| truthy(v))
                .map(py_str)
                .unwrap_or_else(|| {
                    item.get("assets")
                        .and_then(Value::as_array)
                        .into_iter()
                        .flatten()
                        .map(py_str)
                        .collect::<Vec<_>>()
                        .join(", ")
                });
            lines.push(format!(
                "| {} | {} | {} | {} | {} | {} | {asset_or_text} |",
                py_str(&item["id"]),
                py_str(&item["type"]),
                cell(item.get("x")),
                cell(item.get("y")),
                cell(item.get("w")),
                cell(item.get("h"))
            ));
        }
        lines.push(String::new());
    }
    format!("{}\n", lines.join("\n").trim_end())
}

fn truthy(value: &Value) -> bool {
    match value {
        Value::Null => false,
        Value::Bool(b) => *b,
        Value::Number(n) => n.as_f64().is_some_and(|f| f != 0.0),
        Value::String(s) => !s.is_empty(),
        Value::Array(a) => !a.is_empty(),
        Value::Object(o) => !o.is_empty(),
    }
}

fn validation_markdown(all: &BTreeMap<String, Vec<Finding>>) -> String {
    let total: usize = all.values().map(Vec::len).sum();
    let blockers: usize = all.values().flatten().filter(|f| f.is_blocking()).count();
    let mut lines = vec![
        "# OLED UI Validation Report".to_string(),
        String::new(),
        format!("- Frames checked: **{}**", all.len()),
        format!("- Findings: **{total}**"),
        format!("- Blocking findings: **{blockers}**"),
        String::new(),
    ];
    for (name, findings) in all {
        lines.push(format!("## {name}"));
        if findings.is_empty() {
            lines.extend([String::new(), "PASS — no findings.".into(), String::new()]);
            continue;
        }
        lines.push(String::new());
        for f in findings {
            let suffix = f
                .element_id
                .as_ref()
                .filter(|s| !s.is_empty())
                .map(|id| format!(" (`{id}`)"))
                .unwrap_or_default();
            lines.push(format!(
                "- **{} / {}**{suffix}: {}",
                f.severity, f.code, f.message
            ));
        }
        lines.push(String::new());
    }
    format!("{}\n", lines.join("\n").trim_end())
}

/// One rendered frame PNG: `L` 0/255 converted to mode `1` (V1 `_save_png`).
pub fn frame_png(rows: &[Vec<u8>], width: usize, height: usize) -> CoreResult<Vec<u8>> {
    encode_bitmap_png(width, height, rows)
}

pub struct ExportSummary {
    pub output_dir: PathBuf,
    pub frame_count: usize,
    pub frame_hashes: BTreeMap<String, String>,
    pub findings: BTreeMap<String, Vec<Finding>>,
}

fn prune(directory: &Path, suffix: &str, keep: &BTreeSet<String>) {
    fn walk(dir: &Path, base: &Path, suffix: &str, keep: &BTreeSet<String>) {
        let Ok(entries) = std::fs::read_dir(dir) else {
            return;
        };
        for entry in entries.flatten() {
            let path = entry.path();
            // Never follow or delete through symlinks/junctions: they may point outside the export.
            let Ok(kind) = entry.file_type() else {
                continue;
            };
            if kind.is_symlink() {
                continue;
            }
            if kind.is_dir() {
                walk(&path, base, suffix, keep);
                let _ = std::fs::remove_dir(&path);
            } else if path.to_string_lossy().ends_with(suffix) {
                let rel = path.strip_prefix(base).map(posix).unwrap_or_default();
                if !keep.contains(&rel) {
                    let _ = std::fs::remove_file(&path);
                }
            }
        }
    }
    walk(directory, directory, suffix, keep);
}

/// V1 `export_scene`. `states` are `(name, state)` pairs in matrix order.
pub fn export_scene(
    scene: &Map<String, Value>,
    root: &Path,
    output_dir: &Path,
    states: &[(String, State)],
    progress: Progress<'_>,
) -> CoreResult<ExportSummary> {
    let mut folded: BTreeMap<String, String> = BTreeMap::new();
    for (name, _) in states {
        let safe = validate_frame_name(name)?;
        let key = safe.to_lowercase();
        if let Some(previous) = folded.get(&key) {
            if previous != &safe {
                return Err(CoreError::invalid(format!(
                    "frame name collision on Windows: {} vs {}",
                    py_repr(&Value::from(previous.as_str())),
                    py_repr(&Value::from(safe.as_str()))
                )));
            }
        }
        folded.insert(key, safe);
    }
    let reference_dir = output_dir.join("reference");
    let golden_dir = output_dir.join("golden");
    for dir in [&reference_dir, &golden_dir] {
        std::fs::create_dir_all(dir).map_err(|e| crate::resources::io_error(dir, &e))?;
    }
    let mut resources = DiskResources::frozen();
    let total_steps = (states.len() * 2).max(1);
    let mut all: BTreeMap<String, Vec<Finding>> = BTreeMap::new();
    for (index, (name, state)) in states.iter().enumerate() {
        all.insert(
            name.clone(),
            validate_scene(scene, root, Some(state), &mut resources),
        );
        if !progress("export.validation", index + 1, total_steps) {
            return Err(CoreError::new(CANCELLED, "operation cancelled"));
        }
    }
    if all.values().any(|f| has_blockers(f)) {
        atomic_write(
            &output_dir.join("validation_report.md"),
            validation_markdown(&all).as_bytes(),
        )?;
        return Err(CoreError::new(
            EXPORT_BLOCKED,
            format!(
                "export blocked; see {}",
                display(&output_dir.join("validation_report.md"))
            ),
        ));
    }
    let canvas = scene.get("canvas").cloned().unwrap_or(json!({}));
    let (width, height) = (
        py_int(&canvas["w"]).unwrap_or(0),
        py_int(&canvas["h"]).unwrap_or(0),
    );
    let expected = width.max(0).saturating_mul(height.max(0) / 8) as usize;
    let mut frames: BTreeMap<String, Value> = BTreeMap::new();
    let mut hashes = BTreeMap::new();
    let mut used: BTreeSet<PathBuf> = BTreeSet::new();
    let mut sorted: Vec<&(String, State)> = states.iter().collect();
    sorted.sort_by(|a, b| a.0.chars().cmp(b.0.chars()));
    // Every file is an independent atomic write; batching only overlaps fsyncs.
    let mut pending: Vec<(PathBuf, Vec<u8>)> = Vec::new();
    for (render_index, (name, state)) in sorted.iter().enumerate() {
        let result = render_scene(scene, root, state, &mut resources)?;
        let raw = result.framebuffer.to_vlsb()?;
        if raw.len() != expected {
            return Err(CoreError::new(
                EXPORT_BLOCKED,
                format!("{name}: framebuffer length {} != {expected}", raw.len()),
            ));
        }
        pending.push((golden_dir.join(format!("{name}.bin")), raw.clone()));
        let rows: Vec<Vec<u8>> = result.framebuffer.rows().map(<[u8]>::to_vec).collect();
        pending.push((
            reference_dir.join(format!("{name}.png")),
            frame_png(
                &rows,
                result.framebuffer.width(),
                result.framebuffer.height(),
            )?,
        ));
        if pending.len() >= WRITE_BATCH {
            atomic_write_many(&pending)?;
            pending.clear();
        }
        let digest = hex_digest(&raw);
        hashes.insert(name.clone(), digest.clone());
        used.extend(result.used_files.iter().map(|p| py_resolve(p)));
        let mut sorted_state: Vec<(&String, &Value)> = state.iter().collect();
        sorted_state.sort_by(|a, b| a.0.cmp(b.0));
        let lit: usize = result
            .framebuffer
            .pixels()
            .iter()
            .map(|v| usize::from(*v))
            .sum();
        frames.insert(name.clone(), json!({
            "state": Value::Object(sorted_state.into_iter().map(|(k, v)| (k.clone(), v.clone())).collect()),
            "golden": format!("golden/{name}.bin"),
            "reference": format!("reference/{name}.png"),
            "golden_sha256": digest,
            "lit_pixels": lit,
            "elements": result.resolved_elements.iter().map(|item| element_contract(item, root)).collect::<Vec<_>>(),
        }));
        if !progress(
            "export.render",
            states.len() + render_index + 1,
            total_steps,
        ) {
            return Err(CoreError::new(CANCELLED, "operation cancelled"));
        }
    }
    let scene_input: Map<String, Value> = scene
        .iter()
        .filter(|(k, _)| !k.starts_with('_'))
        .map(|(k, v)| (k.clone(), v.clone()))
        .collect();
    let contract = json!({
        "schema_version": 1,
        "product": scene.get("product").cloned().unwrap_or(Value::Null),
        "coordinate_contract": {"origin": "top-left", "x_direction": "right", "y_direction": "down", "bounds": "[x, x+w) × [y, y+h)", "integer_coordinates": true},
        "framebuffer_contract": {"width": width, "height": height, "bytes": expected, "layout": "VLSB page-major", "byte_offset": "(y // 8) * width + x", "bit": "1 << (y % 8)", "polarity": "1 = lit"},
        "scene": scene_input,
        "frames": Value::Object(frames.iter().map(|(k, v)| (k.clone(), v.clone())).collect()),
    });
    pending.push((
        output_dir.join("ui_contract.json"),
        sorted_json_bytes(&contract)?,
    ));
    let mut used_sorted: Vec<PathBuf> = used.into_iter().collect();
    used_sorted.sort_by_key(|p| relative(p, root));
    let mut assets = Vec::new();
    for path in &used_sorted {
        assets.push(asset_entry(path, root, &mut resources)?);
    }
    pending.push((
        output_dir.join("asset_manifest.json"),
        sorted_json_bytes(&json!({"schema_version": 1, "assets": assets}))?,
    ));
    pending.push((
        output_dir.join("UI_SPEC.md"),
        markdown_spec(scene, &frames).into_bytes(),
    ));
    pending.push((
        output_dir.join("validation_report.md"),
        validation_markdown(&all).into_bytes(),
    ));
    atomic_write_many(&pending)?;
    let names: BTreeSet<String> = states.iter().map(|(n, _)| n.clone()).collect();
    prune(
        &golden_dir,
        ".bin",
        &names.iter().map(|n| format!("{n}.bin")).collect(),
    );
    prune(
        &reference_dir,
        ".png",
        &names.iter().map(|n| format!("{n}.png")).collect(),
    );
    Ok(ExportSummary {
        output_dir: output_dir.to_path_buf(),
        frame_count: frames.len(),
        frame_hashes: hashes,
        findings: all,
    })
}

/// V1 `build_thumbnail_wall`. Labels use the built-in 5x7 font (V1 uses Pillow's
/// default font); only the canvas size is checked against V1.
pub fn build_thumbnail_wall(
    images: &[PathBuf],
    output: &Path,
    columns: usize,
    scale: usize,
) -> CoreResult<()> {
    const GAP: usize = 16;
    const LABEL: usize = 18;
    if images.is_empty() {
        return Err(CoreError::invalid(
            "thumbnail wall requires at least one image",
        ));
    }
    let decoded: Vec<_> = images
        .iter()
        .map(|p| read_file(p).and_then(|b| decode_image(&b)))
        .collect::<CoreResult<_>>()?;
    let cell_w = decoded.iter().map(|i| i.width).max().unwrap_or(0) * scale;
    let cell_h = decoded.iter().map(|i| i.height).max().unwrap_or(0) * scale + LABEL;
    let rows = decoded.len().div_ceil(columns);
    let (width, height) = (
        columns * cell_w + (columns + 1) * GAP,
        rows * cell_h + (rows + 1) * GAP,
    );
    let mut canvas = vec![0u8; width * height * 4];
    for px in canvas.chunks_mut(4) {
        px.copy_from_slice(&[245, 245, 247, 255]);
    }
    for (i, (path, image)) in images.iter().zip(&decoded).enumerate() {
        let (row, col) = (i / columns, i % columns);
        let (x0, y0) = (GAP + col * (cell_w + GAP), GAP + row * (cell_h + GAP));
        for y in 0..image.height * scale {
            for x in 0..image.width * scale {
                let p = &image.rgba[((y / scale) * image.width + x / scale) * 4..][..4];
                let luma =
                    (u32::from(p[0]) * 299 + u32::from(p[1]) * 587 + u32::from(p[2]) * 114) / 1000;
                let v = if luma >= 128 { 255 } else { 0 };
                let o = ((y0 + y) * width + x0 + x) * 4;
                canvas[o..o + 4].copy_from_slice(&[v, v, v, 255]);
            }
        }
        let label = path
            .file_stem()
            .map(|s| s.to_string_lossy().to_uppercase())
            .unwrap_or_default();
        let (mut lx, ly) = (x0, y0 + cell_h - LABEL + 2);
        for ch in label.chars() {
            if has_builtin_glyph(ch) {
                if let Ok(glyph) = builtin_glyph_rows(ch, (5, 7), Some(6)) {
                    for (gy, r) in glyph.iter().enumerate() {
                        for (gx, v) in r.iter().enumerate() {
                            let (px, py) = (lx + gx, ly + gy);
                            if *v != 0 && px < width && py < height {
                                let o = (py * width + px) * 4;
                                canvas[o..o + 4].copy_from_slice(&[29, 29, 31, 255]);
                            }
                        }
                    }
                }
            }
            lx += 6;
        }
    }
    atomic_write(output, &encode_rgba_png(width, height, &canvas)?)
}

/// Asset health (V1 `AssetLibrary.scan` + `health_report`), PNG only.
pub struct AssetHealth {
    pub duplicates: Vec<Vec<String>>,
    pub unused: Vec<String>,
    pub invalid: Vec<(String, String)>,
}

pub fn asset_health(
    root: &Path,
    asset_dirs: &[String],
    used: &BTreeSet<String>,
) -> CoreResult<AssetHealth> {
    let root = py_resolve(root);
    let mut entries: Vec<(String, Option<String>, String)> = Vec::new();
    for dir in asset_dirs {
        let base = resolve_under_root(&root, dir, "asset directory")?;
        if !base.is_dir() {
            continue;
        }
        let mut files = Vec::new();
        fn walk(dir: &Path, out: &mut Vec<PathBuf>) {
            for entry in std::fs::read_dir(dir).into_iter().flatten().flatten() {
                let path = entry.path();
                out.push(path.clone());
                // Like Python's rglob: do not recurse through directory links.
                if entry.file_type().is_ok_and(|k| k.is_dir()) {
                    walk(&path, out);
                }
            }
        }
        walk(&base, &mut files);
        files.sort_by_key(|p| posix(p).to_lowercase());
        for path in files {
            let suffix = path
                .extension()
                .map(|e| e.to_string_lossy().to_lowercase())
                .unwrap_or_default();
            if (suffix != "png" && suffix != "bmp") || !path.is_file() {
                continue;
            }
            let resolved = py_resolve(&path);
            let Ok(rel) = resolved.strip_prefix(&root) else {
                continue;
            };
            let rel = posix(rel);
            match DiskResources::decode_bitmap(&resolved, &read_file(&resolved)?) {
                Ok(asset) => {
                    let mut bytes = (asset.width as u32).to_le_bytes().to_vec();
                    bytes.extend((asset.height as u32).to_le_bytes());
                    bytes.extend(asset.rows.iter().flatten());
                    entries.push((rel, Some(hex_digest(&bytes)), String::new()));
                }
                Err(error) => entries.push((rel, None, error.message)),
            }
        }
    }
    let mut by_hash: BTreeMap<String, Vec<String>> = BTreeMap::new();
    let mut invalid = Vec::new();
    for (rel, hash, error) in &entries {
        match hash {
            Some(h) => by_hash.entry(h.clone()).or_default().push(rel.clone()),
            None => invalid.push((rel.clone(), error.clone())),
        }
    }
    let mut groups: Vec<Vec<String>> = by_hash.into_values().collect();
    groups.sort_by(|a, b| a[0].cmp(&b[0]));
    let duplicates = groups.into_iter().filter(|g| g.len() > 1).collect();
    let mut unused: Vec<String> = entries
        .iter()
        .map(|e| e.0.clone())
        .filter(|r| !used.contains(r))
        .collect();
    unused.sort();
    invalid.sort();
    Ok(AssetHealth {
        duplicates,
        unused,
        invalid,
    })
}

/// Deterministic ZIP: sorted entries, 1980-01-01 timestamps, deflate, mode 0644.
pub fn deterministic_zip(source: &Path, target: &Path) -> CoreResult<()> {
    let mut files = Vec::new();
    fn walk(dir: &Path, out: &mut Vec<PathBuf>) {
        for entry in std::fs::read_dir(dir).into_iter().flatten().flatten() {
            let path = entry.path();
            match entry.file_type() {
                Ok(kind) if kind.is_dir() => walk(&path, out),
                Ok(kind) if kind.is_file() => out.push(path),
                _ => {}
            }
        }
    }
    walk(source, &mut files);
    files.sort_by_key(|p| posix(p.strip_prefix(source).unwrap_or(p)));
    let mut buffer = std::io::Cursor::new(Vec::new());
    {
        let mut zip = zip::ZipWriter::new(&mut buffer);
        let options = zip::write::SimpleFileOptions::default()
            .compression_method(zip::CompressionMethod::Deflated)
            .compression_level(Some(9))
            .last_modified_time(zip::DateTime::default())
            .unix_permissions(0o644);
        for path in files {
            let rel = posix(path.strip_prefix(source).unwrap_or(&path));
            zip.start_file(rel, options)
                .map_err(|e| CoreError::new("E-ZIP", e.to_string()))?;
            zip.write_all(&read_file(&path)?)
                .map_err(|e| CoreError::new("E-ZIP", e.to_string()))?;
        }
        zip.finish()
            .map_err(|e| CoreError::new("E-ZIP", e.to_string()))?;
    }
    atomic_write(target, &buffer.into_inner())
}

const HANDOFF_README: &str = "# OLED UI Code AI Handoff\n\nImplementation truth order:\n\n1. `ui_contract.json` — machine-readable geometry/state contract.\n2. `golden/*.bin` — pixel truth; compare framebuffer byte-for-byte.\n3. `UI_SPEC.md` — human-readable implementation guide.\n4. `validation_report.md`, `batch_validation.md`, and `design_rules.md` — release gates.\n5. `thumbnail_wall.png` — fast visual review; never use it to infer coordinates.\n6. `c_headers/*.h` — optional VLSB asset/frame arrays generated from Golden truth.\n\nDo not infer coordinates from screenshots when contract JSON is available.\n";

/// V1 `build_handoff_package`.
pub fn build_handoff_package(
    scene: &Map<String, Value>,
    root: &Path,
    output_zip: &Path,
    states: &[(String, State)],
    policy: IntegerPolicy,
    progress: Progress<'_>,
) -> CoreResult<ExportSummary> {
    let work = std::env::temp_dir().join(format!(
        "mono-handoff-{}-{}",
        std::process::id(),
        hex_digest(posix(output_zip).as_bytes())
            .get(..12)
            .unwrap_or("x")
    ));
    let _ = std::fs::remove_dir_all(&work);
    std::fs::create_dir_all(&work).map_err(|e| crate::resources::io_error(&work, &e))?;
    let result = (|| {
        let summary = export_scene(scene, root, &work, states, &mut |stage, done, total| {
            let ratio = if total == 0 {
                0.0
            } else {
                done as f64 / total as f64
            };
            progress(
                &format!("handoff.{stage}"),
                (ratio * 650.0).round() as usize,
                1000,
            )
        })?;
        let matrix = build_state_matrix(scene, policy)?;
        let matrix_summary = validate_matrix(scene, root, &matrix, &mut |stage, done, total| {
            let ratio = if total == 0 {
                0.0
            } else {
                done as f64 / total as f64
            };
            progress(
                &format!("handoff.{stage}"),
                650 + (ratio * 150.0).round() as usize,
                1000,
            )
        })?;
        atomic_write(
            &work.join("batch_validation.md"),
            matrix_report(&matrix_summary).as_bytes(),
        )?;
        let references: Vec<PathBuf> = states
            .iter()
            .map(|(n, _)| work.join("reference").join(format!("{n}.png")))
            .collect();
        if !references.is_empty() {
            build_thumbnail_wall(
                &references,
                &work.join("thumbnail_wall.png"),
                references.len().clamp(1, 4),
                4,
            )?;
        }
        let headers = work.join("c_headers");
        let mut resources = DiskResources::frozen();
        for (name, state) in states {
            let fb = render_scene(scene, root, state, &mut resources)?.framebuffer;
            atomic_write(
                &headers.join(format!("{name}.h")),
                framebuffer_to_c_header(&fb, &format!("oled_{name}"))?.as_bytes(),
            )?;
        }
        let rules = check_design_rules(scene, scene.get("_design_rules").unwrap_or(&json!({})));
        let mut lines = vec![
            "# Design Rule Check".to_string(),
            String::new(),
            format!("- Findings: **{}**", rules.len()),
            String::new(),
        ];
        if rules.is_empty() {
            lines.push("PASS — no configured design-rule findings.".into());
        }
        for f in &rules {
            let id = f
                .element_id
                .as_ref()
                .filter(|s| !s.is_empty())
                .map(|id| format!(" [{id}]"))
                .unwrap_or_default();
            lines.push(format!(
                "- **{}/{}**{id}: {}",
                f.severity, f.code, f.message
            ));
        }
        atomic_write(
            &work.join("design_rules.md"),
            format!("{}\n", lines.join("\n").trim_end()).as_bytes(),
        )?;
        let asset_dirs: Vec<String> = match scene
            .get("_asset_dirs")
            .and_then(Value::as_array)
            .filter(|a| !a.is_empty())
        {
            Some(dirs) => dirs.iter().map(py_str).collect(),
            None if root.join("assets").exists() => vec!["assets".into()],
            None => Vec::new(),
        };
        if !asset_dirs.is_empty() {
            let mut used = BTreeSet::new();
            for (_, state) in states {
                for path in render_scene(scene, root, state, &mut resources)?.used_files {
                    if let Ok(rel) = py_resolve(&path).strip_prefix(py_resolve(root)) {
                        used.insert(posix(rel));
                    }
                }
            }
            let health = asset_health(root, &asset_dirs, &used)?;
            let mut lines = vec![
                "# Asset Health".to_string(),
                String::new(),
                format!("- Duplicate groups: **{}**", health.duplicates.len()),
                format!("- Unused assets: **{}**", health.unused.len()),
                format!("- Invalid assets: **{}**", health.invalid.len()),
                String::new(),
            ];
            for group in &health.duplicates {
                lines.push(format!(
                    "- Duplicate: {}",
                    group
                        .iter()
                        .map(|p| format!("`{p}`"))
                        .collect::<Vec<_>>()
                        .join(", ")
                ));
            }
            atomic_write(
                &work.join("asset_health.md"),
                format!("{}\n", lines.join("\n").trim_end()).as_bytes(),
            )?;
        }
        atomic_write(&work.join("HANDOFF_README.md"), HANDOFF_README.as_bytes())?;
        progress("handoff.package", 980, 1000);
        deterministic_zip(&work, output_zip)?;
        progress("handoff.completed", 1000, 1000);
        Ok(summary)
    })();
    let _ = std::fs::remove_dir_all(&work);
    result
}
