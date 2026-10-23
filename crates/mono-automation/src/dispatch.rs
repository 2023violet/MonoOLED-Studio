//! Domain handlers (V1 `automation_dispatch.py`).

use std::path::{Path, PathBuf};

use mono_core::bitmap::MonoBitmap;
use mono_core::encoding::encode_bitmap;
use mono_core::font::{FontPack, GlyphMetrics};
use mono_core::formatter::{DEFAULT_PREVIEW_LIMIT, FormattedOutput, OutputItem, format_output};
use mono_core::pixel::PixelDocument;
use mono_core::profiles::{OutputProfile, builtin_profiles, validate_profile_id};
use mono_core::pyvalue::{py_int, py_repr, py_str, py_truthy};
use mono_core::raster::{RgbaImage, rasterize};
use mono_core::render::posix;
use mono_core::state::{init_state, schema_from_scene, validate_state, validate_state_schema};
use mono_font::{GenerateOptions, load_font, rasterize_characters};
use mono_project::atomic::atomic_write;
use mono_project::editor::{EditorSession, align_to, distribute, selection_metrics};
use mono_project::export::{
    deterministic_zip, export_scene, frame_png, has_blockers, validate_scene,
};
use mono_project::fontpack_io::{load_font_pack, save_font_pack};
use mono_project::image_io::{decode_image, encode_bitmap_png, encode_rgba_png};
use mono_project::project::resolve_under_root;
use mono_project::resources::hex_digest;
use serde_json::{Map, Value, json};

use crate::error::{RpcError, RpcResult};
use crate::ops;
use crate::service::{API_VERSION, Service, method_specs, native};

type Params = Map<String, Value>;

/// `params['key']` → Python `KeyError('key')`.
fn req<'a>(params: &'a Params, key: &str) -> RpcResult<&'a Value> {
    params.get(key).ok_or_else(|| RpcError::key(key))
}

fn req_str(params: &Params, key: &str) -> RpcResult<String> {
    req(params, key).map(py_str)
}

fn req_int(params: &Params, key: &str) -> RpcResult<i64> {
    let value = req(params, key)?;
    py_int(value).ok_or_else(|| {
        RpcError::invalid(format!(
            "invalid literal for int() with base 10: {}",
            py_repr(value)
        ))
    })
}

fn opt_int(params: &Params, key: &str, default: i64) -> RpcResult<i64> {
    match params.get(key) {
        None => Ok(default),
        Some(_) => req_int(params, key),
    }
}

fn opt_str(params: &Params, key: &str, default: &str) -> String {
    params.get(key).map_or_else(|| default.to_string(), py_str)
}

fn flag(params: &Params, key: &str) -> bool {
    params.get(key).is_some_and(py_truthy)
}

fn object(value: Option<&Value>) -> Params {
    match value {
        Some(Value::Object(map)) => map.clone(),
        _ => Params::new(),
    }
}

/// Python `json.dumps(value, ensure_ascii=False, sort_keys=True)` (", " / ": ").
fn py_dumps(value: &Value) -> String {
    match value {
        Value::Object(map) => {
            let mut keys: Vec<&String> = map.keys().collect();
            keys.sort();
            let parts: Vec<String> = keys
                .into_iter()
                .map(|k| {
                    format!(
                        "{}: {}",
                        serde_json::to_string(k).unwrap_or_default(),
                        py_dumps(&map[k.as_str()])
                    )
                })
                .collect();
            format!("{{{}}}", parts.join(", "))
        }
        Value::Array(items) => {
            let parts: Vec<String> = items.iter().map(py_dumps).collect();
            format!("[{}]", parts.join(", "))
        }
        other => serde_json::to_string(other).unwrap_or_default(),
    }
}

fn base64(data: &[u8]) -> String {
    const TABLE: &[u8; 64] = b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
    let mut out = String::with_capacity(data.len().div_ceil(3) * 4);
    for chunk in data.chunks(3) {
        let b = [
            chunk[0],
            *chunk.get(1).unwrap_or(&0),
            *chunk.get(2).unwrap_or(&0),
        ];
        let n = (u32::from(b[0]) << 16) | (u32::from(b[1]) << 8) | u32::from(b[2]);
        for i in 0..4 {
            if i <= chunk.len() {
                out.push(char::from(TABLE[((n >> (18 - 6 * i)) & 63) as usize]));
            } else {
                out.push('=');
            }
        }
    }
    out
}

fn hex(data: &[u8]) -> String {
    data.iter().map(|b| format!("{b:02x}")).collect()
}

/// Python `FileNotFoundError(path)` / `FileExistsError(path)`: `str()` is the path.
fn path_error(path: &Path) -> RpcError {
    RpcError::invalid(native(path))
}

/// V1 `PixelDocument.from_image(path)`: Pillow `convert('L')`, `>= 128` is lit.
pub fn pixel_from_image(path: &Path) -> RpcResult<PixelDocument> {
    let bytes = std::fs::read(path)
        .map_err(|e| RpcError::from(mono_project::resources::io_error(path, &e)))?;
    let image = decode_image(&bytes).map_err(|_| {
        RpcError::invalid(format!("unsupported or corrupt image: {}", native(path)))
    })?;
    let (w, h) = (image.width, image.height);
    if w == 0 || h == 0 || w > 4096 || h > 4096 || w * h > 4_194_304 {
        return Err(RpcError::invalid(format!(
            "image too large for Pixel Studio: {w}x{h}"
        )));
    }
    let pixels: Vec<u8> = image
        .rgba
        .chunks(4)
        .map(|p| {
            let l = (u32::from(p[0]) * 19595
                + u32::from(p[1]) * 38470
                + u32::from(p[2]) * 7471
                + 0x8000)
                >> 16;
            u8::from(l >= 128)
        })
        .collect();
    let mut doc = PixelDocument::from_pixels(w, h, pixels)?;
    doc.dirty = false;
    Ok(doc)
}

fn save_pixel_png(doc: &mut PixelDocument, path: &Path) -> RpcResult<()> {
    let png = encode_bitmap_png(doc.width(), doc.height(), &doc.rows())?;
    atomic_write(path, &png)?;
    doc.dirty = false;
    Ok(())
}

pub fn dispatch(
    service: &mut Service,
    method: &str,
    params: &Params,
    tx: Option<&str>,
    before: Option<Vec<Value>>,
) -> RpcResult<Value> {
    if method == "scene.get_schema" {
        return Ok(service.result(json!({"schema": {
            "schema_version": service.scene().get("schema_version").and_then(py_int).unwrap_or(1),
            "element_types": ["placeholder", "image", "image_seq", "digits", "text", "bitmap_text"],
            "common_fields": {"id": "unique string", "type": "element type", "x": "integer px", "y": "integer px", "visible_when": "state predicate?"},
            "image": {"asset": "project-relative path", "resize_policy": "native_only by default"},
            "bitmap_text": {"text": "string", "font_pack": "project-relative FontPack", "x": "int", "y": "int"},
        }})));
    }
    match method.split('.').next().unwrap_or_default() {
        "automation" | "project" => api_and_project(service, method, params),
        "scene" | "selection" | "layout" => {
            scene_selection_layout(service, method, params, tx, before)
        }
        "state" => state(service, method, params, tx),
        "render" | "validate" => render_validate(service, method, params),
        "output" | "asset" | "pixel" | "font" | "export" => resources(service, method, params, tx),
        "job" | "session" => jobs_events(service, method, params),
        _ => Err(RpcError::key(method)),
    }
}

// ----------------------------------------------------------- api & project

