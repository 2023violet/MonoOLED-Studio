//! `StudioAutomationService` (V1 `automation_service.py`): semantic project /
//! scene / pixel / font operations with revisions, transactions, an event
//! stream and long-running jobs.

use std::collections::BTreeMap;
use std::path::{Path, PathBuf};
use std::sync::OnceLock;

use mono_core::pixel::PixelDocument;
use mono_core::render::{RenderResult, posix, render_scene};
use mono_core::state::{IntegerPolicy, State, build_export_states, init_state};
use mono_project::editor::{EditorSession, Selection};
use mono_project::project::{ProjectWorkspace, resolve_under_root};
use mono_project::resources::{DiskResources, hex_digest};
use mono_project::scene_io::{SceneDoc, load_project_scene, load_scene};
use serde_json::{Map, Value, json};

use crate::error::{RpcError, RpcResult};
use crate::jobs::JobManager;

pub const API_VERSION: &str = "1.3.0";
const SPECS_JSON: &str = include_str!("method_specs.json");

/// V1 `METHOD_SPECS`, in declaration order.
pub fn method_specs() -> &'static Map<String, Value> {
    static SPECS: OnceLock<Map<String, Value>> = OnceLock::new();
    SPECS.get_or_init(|| match serde_json::from_str::<Value>(SPECS_JSON) {
        Ok(Value::Object(map)) => map,
        _ => Map::new(),
    })
}

pub fn spec_permission(method: &str) -> Option<&'static str> {
    method_specs()
        .get(method)
        .and_then(|s| s.get("permission"))
        .and_then(Value::as_str)
}

/// Synchronous methods whose result depends only on a snapshot of the scene
/// (the same work `job.start` runs on a thread); the bridge computes them off
/// the draining (UI) thread.
pub const OFFLOADABLE: [&str; 3] = ["render.all_states", "validate.all_states", "export.all"];

/// Snapshot work produced by `Service::offload`.
pub type Offloaded = Box<dyn FnOnce() -> RpcResult<Value> + Send>;

fn transaction_supported(method: &str) -> bool {
    method_specs()
        .get(method)
        .and_then(|s| s.get("transaction_supported"))
        .and_then(Value::as_bool)
        .unwrap_or(false)
}

/// Methods that mutate elements and therefore record one Designer undo step.
const ELEMENT_EDITS: [&str; 5] = [
    "scene.update_element",
    "scene.create_element",
    "scene.delete_elements",
    "layout.align",
    "layout.distribute",
];

struct Transaction {
    scene: Map<String, Value>,
    selection: Vec<String>,
    primary: Option<String>,
}

pub struct PixelEntry {
    pub doc: PixelDocument,
    pub path: Option<PathBuf>,
}

/// Python `json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False)`.
fn sorted_compact(value: &Value) -> String {
    fn sort(value: &Value) -> Value {
        match value {
            Value::Object(map) => {
                let sorted: BTreeMap<&String, Value> =
                    map.iter().map(|(k, v)| (k, sort(v))).collect();
                Value::Object(sorted.into_iter().map(|(k, v)| (k.clone(), v)).collect())
            }
            Value::Array(items) => Value::Array(items.iter().map(sort).collect()),
            other => other.clone(),
        }
    }
    serde_json::to_string(&sort(value)).unwrap_or_default()
}

fn persistent(scene: &Map<String, Value>) -> Map<String, Value> {
    scene
        .iter()
        .filter(|(k, _)| !k.starts_with('_'))
        .map(|(k, v)| (k.clone(), v.clone()))
        .collect()
}

pub fn native(path: &Path) -> String {
    path.display().to_string()
}

pub struct Service {
    pub permission: String,
    pub revision: i64,
    pub session: EditorSession,
    pub project: Option<ProjectWorkspace>,
    pub project_root: PathBuf,
    pub source_path: Option<PathBuf>,
    pub selection: Selection,
    /// True when the session is the Designer's live session (record undo steps).
    pub editor_attached: bool,
    pub resources: DiskResources,
    pub pixels: BTreeMap<String, PixelEntry>,
    pub pixel_order: Vec<String>,
    pub jobs: JobManager,
    tx: BTreeMap<String, Transaction>,
    tx_seq: usize,
    max_transactions: usize,
    events: Vec<Value>,
    event_base: usize,
    event_limit: usize,
    pixel_limit: usize,
    saved_fingerprint: String,
}

