//! Matrix-wide operations that may run inline or as jobs (V1
//! `_render_all_states_payload`, `_validate_all_states_payload`,
//! `_export_all_payload`, `_handoff_payload`).

use std::path::Path;
use std::time::Instant;

use mono_core::pyvalue::{py_str, py_truthy};
use mono_core::render::render_scene;
use mono_core::state::IntegerPolicy;
use mono_project::export::{build_handoff_package, export_scene, validate_scene};
use mono_project::project::resolve_under_root;
use mono_project::resources::{DiskResources, hex_digest};
use serde_json::{Map, Value, json};

use crate::error::{RpcError, RpcResult};
use crate::jobs::ProgressFn;
use crate::service::{Service, native};

fn cancelled() -> RpcError {
    RpcError::invalid("job cancellation requested")
}

fn flag(params: &Map<String, Value>, key: &str, default: bool) -> bool {
    params.get(key).map_or(default, py_truthy)
}

fn elapsed_ms(started: Instant) -> u64 {
    (started.elapsed().as_secs_f64() * 1000.0).round() as u64
}

fn canvas_bytes(scene: &Map<String, Value>) -> i64 {
    let canvas = scene.get("canvas");
    let dim = |k: &str| {
        canvas
            .and_then(|c| c.get(k))
            .and_then(mono_core::pyvalue::py_int)
            .unwrap_or(0)
    };
    dim("w") * ((dim("h") + 7) / 8)
}

pub fn render_all_states(
    scene: &Map<String, Value>,
    root: &Path,
    params: &Map<String, Value>,
    progress: ProgressFn<'_>,
) -> RpcResult<Value> {
    let matrix = Service::state_matrix(scene, params, 5000)?;
    let include = flag(
        params,
        "include_frames",
        !flag(params, "summary_only", false),
    );
    let mut resources = DiskResources::frozen();
    let mut frames = Vec::new();
    let mut expected: Option<usize> = None;
    let started = Instant::now();
    let total = matrix.len();
    for (index, (name, state)) in matrix.iter().enumerate() {
        let result = render_scene(scene, root, state, &mut resources)?;
        let raw = result.framebuffer.to_vlsb()?;
        let size = *expected.get_or_insert(raw.len());
        if raw.len() != size {
            return Err(RpcError::invalid(
                "framebuffer size changed across state matrix",
            ));
        }
        if include {
            let lit: usize = result
                .framebuffer
                .pixels()
                .iter()
                .map(|v| usize::from(*v))
                .sum();
            frames.push(json!({"name": name, "state": state, "sha256": hex_digest(&raw), "lit_pixels": lit}));
        }
        if !progress("render", index + 1, total) {
            return Err(cancelled());
        }
    }
    let mut payload = json!({
        "cases": total,
        "framebuffer_bytes": expected.map_or_else(|| canvas_bytes(scene), |n| n as i64),
        "deterministic": true,
        "elapsed_ms": elapsed_ms(started),
    });
    if include {
        payload["frames"] = Value::Array(frames);
    }
    Ok(payload)
}

pub fn validate_all_states(
    scene: &Map<String, Value>,
    root: &Path,
    params: &Map<String, Value>,
    progress: ProgressFn<'_>,
) -> RpcResult<Value> {
    let matrix = Service::state_matrix(scene, params, 5000)?;
    let include = flag(
        params,
        "include_cases",
        !flag(params, "summary_only", false),
    );
    let mut resources = DiskResources::frozen();
    let (mut failures, mut total_findings, mut blockers) = (Vec::new(), 0usize, 0usize);
    let started = Instant::now();
    let total = matrix.len();
    for (index, (name, state)) in matrix.iter().enumerate() {
        let findings = validate_scene(scene, root, Some(state), &mut resources);
        total_findings += findings.len();
        let case_blockers = findings
            .iter()
            .filter(|f| f.severity == "BLOCKER" || f.severity == "ERROR")
            .count();
        blockers += case_blockers;
        if include && !findings.is_empty() {
            let rows: Vec<Value> = findings
                .iter()
                .map(|f| json!({"severity": f.severity, "code": f.code, "message": f.message, "element_id": f.element_id}))
                .collect();
            failures.push(
                json!({"name": name, "state": state, "blockers": case_blockers, "findings": rows}),
            );
        }
        if !progress("validation", index + 1, total) {
            return Err(cancelled());
        }
    }
    let mut payload = json!({
        "cases": total,
        "findings": total_findings,
        "blockers": blockers,
        "valid": blockers == 0,
        "elapsed_ms": elapsed_ms(started),
    });
    if include {
        payload["cases_with_findings"] = Value::Array(failures);
    }
    Ok(payload)
}

pub fn export_all(
    scene: &Map<String, Value>,
    root: &Path,
    project_root: &Path,
    params: &Map<String, Value>,
    progress: ProgressFn<'_>,
) -> RpcResult<Value> {
    let member = params
        .get("output_dir")
        .map_or_else(|| "exports/agent_all".into(), py_str);
    let output = resolve_under_root(project_root, &member, "export directory")?;
    let states = Service::state_matrix(scene, params, 5000)?;
    let started = Instant::now();
    let summary = export_scene(scene, root, &output, &states, &mut |stage, done, total| {
        progress(stage, done, total)
    })?;
    let mut payload = json!({
        "output_dir": native(&output),
        "frame_count": summary.frame_count,
        "elapsed_ms": elapsed_ms(started),
    });
    if flag(
        params,
        "include_hashes",
        !flag(params, "summary_only", false),
    ) {
        payload["frame_hashes"] = json!(summary.frame_hashes);
    }
    Ok(payload)
}

pub fn handoff(
    scene: &Map<String, Value>,
    root: &Path,
    project_root: &Path,
    params: &Map<String, Value>,
    progress: ProgressFn<'_>,
) -> RpcResult<Value> {
    let member = params
        .get("path")
        .map_or_else(|| "exports/code_ai_handoff.zip".into(), py_str);
    let target = resolve_under_root(project_root, &member, "Code AI handoff")?;
    let is_zip = target
        .extension()
        .is_some_and(|e| e.eq_ignore_ascii_case("zip"));
    if !is_zip {
        return Err(RpcError::invalid("Code AI handoff must end in .zip"));
    }
    let states = Service::state_matrix(scene, params, 5000)?;
    let policy = params
        .get("integer_policy")
        .map_or_else(|| "representative".into(), py_str);
    let started = Instant::now();
    let summary = build_handoff_package(
        scene,
        root,
        &target,
        &states,
        IntegerPolicy::parse(&policy)?,
        &mut |stage, done, total| progress(stage, done, total),
    )?;
    let raw = std::fs::read(&target).map_err(|e| RpcError::invalid(e.to_string()))?;
    Ok(json!({
        "path": native(&target),
        "sha256": hex_digest(&raw),
        "frame_count": summary.frame_count,
        "elapsed_ms": elapsed_ms(started),
    }))
}