fn api_and_project(service: &mut Service, method: &str, params: &Params) -> RpcResult<Value> {
    match method {
        "automation.capabilities" => {
            let mut names: Vec<&String> = method_specs().keys().collect();
            names.sort();
            let methods: Vec<Value> = names
                .into_iter()
                .map(|name| {
                    let mut entry = Map::new();
                    entry.insert("method".into(), json!(name));
                    if let Some(Value::Object(spec)) = method_specs().get(name) {
                        entry.extend(spec.clone());
                    }
                    Value::Object(entry)
                })
                .collect();
            Ok(service.result(json!({
                "api_version": API_VERSION,
                "transport": "JSON-RPC 2.0 / localhost",
                "permissions": ["observe", "edit", "full"],
                "methods": methods,
            })))
        }
        "automation.describe_method" => {
            let name = req_str(params, "method")?;
            let Some(Value::Object(spec)) = method_specs().get(&name) else {
                return Err(RpcError::key(name));
            };
            let mut entry = Map::new();
            entry.insert("method".into(), json!(name));
            entry.extend(spec.clone());
            Ok(service.result(json!({"api_version": API_VERSION, "method": entry})))
        }
        "project.get_contract" => {
            let canvas = object(service.scene().get("canvas"));
            let (w, h) = (
                canvas.get("w").and_then(py_int).unwrap_or(0),
                canvas.get("h").and_then(py_int).unwrap_or(0),
            );
            let project_schema = service
                .project
                .as_ref()
                .map(|p| p.data.get("schema_version").and_then(py_int).unwrap_or(1));
            let scene_schema = service
                .scene()
                .get("schema_version")
                .and_then(py_int)
                .unwrap_or(1);
            Ok(service.result(json!({
                "automation_api": API_VERSION,
                "project_schema_version": project_schema,
                "scene_schema_version": scene_schema,
                "coordinate_contract": {"origin": "top-left", "x_direction": "right", "y_direction": "down", "bounds": "[x,x+w) x [y,y+h)", "integer_pixels": true},
                "framebuffer_contract": {"width": w, "height": h, "bytes": w * ((h + 7) / 8), "layout": "VLSB page-major", "byte_offset": "(y // 8) * width + x", "bit": "1 << (y % 8)", "polarity": "1 = OLED lit"},
                "product_truth": {"renderer": "render.py/render_scene", "scene": service.source_path.as_deref().map(native)},
            })))
        }
        "project.get" => {
            let project = service.project.as_ref();
            Ok(service.result(json!({
                "project_root": native(&service.project_root),
                "project_path": project.map(|p| native(&p.path)),
                "project_name": project.map(mono_project::project::ProjectWorkspace::name),
                "active_screen": project.map(mono_project::project::ProjectWorkspace::active_screen),
                "scene_path": service.source_path.as_deref().map(native),
                "canvas": service.scene().get("canvas").cloned().unwrap_or(json!({})),
                "dirty": service.is_dirty(),
            })))
        }
        "project.list_screens" => {
            let project = service.require_project()?;
            let active = project.active_screen();
            let screens: Vec<Value> = project
                .screens()
                .into_iter()
                .map(|s| json!({"id": s.id, "label": s.label, "path": s.path, "active": s.id == active}))
                .collect();
            Ok(service.result(json!({"screens": screens})))
        }
        "project.list_assets" => {
            Ok(service.result(json!({"assets": list_assets(&service.project_root)})))
        }
        "project.open_screen" => {
            let target = req_str(params, "screen_id")?;
            service.handle_unsaved(params, &target)?;
            service.open_project_screen(&target, "project.open_screen")
        }
        "project.create_screen" => {
            let id = req_str(params, "screen_id")?;
            let wants_open = flag(params, "open");
            if wants_open {
                service.handle_unsaved(params, &id)?;
            }
            let canvas = object(service.scene().get("canvas"));
            let size = (
                canvas.get("w").and_then(py_int).unwrap_or(128),
                canvas.get("h").and_then(py_int).unwrap_or(32),
            );
            let label = params.get("label").filter(|v| !v.is_null()).map(py_str);
            let screen = service.require_project_mut()?.add_screen(
                &id,
                label.as_deref(),
                None,
                Some(size),
            )?;
            if wants_open {
                return service.open_project_screen(&screen.id, "project.create_screen");
            }
            screen_changed(service, "project.create_screen", &screen)
        }
        "project.duplicate_screen" => {
            let new_id = req_str(params, "new_id")?;
            let wants_open = flag(params, "open");
            if wants_open {
                service.handle_unsaved(params, &new_id)?;
            }
            let source = req_str(params, "screen_id")?;
            let label = params.get("label").filter(|v| !v.is_null()).map(py_str);
            let screen = service.require_project_mut()?.duplicate_screen(
                &source,
                &new_id,
                label.as_deref(),
            )?;
            if wants_open {
                return service.open_project_screen(&screen.id, "project.duplicate_screen");
            }
            screen_changed(service, "project.duplicate_screen", &screen)
        }
        "project.rename_screen" => {
            let old = req_str(params, "screen_id")?;
            let new_id = req_str(params, "new_id")?;
            let label = params.get("label").filter(|v| !v.is_null()).map(py_str);
            let project = service.require_project_mut()?;
            let was_active = project.active_screen() == old;
            let screen = project.rename_screen(&old, &new_id, label.as_deref())?;
            if was_active {
                let project = service.require_project()?;
                let path = project.screen_path(&screen.id)?;
                let project_path = native(&project.path);
                service.session.doc.path = path.clone();
                service.source_path = Some(path.clone());
                service
                    .scene_mut()
                    .insert("_path".into(), json!(native(&path)));
                service
                    .scene_mut()
                    .insert("_project_path".into(), json!(project_path));
            }
            screen_changed(service, "project.rename_screen", &screen)
        }
        "project.delete_screen" => {
            let sid = req_str(params, "screen_id")?;
            let was_active = service.require_project()?.active_screen() == sid;
            if was_active {
                service.handle_unsaved(params, "<delete-current>")?;
            }
            service.require_project_mut()?.remove_screen(&sid, true)?;
            if was_active {
                let next = service.require_project()?.active_screen();
                let mut result = service.open_project_screen(&next, "project.delete_screen")?;
                result["deleted_screen"] = json!(sid);
                return Ok(result);
            }
            service.revision += 1;
            service.notify("project.delete_screen", json!({"screen_id": sid}));
            let active = service.require_project()?.active_screen();
            Ok(service.result(json!({"deleted_screen": sid, "active_screen": active, "project_structure_changed": true})))
        }
        "project.save" | "project.save_all" => {
            let target = service.save_current_scene()?;
            let mut saved = Vec::new();
            if method == "project.save_all" {
                for id in service.pixel_order.clone() {
                    if let Some(entry) = service.pixels.get_mut(&id) {
                        if let (Some(path), true) = (entry.path.clone(), entry.doc.dirty) {
                            save_pixel_png(&mut entry.doc, &path)?;
                            saved.push(path);
                        }
                    }
                }
            }
            if let Some(project) = service.project.as_mut() {
                project.save()?;
            }
            let saved: Vec<String> = saved.iter().map(|p| service.rel(p)).collect();
            if method == "project.save" {
                service.notify("project.saved", json!({}));
                Ok(service.result(json!({"saved": true, "path": native(&target)})))
            } else {
                service.notify("project.saved_all", json!({}));
                Ok(service.result(
                    json!({"saved": true, "path": native(&target), "pixel_documents": saved}),
                ))
            }
        }
        _ => Err(RpcError::key(method)),
    }
}

fn screen_changed(
    service: &mut Service,
    event: &str,
    screen: &mono_project::project::ScreenRef,
) -> RpcResult<Value> {
    service.revision += 1;
    service.notify(event, json!({"screen_id": screen.id}));
    let active = service.require_project()?.active_screen();
    Ok(service.result(json!({
        "screen_id": screen.id,
        "label": screen.label,
        "path": screen.path,
        "active_screen": active,
        "project_structure_changed": true,
    })))
}

/// V1 `project.list_assets`: bitmap files under the root, skipping build/VCS folders.
fn list_assets(root: &Path) -> Vec<String> {
    const SKIP: [&str; 8] = [
        ".git",
        "__pycache__",
        ".pytest_cache",
        ".venv",
        ".venv-build",
        "build",
        "dist",
        "release",
    ];
    let mut out = Vec::new();
    fn walk(dir: &Path, root: &Path, out: &mut Vec<String>) {
        let Ok(entries) = std::fs::read_dir(dir) else {
            return;
        };
        for entry in entries.flatten() {
            let path = entry.path();
            let Ok(kind) = entry.file_type() else {
                continue;
            };
            if kind.is_dir() {
                walk(&path, root, out);
            } else if kind.is_file() {
                let ext = path
                    .extension()
                    .map(|e| e.to_string_lossy().to_lowercase())
                    .unwrap_or_default();
                if ["png", "bmp", "jpg", "jpeg"].contains(&ext.as_str()) {
                    if let Ok(rel) = path.strip_prefix(root) {
                        out.push(posix(rel));
                    }
                }
            }
        }
    }
    let skipped_root = root
        .components()
        .any(|c| SKIP.contains(&c.as_os_str().to_string_lossy().as_ref()));
    if skipped_root {
        return out;
    }
    walk(root, root, &mut out);
    out.retain(|rel| !rel.split('/').any(|part| SKIP.contains(&part)));
    out.sort();
    out.dedup();
    out
}

// ------------------------------------------------ scene, selection, layout

fn find_element<'a>(
    scene: &'a mut Map<String, Value>,
    id: &Value,
) -> RpcResult<&'a mut Map<String, Value>> {
    let wanted = py_str(id);
    scene
        .get_mut("elements")
        .and_then(Value::as_array_mut)
        .and_then(|items| {
            items
                .iter_mut()
                .filter_map(Value::as_object_mut)
                .find(|e| e.get("id").map(py_str).as_deref() == Some(wanted.as_str()))
        })
        .ok_or_else(|| RpcError::NotFound(py_repr(id)))
}

fn selection_result(service: &Service) -> Value {
    service
        .result(json!({"ids": service.selection.ids(), "primary_id": service.selection.primary()}))
}