/// V1 `load_scene` adds these private keys; `save_scene` strips them again.
pub fn add_scene_keys(doc: &mut SceneDoc) {
    let disk = std::fs::canonicalize(&doc.path).unwrap_or_else(|_| doc.path.clone());
    let disk = mono_project::project::py_resolve(&disk);
    let entries = [
        ("_path", native(&doc.path)),
        ("_root", native(&doc.root)),
        ("_disk_path", native(&disk)),
        ("_disk_sha256", doc.disk_sha256.clone()),
    ];
    for (key, value) in entries {
        if !doc.data.contains_key(key) {
            doc.data.insert(key.into(), Value::from(value));
        }
    }
}

impl Service {
    pub fn new(
        mut doc: SceneDoc,
        project: Option<ProjectWorkspace>,
        permission: &str,
    ) -> RpcResult<Self> {
        if !["observe", "edit", "full"].contains(&permission) {
            return Err(RpcError::invalid("permission must be observe/edit/full"));
        }
        add_scene_keys(&mut doc);
        let project_root = project
            .as_ref()
            .map(|p| p.root.clone())
            .unwrap_or_else(|| doc.root.clone());
        let source_path = Some(doc.path.clone());
        let session = EditorSession::new(doc)?;
        let mut service = Self {
            permission: permission.into(),
            revision: 0,
            session,
            project,
            project_root,
            source_path,
            selection: Selection::default(),
            editor_attached: false,
            resources: DiskResources::new(),
            pixels: BTreeMap::new(),
            pixel_order: Vec::new(),
            jobs: JobManager::new(4, 16),
            tx: BTreeMap::new(),
            tx_seq: 0,
            max_transactions: 16,
            events: Vec::new(),
            event_base: 0,
            event_limit: 4096,
            pixel_limit: 64,
            saved_fingerprint: String::new(),
        };
        service.saved_fingerprint = service.fingerprint();
        Ok(service)
    }

    /// Service over a project's `screen` (the corpus harness and the CLI bridge).
    pub fn for_project(manifest: &Path, screen: Option<&str>, permission: &str) -> RpcResult<Self> {
        let project = ProjectWorkspace::load(manifest)?;
        let screen = screen
            .map(str::to_string)
            .unwrap_or_else(|| project.active_screen());
        let path = project.screen_path(&screen)?;
        let doc = load_scene(&path, Some(&project.root))?;
        Self::new(doc, Some(project), permission)
    }

    pub fn scene(&self) -> &Map<String, Value> {
        &self.session.doc.data
    }

    pub fn scene_mut(&mut self) -> &mut Map<String, Value> {
        &mut self.session.doc.data
    }

    fn fingerprint(&self) -> String {
        hex_digest(sorted_compact(&Value::Object(persistent(self.scene()))).as_bytes())
    }

    pub fn is_dirty(&self) -> bool {
        self.fingerprint() != self.saved_fingerprint || (self.editor_attached && self.session.dirty)
    }

    /// After a host (the Designer) lends its live session: a clean session
    /// means "saved", so the content baseline follows it.
    pub fn sync_baseline(&mut self) {
        if !self.session.dirty {
            self.saved_fingerprint = self.fingerprint();
        }
    }

    pub fn refresh_saved_baseline(&mut self) {
        self.saved_fingerprint = self.fingerprint();
        self.session.dirty = false;
    }

    // ------------------------------------------------------------- results

    pub fn result(&self, extra: Value) -> Value {
        let mut out = Map::new();
        out.insert("ok".into(), json!(true));
        out.insert("revision".into(), json!(self.revision));
        if let Value::Object(map) = extra {
            for (k, v) in map {
                out.insert(k, v);
            }
        }
        Value::Object(out)
    }

    pub fn notify(&mut self, event: &str, extra: Value) {
        let mut payload = Map::new();
        payload.insert("event".into(), json!(event));
        payload.insert("revision".into(), json!(self.revision));
        if let Value::Object(map) = extra {
            for (k, v) in map {
                payload.insert(k, v);
            }
        }
        self.events.push(Value::Object(payload));
        if self.events.len() > self.event_limit {
            let overflow = self.events.len() - self.event_limit;
            self.events.drain(..overflow);
            self.event_base += overflow;
        }
    }

