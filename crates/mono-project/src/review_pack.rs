//! Deterministic single-file review pack: screens, frames, code views and
//! annotations in one offline HTML file that firmware/hardware reviewers can
//! open without the app or the project.
//!
//! Everything in the file is derived: frame hashes come from the same renderer
//! as `ui_contract.json`, and the page states plainly that this product has a
//! single renderer (no L2 two-implementation claim).

use std::collections::{BTreeMap, BTreeSet};
use std::path::{Path, PathBuf};

use mono_core::c_header::framebuffer_to_c_header;
use mono_core::render::{posix, render_scene};
use mono_core::state::init_state;
use mono_core::{CoreError, CoreResult};
use serde_json::{Map, Value, json};

use crate::atomic::atomic_write;
use crate::export::{Progress, validate_scene};
use crate::project::ProjectWorkspace;
use crate::resources::{DiskResources, hex_digest};
use crate::review::Annotation;
use crate::scene_io::load_project_scene;

/// Annotated states rendered per screen, beyond the init frame.
pub const MAX_ANNOTATED_FRAMES: usize = 8;

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ReviewPackSummary {
    pub output: PathBuf,
    pub screens: usize,
    pub frames: usize,
    pub annotations: usize,
    pub blocking: usize,
    pub bytes: usize,
    pub sha256: String,
}

struct Frame {
    label: String,
    state: Map<String, Value>,
    sha256: String,
    lit: usize,
    vlsb: Vec<u8>,
    c_header: String,
    findings: Vec<Value>,
    elements: Vec<Value>,
}