/// Run a layout helper on a scratch `EditorSession` over the live scene (V1
/// `EditorSession(service.scene)`), then copy the elements back.
fn with_scratch_session<T>(
    service: &mut Service,
    f: impl FnOnce(&mut EditorSession) -> mono_core::CoreResult<T>,
) -> RpcResult<T> {
    let mut scratch = EditorSession::new(service.session.doc.clone())?;
    let out = f(&mut scratch)?;
    let elements = scratch
        .scene()
        .get("elements")
        .cloned()
        .unwrap_or(json!([]));
    service.scene_mut().insert("elements".into(), elements);
    Ok(out)
}

fn layout_ids(service: &Service, params: &Params) -> Vec<String> {
    match params.get("ids") {
        Some(Value::Array(ids)) if !ids.is_empty() => ids.iter().map(py_str).collect(),
        _ => service.selection.ids().to_vec(),
    }
}

fn scene_selection_layout(
    service: &mut Service,
    method: &str,
    params: &Params,
    tx: Option<&str>,
    before: Option<Vec<Value>>,
) -> RpcResult<Value> {
    match method {
        "scene.get" => Ok(service.result(json!({"scene": service.scene()}))),
        "scene.list_elements" => Ok(service.result(json!({"elements": service.elements()}))),
        "scene.update_element" => {
            let id = req(params, "id")?.clone();
            let changes = object(params.get("changes"));
            find_element(service.scene_mut(), &id)?.extend(changes);
            service.changed(method, tx, before);
            Ok(service.result(json!({"changed_elements": [py_str(&id)]})))
        }
        "scene.create_element" => {
            let Value::Object(mut element) = req(params, "element")?.clone() else {
                return Err(RpcError::invalid("element must be an object"));
            };
            let id = element.get("id").map(py_str).unwrap_or_default();
            let duplicate = service
                .elements()
                .iter()
                .any(|e| e.get("id").map(py_str).as_deref() == Some(id.as_str()));
            if id.is_empty() || duplicate {
                return Err(RpcError::invalid("empty or duplicate element id"));
            }
            let is_image = element.get("type").and_then(Value::as_str) == Some("image");
            if is_image && (!element.contains_key("w") || !element.contains_key("h")) {
                let asset = element
                    .get("asset")
                    .map(py_str)
                    .ok_or_else(|| RpcError::key("asset"))?;
                let path = resolve_under_root(&service.project_root, &asset, "image asset")?;
                let raw = mono_project::resources::read_file(&path)?;
                let bitmap = mono_project::resources::DiskResources::decode_bitmap(&path, &raw)?;
                element.entry("w").or_insert(json!(bitmap.width));
                element.entry("h").or_insert(json!(bitmap.height));
            }
            let elements = service.scene_mut().entry("elements").or_insert(json!([]));
            if let Value::Array(items) = elements {
                items.push(Value::Object(element));
            }
            service.changed(method, tx, before);
            Ok(service.result(json!({"changed_elements": [id]})))
        }
        "scene.delete_elements" => {
            let mut ids: Vec<String> = params
                .get("ids")
                .and_then(Value::as_array)
                .map(|v| v.iter().map(py_str).collect())
                .unwrap_or_default();
            let elements = service.elements();
            let kept: Vec<Value> = elements
                .iter()
                .filter(|e| !ids.contains(&e.get("id").map(py_str).unwrap_or_default()))
                .cloned()
                .collect();
            let removed = kept.len() != elements.len();
            service
                .scene_mut()
                .insert("elements".into(), Value::Array(kept));
            if removed {
                let remaining: Vec<String> = service
                    .selection
                    .ids()
                    .iter()
                    .filter(|id| !ids.contains(id))
                    .cloned()
                    .collect();
                service.selection.replace(&remaining, None);
                service.changed(method, tx, before);
            }
            ids.sort();
            ids.dedup();
            Ok(service.result(json!({"changed_elements": ids})))
        }
        "selection.get" => Ok(selection_result(service)),
        "selection.set" => {
            let ids: Vec<String> = params
                .get("ids")
                .and_then(Value::as_array)
                .map(|v| v.iter().map(py_str).collect())
                .unwrap_or_default();
            let primary = params
                .get("primary_id")
                .filter(|v| !v.is_null())
                .map(py_str);
            service.selection.replace(&ids, primary.as_deref());
            service.changed(method, tx, before);
            Ok(selection_result(service))
        }
        "selection.toggle" => {
            let id = req_str(params, "id")?;
            service.selection.toggle(&id);
            service.changed(method, tx, before);
            Ok(selection_result(service))
        }
        "selection.clear" => {
            service.selection.clear();
            service.changed(method, tx, before);
            Ok(service.result(json!({"ids": [], "primary_id": null})))
        }
        "layout.align" => {
            let ids = layout_ids(service, params);
            let mode = req_str(params, "mode")?;
            let reference = opt_str(params, "reference", "selection");
            let primary = params
                .get("primary_id")
                .filter(|v| py_truthy(v))
                .map(py_str)
                .or_else(|| service.selection.primary().map(str::to_string));
            with_scratch_session(service, |s| {
                align_to(s, &ids, &mode, &reference, primary.as_deref())
            })?;
            service.changed(method, tx, before);
            Ok(service.result(json!({"changed_elements": ids})))
        }
        "layout.distribute" => {
            let ids = layout_ids(service, params);
            let axis = req_str(params, "axis")?;
            with_scratch_session(service, |s| distribute(s, &ids, &axis))?;
            service.changed(method, tx, before);
            Ok(service.result(json!({"changed_elements": ids})))
        }
        "layout.measure" => {
            let ids = layout_ids(service, params);
            if ids.len() == 2 {
                let (a, b) = with_scratch_session(service, |s| {
                    Ok((s.geometry(&ids[0])?, s.geometry(&ids[1])?))
                })?;
                let horizontal_gap = 0.max((b.x - (a.x + a.w)).max(a.x - (b.x + b.w)));
                let vertical_gap = 0.max((b.y - (a.y + a.h)).max(a.y - (b.y + b.h)));
                let center = |p: i64, s: i64| p as f64 + s as f64 / 2.0;
                return Ok(service.result(json!({"measurement": {
                    "dx": b.x - a.x,
                    "dy": b.y - a.y,
                    "horizontal_gap": horizontal_gap,
                    "vertical_gap": vertical_gap,
                    "center_dx": center(b.x, b.w) - center(a.x, a.w),
                    "center_dy": center(b.y, b.h) - center(a.y, a.h),
                }})));
            }
            let m = with_scratch_session(service, |s| selection_metrics(s, &ids))?;
            Ok(service.result(json!({"measurement": {
                "bounds": [m.bounds.0, m.bounds.1, m.bounds.2, m.bounds.3],
                "horizontal_gaps": m.horizontal_gaps,
                "vertical_gaps": m.vertical_gaps,
                "equal_horizontal_spacing": m.equal_horizontal_spacing,
                "equal_vertical_spacing": m.equal_vertical_spacing,
            }})))
        }
        _ => Err(RpcError::key(method)),
    }
}

// -------------------------------------------------------------------- state

/// V1 `apply_state_schema`.
fn apply_state_schema(scene: &mut Map<String, Value>, schema: &Value) {
    scene.insert(
        "states".into(),
        schema.get("variables").cloned().unwrap_or(json!({})),
    );
    match schema.get("relations").and_then(Value::as_array) {
        Some(relations) if !relations.is_empty() => {
            scene.insert("state_relations".into(), Value::Array(relations.clone()));
        }
        _ => {
            scene.remove("state_relations");
        }
    }
}

