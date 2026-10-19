//! Production scene renderer (V1 `render.py`).
//!
//! Every preview, export and Automation API path renders through this one
//! function. File access goes through [`Resources`], implemented by
//! `mono-project`, so the core stays free of IO.

use std::path::{Component, Path, PathBuf};
use std::sync::Arc;

use indexmap::IndexMap;
use serde_json::{Map, Value, json};

use crate::assets::{BitmapAsset, ModeFont};
use crate::error::{CoreError, CoreResult};
use crate::font::FontPack;
use crate::framebuffer::FrameBuffer;
use crate::pyvalue::{py_int, py_str};
use crate::state::{State, subst, when_match};

/// Loads decoded resources by absolute path. Implementations may cache by content.
pub trait Resources {
    fn bitmap(&mut self, path: &Path) -> CoreResult<Arc<BitmapAsset>>;
    fn mode_font(&mut self, path: &Path) -> CoreResult<Arc<ModeFont>>;
    fn font_pack(&mut self, root: &Path) -> CoreResult<Arc<FontPack>>;
}

#[derive(Debug, Clone)]
pub struct RenderResult {
    pub framebuffer: FrameBuffer,
    pub resolved_elements: Vec<Value>,
    pub used_assets: Vec<Arc<BitmapAsset>>,
    pub used_files: Vec<PathBuf>,
}

/// Lexically normalise `.` and `..` without touching the filesystem.
pub fn normalize_path(path: &Path) -> PathBuf {
    let mut out = PathBuf::new();
    for component in path.components() {
        match component {
            Component::CurDir => {}
            Component::ParentDir => {
                if !out.pop() {
                    out.push("..");
                }
            }
            other => out.push(other.as_os_str()),
        }
    }
    out
}

/// V1 `scene.resolve`: absolute paths kept, relative ones joined to the scene root.
pub fn resolve(root: &Path, member: &str) -> PathBuf {
    let path = Path::new(member);
    if path.is_absolute() {
        normalize_path(path)
    } else {
        normalize_path(&root.join(path))
    }
}

pub fn posix(path: &Path) -> String {
    path.to_string_lossy().replace('\\', "/")
}

fn key_error(key: &str) -> CoreError {
    CoreError::new("E-CORE-KEY", format!("'{key}'"))
}

fn field<'a>(element: &'a Map<String, Value>, key: &str) -> CoreResult<&'a Value> {
    element.get(key).ok_or_else(|| key_error(key))
}

/// Renderer geometry is clamped to +-1e9 px: far outside any canvas, so drawing is
/// unchanged, and every later sum/product stays inside i64 (V1 uses bigints).
pub const GEOMETRY_LIMIT: i64 = 1_000_000_000;

fn to_int(value: &Value) -> CoreResult<i64> {
    match value {
        Value::Null | Value::Array(_) | Value::Object(_) => Err(CoreError::new(
            "E-CORE-TYPE",
            format!(
                "int() argument must be a string, a bytes-like object or a real number, not '{}'",
                match value {
                    Value::Null => "NoneType",
                    Value::Array(_) => "list",
                    _ => "dict",
                }
            ),
        )),
        _ => py_int(value)
            .map(|v| v.clamp(-GEOMETRY_LIMIT, GEOMETRY_LIMIT))
            .ok_or_else(|| {
                CoreError::invalid(format!(
                    "invalid literal for int() with base 10: {}",
                    py_str(value)
                ))
            }),
    }
}

fn int_field(element: &Map<String, Value>, key: &str) -> CoreResult<i64> {
    to_int(field(element, key)?)
}

fn int_or(element: &Map<String, Value>, key: &str, default: i64) -> CoreResult<i64> {
    match element.get(key) {
        Some(value) => to_int(value),
        None => Ok(default),
    }
}

fn str_or(element: &Map<String, Value>, key: &str, default: &str) -> Value {
    element
        .get(key)
        .cloned()
        .unwrap_or_else(|| Value::from(default))
}

struct Ctx<'a, R: Resources> {
    root: &'a Path,
    state: &'a State,
    resources: &'a mut R,
    cache: IndexMap<String, Arc<BitmapAsset>>,
    used_files: Vec<PathBuf>,
}