    pub fn events_since(&self, since: usize) -> Value {
        let retained_from = self.event_base;
        let start = since.saturating_sub(retained_from).min(self.events.len());
        json!({
            "events": self.events[start..].to_vec(),
            "retained_from": retained_from,
            "dropped_before": retained_from.saturating_sub(since),
            "next_cursor": retained_from + self.events.len(),
        })
    }

    /// V1 `_changed`: outside a transaction, bump the revision and emit an event.
    pub fn changed(&mut self, method: &str, transaction: Option<&str>, before: Option<Vec<Value>>) {
        if transaction.is_none() {
            if let (true, Some(before)) = (self.editor_attached, before) {
                self.session
                    .record_external_batch(before, &format!("agent_{}", method.replace('.', "_")));
            }
            self.revision += 1;
            self.notify(method, json!({}));
        }
    }

    // --------------------------------------------------------- transactions

    fn check_revision(&self, expected: Option<&Value>) -> RpcResult<()> {
        let Some(expected) = expected.filter(|v| !v.is_null()) else {
            return Ok(());
        };
        let value = mono_core::pyvalue::py_int(expected)
            .ok_or_else(|| RpcError::invalid("invalid _expected_revision"))?;
        if value != self.revision {
            return Err(RpcError::StaleRevision(format!(
                "expected revision {value}, current {}",
                self.revision
            )));
        }
        Ok(())
    }

    fn write_guard(&self, method: &str) -> RpcResult<()> {
        if self.permission == "observe" && spec_permission(method) != Some("observe") {
            return Err(RpcError::PermissionDenied(method.into()));
        }
        Ok(())
    }

    pub fn begin_transaction(&mut self, expected: Option<&Value>) -> RpcResult<String> {
        self.check_revision(expected)?;
        self.write_guard("history.begin_transaction")?;
        if self.tx.len() >= self.max_transactions {
            return Err(RpcError::Transaction(format!(
                "active transaction limit reached: {}",
                self.max_transactions
            )));
        }
        self.tx_seq += 1;
        let id = format!("tx-{}", self.tx_seq);
        self.tx.insert(
            id.clone(),
            Transaction {
                scene: self.scene().clone(),
                selection: self.selection.ids().to_vec(),
                primary: self.selection.primary().map(str::to_string),
            },
        );
        Ok(id)
    }

    pub fn commit_transaction(&mut self, id: &str) -> RpcResult<Value> {
        let tx = self
            .tx
            .remove(id)
            .ok_or_else(|| RpcError::Transaction(id.into()))?;
        if self.editor_attached {
            self.session
                .record_external_scene(tx.scene, "agent_transaction");
        }
        self.revision += 1;
        self.notify("transaction.committed", json!({}));
        Ok(self.result(json!({})))
    }

    pub fn rollback_transaction(&mut self, id: &str) -> RpcResult<Value> {
        let tx = self
            .tx
            .remove(id)
            .ok_or_else(|| RpcError::Transaction(id.into()))?;
        // V1 rollback rebinds the editor (`reset_scene`): runtime state and
        // history must match the restored scene, not the rolled-back one.
        let mut doc = self.session.doc.clone();
        doc.data = tx.scene;
        self.session.reset_scene(doc)?;
        self.selection.replace(&tx.selection, tx.primary.as_deref());
        self.notify("transaction.rolled_back", json!({}));
        Ok(self.result(json!({})))
    }

    /// V1 `call`: guards, then the domain dispatchers.
    /// For the matrix-wide synchronous methods: run `call`'s guards now and
    /// return the work as a snapshot closure that may run on another thread
    /// and yields the same result. `None` for every other call (and inside
    /// transactions), which must go through `call`.
    pub fn offload(
        &self,
        method: &str,
        params: &Map<String, Value>,
        expected: Option<&Value>,
        transaction: Option<&str>,
    ) -> Option<RpcResult<Offloaded>> {
        if transaction.is_some() || !OFFLOADABLE.contains(&method) {
            return None;
        }
        Some((|| {
            self.check_revision(expected)?;
            self.write_guard(method)?;
            let work = crate::dispatch::matrix_work(self, method, params.clone());
            Ok(Box::new(move || work(&mut |_, _, _| true)) as Offloaded)
        })())
    }