fn state(
    service: &mut Service,
    method: &str,
    params: &Params,
    tx: Option<&str>,
) -> RpcResult<Value> {
    match method {
        "state.get_schema" | "state.list" => {
            let schema = schema_from_scene(service.scene());
            Ok(service.result(json!({
                "states": schema.get("variables").cloned().unwrap_or(json!({})),
                "relations": schema.get("relations").cloned().unwrap_or(json!([])),
                "schema": schema,
            })))
        }
        "state.validate_schema" => {
            let checked = validate_state_schema(params.get("schema").unwrap_or(&Value::Null));
            Ok(service.result(checked))
        }
        "state.set_schema" => {
            let checked = validate_state_schema(params.get("schema").unwrap_or(&Value::Null));
            if checked.get("valid") != Some(&json!(true)) {
                return Err(RpcError::invalid(format!(
                    "invalid state schema: {}",
                    py_dumps(checked.get("errors").unwrap_or(&json!([])))
                )));
            }
            let normalized = checked.get("schema").cloned().unwrap_or(json!({}));
            let before = service.scene().clone();
            let changed = schema_from_scene(service.scene()) != normalized;
            if changed {
                apply_state_schema(service.scene_mut(), &normalized);
                if service.editor_attached {
                    service.session.state = init_state(service.scene());
                    service.session.dirty = true;
                }
                if tx.is_none() {
                    if service.editor_attached {
                        service
                            .session
                            .record_external_scene(before, "agent_state_set_schema");
                    }
                    service.revision += 1;
                    service.notify(method, json!({}));
                }
            }
            let schema = schema_from_scene(service.scene());
            Ok(service.result(json!({"schema": schema, "changed": changed})))
        }
        "state.validate" => {
            let violations = validate_state(
                &schema_from_scene(service.scene()),
                params.get("state").unwrap_or(&Value::Null),
            );
            Ok(service.result(json!({"valid": violations.is_empty(), "violations": violations})))
        }
        "state.enumerate" => {
            let matrix = Service::state_matrix(service.scene(), params, 5000)?;
            let mut payload = json!({
                "cases": matrix.len(),
                "integer_policy": opt_str(params, "integer_policy", "representative"),
                "warning": if matrix.len() > 10_000 { json!("LARGE_STATE_MATRIX") } else { Value::Null },
            });
            let include = params
                .get("include_states")
                .map_or(!flag(params, "summary_only"), py_truthy);
            if include {
                payload["states"] =
                    Value::Array(matrix.into_iter().map(|(_, s)| Value::Object(s)).collect());
            }
            Ok(service.result(payload))
        }
        "state.count" => {
            let mut count_params = params.clone();
            count_params.entry("max_cases").or_insert(json!(100_000));
            let matrix = Service::state_matrix(service.scene(), &count_params, 100_000)?;
            Ok(service.result(json!({
                "cases": matrix.len(),
                "integer_policy": opt_str(params, "integer_policy", "representative"),
                "warning": if matrix.len() > 10_000 { json!("LARGE_STATE_MATRIX") } else { Value::Null },
            })))
        }
        _ => Err(RpcError::key(method)),
    }
}

// --------------------------------------------------------- render/validate

fn frame_json(result: &mono_core::render::RenderResult) -> RpcResult<Value> {
    let raw = result.framebuffer.to_vlsb()?;
    Ok(json!({
        "width": result.framebuffer.width(),
        "height": result.framebuffer.height(),
        "bytes": raw.len(),
        "sha256": hex_digest(&raw),
        "vlsb_hex": hex(&raw),
    }))
}

fn framebuffer_png(result: &mono_core::render::RenderResult) -> RpcResult<Vec<u8>> {
    let fb = &result.framebuffer;
    let rows: Vec<Vec<u8>> = fb.rows().map(<[u8]>::to_vec).collect();
    Ok(frame_png(&rows, fb.width(), fb.height())?)
}

/// V1 `_annotated_preview_bytes`: nearest-neighbour enlargement plus red boxes
/// and ids. Labels use the built-in 5x7 font (V1: Pillow's default font).
fn annotated_png(result: &mono_core::render::RenderResult, scale: i64) -> RpcResult<Vec<u8>> {
    let scale = scale.clamp(1, 32) as usize;
    let fb = &result.framebuffer;
    let (w, h) = (fb.width() * scale, fb.height() * scale);
    let mut rgba = vec![0u8; w * h * 4];
    for (y, row) in fb.rows().enumerate() {
        for (x, v) in row.iter().enumerate() {
            let c = if *v != 0 { 255 } else { 0 };
            for dy in 0..scale {
                for dx in 0..scale {
                    let i = ((y * scale + dy) * w + x * scale + dx) * 4;
                    rgba[i..i + 4].copy_from_slice(&[c, c, c, 255]);
                }
            }
        }
    }
    let mut set = |x: i64, y: i64| {
        if x >= 0 && y >= 0 && (x as usize) < w && (y as usize) < h {
            let i = (y as usize * w + x as usize) * 4;
            rgba[i..i + 4].copy_from_slice(&[255, 0, 0, 255]);
        }
    };
    let line = (scale / 3).max(1) as i64;
    let s = scale as i64;
    for item in &result.resolved_elements {
        if item.get("visible").is_some_and(|v| v == &json!(false)) {
            continue;
        }
        let num = |k: &str| item.get(k).and_then(py_int);
        let (Some(x), Some(y), Some(bw), Some(bh)) = (num("x"), num("y"), num("w"), num("h"))
        else {
            continue;
        };
        let (x, y, bw, bh) = (x * s, y * s, bw * s, bh * s);
        if bw <= 0 || bh <= 0 {
            continue;
        }
        for t in 0..line {
            for px in x..x + bw {
                set(px, y + t);
                set(px, y + bh - 1 - t);
            }
            for py in y..y + bh {
                set(x + t, py);
                set(x + bw - 1 - t, py);
            }
        }
        let label = item.get("id").map(py_str).unwrap_or_default();
        let mut cursor = x + 1;
        for ch in label.chars() {
            if let Ok(rows) =
                mono_core::font::builtin_glyph_rows(ch.to_ascii_uppercase(), (5, 7), Some(6))
            {
                for (gy, row) in rows.iter().enumerate() {
                    for (gx, v) in row.iter().enumerate() {
                        if *v != 0 {
                            set(cursor + gx as i64, y + 1 + gy as i64);
                        }
                    }
                }
            }
            cursor += 6;
        }
    }
    Ok(encode_rgba_png(w, h, &rgba)?)
}

fn render_validate(service: &mut Service, method: &str, params: &Params) -> RpcResult<Value> {
    match method {
        "render.current" | "render.framebuffer" | "render.resolved_elements" | "render.png" => {
            let (state, result) = service.render(params.get("state"))?;
            match method {
                "render.framebuffer" => Ok(service.result(json!({"framebuffer": frame_json(&result)?, "state": state}))),
                "render.resolved_elements" => Ok(service.result(json!({"resolved_elements": result.resolved_elements, "state": state}))),
                "render.png" => {
                    let png = framebuffer_png(&result)?;
                    Ok(service.result(json!({
                        "png_base64": base64(&png),
                        "png_sha256": hex_digest(&png),
                        "width": result.framebuffer.width(),
                        "height": result.framebuffer.height(),
                        "state": state,
                    })))
                }
                _ => Ok(service.result(json!({"framebuffer": frame_json(&result)?, "resolved_elements": result.resolved_elements, "state": state}))),
            }
        }
        "render.preview_file" | "render.annotated_preview" => {
            let (state, result) = service.render(params.get("state"))?;
            let (default, label) = if method == "render.preview_file" {
                (".oled/agent/preview/current.png", "preview file")
            } else {
                (".oled/agent/preview/annotated.png", "annotated preview")
            };
            let target = service.under_root(&opt_str(params, "path", default), label)?;
            if !target
                .extension()
                .is_some_and(|e| e.eq_ignore_ascii_case("png"))
            {
                return Err(RpcError::invalid(format!("{label} must end in .png")));
            }
            let raw = if method == "render.preview_file" {
                framebuffer_png(&result)?
            } else {
                annotated_png(&result, opt_int(params, "scale", 6)?)?
            };
            atomic_write(&target, &raw)?;
            let mut out =
                json!({"path": native(&target), "sha256": hex_digest(&raw), "state": state});
            if method == "render.annotated_preview" {
                out["resolved_elements"] = json!(result.resolved_elements);
            }
            Ok(service.result(out))
        }
        "render.pixel_diff" => {
            let (before_state, before) = service.render(params.get("before_state"))?;
            let (after_state, after) = service.render(params.get("after_state"))?;
            let (a, b) = (&before.framebuffer, &after.framebuffer);
            if (a.width(), a.height()) != (b.width(), b.height()) {
                return Err(RpcError::invalid("framebuffers must have the same size"));
            }
            let (mut changed, mut bbox): (usize, Option<(usize, usize, usize, usize)>) = (0, None);
            let width = a.width();
            for (i, (pa, pb)) in a.pixels().iter().zip(b.pixels()).enumerate() {
                if pa != pb {
                    changed += 1;
                    let (x, y) = (i % width, i / width);
                    bbox = Some(match bbox {
                        None => (x, y, x + 1, y + 1),
                        Some((x0, y0, x1, y1)) => {
                            (x0.min(x), y0.min(y), x1.max(x + 1), y1.max(y + 1))
                        }
                    });
                }
            }
            let total = a.pixels().len();
            let percent = if total == 0 {
                0.0
            } else {
                changed as f64 / total as f64 * 100.0
            };
            Ok(service.result(json!({
                "before_state": before_state,
                "after_state": after_state,
                "changed_pixels": changed,
                "percent": percent,
                "bbox": bbox.map(|(x0, y0, x1, y1)| json!([x0, y0, x1, y1])),
            })))
        }
        "render.all_states" => {
            let root = service.session.doc.root.clone();
            let payload =
                ops::render_all_states(service.scene(), &root, params, &mut |_, _, _| true)?;
            Ok(service.result(payload))
        }
        "validate.current" => {
            let state = match params.get("state") {
                Some(Value::Object(map)) if !map.is_empty() => map.clone(),
                _ => init_state(service.scene()),
            };
            let root = service.session.doc.root.clone();
            let findings = validate_scene(
                &service.session.doc.data,
                &root,
                Some(&state),
                &mut service.resources,
            );
            let rows: Vec<Value> = findings
                .iter()
                .map(|f| json!({"severity": f.severity, "code": f.code, "message": f.message, "element_id": f.element_id}))
                .collect();
            let blockers = findings
                .iter()
                .filter(|f| f.severity == "BLOCKER" || f.severity == "ERROR")
                .count();
            Ok(service.result(
                json!({"findings": rows, "blockers": blockers, "valid": !has_blockers(&findings)}),
            ))
        }
        "validate.all_states" => {
            let root = service.session.doc.root.clone();
            let payload =
                ops::validate_all_states(service.scene(), &root, params, &mut |_, _, _| true)?;
            Ok(service.result(payload))
        }
        _ => Err(RpcError::key(method)),
    }
}