/// Build the pack and write it atomically. Two runs with the same project and
/// review file produce byte-identical output.
pub fn build_review_pack(
    project: &ProjectWorkspace,
    annotations: &[Annotation],
    output: &Path,
    progress: Progress<'_>,
) -> CoreResult<ReviewPackSummary> {
    let screens = sorted_screens(project);
    let total = screens.len().max(1);
    let mut resources = DiskResources::frozen();
    let mut screens_json = Vec::new();
    let mut frames_total = 0;
    let mut blocking_total = 0;
    for (index, screen) in screens.iter().enumerate() {
        let scene = match load_project_scene(project, Some(&screen.id)) {
            Ok(scene) => scene,
            Err(error) => {
                return Err(CoreError::new(
                    "E-REVIEW-PACK",
                    format!("{}: {}", screen.id, error.message),
                ));
            }
        };
        let mut states: Vec<Map<String, Value>> = vec![init_state(&scene.data)];
        let mut seen: BTreeSet<String> = BTreeSet::new();
        for annotation in annotations.iter().filter(|a| a.screen == screen.id) {
            if !annotation.state.is_empty() {
                let key = canonical_state(&annotation.state);
                if seen.insert(key) && states.len() <= MAX_ANNOTATED_FRAMES {
                    states.push(annotation.state.clone());
                }
            }
        }
        let mut frames = Vec::new();
        let mut init_blocking = 0;
        let mut init_warnings = 0;
        for (state_index, state) in states.iter().enumerate() {
            let result = render_scene(&scene.data, &project.root, state, &mut resources)?;
            let vlsb = result.framebuffer.to_vlsb()?;
            let lit = vlsb.iter().map(|byte| byte.count_ones() as usize).sum();
            let findings = validate_scene(&scene.data, &project.root, Some(state), &mut resources);
            if state_index == 0 {
                init_blocking = findings
                    .iter()
                    .filter(|finding| finding.is_blocking())
                    .count();
                init_warnings = findings.len().saturating_sub(init_blocking);
            }
            let findings_json: Vec<Value> = findings
                .iter()
                .map(|finding| {
                    json!({
                        "severity": finding.severity,
                        "code": finding.code,
                        "message": finding.message,
                        "element": finding.element_id,
                    })
                })
                .collect();
            let elements = result
                .resolved_elements
                .iter()
                .map(|element| {
                    json!({
                        "id": element.get("id").cloned().unwrap_or(Value::Null),
                        "type": element.get("type").cloned().unwrap_or(Value::Null),
                        "x": element.get("x").cloned().unwrap_or(Value::Null),
                        "y": element.get("y").cloned().unwrap_or(Value::Null),
                        "w": element.get("w").cloned().unwrap_or(Value::Null),
                        "h": element.get("h").cloned().unwrap_or(Value::Null),
                        "visible": element.get("visible").cloned().unwrap_or(Value::Bool(true)),
                    })
                })
                .collect();
            frames.push(Frame {
                label: if state_index == 0 {
                    "init".to_string()
                } else {
                    format!("state {state_index}")
                },
                state: state.clone(),
                sha256: hex_digest(&vlsb),
                lit,
                vlsb,
                c_header: framebuffer_to_c_header(&result.framebuffer, "ui_frame")?,
                findings: findings_json,
                elements,
            });
        }
        blocking_total += init_blocking;
        frames_total += frames.len();
        let frames: Vec<Value> = frames
            .into_iter()
            .map(|frame| {
                json!({
                    "label": frame.label,
                    "state": Value::Object(frame.state),
                    "sha256": frame.sha256,
                    "lit_pixels": frame.lit,
                    "bytes": frame.vlsb.len(),
                    "vlsb": base64(&frame.vlsb),
                    "hex": hex_spaced(&frame.vlsb),
                    "c_header": frame.c_header,
                    "findings": frame.findings,
                    "elements": frame.elements,
                })
            })
            .collect();
        screens_json.push(json!({
            "id": screen.id,
            "label": screen.label,
            "category": screen.category,
            "blockers": init_blocking,
            "warnings": init_warnings,
            "canvas": scene.data.get("canvas").cloned().unwrap_or(Value::Null),
            "frames": frames,
        }));
        if !progress("review.screens", index + 1, total) {
            return Err(CoreError::new(
                crate::export::CANCELLED,
                "operation cancelled",
            ));
        }
    }
    let mut annotation_rows: Vec<Value> = annotations
        .iter()
        .map(|annotation| {
            json!({
                "id": annotation.id,
                "kind": annotation.kind.as_str(),
                "screen": annotation.screen,
                "state": Value::Object(sorted_state(&annotation.state)),
                "element": annotation.element,
                "title": annotation.title,
                "body": annotation.body,
                "evidence": {
                    "sha256": annotation.evidence.sha256,
                    "lit_pixels": annotation.evidence.lit_pixels,
                    "source": annotation.evidence.source,
                },
                "created_utc": annotation.created_utc,
                "updated_utc": annotation.updated_utc,
            })
        })
        .collect();
    annotation_rows.sort_by_key(annotation_sort_key);
    let pack = json!({
        "schema_version": 1,
        "product": project.name(),
        "version": env!("CARGO_PKG_VERSION"),
        "renderer": {
            "name": "MonoOLED Studio canonical renderer",
            "second_implementation": false,
            "note": "Frames come from the same renderer that writes ui_contract.json. \
                     This product has one renderer, so this pack makes no L2 claim.",
        },
        "coordinate_contract": {
            "origin": "top-left",
            "x_direction": "right",
            "y_direction": "down",
            "bounds": "[x, x+w) × [y, y+h)",
            "integer_coordinates": true,
        },
        "framebuffer_contract": {
            "layout": "VLSB page-major",
            "byte_offset": "(y // 8) * width + x",
            "bit": "1 << (y % 8)",
            "polarity": "1 = lit",
        },
        "design_rules": project.data.get("design_rules").cloned().unwrap_or(json!({})),
        "screens": screens_json,
        "annotations": annotation_rows,
        "totals": {
            "screens": screens.len(),
            "frames": frames_total,
            "annotations": annotations.len(),
            "blocking": blocking_total,
        },
    });
    let data = script_json(&pack)?;
    let html = HTML_TEMPLATE.replace("__PACK_DATA__", &data);
    let bytes = html.as_bytes();
    if let Some(parent) = output.parent() {
        std::fs::create_dir_all(parent).map_err(|error| {
            CoreError::new("E-REVIEW-PACK", format!("{}: {error}", posix(parent)))
        })?;
    }
    atomic_write(output, bytes)?;
    Ok(ReviewPackSummary {
        output: output.to_path_buf(),
        screens: screens.len(),
        frames: frames_total,
        annotations: annotations.len(),
        blocking: blocking_total,
        bytes: bytes.len(),
        sha256: hex_digest(bytes),
    })
}

struct ScreenRow {
    id: String,
    label: String,
    category: String,
}

fn sorted_screens(project: &ProjectWorkspace) -> Vec<ScreenRow> {
    let categories: BTreeMap<String, String> = project
        .data
        .get("screens")
        .and_then(Value::as_array)
        .into_iter()
        .flatten()
        .filter_map(|screen| {
            let id = screen.get("id").and_then(Value::as_str)?;
            let category = screen.get("category").and_then(Value::as_str)?;
            (!category.trim().is_empty()).then(|| (id.to_string(), category.trim().to_string()))
        })
        .collect();
    let mut rows: Vec<ScreenRow> = project
        .screens()
        .into_iter()
        .map(|screen| ScreenRow {
            category: categories
                .get(&screen.id)
                .cloned()
                .unwrap_or_else(|| category_for(&screen.id)),
            id: screen.id,
            label: screen.label,
        })
        .collect();
    rows.sort_by(|a, b| {
        a.category
            .chars()
            .cmp(b.category.chars())
            .then_with(|| a.label.chars().cmp(b.label.chars()))
            .then_with(|| a.id.chars().cmp(b.id.chars()))
    });
    rows
}