impl<R: Resources> Ctx<'_, R> {
    fn bitmap(&mut self, path: &Path) -> CoreResult<Arc<BitmapAsset>> {
        let asset = self.resources.bitmap(path)?;
        self.cache.insert(asset.path.clone(), asset.clone());
        Ok(asset)
    }
}

fn rows_of(asset: &BitmapAsset) -> &[Vec<u8>] {
    &asset.rows
}

fn render_image<R: Resources>(
    fb: &mut FrameBuffer,
    element: &Map<String, Value>,
    ctx: &mut Ctx<'_, R>,
    kind: &str,
) -> CoreResult<Value> {
    let (path, extra) = if kind == "image" {
        let lower = element.get("var_lower").is_some_and(truthy);
        let template = py_str(field(element, "asset")?);
        (
            resolve(ctx.root, &subst(&template, ctx.state, lower)?),
            None,
        )
    } else {
        let name = py_str(field(element, "bind")?);
        let raw = ctx.state.get(&name).ok_or_else(|| key_error(&name))?;
        let value = to_int(raw)?;
        let filename = py_str(field(element, "pattern")?).replace("{n}", &value.to_string());
        let dir = resolve(ctx.root, &py_str(field(element, "dir")?));
        (normalize_path(&dir.join(filename)), Some((name, value)))
    };
    let asset = ctx.bitmap(&path)?;
    let (x, y) = (int_field(element, "x")?, int_field(element, "y")?);
    fb.or_mask(rows_of(&asset), x, y);
    let mut out = Map::new();
    out.insert("id".into(), field(element, "id")?.clone());
    out.insert("type".into(), Value::from(kind));
    out.insert("visible".into(), Value::Bool(true));
    out.insert("x".into(), x.into());
    out.insert("y".into(), y.into());
    out.insert("w".into(), int_or(element, "w", asset.width as i64)?.into());
    out.insert(
        "h".into(),
        int_or(element, "h", asset.height as i64)?.into(),
    );
    out.insert("native_w".into(), asset.width.into());
    out.insert("native_h".into(), asset.height.into());
    if let Some((name, value)) = extra {
        out.insert("bind".into(), name.into());
        out.insert("value".into(), value.into());
    }
    out.insert("assets".into(), json!([asset.path]));
    out.insert("blend".into(), str_or(element, "blend", "or"));
    out.insert(
        "resize_policy".into(),
        str_or(element, "resize_policy", "native_only"),
    );
    Ok(Value::Object(out))
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

fn render_digits<R: Resources>(
    fb: &mut FrameBuffer,
    element: &Map<String, Value>,
    ctx: &mut Ctx<'_, R>,
) -> CoreResult<Value> {
    let name = py_str(field(element, "bind")?);
    let mut raw = py_str(ctx.state.get(&name).ok_or_else(|| key_error(&name))?);
    // Digit strings longer than 4096 are not a meaningful OLED layout; bound the padding work.
    let min_digits = int_or(element, "min_digits", 1)?.min(4096);
    let is_digit = !raw.is_empty() && raw.chars().all(|c| c.is_numeric());
    if is_digit && (raw.chars().count() as i64) < min_digits {
        let pad = py_str(&str_or(element, "pad_char", "0"));
        let pad_char = pad.chars().next().unwrap_or('0');
        let missing = min_digits as usize - raw.chars().count();
        raw = std::iter::repeat_n(pad_char, missing)
            .chain(raw.chars())
            .collect();
    }
    let (x0, y) = (int_field(element, "x")?, int_field(element, "y")?);
    let digit_w = int_field(element, "digit_w")?;
    let digit_h = int_field(element, "digit_h")?;
    let tracking = int_or(element, "tracking", 0)?;
    let pattern = py_str(field(element, "pattern")?);
    let dir = resolve(ctx.root, &py_str(field(element, "dir")?));
    let mut paths = Vec::new();
    let chars: Vec<char> = raw.chars().collect();
    for (index, ch) in chars.iter().enumerate() {
        let path = normalize_path(&dir.join(pattern.replace("{d}", &ch.to_string())));
        let asset = ctx.bitmap(&path)?;
        paths.push(Value::from(asset.path.clone()));
        fb.or_mask(rows_of(&asset), x0 + index as i64 * (digit_w + tracking), y);
    }
    let n = chars.len() as i64;
    let width = if n == 0 {
        0
    } else {
        n * digit_w + (n - 1) * tracking
    };
    Ok(json!({
        "id": field(element, "id")?, "type": "digits", "visible": true,
        "x": x0, "y": y, "w": width, "h": digit_h, "native_w": width, "native_h": digit_h,
        "bind": name, "text": raw, "assets": paths,
        "blend": str_or(element, "blend", "or"), "resize_policy": str_or(element, "resize_policy", "native_only"),
    }))
}

fn render_text<R: Resources>(
    fb: &mut FrameBuffer,
    element: &Map<String, Value>,
    ctx: &mut Ctx<'_, R>,
) -> CoreResult<Value> {
    let text = subst(&py_str(field(element, "text")?), ctx.state, false)?.to_uppercase();
    let header = resolve(ctx.root, &py_str(field(element, "font_header")?));
    let font = ctx.resources.mode_font(&header)?;
    ctx.used_files.push(header.clone());
    let cell_w = int_or(element, "cell_w", 5)?;
    let cell_h = int_or(element, "cell_h", 7)?;
    let advance = int_or(element, "advance", cell_w + 1)?;
    let count = text.chars().count() as i64;
    let width = if count == 0 {
        0
    } else {
        (count - 1) * advance + cell_w
    };
    let (x, y) = match element
        .get("zone")
        .and_then(Value::as_object)
        .filter(|z| !z.is_empty())
    {
        Some(zone) => {
            let zx = int_field(zone, "x")?;
            let x = match py_str(&str_or(element, "align", "left")).as_str() {
                "left" => zx,
                "center" => zx + (int_field(zone, "w")? - width).div_euclid(2),
                "right" => zx + int_field(zone, "w")? - width,
                other => return Err(CoreError::invalid(format!("unknown text align: {other}"))),
            };
            let y = match element.get("y") {
                Some(_) => int_field(element, "y")?,
                None => int_field(zone, "y")?,
            };
            (x, y)
        }
        None => (int_field(element, "x")?, int_field(element, "y")?),
    };
    for (index, ch) in text.chars().enumerate() {
        let glyph = font.get(&ch).ok_or_else(|| {
            CoreError::invalid(format!(
                "font does not contain '{ch}' for element {}",
                py_str(element.get("id").unwrap_or(&Value::Null))
            ))
        })?;
        fb.or_mask(glyph, x + index as i64 * advance, y);
    }
    Ok(json!({
        "id": field(element, "id")?, "type": "text", "visible": true,
        "x": x, "y": y, "w": width, "h": cell_h, "native_w": width, "native_h": cell_h,
        "text": text, "assets": [posix(&header)],
        "blend": str_or(element, "blend", "or"), "resize_policy": "native_only",
    }))
}

fn render_bitmap_text<R: Resources>(
    fb: &mut FrameBuffer,
    element: &Map<String, Value>,
    ctx: &mut Ctx<'_, R>,
) -> CoreResult<Value> {
    let text = subst(
        &py_str(
            &element
                .get("text")
                .cloned()
                .unwrap_or_else(|| Value::from("")),
        ),
        ctx.state,
        false,
    )?;
    let pack_root = resolve(ctx.root, &py_str(field(element, "font_pack")?));
    let pack = ctx.resources.font_pack(&pack_root)?;
    let (x0, y) = (int_or(element, "x", 0)?, int_or(element, "y", 0)?);
    let mut x = x0;
    let mut assets = Vec::new();
    for ch in text.chars() {
        let glyph = pack.glyph(ch).ok_or_else(|| {
            CoreError::invalid(format!(
                "font pack does not contain '{ch}' for element {}",
                py_str(element.get("id").unwrap_or(&Value::Null))
            ))
        })?;
        fb.or_mask(
            &glyph.rows,
            x + i64::from(glyph.metrics.bearing_x),
            y + i64::from(glyph.metrics.bearing_y),
        );
        assets.push(posix(
            &pack_root
                .join("glyphs")
                .join(format!("U+{:04X}.png", ch as u32)),
        ));
        x += i64::from(glyph.metrics.advance);
    }
    let width = match text.chars().last().and_then(|c| pack.glyph(c)) {
        Some(last) => (x - x0 - (i64::from(last.metrics.advance) - pack.cell.0 as i64)).max(0),
        None => 0,
    };
    ctx.used_files.push(pack_root.join("fontpack.json"));
    ctx.used_files.extend(assets.iter().map(PathBuf::from));
    Ok(json!({
        "id": field(element, "id")?, "type": "bitmap_text", "visible": true,
        "x": x0, "y": y, "w": width, "h": pack.cell.1, "native_w": width, "native_h": pack.cell.1,
        "text": text, "font_pack": posix(&pack_root), "assets": assets,
        "blend": str_or(element, "blend", "or"), "resize_policy": "native_only",
    }))
}

fn render_placeholder(element: &Map<String, Value>) -> CoreResult<Value> {
    let id = field(element, "id")?.clone();
    let label = element
        .get("label")
        .map(py_str)
        .unwrap_or_else(|| py_str(&id));
    Ok(json!({
        "id": id, "type": "placeholder", "visible": true,
        "x": int_field(element, "x")?, "y": int_field(element, "y")?,
        "w": int_field(element, "w")?, "h": int_field(element, "h")?,
        "label": label, "assets": [], "placeholder": true, "rendered": false,
        "blend": "none", "resize_policy": "draft",
    }))
}

fn zone_value(element: &Map<String, Value>, key: &str) -> Value {
    element
        .get(key)
        .cloned()
        .or_else(|| element.get("zone").and_then(|z| z.get(key)).cloned())
        .unwrap_or(Value::Null)
}

/// V1 `render_scene`. `root` is the scene root (`scene['_root']`).
pub fn render_scene<R: Resources>(
    scene: &Map<String, Value>,
    root: &Path,
    state: &State,
    resources: &mut R,
) -> CoreResult<RenderResult> {
    let canvas = field(scene, "canvas")?
        .as_object()
        .ok_or_else(|| key_error("canvas"))?;
    let width = int_field(canvas, "w")?;
    let height = int_field(canvas, "h")?;
    let mut fb = FrameBuffer::new(width.max(0) as usize, height.max(0) as usize)?;
    let mut ctx = Ctx {
        root,
        state,
        resources,
        cache: IndexMap::new(),
        used_files: Vec::new(),
    };
    let mut resolved = Vec::new();
    let empty = Vec::new();
    let elements = field(scene, "elements")?.as_array().unwrap_or(&empty);
    for raw in elements {
        let element = raw
            .as_object()
            .ok_or_else(|| CoreError::invalid("scene element must be an object"))?;
        let hidden = element.get("hidden").is_some_and(truthy);
        if hidden || !when_match(element.get("visible_when"), state)? {
            resolved.push(json!({
                "id": field(element, "id")?, "type": field(element, "type")?, "visible": false,
                "x": zone_value(element, "x"), "y": zone_value(element, "y"),
                "w": zone_value(element, "w"), "h": zone_value(element, "h"), "assets": [],
            }));
            continue;
        }
        let kind = py_str(field(element, "type")?);
        let item = match kind.as_str() {
            "image" | "image_seq" => render_image(&mut fb, element, &mut ctx, &kind)?,
            "digits" => render_digits(&mut fb, element, &mut ctx)?,
            "text" => render_text(&mut fb, element, &mut ctx)?,
            "bitmap_text" => render_bitmap_text(&mut fb, element, &mut ctx)?,
            "placeholder" => render_placeholder(element)?,
            other => {
                return Err(CoreError::invalid(format!(
                    "unsupported element type: {other}"
                )));
            }
        };
        resolved.push(item);
    }
    let mut used_files = ctx.used_files;
    used_files.extend(ctx.cache.values().map(|asset| PathBuf::from(&asset.path)));
    used_files.sort_by_key(|p| posix(p));
    used_files.dedup_by_key(|p| posix(p));
    Ok(RenderResult {
        framebuffer: fb,
        resolved_elements: resolved,
        used_assets: ctx.cache.values().cloned().collect(),
        used_files,
    })
}