    pub fn call(
        &mut self,
        method: &str,
        params: &Map<String, Value>,
        expected: Option<&Value>,
        transaction: Option<&str>,
    ) -> RpcResult<Value> {
        self.check_revision(expected)?;
        self.write_guard(method)?;
        if !method_specs().contains_key(method) {
            return Err(RpcError::key(method));
        }
        if let Some(tx) = transaction {
            if !self.tx.contains_key(tx) {
                return Err(RpcError::Transaction(tx.into()));
            }
            if !transaction_supported(method) {
                return Err(RpcError::Transaction(format!(
                    "{method} is not transaction-safe"
                )));
            }
        }
        let before =
            (self.editor_attached && transaction.is_none() && ELEMENT_EDITS.contains(&method))
                .then(|| self.elements());
        crate::dispatch::dispatch(self, method, params, transaction, before)
    }

    // ------------------------------------------------------------- helpers

    pub fn elements(&self) -> Vec<Value> {
        self.scene()
            .get("elements")
            .and_then(Value::as_array)
            .cloned()
            .unwrap_or_default()
    }

    pub fn require_project(&self) -> RpcResult<&ProjectWorkspace> {
        self.project.as_ref().ok_or_else(|| {
            RpcError::invalid("current scene is not attached to an OLED project manifest")
        })
    }

    pub fn require_project_mut(&mut self) -> RpcResult<&mut ProjectWorkspace> {
        self.project.as_mut().ok_or_else(|| {
            RpcError::invalid("current scene is not attached to an OLED project manifest")
        })
    }

    /// V1 `_render`: an empty/missing state means the scene's initial state.
    pub fn render(&mut self, state: Option<&Value>) -> RpcResult<(State, RenderResult)> {
        let state = match state {
            Some(Value::Object(map)) if !map.is_empty() => map.clone(),
            _ => init_state(self.scene()),
        };
        let root = self.session.doc.root.clone();
        let result = render_scene(&self.session.doc.data, &root, &state, &mut self.resources)?;
        Ok((state, result))
    }

    pub fn under_root(&self, member: &str, label: &str) -> RpcResult<PathBuf> {
        Ok(resolve_under_root(&self.project_root, member, label)?)
    }

    /// V1 `_asset_path`: project member with a bitmap suffix.
    pub fn asset_path(&self, member: &str, label: &str) -> RpcResult<PathBuf> {
        let path = self.under_root(member, label)?;
        let ext = path
            .extension()
            .map(|e| format!(".{}", e.to_string_lossy().to_lowercase()))
            .unwrap_or_default();
        if ![".png", ".bmp", ".jpg", ".jpeg"].contains(&ext.as_str()) {
            return Err(RpcError::invalid(format!(
                "{label} must be a supported bitmap file: {ext}"
            )));
        }
        Ok(path)
    }

    pub fn rel(&self, path: &Path) -> String {
        let root = mono_project::project::py_resolve(&self.project_root);
        let path = mono_project::project::py_resolve(path);
        path.strip_prefix(&root)
            .map(posix)
            .unwrap_or_else(|_| posix(&path))
    }

    pub fn file_result(&self, path: &Path) -> RpcResult<Value> {
        let raw = std::fs::read(path).map_err(|e| RpcError::invalid(e.to_string()))?;
        Ok(json!({"path": self.rel(path), "bytes": raw.len(), "sha256": hex_digest(&raw)}))
    }

    pub fn register_pixel(&mut self, id: &str, doc: PixelDocument, path: PathBuf) -> RpcResult<()> {
        if !self.pixels.contains_key(id) && self.pixels.len() >= self.pixel_limit {
            return Err(RpcError::invalid(format!(
                "pixel document limit reached: {}",
                self.pixel_limit
            )));
        }
        if !self.pixel_order.iter().any(|p| p == id) {
            self.pixel_order.push(id.into());
        }
        self.pixels.insert(
            id.into(),
            PixelEntry {
                doc,
                path: Some(path),
            },
        );
        Ok(())
    }