fn category_for(id: &str) -> String {
    match id.split_once(['_', '-', '.']) {
        Some((prefix, _)) if !prefix.is_empty() => prefix.to_string(),
        _ => "Screens".to_string(),
    }
}

/// JSON object with sorted keys, used as the dedup key for states.
fn canonical_state(state: &Map<String, Value>) -> String {
    serde_json::to_string(&Value::Object(sorted_state(state))).unwrap_or_default()
}

fn sorted_state(state: &Map<String, Value>) -> Map<String, Value> {
    state
        .iter()
        .map(|(key, value)| (key.clone(), value.clone()))
        .collect::<BTreeMap<_, _>>()
        .into_iter()
        .collect()
}

fn annotation_sort_key(annotation: &Value) -> (String, String, String, String, String) {
    let text = |key: &str| {
        annotation
            .get(key)
            .and_then(Value::as_str)
            .unwrap_or_default()
            .to_string()
    };
    (
        text("screen"),
        annotation
            .get("state")
            .and_then(Value::as_object)
            .map(canonical_state)
            .unwrap_or_default(),
        text("element"),
        text("kind"),
        text("id"),
    )
}

/// RFC 4648 base64 with padding; written out so the pack has no new dependency.
pub fn base64(data: &[u8]) -> String {
    const ALPHABET: &[u8; 64] = b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
    let mut out = String::with_capacity(data.len().div_ceil(3) * 4);
    for chunk in data.chunks(3) {
        let b0 = chunk[0] as u32;
        let b1 = chunk.get(1).copied().unwrap_or(0) as u32;
        let b2 = chunk.get(2).copied().unwrap_or(0) as u32;
        let triple = (b0 << 16) | (b1 << 8) | b2;
        out.push(ALPHABET[((triple >> 18) & 0x3f) as usize] as char);
        out.push(ALPHABET[((triple >> 12) & 0x3f) as usize] as char);
        if chunk.len() > 1 {
            out.push(ALPHABET[((triple >> 6) & 0x3f) as usize] as char);
        } else {
            out.push('=');
        }
        if chunk.len() > 2 {
            out.push(ALPHABET[(triple & 0x3f) as usize] as char);
        } else {
            out.push('=');
        }
    }
    out
}

/// Python `bytes.hex(' ')`, matching the code view in the app.
fn hex_spaced(data: &[u8]) -> String {
    data.iter()
        .map(|byte| format!("{byte:02x}"))
        .collect::<Vec<_>>()
        .join(" ")
}

/// JSON that is safe inside `<script>`: `<`, `>`, `&` and the JS line
/// separators are escaped, so annotation text cannot close the tag.
fn script_json(value: &Value) -> CoreResult<String> {
    let text = serde_json::to_string(value)
        .map_err(|error| CoreError::new("E-REVIEW-PACK", error.to_string()))?;
    Ok(text
        .replace('<', "\\u003c")
        .replace('>', "\\u003e")
        .replace('&', "\\u0026")
        .replace('\u{2028}', "\\u2028")
        .replace('\u{2029}', "\\u2029"))
}