// ------------------------------------------ output, assets, pixel, font, export

/// (active id, builtins overridden/extended by project profiles, saved ids).
type ProfileSet = (String, Vec<(String, OutputProfile)>, Vec<String>);

fn project_profiles(service: &Service) -> RpcResult<ProfileSet> {
    let mut merged: Vec<(String, OutputProfile)> = builtin_profiles()
        .into_iter()
        .map(|(id, p)| (id.to_string(), p))
        .collect();
    let Some(project) = service.project.as_ref() else {
        return Ok(("ssd1306_vlsb_c".into(), merged, Vec::new()));
    };
    let (active, saved) = project.output_profiles()?;
    let saved_ids: Vec<String> = saved.iter().map(|(id, _)| id.clone()).collect();
    for (id, profile) in saved {
        match merged.iter_mut().find(|(existing, _)| *existing == id) {
            Some(slot) => slot.1 = profile,
            None => merged.push((id, profile)),
        }
    }
    Ok((active, merged, saved_ids))
}

fn resolve_profile(
    service: &Service,
    params: &Params,
) -> RpcResult<(Option<String>, OutputProfile)> {
    let draft = params.get("profile").filter(|v| !v.is_null());
    let id = params.get("profile_id").filter(|v| !v.is_null());
    if draft.is_some() && id.is_some() {
        return Err(RpcError::invalid("provide profile_id or profile, not both"));
    }
    if let Some(raw) = draft {
        return Ok((None, OutputProfile::from_json(raw)?));
    }
    let (active, merged, _) = project_profiles(service)?;
    let id = id.filter(|v| py_truthy(v)).map_or(active, py_str);
    let profile = merged
        .into_iter()
        .find(|(pid, _)| *pid == id)
        .map(|(_, p)| p)
        .ok_or_else(|| RpcError::key(format!("unknown output profile: {id}")))?;
    Ok((Some(id), profile))
}

fn bitmap_item(
    service: &mut Service,
    source: Option<&Value>,
    profile: &OutputProfile,
    state: Option<&Value>,
) -> RpcResult<OutputItem> {
    let source = match source {
        Some(Value::Object(map)) if !map.is_empty() => map.clone(),
        _ => object(Some(&json!({"kind": "current_scene"}))),
    };
    let kind = opt_str(&source, "kind", "current_scene");
    let (bitmap, name) = match kind.as_str() {
        "current_scene" => {
            let (_, rendered) = service.render(source.get("state").or(state))?;
            (
                rendered.framebuffer.to_bitmap(),
                opt_str(&source, "name", "current_frame"),
            )
        }
        "pixel_document" | "current_selection" => {
            let id = req_str(&source, "document_id")?;
            let entry = service
                .pixels
                .get(&id)
                .ok_or_else(|| RpcError::key(format!("unknown pixel document: {id}")))?;
            let rows = entry.doc.rows();
            let bitmap = if kind == "current_selection" {
                let bounds: Vec<i64> = req(&source, "bounds")?
                    .as_array()
                    .map(|v| v.iter().filter_map(py_int).collect())
                    .unwrap_or_default();
                let [x, y, w, h] = bounds[..] else {
                    return Err(RpcError::invalid(
                        "selection bounds must be a non-empty region inside the PixelDocument",
                    ));
                };
                let (dw, dh) = (entry.doc.width() as i64, entry.doc.height() as i64);
                if w <= 0 || h <= 0 || x < 0 || y < 0 || x + w > dw || y + h > dh {
                    return Err(RpcError::invalid(
                        "selection bounds must be a non-empty region inside the PixelDocument",
                    ));
                }
                MonoBitmap::from_rows(
                    rows[y as usize..(y + h) as usize]
                        .iter()
                        .map(|r| r[x as usize..(x + w) as usize].to_vec()),
                )?
            } else {
                MonoBitmap::from_rows(rows)?
            };
            (bitmap, opt_str(&source, "name", "pixel_bitmap"))
        }
        "image" => {
            let member = req_str(&source, "path")?;
            let path = resolve_under_root(&service.project_root, &member, "bitmap source image")?;
            let raw = mono_project::resources::read_file(&path)?;
            let decoded = decode_image(&raw)?;
            let image = RgbaImage::new(decoded.width, decoded.height, decoded.rgba)?;
            let size = source
                .get("output_size")
                .and_then(Value::as_array)
                .and_then(
                    |v| match (v.first().and_then(py_int), v.get(1).and_then(py_int)) {
                        (Some(w), Some(h)) => Some((w.max(0) as usize, h.max(0) as usize)),
                        _ => None,
                    },
                );
            let stem = path
                .file_stem()
                .map(|s| s.to_string_lossy().into_owned())
                .unwrap_or_default();
            (
                rasterize(&image, &profile.raster, size)?,
                opt_str(&source, "name", &stem),
            )
        }
        other => {
            return Err(RpcError::invalid(format!(
                "unsupported bitmap source: {other}"
            )));
        }
    };
    let mut item = OutputItem::bitmap(name, encode_bitmap(&bitmap, &profile.encoding));
    item.width = Some(bitmap.width());
    item.height = Some(bitmap.height());
    Ok(item)
}

fn font_root(service: &Service, font_id: &str) -> RpcResult<PathBuf> {
    service.under_root(font_id, "font pack")
}

fn font_items(
    service: &Service,
    font_id: &str,
    characters: Option<&Value>,
    profile: &OutputProfile,
) -> RpcResult<Vec<OutputItem>> {
    let pack = load_font_pack(&font_root(service, font_id)?)?;
    let chars: Vec<char> = match characters.filter(|v| !v.is_null()) {
        None => {
            let mut all: Vec<char> = pack.characters().collect();
            all.sort_unstable();
            all
        }
        Some(value) => {
            let mut out = Vec::new();
            for c in py_str(value).chars() {
                if !out.contains(&c) {
                    out.push(c);
                }
            }
            out
        }
    };
    if chars.is_empty() {
        return Err(RpcError::invalid(
            "font output requires at least one character",
        ));
    }
    let missing: Vec<Value> = chars
        .iter()
        .filter(|c| pack.glyph(**c).is_none())
        .map(|c| json!(c.to_string()))
        .collect();
    if !missing.is_empty() {
        return Err(RpcError::key(format!(
            "missing glyphs: {}",
            py_repr(&Value::Array(missing))
        )));
    }
    chars
        .iter()
        .map(|c| {
            let glyph = pack.glyph(*c).ok_or_else(|| RpcError::key(c.to_string()))?;
            let bitmap = MonoBitmap::from_rows(glyph.rows.iter().cloned())?;
            let mut item =
                OutputItem::bitmap(c.to_string(), encode_bitmap(&bitmap, &profile.encoding));
            item.codepoint = Some(u32::from(*c));
            item.width = Some(bitmap.width());
            item.height = Some(bitmap.height());
            item.bearing_x = glyph.metrics.bearing_x;
            item.bearing_y = glyph.metrics.bearing_y;
            item.advance = glyph.metrics.advance;
            Ok(item)
        })
        .collect()
}

fn index_rows(formatted: &FormattedOutput) -> Value {
    json!(formatted.index)
}

fn write_formatted(
    service: &Service,
    member: &str,
    profile: &OutputProfile,
    formatted: &FormattedOutput,
) -> RpcResult<Value> {
    let target = service.under_root(member, "output data file")?;
    let binary = profile.to_json().pointer("/text/container") == Some(&json!("binary"));
    let raw = if binary {
        formatted.data.clone()
    } else {
        formatted.text.clone().into_bytes()
    };
    atomic_write(&target, &raw)?;
    let mut result = json!({
        "path": native(&target),
        "sha256": hex_digest(&raw),
        "byte_count": formatted.data.len(),
        "index": index_rows(formatted),
    });
    let sidecar = profile.to_json().pointer("/text/index_mode") == Some(&json!("sidecar"));
    if sidecar && !formatted.sidecar_text.is_empty() {
        let stem = target
            .file_stem()
            .map(|s| s.to_string_lossy().into_owned())
            .unwrap_or_default();
        let index_path = target.with_file_name(format!("{stem}_index.h"));
        let index_raw = formatted.sidecar_text.as_bytes();
        atomic_write(&index_path, index_raw)?;
        result["index_path"] = json!(native(&index_path));
        result["index_sha256"] = json!(hex_digest(index_raw));
    }
    Ok(service.result(result))
}

