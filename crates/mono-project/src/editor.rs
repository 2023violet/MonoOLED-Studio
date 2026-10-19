//! GUI-independent scene authoring session (V1 `editor_model.EditorSession`,
//! `document.SceneDocument`, `selection_model`, `selection_tools`).
//!
//! The scene JSON stays the single layout truth. Every user action is one undo
//! step; a pointer drag coalesces into a single step until `end_coalesced_edit`.

use std::collections::BTreeSet;
use std::path::{Path, PathBuf};

use mono_core::pyvalue::{is_py_int, py_int, py_str};
use mono_core::render::{RenderResult, Resources, normalize_path, posix, render_scene, resolve};
use mono_core::runtime::SceneRuntime;
use mono_core::state::{State, init_state, subst, when_match};
use mono_core::{CoreError, CoreResult};
use serde_json::{Map, Value, json};

use crate::atomic::atomic_write_json;
use crate::export::{Finding, validate_scene};
use crate::project::py_resolve;
use crate::resources::{DiskResources, hex_digest, read_file};
use crate::scene_io::SceneDoc;

pub const MAX_HISTORY: usize = 500;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct Editable {
    pub x: bool,
    pub y: bool,
    pub w: bool,
    pub h: bool,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct Geometry {
    pub x: i64,
    pub y: i64,
    pub w: i64,
    pub h: i64,
    pub editable: Editable,
}

/// One undoable action: element-list snapshots, or whole-scene snapshots.
#[derive(Debug, Clone)]
enum Command {
    Elements {
        label: String,
        before: Vec<Value>,
        after: Vec<Value>,
    },
    Scene {
        label: String,
        before: Map<String, Value>,
        after: Map<String, Value>,
    },
}

pub struct EditorSession {
    pub doc: SceneDoc,
    pub state: State,
    pub elapsed: i64,
    pub resources: DiskResources,
    pub dirty: bool,
    disk_fingerprint: Option<String>,
    undo: Vec<Command>,
    redo: Vec<Command>,
    coalesce_open: bool,
}

fn key_error(message: impl Into<String>) -> CoreError {
    CoreError::new("E-CORE-KEY", format!("'{}'", message.into()))
}

fn int_of(value: Option<&Value>) -> i64 {
    value.and_then(py_int).unwrap_or(0)
}

/// Python `round()` (banker's rounding).
pub fn py_round(value: f64) -> i64 {
    let floor = value.floor();
    if (value - floor - 0.5).abs() < 1e-12 {
        if (floor as i64) % 2 == 0 {
            floor as i64
        } else {
            floor as i64 + 1
        }
    } else {
        value.round() as i64
    }
}

impl EditorSession {
    pub fn new(doc: SceneDoc) -> CoreResult<Self> {
        let state = SceneRuntime::new(&doc.data, None)?.state;
        let disk_fingerprint = std::fs::read(&doc.path).ok().map(|b| hex_digest(&b));
        Ok(Self {
            doc,
            state,
            elapsed: 0,
            resources: DiskResources::new(),
            dirty: false,
            disk_fingerprint,
            undo: Vec::new(),
            redo: Vec::new(),
            coalesce_open: false,
        })
    }

    pub fn scene(&self) -> &Map<String, Value> {
        &self.doc.data
    }

    pub fn root(&self) -> &Path {
        &self.doc.root
    }

    pub fn can_undo(&self) -> bool {
        !self.undo.is_empty()
    }

    pub fn can_redo(&self) -> bool {
        !self.redo.is_empty()
    }

    fn elements(&self) -> Vec<Value> {
        self.doc
            .data
            .get("elements")
            .and_then(Value::as_array)
            .cloned()
            .unwrap_or_default()
    }

    fn set_elements(&mut self, items: Vec<Value>) {
        self.doc.data.insert("elements".into(), Value::Array(items));
    }

    pub fn element_ids(&self) -> Vec<String> {
        self.elements()
            .iter()
            .map(|e| e.get("id").map(py_str).unwrap_or_default())
            .collect()
    }

    pub fn element(&self, id: &str) -> CoreResult<Map<String, Value>> {
        self.elements()
            .into_iter()
            .find(|e| e.get("id").map(py_str).as_deref() == Some(id))
            .and_then(|e| e.as_object().cloned())
            .ok_or_else(|| key_error(format!("unknown element id: {id}")))
    }

    fn push_undo(&mut self, command: Command) {
        self.undo.push(command);
        if self.undo.len() > MAX_HISTORY {
            let excess = self.undo.len() - MAX_HISTORY;
            self.undo.drain(..excess);
        }
    }

    /// Mutate the element list as one undoable action (rolled back on error).
    fn batch_edit(
        &mut self,
        label: &str,
        mutate: impl FnOnce(&mut Vec<Value>) -> CoreResult<()>,
    ) -> CoreResult<bool> {
        let before = self.elements();
        let mut working = before.clone();
        mutate(&mut working)?;
        if working == before {
            return Ok(false);
        }
        self.set_elements(working.clone());
        self.dirty = true;
        self.push_undo(Command::Elements {
            label: label.into(),
            before,
            after: working,
        });
        self.redo.clear();
        self.coalesce_open = false;
        Ok(true)
    }

    fn resolved_size(&mut self, element: &Map<String, Value>) -> CoreResult<(i64, i64, i64, i64)> {
        let id = element.get("id").map(py_str).unwrap_or_default();
        let hidden = element
            .get("hidden")
            .is_some_and(|v| v == &Value::Bool(true))
            || !when_match(element.get("visible_when"), &self.state)?;
        let zone = element.get("zone").cloned().unwrap_or(json!({}));
        let pick = |k: &str| {
            element
                .get(k)
                .or_else(|| zone.get(k))
                .map(|v| int_of(Some(v)))
                .unwrap_or(0)
        };
        if hidden {
            return Ok((pick("x"), pick("y"), pick("w"), pick("h")));
        }
        let kind = element.get("type").map(py_str).unwrap_or_default();
        let root = self.doc.root.clone();
        let x = int_of(element.get("x"));
        let y = int_of(element.get("y"));
        match kind.as_str() {
            "placeholder" => Ok((x, y, int_of(element.get("w")), int_of(element.get("h")))),
            "image" | "image_seq" => {
                let path = if kind == "image" {
                    let lower = element
                        .get("var_lower")
                        .is_some_and(|v| v == &Value::Bool(true));
                    resolve(
                        &root,
                        &subst(
                            &py_str(element.get("asset").ok_or_else(|| key_error("asset"))?),
                            &self.state,
                            lower,
                        )?,
                    )
                } else {
                    let bind = py_str(element.get("bind").ok_or_else(|| key_error("bind"))?);
                    let value = int_of(self.state.get(&bind));
                    let file = py_str(element.get("pattern").ok_or_else(|| key_error("pattern"))?)
                        .replace("{n}", &value.to_string());
                    normalize_path(
                        &resolve(
                            &root,
                            &py_str(element.get("dir").ok_or_else(|| key_error("dir"))?),
                        )
                        .join(file),
                    )
                };
                let asset = self.resources.bitmap(&py_resolve(&path))?;
                Ok((
                    x,
                    y,
                    element
                        .get("w")
                        .map_or(asset.width as i64, |v| int_of(Some(v))),
                    element
                        .get("h")
                        .map_or(asset.height as i64, |v| int_of(Some(v))),
                ))
            }
            "digits" | "text" | "bitmap_text" => {
                // Width/height follow the renderer; render just this element on a scratch canvas.
                let mut scene = self.doc.data.clone();
                scene.insert("elements".into(), json!([Value::Object(element.clone())]));
                let result = render_scene(&scene, &root, &self.state, &mut self.resources)?;
                let item = result
                    .resolved_elements
                    .first()
                    .cloned()
                    .unwrap_or(json!({}));
                Ok((
                    int_of(item.get("x")),
                    int_of(item.get("y")),
                    int_of(item.get("w")),
                    int_of(item.get("h")),
                ))
            }
            other => Err(CoreError::invalid(format!(
                "unsupported element type: {other} ({id})"
            ))),
        }
    }

    /// V1 `geometry`.
    pub fn geometry(&mut self, id: &str) -> CoreResult<Geometry> {
        let element = self.element(id)?;
        let zone = element.get("zone").and_then(Value::as_object).cloned();
        let native_locked = element.get("type").map(py_str).as_deref() == Some("image")
            && element
                .get("resize_policy")
                .map(py_str)
                .unwrap_or_else(|| "native_only".into())
                == "native_only";
        if zone.is_none()
            && ["x", "y", "w", "h"]
                .iter()
                .all(|k| element.contains_key(*k))
        {
            return Ok(Geometry {
                x: int_of(element.get("x")),
                y: int_of(element.get("y")),
                w: int_of(element.get("w")),
                h: int_of(element.get("h")),
                editable: Editable {
                    x: true,
                    y: true,
                    w: !native_locked,
                    h: !native_locked,
                },
            });
        }
        if let Some(zone) = &zone {
            if ["x", "y", "w", "h"].iter().all(|k| zone.contains_key(*k)) {
                return Ok(Geometry {
                    x: int_of(zone.get("x")),
                    y: int_of(zone.get("y")),
                    w: int_of(zone.get("w")),
                    h: int_of(zone.get("h")),
                    editable: Editable {
                        x: true,
                        y: true,
                        w: true,
                        h: true,
                    },
                });
            }
        }
        let (rx, ry, rw, rh) = self.resolved_size(&element)?;
        Ok(Geometry {
            x: element.get("x").map_or(rx, |v| int_of(Some(v))),
            y: element.get("y").map_or(ry, |v| int_of(Some(v))),
            w: element
                .get("w")
                .filter(|v| !v.is_null())
                .map_or(rw, |v| int_of(Some(v))),
            h: element
                .get("h")
                .filter(|v| !v.is_null())
                .map_or(rh, |v| int_of(Some(v))),
            editable: Editable {
                x: element.contains_key("x"),
                y: element.contains_key("y"),
                w: element.contains_key("w") && !native_locked,
                h: element.contains_key("h") && !native_locked,
            },
        })
    }

    fn geometry_changes(
        &mut self,
        id: &str,
        values: &[(&str, i64)],
    ) -> CoreResult<Vec<(String, i64)>> {
        let element = self.element(id)?;
        if element
            .get("locked")
            .is_some_and(|v| v == &Value::Bool(true))
        {
            return Err(CoreError::invalid(format!("{id} is locked")));
        }
        let zone = element.get("zone").and_then(Value::as_object).cloned();
        let geom = self.geometry(id)?;
        let mut changes = Vec::new();
        for (name, value) in values {
            let editable = match *name {
                "x" => geom.editable.x,
                "y" => geom.editable.y,
                "w" => geom.editable.w,
                "h" => geom.editable.h,
                other => return Err(key_error(format!("unknown geometry field: {other}"))),
            };
            if !editable {
                return Err(CoreError::invalid(format!("{id}.{name} is not editable")));
            }
            if let Some(zone) = &zone {
                changes.push((format!("zone.{name}"), *value));
                if *name == "y" && element.contains_key("y") {
                    let offset = int_of(element.get("y")) - int_of(zone.get("y"));
                    changes.push(("y".into(), value + offset));
                }
            } else {
                changes.push(((*name).to_string(), *value));
            }
        }
        Ok(changes)
    }

    /// V1 `batch_set_geometry`; with `coalesce`, repeated batches of the same label are one undo step.
    pub fn batch_set_geometry(
        &mut self,
        changes_by_id: &[(String, Vec<(&str, i64)>)],
        label: &str,
        coalesce: bool,
    ) -> CoreResult<bool> {
        let mut prepared = Vec::new();
        for (id, values) in changes_by_id {
            let changes = self.geometry_changes(id, values)?;
            if !changes.is_empty() {
                prepared.push((id.clone(), changes));
            }
        }
        if prepared.is_empty() {
            return Ok(false);
        }
        let before = self.elements();
        let mut after = before.clone();
        for (id, changes) in &prepared {
            if let Some(element) = after
                .iter_mut()
                .find(|e| e.get("id").map(py_str).as_deref() == Some(id))
            {
                for (path, value) in changes {
                    set_path(element, path, *value);
                }
            }
        }
        if after == before {
            return Ok(false);
        }
        self.set_elements(after.clone());
        self.dirty = true;
        self.redo.clear();
        let coalesced = coalesce
            && self.coalesce_open
            && matches!(self.undo.last(), Some(Command::Elements { label: last, .. }) if last == label);
        if coalesced {
            if let Some(Command::Elements {
                after: last_after, ..
            }) = self.undo.last_mut()
            {
                *last_after = after;
            }
        } else {
            self.push_undo(Command::Elements {
                label: label.into(),
                before,
                after,
            });
        }
        self.coalesce_open = coalesce;
        Ok(true)
    }

    pub fn set_geometry(
        &mut self,
        id: &str,
        values: &[(&str, i64)],
        coalesce: bool,
    ) -> CoreResult<bool> {
        if values.is_empty() {
            return Ok(false);
        }
        self.batch_set_geometry(
            &[(id.to_string(), values.to_vec())],
            &format!("geometry:{id}"),
            coalesce,
        )
    }

    pub fn batch_move(
        &mut self,
        ids: &[String],
        dx: i64,
        dy: i64,
        coalesce: bool,
    ) -> CoreResult<bool> {
        let mut changes = Vec::new();
        for id in ids {
            let element = self.element(id)?;
            if element
                .get("locked")
                .is_some_and(|v| v == &Value::Bool(true))
            {
                continue;
            }
            let geom = self.geometry(id)?;
            let mut values = Vec::new();
            if dx != 0 && geom.editable.x {
                values.push(("x", geom.x + dx));
            }
            if dy != 0 && geom.editable.y {
                values.push(("y", geom.y + dy));
            }
            if !values.is_empty() {
                changes.push((id.clone(), values));
            }
        }
        if changes.is_empty() {
            return Ok(false);
        }
        self.batch_set_geometry(&changes, "move_batch", coalesce)
    }

    pub fn end_coalesced_edit(&mut self) {
        self.coalesce_open = false;
    }

    fn apply(&mut self, command: &Command, forward: bool) {
        match command {
            Command::Elements { before, after, .. } => {
                self.set_elements(if forward {
                    after.clone()
                } else {
                    before.clone()
                });
            }
            Command::Scene { before, after, .. } => {
                self.doc.data = if forward {
                    after.clone()
                } else {
                    before.clone()
                };
                self.state = init_state(&self.doc.data);
                if let Ok(runtime) = SceneRuntime::new(&self.doc.data, None) {
                    self.state = runtime.state;
                }
                self.resources = DiskResources::new();
            }
        }
        self.dirty = true;
    }

    pub fn undo(&mut self) -> bool {
        self.end_coalesced_edit();
        let Some(command) = self.undo.pop() else {
            return false;
        };
        self.apply(&command, false);
        self.redo.push(command);
        true
    }

    pub fn redo(&mut self) -> bool {
        self.end_coalesced_edit();
        let Some(command) = self.redo.pop() else {
            return false;
        };
        self.apply(&command, true);
        self.push_undo(command);
        true
    }

    pub fn undo_label(&self) -> Option<&str> {
        self.undo.last().map(|c| match c {
            Command::Elements { label, .. } | Command::Scene { label, .. } => label.as_str(),
        })
    }

    /// Record an externally applied element mutation as one undo step (Automation transactions).
    pub fn record_external_batch(&mut self, before: Vec<Value>, label: &str) -> bool {
        let after = self.elements();
        if before == after {
            return false;
        }
        self.push_undo(Command::Elements {
            label: label.into(),
            before,
            after,
        });
        self.redo.clear();
        self.dirty = true;
        self.coalesce_open = false;
        true
    }

    /// Record a root-level scene mutation (e.g. state schema) as one undo step.
    pub fn record_external_scene(&mut self, before: Map<String, Value>, label: &str) -> bool {
        let after = self.doc.data.clone();
        if before == after {
            return false;
        }
        self.push_undo(Command::Scene {
            label: label.into(),
            before,
            after,
        });
        self.redo.clear();
        self.dirty = true;
        self.coalesce_open = false;
        true
    }

    pub fn add_elements(&mut self, elements: Vec<Value>, label: &str) -> CoreResult<Vec<String>> {
        if elements.is_empty() {
            return Ok(Vec::new());
        }
        let incoming: Vec<String> = elements
            .iter()
            .map(|e| e.get("id").map(py_str).unwrap_or_default())
            .collect();
        let unique: BTreeSet<&String> = incoming.iter().collect();
        if incoming.iter().any(String::is_empty) || unique.len() != incoming.len() {
            return Err(CoreError::invalid(
                "duplicate or empty element id in inserted elements",
            ));
        }
        let existing: BTreeSet<String> = self.element_ids().into_iter().collect();
        let mut duplicate: Vec<&String> = incoming
            .iter()
            .filter(|id| existing.contains(*id))
            .collect();
        if !duplicate.is_empty() {
            duplicate.sort();
            return Err(CoreError::invalid(format!(
                "duplicate element ids: [{}]",
                duplicate
                    .iter()
                    .map(|d| format!("'{d}'"))
                    .collect::<Vec<_>>()
                    .join(", ")
            )));
        }
        self.batch_edit(label, |items| {
            items.extend(elements);
            Ok(())
        })?;
        Ok(incoming)
    }

    pub fn add_placeholder(
        &mut self,
        id: &str,
        x: i64,
        y: i64,
        w: i64,
        h: i64,
        label: Option<&str>,
    ) -> CoreResult<String> {
        if self.element_ids().iter().any(|e| e == id) {
            return Err(CoreError::invalid(format!("duplicate element id: {id}")));
        }
        let element = json!({"id": id, "type": "placeholder", "x": x, "y": y, "w": w, "h": h, "label": label.unwrap_or(id)});
        self.batch_edit("add_placeholder", |items| {
            items.push(element);
            Ok(())
        })?;
        Ok(id.to_string())
    }

    pub fn remove_elements(&mut self, ids: &[String]) -> CoreResult<()> {
        if ids.is_empty() {
            return Ok(());
        }
        let existing: BTreeSet<String> = self.element_ids().into_iter().collect();
        let mut missing: Vec<&String> = ids.iter().filter(|id| !existing.contains(*id)).collect();
        if !missing.is_empty() {
            missing.sort();
            return Err(key_error(format!(
                "unknown element ids: [{}]",
                missing
                    .iter()
                    .map(|m| format!("'{m}'"))
                    .collect::<Vec<_>>()
                    .join(", ")
            )));
        }
        let set: BTreeSet<&String> = ids.iter().collect();
        self.batch_edit("remove_elements", |items| {
            items.retain(|e| !set.contains(&e.get("id").map(py_str).unwrap_or_default()));
            Ok(())
        })?;
        Ok(())
    }

    fn flag(&mut self, ids: &[String], key: &str, on: bool, label: &str) -> CoreResult<()> {
        let set: BTreeSet<String> = ids.iter().cloned().collect();
        let key = key.to_string();
        self.batch_edit(label, |items| {
            let mut found = BTreeSet::new();
            for item in items.iter_mut() {
                let id = item.get("id").map(py_str).unwrap_or_default();
                if set.contains(&id) {
                    found.insert(id);
                    if let Some(map) = item.as_object_mut() {
                        if on {
                            map.insert(key.clone(), Value::Bool(true));
                        } else {
                            map.shift_remove(&key);
                        }
                    }
                }
            }
            let missing: Vec<&String> = set.iter().filter(|id| !found.contains(*id)).collect();
            if missing.is_empty() {
                Ok(())
            } else {
                Err(key_error(format!("unknown element ids: {missing:?}")))
            }
        })?;
        Ok(())
    }

    pub fn set_locked(&mut self, ids: &[String], locked: bool) -> CoreResult<()> {
        self.flag(
            ids,
            "locked",
            locked,
            if locked { "lock" } else { "unlock" },
        )
    }

    pub fn set_hidden(&mut self, ids: &[String], hidden: bool) -> CoreResult<()> {
        self.flag(ids, "hidden", hidden, if hidden { "hide" } else { "show" })
    }

    pub fn group_elements(&mut self, ids: &[String], group_id: &str) -> CoreResult<String> {
        let set: BTreeSet<String> = ids.iter().cloned().collect();
        if set.len() < 2 {
            return Err(CoreError::invalid("group requires at least two elements"));
        }
        if group_id.is_empty() {
            return Err(CoreError::invalid("group_id must not be empty"));
        }
        self.batch_edit("group", |items| {
            let mut found = 0;
            for item in items.iter_mut() {
                if set.contains(&item.get("id").map(py_str).unwrap_or_default()) {
                    item["group"] = json!(group_id);
                    found += 1;
                }
            }
            if found == set.len() {
                Ok(())
            } else {
                Err(key_error("unknown element id"))
            }
        })?;
        Ok(group_id.into())
    }

    pub fn ungroup_elements(&mut self, ids: &[String]) -> CoreResult<()> {
        let set: BTreeSet<String> = ids.iter().cloned().collect();
        self.batch_edit("ungroup", |items| {
            for item in items.iter_mut() {
                if set.contains(&item.get("id").map(py_str).unwrap_or_default()) {
                    if let Some(map) = item.as_object_mut() {
                        map.shift_remove("group");
                    }
                }
            }
            Ok(())
        })?;
        Ok(())
    }

    fn reorder(&mut self, ids: &[String], front: bool) -> CoreResult<()> {
        let set: BTreeSet<String> = ids.iter().cloned().collect();
        self.batch_edit(
            if front {
                "bring_to_front"
            } else {
                "send_to_back"
            },
            |items| {
                let (chosen, rest): (Vec<Value>, Vec<Value>) = items
                    .drain(..)
                    .partition(|e| set.contains(&e.get("id").map(py_str).unwrap_or_default()));
                if chosen.len() != set.len() {
                    return Err(key_error("unknown element id"));
                }
                *items = if front {
                    [rest, chosen].concat()
                } else {
                    [chosen, rest].concat()
                };
                Ok(())
            },
        )?;
        Ok(())
    }

    pub fn bring_to_front(&mut self, ids: &[String]) -> CoreResult<()> {
        self.reorder(ids, true)
    }

    pub fn send_to_back(&mut self, ids: &[String]) -> CoreResult<()> {
        self.reorder(ids, false)
    }

    /// V1 `assign_bitmap`: placeholder/image becomes an image of the asset (imported into the project if outside).
    pub fn assign_bitmap(&mut self, id: &str, source: &Path) -> CoreResult<()> {
        let element = self.element(id)?;
        let kind = element.get("type").map(py_str).unwrap_or_default();
        if kind != "placeholder" && kind != "image" {
            return Err(CoreError::invalid(format!(
                "{id}: bitmap assignment is only valid for placeholder/image elements"
            )));
        }
        let source = py_resolve(source);
        let raw = read_file(&source)?;
        let asset = DiskResources::decode_bitmap(&source, &raw)?;
        let root = py_resolve(&self.doc.root);
        let stored = match source.strip_prefix(&root) {
            Ok(rel) => posix(rel),
            Err(_) => {
                let dir = root.join("assets").join("imported");
                std::fs::create_dir_all(&dir).map_err(|e| crate::resources::io_error(&dir, &e))?;
                let name = source
                    .file_name()
                    .map(|n| n.to_string_lossy().into_owned())
                    .unwrap_or_else(|| "asset.png".into());
                let mut target = dir.join(&name);
                if target.exists() && std::fs::read(&target).ok().as_deref() != Some(raw.as_slice())
                {
                    let stem = source
                        .file_stem()
                        .map(|s| s.to_string_lossy().into_owned())
                        .unwrap_or_default();
                    let ext = source
                        .extension()
                        .map(|e| e.to_string_lossy().to_lowercase())
                        .unwrap_or_default();
                    target = dir.join(format!("{stem}_{}.{ext}", &asset.sha256[..8]));
                }
                if !target.exists() {
                    crate::atomic::atomic_write(&target, &raw)?;
                }
                posix(target.strip_prefix(&root).unwrap_or(&target))
            }
        };
        let (w, h) = (asset.width, asset.height);
        self.batch_edit("assign_bitmap", |items| {
            if let Some(item) = items
                .iter_mut()
                .find(|e| e.get("id").map(py_str).as_deref() == Some(id))
            {
                if let Some(map) = item.as_object_mut() {
                    map.insert("type".into(), json!("image"));
                    map.insert("asset".into(), json!(stored));
                    map.insert("w".into(), json!(w));
                    map.insert("h".into(), json!(h));
                    map.shift_remove("label");
                    map.entry("blend").or_insert(json!("or"));
                    map.entry("resize_policy").or_insert(json!("native_only"));
                }
            }
            Ok(())
        })?;
        Ok(())
    }

    /// V1 `set_canvas_size` (not an undo step in V1).
    pub fn set_canvas_size(&mut self, width: i64, height: i64) -> CoreResult<()> {
        if width <= 0 {
            return Err(CoreError::invalid(
                "canvas width must be a positive integer",
            ));
        }
        if height <= 0 || height % 8 != 0 {
            return Err(CoreError::invalid(
                "canvas height must be a positive integer divisible by 8",
            ));
        }
        let canvas = self.doc.data.entry("canvas").or_insert_with(|| json!({}));
        if int_of(canvas.get("w")) == width && int_of(canvas.get("h")) == height {
            return Ok(());
        }
        canvas["w"] = json!(width);
        canvas["h"] = json!(height);
        let storage = self.doc.data.entry("storage").or_insert_with(|| json!({}));
        storage["bytes_per_frame"] = json!(width * (height / 8));
        self.dirty = true;
        Ok(())
    }

    pub fn set_state(&mut self, name: &str, value: Value) -> CoreResult<()> {
        let mut runtime = SceneRuntime::new(&self.doc.data, None)?;
        runtime.state = self.state.clone();
        runtime.elapsed = self.elapsed;
        runtime.set_state(name, value)?;
        self.state = runtime.state;
        Ok(())
    }

    pub fn step(&mut self, amount: i64) -> CoreResult<()> {
        let mut runtime = SceneRuntime::new(&self.doc.data, None)?;
        runtime.state = self.state.clone();
        runtime.elapsed = self.elapsed;
        runtime.step(&json!(amount))?;
        self.state = runtime.state;
        self.elapsed = runtime.elapsed;
        Ok(())
    }

    pub fn reset_runtime(&mut self) -> CoreResult<()> {
        let runtime = SceneRuntime::new(&self.doc.data, None)?;
        self.state = runtime.state;
        self.elapsed = 0;
        Ok(())
    }

    pub fn render(&mut self) -> CoreResult<RenderResult> {
        let root = self.doc.root.clone();
        render_scene(&self.doc.data, &root, &self.state, &mut self.resources)
    }

    pub fn validate(&mut self) -> Vec<Finding> {
        let root = self.doc.root.clone();
        let state = self.state.clone();
        validate_scene(&self.doc.data, &root, Some(&state), &mut self.resources)
    }

    /// V1 `SceneDocument.save`: refuses external modifications, atomic write.
    pub fn save(&mut self) -> CoreResult<PathBuf> {
        let current = std::fs::read(&self.doc.path).ok().map(|b| hex_digest(&b));
        match (&self.disk_fingerprint, &current) {
            (Some(expected), actual) if actual.as_ref() != Some(expected) => {
                return Err(CoreError::new(
                    "E-SCENE-EXTERNAL",
                    format!("scene was externally modified: {}", posix(&self.doc.path)),
                ));
            }
            (None, Some(_)) => {
                return Err(CoreError::new(
                    "E-SCENE-EXTERNAL",
                    format!("scene file appeared externally: {}", posix(&self.doc.path)),
                ));
            }
            _ => {}
        }
        let data: Map<String, Value> = self
            .doc
            .data
            .iter()
            .filter(|(k, _)| !k.starts_with('_'))
            .map(|(k, v)| (k.clone(), v.clone()))
            .collect();
        atomic_write_json(&self.doc.path, &Value::Object(data))?;
        self.disk_fingerprint = std::fs::read(&self.doc.path).ok().map(|b| hex_digest(&b));
        self.dirty = false;
        Ok(self.doc.path.clone())
    }

    pub fn scene_value(&self) -> Value {
        Value::Object(self.doc.data.clone())
    }

    pub fn is_int(value: &Value) -> bool {
        is_py_int(value)
    }
}

fn set_path(element: &mut Value, path: &str, value: i64) {
    let parts: Vec<&str> = path.split('.').collect();
    let mut node = element;
    for part in &parts[..parts.len() - 1] {
        let Some(next) = node.get_mut(*part) else {
            return;
        };
        node = next;
    }
    if let (Some(last), Some(map)) = (parts.last(), node.as_object_mut()) {
        map.insert((*last).to_string(), json!(value));
    }
}

/// Selection with an optional primary element (V1 `SelectionModel`).
#[derive(Debug, Clone, Default, PartialEq, Eq)]
pub struct Selection {
    ids: Vec<String>,
    primary: Option<String>,
}

impl Selection {
    pub fn ids(&self) -> &[String] {
        &self.ids
    }

    pub fn primary(&self) -> Option<&str> {
        self.primary.as_deref()
    }

    pub fn clear(&mut self) {
        self.ids.clear();
        self.primary = None;
    }

    pub fn replace(&mut self, ids: &[String], primary: Option<&str>) {
        self.ids.clear();
        for id in ids {
            if !self.ids.contains(id) {
                self.ids.push(id.clone());
            }
        }
        self.primary = primary
            .filter(|p| self.ids.iter().any(|i| i == p))
            .map(str::to_string)
            .or_else(|| self.ids.last().cloned());
    }

    pub fn toggle(&mut self, id: &str) -> bool {
        if let Some(pos) = self.ids.iter().position(|i| i == id) {
            self.ids.remove(pos);
            if self.primary.as_deref() == Some(id) {
                self.primary = self.ids.last().cloned();
            }
            false
        } else {
            self.ids.push(id.into());
            self.primary = Some(id.into());
            true
        }
    }

    pub fn contains(&self, id: &str) -> bool {
        self.ids.iter().any(|i| i == id)
    }

    pub fn retain_existing(&mut self, existing: &[String]) {
        self.ids.retain(|i| existing.contains(i));
        if self.primary.as_ref().is_some_and(|p| !existing.contains(p)) {
            self.primary = self.ids.last().cloned();
        }
    }
}

fn geoms(session: &mut EditorSession, ids: &[String]) -> CoreResult<Vec<(String, Geometry)>> {
    if ids.is_empty() {
        return Err(CoreError::invalid("at least one element is required"));
    }
    ids.iter()
        .map(|id| Ok((id.clone(), session.geometry(id)?)))
        .collect()
}

/// V1 `align_to` with reference `selection`, `primary` or `canvas`.
pub fn align_to(
    session: &mut EditorSession,
    ids: &[String],
    mode: &str,
    reference: &str,
    primary: Option<&str>,
) -> CoreResult<()> {
    let items = geoms(session, ids)?;
    let (left, top, right, bottom) = match reference {
        "primary" => {
            let p = primary
                .filter(|p| ids.iter().any(|i| i == p))
                .ok_or_else(|| CoreError::invalid("primary_id must be selected"))?;
            let g = session.geometry(p)?;
            (g.x, g.y, g.x + g.w, g.y + g.h)
        }
        "canvas" => {
            let canvas = session.scene().get("canvas").cloned().unwrap_or(json!({}));
            (0, 0, int_of(canvas.get("w")), int_of(canvas.get("h")))
        }
        "selection" => (
            items.iter().map(|(_, g)| g.x).min().unwrap_or(0),
            items.iter().map(|(_, g)| g.y).min().unwrap_or(0),
            items.iter().map(|(_, g)| g.x + g.w).max().unwrap_or(0),
            items.iter().map(|(_, g)| g.y + g.h).max().unwrap_or(0),
        ),
        other => {
            return Err(CoreError::invalid(format!(
                "unsupported alignment reference: {other}"
            )));
        }
    };
    let (cx, cy) = ((left + right) as f64 / 2.0, (top + bottom) as f64 / 2.0);
    let mut changes = Vec::new();
    for (id, g) in &items {
        if reference == "primary" && Some(id.as_str()) == primary {
            continue;
        }
        let values = match mode {
            "left" => vec![("x", left)],
            "right" => vec![("x", right - g.w)],
            "top" => vec![("y", top)],
            "bottom" => vec![("y", bottom - g.h)],
            "hcenter" => vec![("x", py_round(cx - g.w as f64 / 2.0))],
            "vcenter" => vec![("y", py_round(cy - g.h as f64 / 2.0))],
            other => {
                return Err(CoreError::invalid(format!(
                    "unsupported alignment mode: {other}"
                )));
            }
        };
        changes.push((id.clone(), values));
    }
    session.batch_set_geometry(&changes, &format!("align_to:{reference}:{mode}"), false)?;
    Ok(())
}

/// V1 `distribute` (needs at least three elements).
pub fn distribute(session: &mut EditorSession, ids: &[String], axis: &str) -> CoreResult<()> {
    let mut items = geoms(session, ids)?;
    if items.len() < 3 {
        return Ok(());
    }
    let horizontal = match axis {
        "horizontal" => true,
        "vertical" => false,
        other => {
            return Err(CoreError::invalid(format!(
                "unsupported distribution axis: {other}"
            )));
        }
    };
    items.sort_by_key(|(_, g)| if horizontal { g.x } else { g.y });
    let first = if horizontal {
        items[0].1.x
    } else {
        items[0].1.y
    };
    let last_g = items[items.len() - 1].1;
    let last = if horizontal { last_g.x } else { last_g.y };
    let step = (last - first) as f64 / (items.len() - 1) as f64;
    let key = if horizontal { "x" } else { "y" };
    let changes: Vec<(String, Vec<(&str, i64)>)> = items[1..items.len() - 1]
        .iter()
        .enumerate()
        .map(|(i, (id, _))| {
            (
                id.clone(),
                vec![(key, py_round(first as f64 + step * (i + 1) as f64))],
            )
        })
        .collect();
    session.batch_set_geometry(&changes, &format!("distribute:{axis}"), false)?;
    Ok(())
}

pub fn snap_positions(session: &mut EditorSession, ids: &[String], grid: i64) -> CoreResult<()> {
    if grid <= 0 {
        return Err(CoreError::invalid("grid must be a positive integer"));
    }
    let items = geoms(session, ids)?;
    let changes: Vec<(String, Vec<(&str, i64)>)> = items
        .iter()
        .map(|(id, g)| {
            (
                id.clone(),
                vec![
                    ("x", py_round(g.x as f64 / grid as f64) * grid),
                    ("y", py_round(g.y as f64 / grid as f64) * grid),
                ],
            )
        })
        .collect();
    session.batch_set_geometry(&changes, &format!("snap:{grid}"), false)?;
    Ok(())
}

/// Editor-only smart guides for a moving element (never affect the framebuffer).
pub fn smart_guides(
    session: &mut EditorSession,
    moving: &str,
    tolerance: i64,
) -> CoreResult<(Vec<i64>, Vec<i64>)> {
    let m = session.geometry(moving)?;
    let mx = [m.x, m.x + m.w / 2, m.x + m.w];
    let my = [m.y, m.y + m.h / 2, m.y + m.h];
    let (mut gx, mut gy) = (BTreeSet::new(), BTreeSet::new());
    for element in session.elements() {
        let id = element.get("id").map(py_str).unwrap_or_default();
        if id == moving || element.get("hidden") == Some(&Value::Bool(true)) {
            continue;
        }
        let Ok(g) = session.geometry(&id) else {
            continue;
        };
        for a in mx {
            for b in [g.x, g.x + g.w / 2, g.x + g.w] {
                if (a - b).abs() <= tolerance {
                    gx.insert(b);
                }
            }
        }
        for a in my {
            for b in [g.y, g.y + g.h / 2, g.y + g.h] {
                if (a - b).abs() <= tolerance {
                    gy.insert(b);
                }
            }
        }
    }
    Ok((gx.into_iter().collect(), gy.into_iter().collect()))
}

#[derive(Debug, Clone, PartialEq)]
pub struct SelectionMetrics {
    pub bounds: (i64, i64, i64, i64),
    pub horizontal_gaps: Vec<i64>,
    pub vertical_gaps: Vec<i64>,
    pub equal_horizontal_spacing: bool,
    pub equal_vertical_spacing: bool,
}

pub fn selection_metrics(
    session: &mut EditorSession,
    ids: &[String],
) -> CoreResult<SelectionMetrics> {
    let items = geoms(session, ids)?;
    let gs: Vec<Geometry> = items.iter().map(|(_, g)| *g).collect();
    let left = gs.iter().map(|g| g.x).min().unwrap_or(0);
    let top = gs.iter().map(|g| g.y).min().unwrap_or(0);
    let right = gs.iter().map(|g| g.x + g.w).max().unwrap_or(0);
    let bottom = gs.iter().map(|g| g.y + g.h).max().unwrap_or(0);
    let mut by_x = gs.clone();
    by_x.sort_by_key(|g| g.x);
    let hs: Vec<i64> = by_x
        .windows(2)
        .map(|w| (w[1].x - (w[0].x + w[0].w)).max(0))
        .collect();
    let mut by_y = gs;
    by_y.sort_by_key(|g| g.y);
    let vs: Vec<i64> = by_y
        .windows(2)
        .map(|w| (w[1].y - (w[0].y + w[0].h)).max(0))
        .collect();
    let all_eq = |v: &[i64]| !v.is_empty() && v.iter().all(|x| *x == v[0]);
    Ok(SelectionMetrics {
        bounds: (left, top, right - left, bottom - top),
        equal_horizontal_spacing: all_eq(&hs),
        equal_vertical_spacing: all_eq(&vs),
        horizontal_gaps: hs,
        vertical_gaps: vs,
    })
}