const HTML_TEMPLATE: &str = r#"<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>MonoOLED review pack</title>
<style>
:root { color-scheme: dark; --bg:#0d0f10; --panel:#16191b; --line:#2a2f33; --text:#e8ecef;
        --muted:#9aa3a8; --accent:#7fd4c1; --bad:#e57373; --warn:#e0b252; --ok:#7fce8a; }
* { box-sizing: border-box; }
body { margin:0; background:var(--bg); color:var(--text);
       font:14px/1.5 "Segoe UI", system-ui, sans-serif; }
header { padding:18px 24px; border-bottom:1px solid var(--line); display:flex; gap:16px; align-items:baseline; }
header h1 { font-size:18px; margin:0; }
header .meta { color:var(--muted); font-size:13px; }
main { display:grid; grid-template-columns:300px 1fr; min-height:calc(100vh - 66px); }
aside { border-right:1px solid var(--line); padding:14px; overflow:auto; }
aside input[type=search] { width:100%; padding:8px; background:var(--panel);
       border:1px solid var(--line); color:var(--text); border-radius:6px; }
.filters { display:flex; gap:6px; margin:10px 0; }
.filters button { flex:1; padding:6px; background:var(--panel); color:var(--muted);
       border:1px solid var(--line); border-radius:6px; cursor:pointer; }
.filters button.on { color:var(--text); border-color:var(--accent); }
.group { color:var(--muted); font-size:12px; text-transform:uppercase; letter-spacing:.06em; margin:14px 0 6px; }
.screen { padding:8px 10px; border-radius:6px; cursor:pointer; display:flex; gap:8px; align-items:center; }
.screen:hover { background:var(--panel); }
.screen.on { background:var(--panel); outline:1px solid var(--line); }
.screen .name { flex:1; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.pill { font-size:11px; padding:1px 7px; border-radius:999px; border:1px solid var(--line); }
.pill.bad { color:var(--bad); border-color:var(--bad); }
.pill.ok { color:var(--ok); border-color:var(--ok); }
section.view { padding:20px 24px; overflow:auto; }
h2 { font-size:16px; margin:0 0 4px; }
.sub { color:var(--muted); font-size:13px; margin-bottom:14px; }
.frames { display:flex; gap:6px; flex-wrap:wrap; margin-bottom:14px; }
.frames button { padding:5px 10px; background:var(--panel); color:var(--muted);
       border:1px solid var(--line); border-radius:6px; cursor:pointer; }
.frames button.on { color:var(--text); border-color:var(--accent); }
.tabs { display:flex; gap:6px; margin-bottom:10px; }
.tabs button.on { color:var(--accent); }
.grid { display:grid; grid-template-columns:minmax(260px, 1fr) 1fr; gap:16px; align-items:start; }
canvas { width:100%; background:#000; border:1px solid var(--line); border-radius:8px;
         image-rendering:pixelated; cursor:crosshair; }
.readout { color:var(--muted); font-size:12px; margin-top:6px; font-family:Consolas, monospace; }
.card { background:var(--panel); border:1px solid var(--line); border-radius:8px; padding:12px; margin-bottom:12px; }
.card h3 { margin:0 0 6px; font-size:13px; color:var(--muted); font-weight:600; }
.kv { display:grid; grid-template-columns:110px 1fr; gap:4px 10px; font-size:13px; }
.kv span:first-child { color:var(--muted); }
code, .mono { font-family:Consolas, monospace; font-size:12px; word-break:break-all; }
pre { background:var(--bg); border:1px solid var(--line); border-radius:6px;
      padding:10px; overflow:auto; max-height:340px; font-size:12px; }
button.copy { background:transparent; border:1px solid var(--line); color:var(--muted);
      border-radius:6px; padding:2px 8px; cursor:pointer; font-size:12px; }
.note { border-left:3px solid var(--accent); padding:8px 12px; background:var(--panel); margin-bottom:10px; }
.note .title { font-weight:600; }
.note .anchor { color:var(--muted); font-size:12px; font-family:Consolas, monospace; }
.note.defect { border-left-color:var(--bad); }
.note.decision { border-left-color:var(--warn); }
.findings li { margin:2px 0; }
.banner { margin:0 24px 0; padding:10px 14px; border:1px solid var(--line);
          border-radius:8px; background:var(--panel); color:var(--muted); font-size:13px; margin-top:14px; }
.hidden { display:none; }
</style>
</head>
<body>
<header>
  <h1>MonoOLED Studio review pack</h1>
  <div class="meta" id="meta"></div>
</header>
<div class="banner" id="honesty"></div>
<main>
  <aside>
    <input id="search" type="search" placeholder="Search screens…">
    <div class="filters" id="filters">
      <button data-filter="all" class="on">All</button>
      <button data-filter="blocking">Blocking</button>
      <button data-filter="annotated">Annotated</button>
    </div>
    <div id="screens"></div>
  </aside>
  <section class="view" id="view"></section>
</main>
<script id="pack-data" type="application/json">__PACK_DATA__</script>
<script>
const PACK = JSON.parse(document.getElementById('pack-data').textContent);
const initial = PACK.screens.find((s) => s.blockers > 0)
  || PACK.screens.find((s) => PACK.annotations.some((a) => a.screen === s.id))
  || PACK.screens[0];
const state = { screen: initial ? initial.id : null, frame: 0,
                view: 'device', query: '', filter: 'all', page: 'screen' };
const xml = (text) => String(text ?? '');
function el(tag, attrs = {}, children = []) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (key === 'class') node.className = value;
    else if (key.startsWith('on')) node.addEventListener(key.slice(2), value);
    else node.setAttribute(key, value);
  }
  for (const child of [].concat(children)) {
    node.append(child instanceof Node ? child : document.createTextNode(xml(child)));
  }
  return node;
}
function findValue(...args) {
  return args.reduce((value, key) => (value == null ? value : value[key]), PACK);
}
function currentScreen() { return PACK.screens.find((s) => s.id === state.screen); }
function currentFrame() {
  const screen = currentScreen();
  return screen && screen.frames[state.frame] ? screen.frames[state.frame] : null;
}
function annotationsFor(id) { return PACK.annotations.filter((a) => a.screen === id); }
function matches(screen) {
  const q = state.query.trim().toLowerCase();
  const hit = !q || (screen.label + ' ' + screen.id + ' ' + screen.category).toLowerCase().includes(q);
  const keep = state.filter === 'blocking' ? screen.blockers > 0
             : state.filter === 'annotated' ? annotationsFor(screen.id).length > 0 : true;
  return hit && keep;
}
function base64Bytes(text) {
  const binary = atob(text);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
  return bytes;
}
function draw(canvas, frame, width, height) {
  const bytes = base64Bytes(frame.vlsb);
  const scale = Math.max(1, Math.floor(960 / width));
  canvas.width = width * scale;
  canvas.height = height * scale;
  const ctx = canvas.getContext('2d');
  ctx.fillStyle = '#000';
  ctx.fillRect(0, 0, canvas.width, canvas.height);
  ctx.fillStyle = '#fff';
  for (let y = 0; y < height; y++) {
    for (let x = 0; x < width; x++) {
      const byte = bytes[(y >> 3) * width + x];
      if ((byte >> (y & 7)) & 1) ctx.fillRect(x * scale, y * scale, scale, scale);
    }
  }
}
function copyText(text, button) {
  navigator.clipboard.writeText(text).then(() => { button.textContent = 'Copied'; })
    .catch(() => { button.textContent = 'Copy failed'; });
}
function header() {
  document.getElementById('meta').textContent =
    `${PACK.totals.screens} screens · ${PACK.totals.frames} frames · ` +
    `${PACK.totals.annotations} annotations · ${PACK.totals.blocking} blocking · v${PACK.version}`;
  document.getElementById('honesty').textContent = PACK.renderer.note;
}
function renderSidebar() {
  const host = document.getElementById('screens');
  host.replaceChildren();
  const groups = new Map();
  for (const screen of PACK.screens.filter(matches)) {
    if (!groups.has(screen.category)) groups.set(screen.category, []);
    groups.get(screen.category).push(screen);
  }
  for (const [category, screens] of groups) {
    host.append(el('div', { class: 'group' }, `${category} · ${screens.length}`));
    for (const screen of screens) {
      const notes = annotationsFor(screen.id).length;
      const badge = screen.blockers > 0
        ? el('span', { class: 'pill bad' }, `${screen.blockers} blockers`)
        : el('span', { class: 'pill ok' }, 'valid');
      host.append(el('div', {
        class: 'screen' + (screen.id === state.screen ? ' on' : ''),
        onclick: () => { state.screen = screen.id; state.frame = 0; state.page = 'screen'; render(); },
      }, [el('span', { class: 'name' }, screen.label), notes ? el('span', { class: 'pill' }, `${notes} notes`) : '', badge]));
    }
  }
  if (!host.childElementCount) host.append(el('div', { class: 'sub' }, 'No screens match.'));
}
function renderScreen(view) {
  const screen = currentScreen();
  if (!screen) { view.append(el('div', { class: 'sub' }, 'No screens in this pack.')); return; }
  const frame = currentFrame();
  view.append(el('h2', {}, screen.label), el('div', { class: 'sub' },
    `${screen.id} · ${screen.category} · ${screen.blockers} blockers · ${screen.warnings} warnings`));
  const frames = el('div', { class: 'frames' });
  screen.frames.forEach((item, index) => frames.append(el('button', {
    class: index === state.frame ? 'on' : '',
    onclick: () => { state.frame = index; render(); },
  }, item.label)));
  view.append(frames);
  const tabs = el('div', { class: 'tabs' });
  for (const mode of ['device', 'code']) {
    tabs.append(el('button', {
      class: state.view === mode ? 'on' : '',
      onclick: () => { state.view = mode; render(); },
    }, mode === 'device' ? 'Device' : 'Code'));
  }
  const grid = el('div', { class: 'grid' });
  const left = el('div');
  const right = el('div');
  if (state.view === 'device') {
    const canvas = el('canvas');
    left.append(canvas);
    const width = screen.canvas && screen.canvas.w ? screen.canvas.w : 128;
    const height = screen.canvas && screen.canvas.h ? screen.canvas.h : 32;
    draw(canvas, frame, width, height);
    const readout = el('div', { class: 'readout' }, `x — · y — · ${width}×${height}`);
    canvas.addEventListener('mousemove', (event) => {
      const rect = canvas.getBoundingClientRect();
      const x = Math.floor((event.clientX - rect.left) / rect.width * width);
      const y = Math.floor((event.clientY - rect.top) / rect.height * height);
      const inside = x >= 0 && y >= 0 && x < width && y < height;
      readout.textContent = inside ? `x ${x} · y ${y} · ${width}×${height}` : `x — · y — · ${width}×${height}`;
    });
    canvas.addEventListener('mouseleave', () => { readout.textContent = `x — · y — · ${width}×${height}`; });
    left.append(readout);
  } else {
    left.append(el('div', { class: 'card' }, [el('h3', {}, 'C header'), el('pre', {}, frame.c_header)]));
    right.append(el('div', { class: 'card' }, [el('h3', {}, 'VLSB hex'), el('pre', {}, frame.hex)]));
  }
  const hash = el('div', { class: 'kv' }, [
    el('span', {}, 'SHA-256'), el('span', { class: 'mono' }, frame.sha256),
    el('span', {}, 'Lit pixels'), el('span', { class: 'mono' }, String(frame.lit_pixels)),
    el('span', {}, 'Bytes'), el('span', { class: 'mono' }, String(frame.bytes)),
    el('span', {}, 'State'), el('span', { class: 'mono' }, JSON.stringify(frame.state)),
  ]);
  const copy = el('button', { class: 'copy' }, 'Copy hash');
  copy.addEventListener('click', () => copyText(frame.sha256, copy));
  const evidence = el('div', { class: 'card' }, [el('h3', {}, 'Evidence'), hash, copy,
    el('div', { class: 'sub' }, 'Hash from the canonical renderer; compare with ui_contract.json golden_sha256.')]);
  const findings = el('div', { class: 'card' }, [el('h3', {}, 'Findings')]);
  if (frame.findings.length) {
    const list = el('ul', { class: 'findings' });
    for (const finding of frame.findings) {
      list.append(el('li', {}, `${finding.severity} · ${finding.code} · ${finding.message}`));
    }
    findings.append(list);
  } else findings.append(el('div', { class: 'sub' }, 'No findings for this state.'));
  const elements = el('div', { class: 'card' }, [el('h3', {}, 'Visible elements')]);
  const rows = frame.elements.filter((element) => element.visible !== false);
  if (rows.length) {
    const list = el('ul', { class: 'findings' });
    for (const element of rows) {
      list.append(el('li', { class: 'mono' }, `${element.id} · ${element.type} · ${element.x},${element.y} · ${element.w}×${element.h}`));
    }
    elements.append(list);
  } else elements.append(el('div', { class: 'sub' }, 'No visible elements.'));
  right.append(evidence, findings, elements);
  grid.append(left, right);
  view.append(grid);
  const notes = annotationsFor(screen.id);
  const noteCard = el('div', { class: 'card' }, [el('h3', {}, `Annotations (${notes.length})`)]);
  if (!notes.length) noteCard.append(el('div', { class: 'sub' }, 'No annotations for this screen.'));
  for (const note of notes) {
    noteCard.append(el('div', { class: 'note ' + note.kind }, [
      el('div', { class: 'title' }, note.title),
      el('div', { class: 'anchor' }, `${note.kind} · ${note.element || '—'} · ${note.evidence.sha256.slice(0, 12)} · ${note.evidence.lit_pixels} lit`),
      el('div', {}, note.body),
    ]));
  }
  view.append(noteCard);
}
function renderContract(view) {
  view.append(el('h2', {}, 'Contract and conventions'));
  view.append(el('div', { class: 'sub' }, 'Everything below is derived from the project and the renderer.'));
  const rules = el('div', { class: 'card' }, [el('h3', {}, 'Coordinates')]);
  const kv = el('div', { class: 'kv' });
  for (const [key, value] of Object.entries(PACK.coordinate_contract)) kv.append(el('span', {}, key), el('span', {}, String(value)));
  for (const [key, value] of Object.entries(PACK.framebuffer_contract)) kv.append(el('span', {}, key), el('span', { class: 'mono' }, String(value)));
  rules.append(kv);
  view.append(rules);
  const hashes = el('div', { class: 'card' }, [el('h3', {}, 'Frame hashes')]);
  for (const screen of PACK.screens) {
    for (const frame of screen.frames) {
      hashes.append(el('div', { class: 'mono' }, `${screen.id} · ${frame.label} · ${frame.sha256} · ${frame.lit_pixels} lit`));
    }
  }
  view.append(hashes);
  const design = el('div', { class: 'card' }, [el('h3', {}, 'Design rules'), el('pre', {}, JSON.stringify(PACK.design_rules, null, 2))]);
  view.append(design);
  const honesty = el('div', { class: 'card' }, [el('h3', {}, 'What this pack does not claim')]);
  honesty.append(el('div', { class: 'sub' }, PACK.renderer.note));
  honesty.append(el('div', { class: 'sub' }, 'There is no key/event model and no hardware simulation in this build; states are explicit presets.'));
  view.append(honesty);
}
function render() {
  header();
  renderSidebar();
  const view = document.getElementById('view');
  view.replaceChildren();
  if (state.page === 'contract') renderContract(view); else renderScreen(view);
}
document.getElementById('search').addEventListener('input', (event) => {
  state.query = event.target.value;
  renderSidebar();
});
for (const button of document.querySelectorAll('#filters button')) {
  button.addEventListener('click', () => {
    state.filter = button.dataset.filter;
    for (const other of document.querySelectorAll('#filters button')) other.classList.toggle('on', other === button);
    renderSidebar();
  });
}
document.addEventListener('keydown', (event) => {
  if (event.key === 'c' && !event.target.matches('input')) {
    state.page = state.page === 'contract' ? 'screen' : 'contract';
    render();
  }
});
render();
</script>
</body>
</html>
"#;