fn format(
    items: &[OutputItem],
    profile: &OutputProfile,
    symbol: &str,
) -> RpcResult<FormattedOutput> {
    Ok(format_output(
        items,
        &profile.text,
        symbol,
        DEFAULT_PREVIEW_LIMIT,
    )?)
}

fn resources(
    service: &mut Service,
    method: &str,
    params: &Params,
    tx: Option<&str>,
) -> RpcResult<Value> {
    match method {
        "output.list_profiles" => {
            let (active, mut merged, _) = project_profiles(service)?;
            merged.sort_by(|a, b| a.0.cmp(&b.0));
            let profiles: Vec<Value> = merged
                .into_iter()
                .map(|(id, p)| {
                    let mut entry = Map::new();
                    entry.insert("id".into(), json!(id));
                    if let Value::Object(map) = p.to_json() {
                        entry.extend(map);
                    }
                    Value::Object(entry)
                })
                .collect();
            Ok(service.result(json!({"active_profile": active, "profiles": profiles, "temporary": service.project.is_none()})))
        }
        "output.get_profile" => {
            let (active, merged, _) = project_profiles(service)?;
            let id = params
                .get("profile_id")
                .filter(|v| py_truthy(v))
                .map_or_else(|| active.clone(), py_str);
            let profile = merged
                .into_iter()
                .find(|(pid, _)| *pid == id)
                .map(|(_, p)| p)
                .ok_or_else(|| RpcError::key(format!("unknown output profile: {id}")))?;
            Ok(service.result(
                json!({"profile_id": id, "profile": profile.to_json(), "active": id == active}),
            ))
        }
        "output.upsert_profile" | "output.delete_profile" | "output.set_active_profile" => {
            if service.project.is_none() {
                return Err(RpcError::invalid(
                    "output profile changes require an OLED project",
                ));
            }
            let id = req_str(params, "profile_id")?;
            match method {
                "output.upsert_profile" => {
                    validate_profile_id(&id)?;
                    let profile = OutputProfile::from_json(req(params, "profile")?)?;
                    let activate = flag(params, "activate");
                    service
                        .require_project_mut()?
                        .upsert_output_profile(&id, &profile, activate)?;
                }
                "output.delete_profile" => {
                    service.require_project_mut()?.delete_output_profile(&id)?
                }
                _ => {
                    let (_, merged, saved) = project_profiles(service)?;
                    let profile = merged
                        .into_iter()
                        .find(|(pid, _)| *pid == id)
                        .map(|(_, p)| p)
                        .ok_or_else(|| RpcError::key(format!("unknown output profile: {id}")))?;
                    if saved.contains(&id) {
                        service
                            .require_project_mut()?
                            .set_active_output_profile(&id)?;
                    } else {
                        service
                            .require_project_mut()?
                            .upsert_output_profile(&id, &profile, true)?;
                    }
                }
            }
            service.changed(method, tx, None);
            let (active, saved) = service.require_project()?.output_profiles()?;
            let mut ids: Vec<String> = saved.into_iter().map(|(pid, _)| pid).collect();
            ids.sort();
            Ok(
                service
                    .result(json!({"active_profile": active, "profile_id": id, "profiles": ids})),
            )
        }
        "output.preview" => {
            let (profile_id, profile) = resolve_profile(service, params)?;
            let source = object(params.get("source"));
            let items = if source.get("kind").and_then(Value::as_str) == Some("font_pack") {
                let font_id = req_str(&source, "font_id")?;
                font_items(service, &font_id, source.get("characters"), &profile)?
            } else {
                vec![bitmap_item(
                    service,
                    params.get("source"),
                    &profile,
                    params.get("state"),
                )?]
            };
            let symbol = params
                .get("symbol")
                .map_or_else(|| items[0].name.clone(), py_str);
            let formatted = format(&items, &profile, &symbol)?;
            let head = &formatted.data[..formatted.data.len().min(256)];
            Ok(service.result(json!({
                "profile_id": profile_id,
                "profile": profile.to_json(),
                "byte_count": formatted.data.len(),
                "data_sha256": hex_digest(&formatted.data),
                "data_hex": hex(head),
                "data_hex_truncated": formatted.data.len() > 256,
                "preview_text": formatted.preview_text,
                "preview_truncated": formatted.preview_truncated,
                "index": index_rows(&formatted),
            })))
        }
        "asset.create" => {
            let path = service.asset_path(&req_str(params, "path")?, "asset create")?;
            let (w, h) = (req_int(params, "width")?, req_int(params, "height")?);
            if w <= 0 || h <= 0 {
                return Err(RpcError::invalid("width and height must be positive"));
            }
            let mut doc = PixelDocument::new(w as usize, h as usize)?;
            if opt_int(params, "value", 0)? != 0 {
                doc.clear(true);
            }
            save_pixel_png(&mut doc, &path)?;
            service.revision += 1;
            let rel = service.rel(&path);
            service.notify(method, json!({"path": rel}));
            let file = service.file_result(&path)?;
            Ok(service.result(file))
        }
        "asset.import" => {
            let source = PathBuf::from(req_str(params, "source")?);
            let source = mono_project::project::py_resolve(&source);
            if !source.is_file() {
                return Err(path_error(&source));
            }
            let target = service.asset_path(&req_str(params, "target")?, "asset import target")?;
            let raw = std::fs::read(&source).map_err(|e| RpcError::invalid(e.to_string()))?;
            atomic_write(&target, &raw)?;
            pixel_from_image(&target)?;
            service.revision += 1;
            let rel = service.rel(&target);
            service.notify(method, json!({"path": rel}));
            let file = service.file_result(&target)?;
            Ok(service.result(file))
        }
        "asset.copy" | "asset.rename" => {
            let source = service.asset_path(&req_str(params, "path")?, "asset source")?;
            let target = service.asset_path(&req_str(params, "target")?, "asset target")?;
            if !source.exists() {
                return Err(path_error(&source));
            }
            if target.exists() {
                return Err(path_error(&target));
            }
            if let Some(parent) = target.parent() {
                std::fs::create_dir_all(parent).map_err(|e| RpcError::invalid(e.to_string()))?;
            }
            if method == "asset.copy" {
                std::fs::copy(&source, &target).map_err(|e| RpcError::invalid(e.to_string()))?;
            } else {
                std::fs::rename(&source, &target).map_err(|e| RpcError::invalid(e.to_string()))?;
                for entry in service.pixels.values_mut() {
                    if entry.path.as_deref() == Some(source.as_path()) {
                        entry.path = Some(target.clone());
                    }
                }
            }
            service.revision += 1;
            let rel = service.rel(&target);
            service.notify(method, json!({"path": rel}));
            let file = service.file_result(&target)?;
            Ok(service.result(file))
        }
        "asset.delete" => {
            let path = service.asset_path(&req_str(params, "path")?, "asset delete")?;
            if !path.exists() {
                return Err(path_error(&path));
            }
            std::fs::remove_file(&path).map_err(|e| RpcError::invalid(e.to_string()))?;
            let bound: Vec<String> = service
                .pixels
                .iter()
                .filter(|(_, e)| e.path.as_deref() == Some(path.as_path()))
                .map(|(id, _)| id.clone())
                .collect();
            for id in bound {
                service.unregister_pixel(&id);
            }
            service.revision += 1;
            let rel = service.rel(&path);
            service.notify(method, json!({"path": rel}));
            Ok(service.result(json!({"deleted": true, "path": rel})))
        }
        "pixel.create" => {
            let path = service.asset_path(&req_str(params, "path")?, "pixel asset")?;
            if path.exists() && !flag(params, "overwrite") {
                return Err(path_error(&path));
            }
            let (w, h) = (req_int(params, "width")?, req_int(params, "height")?);
            if w <= 0 || h <= 0 {
                return Err(RpcError::invalid("width and height must be positive"));
            }
            let mut doc = PixelDocument::new(w as usize, h as usize)?;
            doc.dirty = false;
            let id = format!("pixel:{}", service.rel(&path));
            service.register_pixel(&id, doc, path)?;
            service.pixel_result(&id)
        }
        "pixel.open" => {
            let path = service.asset_path(&req_str(params, "path")?, "pixel asset")?;
            let doc = pixel_from_image(&path)?;
            let id = format!("pixel:{}", service.rel(&path));
            service.register_pixel(&id, doc, path)?;
            service.pixel_result(&id)
        }
        "pixel.get_document" => service.pixel_result(&req_str(params, "document_id")?),
        m if m.starts_with("pixel.") => pixel_edit(service, method, params, tx),
        "font.list" => {
            let mut manifests = Vec::new();
            collect_manifests(&service.project_root, &mut manifests);
            manifests.sort();
            let fonts: Vec<Value> = manifests
                .iter()
                .filter_map(|m| {
                    let root = m.parent()?;
                    let pack = load_font_pack(root).ok()?;
                    Some(json!({"font_id": service.rel(root), "name": pack.name, "cell": [pack.cell.0, pack.cell.1], "glyph_count": pack.len()}))
                })
                .collect();
            Ok(service.result(json!({"fonts": fonts})))
        }
        "font.create_pack" => {
            let root = service.under_root(&req_str(params, "path")?, "font pack")?;
            let cell: Vec<i64> = match params.get("cell") {
                Some(Value::Array(v)) => v.iter().filter_map(py_int).collect(),
                _ => vec![5, 8],
            };
            let [cw, ch] = cell[..] else {
                return Err(RpcError::invalid("cell must be [width, height]"));
            };
            let name = params.get("name").map_or_else(
                || {
                    root.file_name()
                        .map(|n| n.to_string_lossy().into_owned())
                        .unwrap_or_default()
                },
                py_str,
            );
            let pack = FontPack::new(
                name,
                (cw, ch),
                opt_int(params, "baseline", ch - 1)?,
                opt_int(params, "advance", cw + 1)?,
            )?;
            save_font_pack(&root, &pack, None)?;
            service.changed(method, tx, None);
            Ok(service.result(json!({"font_id": service.rel(&root), "name": pack.name, "cell": [pack.cell.0, pack.cell.1]})))
        }
        "font.get_pack" => {
            let root = font_root(service, &req_str(params, "font_id")?)?;
            let pack = load_font_pack(&root)?;
            let chars: Vec<String> = pack.characters().map(|c| c.to_string()).collect();
            Ok(service.result(json!({
                "font_id": service.rel(&root),
                "name": pack.name,
                "cell": [pack.cell.0, pack.cell.1],
                "baseline": pack.baseline,
                "advance": pack.advance,
                "characters": chars,
            })))
        }
        "font.generate_glyphs" => {
            let root = font_root(service, &req_str(params, "font_id")?)?;
            let mut pack = load_font_pack(&root)?;
            let font = match params.get("font_path").filter(|v| !v.is_null()) {
                Some(path) => {
                    let path = PathBuf::from(py_str(path));
                    let bytes = std::fs::read(&path).map_err(|e| {
                        RpcError::from(mono_project::resources::io_error(&path, &e))
                    })?;
                    Some(load_font(bytes)?)
                }
                None => None,
            };
            let offset: Vec<i64> = match params.get("offset") {
                Some(Value::Array(v)) => v.iter().filter_map(py_int).collect(),
                _ => vec![0, 0],
            };
            let alignment = opt_str(params, "alignment", "glyph_width");
            let options = GenerateOptions {
                font_size: opt_int(params, "font_size", 12)?,
                threshold: opt_int(params, "threshold", 128)?,
                offset: (
                    offset.first().copied().unwrap_or(0),
                    offset.get(1).copied().unwrap_or(0),
                ),
                alignment: serde_json::from_value(json!(alignment)).map_err(|_| {
                    RpcError::invalid(format!("unsupported alignment: {alignment}"))
                })?,
                antialias_scale: opt_int(params, "antialias_scale", 1)?,
            };
            let characters = opt_str(params, "characters", "");
            let chars = rasterize_characters(&mut pack, &characters, font.as_ref(), &options)?;
            save_font_pack(&root, &pack, Some(&chars))?;
            service.changed(method, tx, None);
            Ok(service.result(json!({"font_id": service.rel(&root), "count": chars.len()})))
        }
        "font.get_glyph" => {
            let root = font_root(service, &req_str(params, "font_id")?)?;
            let pack = load_font_pack(&root)?;
            let text = req_str(params, "char")?;
            let glyph = single_char(&text)
                .and_then(|c| pack.glyph(c))
                .ok_or_else(|| RpcError::key(text.clone()))?;
            let m = glyph.metrics;
            Ok(service.result(json!({
                "font_id": service.rel(&root),
                "char": text,
                "pixels": glyph.rows,
                "metrics": {"bearing_x": m.bearing_x, "bearing_y": m.bearing_y, "advance": m.advance},
            })))
        }
        "font.update_glyph" => {
            let root = font_root(service, &req_str(params, "font_id")?)?;
            let mut pack = load_font_pack(&root)?;
            let text = req_str(params, "char")?;
            let ch = single_char(&text)
                .ok_or_else(|| RpcError::invalid("glyph key must be exactly one character"))?;
            let rows: Vec<Vec<u8>> = req(params, "pixels")?
                .as_array()
                .map(|rows| {
                    rows.iter()
                        .map(|r| {
                            r.as_array()
                                .map(|v| v.iter().map(|x| u8::from(py_truthy(x))).collect())
                                .unwrap_or_default()
                        })
                        .collect()
                })
                .unwrap_or_default();
            let metrics = object(params.get("metrics"));
            let metric = |k: &str, d: i64| metrics.get(k).and_then(py_int).unwrap_or(d) as i32;
            pack.set_glyph(
                ch,
                rows,
                Some(GlyphMetrics {
                    bearing_x: metric("bearing_x", 0),
                    bearing_y: metric("bearing_y", 0),
                    advance: metric("advance", i64::from(pack.advance)),
                }),
            )?;
            save_font_pack(&root, &pack, None)?;
            service.changed(method, tx, None);
            Ok(service.result(json!({"font_id": service.rel(&root), "char": text})))
        }
        "font.set_metrics" => {
            let root = font_root(service, &req_str(params, "font_id")?)?;
            let mut pack = load_font_pack(&root)?;
            let baseline = opt_int(params, "baseline", i64::from(pack.baseline))?;
            let advance = opt_int(params, "advance", i64::from(pack.advance))?;
            pack.set_metrics(Some(baseline), Some(advance))?;
            save_font_pack(&root, &pack, None)?;
            service.changed(method, tx, None);
            Ok(service.result(json!({"font_id": service.rel(&root), "baseline": pack.baseline, "advance": pack.advance})))
        }
        "export.current" => {
            let output = service.under_root(
                &opt_str(params, "output_dir", "exports/agent_current"),
                "export directory",
            )?;
            let state = match params.get("state") {
                Some(Value::Object(map)) if !map.is_empty() => map.clone(),
                _ => init_state(service.scene()),
            };
            let root = service.session.doc.root.clone();
            let summary = export_scene(
                service.scene(),
                &root,
                &output,
                &[("current".into(), state)],
                &mut |_, _, _| true,
            )?;
            Ok(service.result(json!({"output_dir": native(&output), "frame_count": summary.frame_count, "frame_hashes": summary.frame_hashes})))
        }
        "export.all" => {
            let root = service.session.doc.root.clone();
            let payload = ops::export_all(
                service.scene(),
                &root,
                &service.project_root,
                params,
                &mut |_, _, _| true,
            )?;
            Ok(service.result(payload))
        }
        "export.c_header" => {
            let target =
                service.under_root(&opt_str(params, "path", "exports/current.h"), "C header")?;
            let (_, result) = service.render(params.get("state"))?;
            let text = mono_core::c_header::framebuffer_to_c_header(
                &result.framebuffer,
                &opt_str(params, "symbol", "oled_frame"),
            )?;
            atomic_write(&target, text.as_bytes())?;
            Ok(service
                .result(json!({"path": native(&target), "sha256": hex_digest(text.as_bytes())})))
        }
        "export.bitmap_data" => {
            let (profile_id, profile) = resolve_profile(service, params)?;
            let item = bitmap_item(service, params.get("source"), &profile, params.get("state"))?;
            let symbol = params
                .get("symbol")
                .map_or_else(|| item.name.clone(), py_str);
            let formatted = format(std::slice::from_ref(&item), &profile, &symbol)?;
            let mut result = write_formatted(
                service,
                &opt_str(params, "path", "exports/bitmap.h"),
                &profile,
                &formatted,
            )?;
            result["profile_id"] = json!(profile_id);
            Ok(result)
        }
        "export.font_data" => {
            let (profile_id, profile) = resolve_profile(service, params)?;
            let font_id = req_str(params, "font_id")?;
            let items = font_items(service, &font_id, params.get("characters"), &profile)?;
            let default_symbol = Path::new(&font_id)
                .file_name()
                .map(|n| n.to_string_lossy().into_owned())
                .filter(|n| !n.is_empty())
                .unwrap_or_else(|| "font_data".into());
            let symbol = params.get("symbol").map_or(default_symbol, py_str);
            let formatted = format(&items, &profile, &symbol)?;
            let mut result = write_formatted(
                service,
                &opt_str(params, "path", &format!("exports/{symbol}.h")),
                &profile,
                &formatted,
            )?;
            result["profile_id"] = json!(profile_id);
            Ok(result)
        }
        "export.font_pack" => {
            let root = font_root(service, &req_str(params, "font_id")?)?;
            load_font_pack(&root)?;
            let name = root
                .file_name()
                .map(|n| n.to_string_lossy().into_owned())
                .unwrap_or_default();
            let target = service.under_root(
                &opt_str(params, "path", &format!("exports/{name}.fontpack.zip")),
                "font export",
            )?;
            if !target
                .extension()
                .is_some_and(|e| e.eq_ignore_ascii_case("zip"))
            {
                return Err(RpcError::invalid("font export must end in .zip"));
            }
            deterministic_zip(&root, &target)?;
            let raw = std::fs::read(&target).map_err(|e| RpcError::invalid(e.to_string()))?;
            Ok(service.result(json!({"path": native(&target), "sha256": hex_digest(&raw)})))
        }
        "export.code_ai_handoff" => {
            let root = service.session.doc.root.clone();
            let payload = ops::handoff(
                service.scene(),
                &root,
                &service.project_root,
                params,
                &mut |_, _, _| true,
            )?;
            Ok(service.result(payload))
        }
        _ => Err(RpcError::key(method)),
    }
}