    pub fn unregister_pixel(&mut self, id: &str) {
        self.pixels.remove(id);
        self.pixel_order.retain(|p| p != id);
    }

    pub fn pixel_result(&self, id: &str) -> RpcResult<Value> {
        let entry = self
            .pixels
            .get(id)
            .ok_or_else(|| RpcError::key(format!("unknown pixel document: {id}")))?;
        let raw = entry.doc.to_vlsb();
        Ok(self.result(json!({
            "document_id": id,
            "width": entry.doc.width(),
            "height": entry.doc.height(),
            "bytes": raw.len(),
            "sha256": hex_digest(&raw),
            "pixels": entry.doc.rows(),
            "dirty": entry.doc.dirty,
        })))
    }

    // -------------------------------------------------------- project screens

    /// V1 `_handle_unsaved_policy`.
    pub fn handle_unsaved(&mut self, params: &Map<String, Value>, target: &str) -> RpcResult<()> {
        let flag = |k: &str| params.get(k).is_some_and(mono_core::pyvalue::py_truthy);
        let (save, discard) = (flag("save_current"), flag("discard_current"));
        if save && discard {
            return Err(RpcError::invalid(
                "save_current and discard_current are mutually exclusive",
            ));
        }
        if !self.is_dirty() {
            return Ok(());
        }
        if save {
            self.save_current_scene()?;
            if let Some(project) = self.project.as_mut() {
                project.save()?;
            }
            return Ok(());
        }
        if discard {
            return Ok(());
        }
        let current = self
            .project
            .as_ref()
            .map(|p| mono_core::pyvalue::py_repr(&Value::from(p.active_screen())))
            .unwrap_or_else(|| "None".into());
        let target = mono_core::pyvalue::py_repr(&Value::from(target));
        Err(RpcError::Unsaved(format!(
            "UNSAVED_CHANGES: current screen {current} has unsaved changes; use save_current=true or discard_current=true before opening {target}"
        )))
    }

    pub fn save_current_scene(&mut self) -> RpcResult<PathBuf> {
        let path = self
            .source_path
            .clone()
            .ok_or_else(|| RpcError::invalid("current scene has no writable source path"))?;
        mono_project::atomic::atomic_write_json(&path, &Value::Object(persistent(self.scene())))?;
        self.refresh_saved_baseline();
        Ok(path)
    }

    /// V1 `_open_project_screen`.
    pub fn open_project_screen(&mut self, screen_id: &str, event: &str) -> RpcResult<Value> {
        let project = self.require_project_mut()?;
        project.screen(screen_id)?;
        project.set_active_screen(screen_id)?;
        project.save()?;
        let project = self.require_project()?;
        let mut doc = load_project_scene(project, Some(screen_id))?;
        add_scene_keys(&mut doc);
        let path = doc.path.clone();
        let root = project.root.clone();
        // V1 `editor_session.reset_scene`: history and fingerprint belong to the screen.
        self.session.reset_scene(doc)?;
        self.source_path = Some(path.clone());
        self.project_root = root;
        self.selection.clear();
        self.tx.clear();
        self.refresh_saved_baseline();
        self.revision += 1;
        self.notify(event, json!({"active_screen": screen_id}));
        Ok(self.result(json!({
            "active_screen": screen_id,
            "scene_path": native(&path),
            "active_screen_changed": true,
            "project_structure_changed": true,
        })))
    }

    pub fn state_matrix(
        scene: &Map<String, Value>,
        params: &Map<String, Value>,
        default_limit: usize,
    ) -> RpcResult<Vec<(String, State)>> {
        let policy = params
            .get("integer_policy")
            .map(mono_core::pyvalue::py_str)
            .unwrap_or_else(|| "representative".into());
        let policy = IntegerPolicy::parse(&policy)?;
        let max_cases = params
            .get("max_cases")
            .and_then(mono_core::pyvalue::py_int)
            .map_or(default_limit, |v| v.max(0) as usize);
        let allow = params
            .get("allow_large_matrix")
            .is_some_and(mono_core::pyvalue::py_truthy);
        Ok(build_export_states(scene, policy, max_cases, allow)?)
    }
}