#[cfg(test)]
#[allow(clippy::unwrap_used, clippy::expect_used)]
mod tests {
    use super::*;

    #[test]
    fn base64_matches_rfc4648_vectors() {
        let vectors = [
            ("", ""),
            ("f", "Zg=="),
            ("fo", "Zm8="),
            ("foo", "Zm9v"),
            ("foob", "Zm9vYg=="),
            ("fooba", "Zm9vYmE="),
            ("foobar", "Zm9vYmFy"),
        ];
        for (input, expected) in vectors {
            assert_eq!(base64(input.as_bytes()), expected, "{input}");
        }
    }

    #[test]
    fn script_json_escapes_markup_and_line_separators() {
        let value = json!({"title": "</script><img onerror=x>", "note": "a\u{2028}b"});
        let text = script_json(&value).unwrap();
        assert!(!text.contains("</script>"));
        assert!(text.contains("\\u003c/script\\u003e"));
        assert!(text.contains("\\u2028"));
    }

    use std::path::PathBuf;

    use crate::review::{AnnotationKind, Evidence};

    fn project(name: &str) -> (ProjectWorkspace, PathBuf) {
        let root = std::env::temp_dir().join(format!("mono-pack-{name}-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&root);
        let repo = Path::new(env!("CARGO_MANIFEST_DIR")).join("../..");
        copy_dir(&repo.join("test_assets/projects/curing_lite"), &root);
        let root = crate::project::py_resolve(&root);
        let workspace = ProjectWorkspace::load(&root.join("project.oled.json")).unwrap();
        (workspace, root)
    }

    fn copy_dir(from: &Path, to: &Path) {
        std::fs::create_dir_all(to).unwrap();
        for entry in std::fs::read_dir(from).unwrap() {
            let entry = entry.unwrap();
            let target = to.join(entry.file_name());
            if entry.file_type().unwrap().is_dir() {
                copy_dir(&entry.path(), &target);
            } else {
                std::fs::copy(entry.path(), target).unwrap();
            }
        }
    }

    fn annotation(id: &str, screen: &str, battery: i64, title: &str) -> Annotation {
        let mut state = Map::new();
        state.insert("battery".into(), json!(battery));
        state.insert("mode".into(), json!("NORMAL"));
        state.insert("phase".into(), json!("standby"));
        state.insert("seconds".into(), json!(300));
        Annotation {
            id: id.into(),
            kind: AnnotationKind::Defect,
            screen: screen.into(),
            state,
            element: Some("running_icon".into()),
            title: title.into(),
            body: "check the glyph baseline".into(),
            evidence: Evidence {
                sha256: "00".repeat(32),
                lit_pixels: 686,
                frame: None,
                source: "designer".into(),
            },
            created_utc: "2026-10-28T00:00:00+00:00".into(),
            updated_utc: "2026-10-28T00:00:00+00:00".into(),
        }
    }

    fn build(
        project: &ProjectWorkspace,
        annotations: &[Annotation],
        name: &str,
    ) -> (String, Value) {
        let output = project.root.join("review").join(format!("{name}.html"));
        let summary =
            build_review_pack(project, annotations, &output, &mut |_, _, _| true).unwrap();
        assert_eq!(
            summary.bytes,
            std::fs::metadata(&output).unwrap().len() as usize
        );
        let html = std::fs::read_to_string(&output).unwrap();
        let start =
            html.find("type=\"application/json\">").unwrap() + "type=\"application/json\">".len();
        let end = html[start..].find("</script>").unwrap() + start;
        let data: Value = serde_json::from_str(&html[start..end]).unwrap();
        (html, data)
    }

    fn decode64(text: &str) -> Vec<u8> {
        const ALPHABET: &[u8; 64] =
            b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
        let mut out = Vec::new();
        let mut buffer = 0u32;
        let mut bits = 0;
        for byte in text.bytes().filter(|b| *b != b'=') {
            let value = ALPHABET.iter().position(|c| *c == byte).unwrap() as u32;
            buffer = (buffer << 6) | value;
            bits += 6;
            if bits >= 8 {
                bits -= 8;
                out.push((buffer >> bits) as u8);
            }
        }
        out
    }

    #[test]
    fn review_pack_is_byte_identical_for_same_inputs() {
        let (project, root) = project("stable");
        let annotations = [annotation("n1", "main", 0, "gap")];
        let first = project.root.join("review/a.html");
        let second = project.root.join("review/b.html");
        build_review_pack(&project, &annotations, &first, &mut |_, _, _| true).unwrap();
        build_review_pack(&project, &annotations, &second, &mut |_, _, _| true).unwrap();
        assert_eq!(
            std::fs::read(&first).unwrap(),
            std::fs::read(&second).unwrap()
        );
        let _ = std::fs::remove_dir_all(&root);
    }

    #[test]
    fn escapes_annotation_text() {
        let (project, root) = project("escape");
        let hostile = annotation("n1", "main", 0, "</script><img src=x onerror=alert(1)>");
        let (html, _) = build(&project, &[hostile], "escape");
        assert!(!html.contains("</script><img"));
        assert!(html.contains("\\u003c/script\\u003e"));
        let _ = std::fs::remove_dir_all(&root);
    }

    #[test]
    fn frame_hash_matches_render() {
        let (project, root) = project("hash");
        let (_, data) = build(&project, &[], "hash");
        let frame = &data["screens"][0]["frames"][0];
        let raw = decode64(frame["vlsb"].as_str().unwrap());
        assert_eq!(hex_digest(&raw), frame["sha256"].as_str().unwrap());
        let lit: usize = raw.iter().map(|byte| byte.count_ones() as usize).sum();
        assert_eq!(lit, frame["lit_pixels"].as_u64().unwrap() as usize);
        assert_eq!(raw.len(), frame["bytes"].as_u64().unwrap() as usize);
        let _ = std::fs::remove_dir_all(&root);
    }

    #[test]
    fn orders_screens_and_annotations() {
        let (project, root) = project("order");
        let annotations = [
            annotation("b", "main", 0, "B"),
            annotation("a", "main", 1, "A"),
            annotation("c", "123", 0, "C"),
        ];
        let (_, data) = build(&project, &annotations, "order");
        let ids: Vec<&str> = data["screens"]
            .as_array()
            .unwrap()
            .iter()
            .map(|screen| screen["id"].as_str().unwrap())
            .collect();
        assert_eq!(ids, ["123", "main"]);
        let order: Vec<&str> = data["annotations"]
            .as_array()
            .unwrap()
            .iter()
            .map(|note| note["id"].as_str().unwrap())
            .collect();
        assert_eq!(order, ["c", "b", "a"]);
        let _ = std::fs::remove_dir_all(&root);
    }

    #[test]
    fn omits_absolute_paths() {
        let (project, root) = project("paths");
        let (html, _) = build(&project, &[], "paths");
        let absolute = root.to_string_lossy().replace('\\', "\\\\");
        assert!(!html.contains(&absolute));
        assert!(!html.contains(&root.to_string_lossy().to_string()));
        let _ = std::fs::remove_dir_all(&root);
    }

    #[test]
    fn embeds_annotated_states() {
        let (project, root) = project("states");
        let (_, data) = build(&project, &[annotation("n1", "main", 0, "low")], "states");
        let main = data["screens"]
            .as_array()
            .unwrap()
            .iter()
            .find(|screen| screen["id"] == "main")
            .unwrap();
        assert_eq!(main["frames"].as_array().unwrap().len(), 2);
        assert_eq!(main["frames"][1]["label"], "state 1");
        assert_eq!(main["frames"][1]["state"]["battery"], 0);
        let _ = std::fs::remove_dir_all(&root);
    }
}