fn single_char(text: &str) -> Option<char> {
    let mut chars = text.chars();
    match (chars.next(), chars.next()) {
        (Some(c), None) => Some(c),
        _ => None,
    }
}

fn collect_manifests(dir: &Path, out: &mut Vec<PathBuf>) {
    let Ok(entries) = std::fs::read_dir(dir) else {
        return;
    };
    for entry in entries.flatten() {
        let path = entry.path();
        match entry.file_type() {
            Ok(kind) if kind.is_dir() => collect_manifests(&path, out),
            Ok(kind)
                if kind.is_file() && path.file_name().is_some_and(|n| n == "fontpack.json") =>
            {
                out.push(path)
            }
            _ => {}
        }
    }
}

fn pixel_edit(
    service: &mut Service,
    method: &str,
    params: &Params,
    tx: Option<&str>,
) -> RpcResult<Value> {
    let id = req_str(params, "document_id")?;
    if !service.pixels.contains_key(&id) {
        return Err(RpcError::key(format!("unknown pixel document: {id}")));
    }
    match method {
        "pixel.undo" | "pixel.redo" => {
            let entry = service
                .pixels
                .get_mut(&id)
                .ok_or_else(|| RpcError::key(id.clone()))?;
            let moved = if method == "pixel.undo" {
                entry.doc.undo()
            } else {
                entry.doc.redo()
            };
            if moved {
                service.changed(method, tx, None);
            }
            return service.pixel_result(&id);
        }
        "pixel.close" => {
            let dirty = service.pixels.get(&id).is_some_and(|e| e.doc.dirty);
            if dirty && !flag(params, "discard") {
                return Err(RpcError::Unsaved(format!(
                    "unsaved pixel document: {id}; save first or use discard=true"
                )));
            }
            service.unregister_pixel(&id);
            return Ok(service.result(json!({"document_id": id, "closed": true})));
        }
        "pixel.save" => {
            let target = match params.get("path").filter(|v| !v.is_null()) {
                Some(member) => service.asset_path(&py_str(member), "pixel save")?,
                None => service
                    .pixels
                    .get(&id)
                    .and_then(|e| e.path.clone())
                    .ok_or_else(|| RpcError::invalid("pixel document has no target path"))?,
            };
            let entry = service
                .pixels
                .get_mut(&id)
                .ok_or_else(|| RpcError::key(id.clone()))?;
            save_pixel_png(&mut entry.doc, &target)?;
            entry.path = Some(target);
        }
        _ => {
            let value = opt_int(params, "value", 1)? != 0;
            let entry = service
                .pixels
                .get_mut(&id)
                .ok_or_else(|| RpcError::key(id.clone()))?;
            let doc = &mut entry.doc;
            match method {
                "pixel.paint" => doc.brush(
                    req_int(params, "x")?,
                    req_int(params, "y")?,
                    value,
                    opt_int(params, "size", 1)?,
                ),
                "pixel.erase" => doc.brush(
                    req_int(params, "x")?,
                    req_int(params, "y")?,
                    false,
                    opt_int(params, "size", 1)?,
                ),
                "pixel.line" => doc.line(
                    req_int(params, "x0")?,
                    req_int(params, "y0")?,
                    req_int(params, "x1")?,
                    req_int(params, "y1")?,
                    value,
                ),
                "pixel.rect" => doc.rectangle(
                    req_int(params, "x0")?,
                    req_int(params, "y0")?,
                    req_int(params, "x1")?,
                    req_int(params, "y1")?,
                    flag(params, "filled"),
                    value,
                ),
                "pixel.fill" => {
                    doc.flood_fill(req_int(params, "x")?, req_int(params, "y")?, value)?
                }
                "pixel.resize_canvas" => doc.resize_canvas(
                    req_int(params, "width")?,
                    req_int(params, "height")?,
                    &opt_str(params, "anchor", "center"),
                )?,
                "pixel.rotate" => match opt_int(params, "angle", 90)?.rem_euclid(360) {
                    0 => {}
                    90 => doc.rotate90()?,
                    180 => doc.rotate180(),
                    270 => doc.rotate270(),
                    _ => {
                        return Err(RpcError::invalid(
                            "pixel rotation supports 0/90/180/270 only",
                        ));
                    }
                },
                "pixel.flip" => match opt_str(params, "axis", "horizontal").as_str() {
                    "horizontal" => doc.flip_horizontal(),
                    "vertical" => doc.flip_vertical(),
                    _ => return Err(RpcError::invalid("axis must be horizontal/vertical")),
                },
                _ => return Err(RpcError::key(method)),
            }
        }
    }
    service.changed(method, tx, None);
    service.pixel_result(&id)
}

// --------------------------------------------------------------- jobs/events

/// The matrix-wide work of `render.all_states`, `validate.all_states`,
/// `export.all` and `export.code_ai_handoff` over a snapshot of the service,
/// producing exactly the synchronous result (`ok`, `revision`, payload). Runs
/// on any thread: `job.start` and the bridge's off-UI-thread calls use it.
pub(crate) fn matrix_work(
    service: &Service,
    operation: &str,
    arguments: Params,
) -> crate::jobs::Runner {
    let scene = service.scene().clone();
    let root = service.session.doc.root.clone();
    let project_root = service.project_root.clone();
    let revision = service.revision;
    let op = operation.to_string();
    Box::new(move |progress| {
        let payload = match op.as_str() {
            "render.all_states" => ops::render_all_states(&scene, &root, &arguments, progress)?,
            "validate.all_states" => ops::validate_all_states(&scene, &root, &arguments, progress)?,
            "export.all" => ops::export_all(&scene, &root, &project_root, &arguments, progress)?,
            _ => ops::handoff(&scene, &root, &project_root, &arguments, progress)?,
        };
        let mut out = Map::new();
        out.insert("ok".into(), json!(true));
        out.insert("revision".into(), json!(revision));
        if let Value::Object(map) = payload {
            out.extend(map);
        }
        Ok(Value::Object(out))
    })
}

fn jobs_events(service: &mut Service, method: &str, params: &Params) -> RpcResult<Value> {
    match method {
        "job.start" => {
            let operation = req_str(params, "operation")?;
            const ALLOWED: [&str; 4] = [
                "render.all_states",
                "validate.all_states",
                "export.all",
                "export.code_ai_handoff",
            ];
            if !ALLOWED.contains(&operation.as_str()) {
                return Err(RpcError::invalid(format!(
                    "unsupported long-running operation: {operation}"
                )));
            }
            if service.permission == "observe" && operation.starts_with("export.") {
                return Err(RpcError::PermissionDenied(operation));
            }
            let arguments = object(params.get("arguments"));
            let work = matrix_work(service, &operation, arguments);
            let id = service.jobs.start(&operation, work)?;
            Ok(service.result(json!({"job_id": id, "operation": operation, "state": "queued"})))
        }
        "job.status" => {
            let status = service.jobs.status(&req_str(params, "job_id")?)?;
            Ok(service.result(status))
        }
        "job.result" => {
            let result = service.jobs.result(&req_str(params, "job_id")?)?;
            Ok(service.result(result))
        }
        "job.cancel" => {
            let result = service.jobs.cancel(&req_str(params, "job_id")?)?;
            Ok(service.result(result))
        }
        "job.release" => {
            let result = service.jobs.release(&req_str(params, "job_id")?)?;
            Ok(service.result(result))
        }
        "session.events" => {
            let since = opt_int(params, "since", 0)?.max(0) as usize;
            let events = service.events_since(since);
            Ok(service.result(events))
        }
        _ => Err(RpcError::key(method)),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn base64_matches_rfc4648_vectors() {
        assert_eq!(base64(b""), "");
        assert_eq!(base64(b"f"), "Zg==");
        assert_eq!(base64(b"fo"), "Zm8=");
        assert_eq!(base64(b"foobar"), "Zm9vYmFy");
    }

    #[test]
    fn py_dumps_sorts_keys_with_python_separators() {
        let value = json!([{"path": "a", "code": "X", "message": "é"}]);
        assert_eq!(
            py_dumps(&value),
            r#"[{"code": "X", "message": "é", "path": "a"}]"#
        );
    }
}
