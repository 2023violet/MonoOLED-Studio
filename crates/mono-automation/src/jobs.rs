//! Server-owned long-running jobs (V1 `automation_jobs.AutomationJobManager`).
//! Each job runs on its own thread against a snapshot taken at start time.

use std::collections::BTreeMap;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex, MutexGuard};
use std::time::Instant;

use serde_json::{Value, json};

use crate::error::{RpcError, RpcResult};

pub const TERMINAL: [&str; 3] = ["completed", "failed", "cancelled"];

/// The runners' cancellation errors (ops: progress returned false; mono-project
/// export: CANCELLED -> "operation cancelled").
fn is_cancellation(error: &RpcError) -> bool {
    matches!(
        error.message(),
        "job cancellation requested" | "operation cancelled"
    )
}

/// Progress sink handed to a runner: returns false once cancellation was requested.
pub type ProgressFn<'a> = &'a mut dyn FnMut(&str, usize, usize) -> bool;
pub type Runner = Box<dyn FnOnce(ProgressFn<'_>) -> RpcResult<Value> + Send>;

struct Job {
    id: String,
    operation: String,
    seq: usize,
    state: String,
    stage: String,
    completed: usize,
    total: usize,
    started: Option<Instant>,
    finished: Option<Instant>,
    result: Option<Value>,
    error: Option<Value>,
    cancel_requested: bool,
    cancel: Arc<AtomicBool>,
}

#[derive(Default)]
struct Registry {
    seq: usize,
    jobs: BTreeMap<String, Job>,
}

pub struct JobManager {
    inner: Arc<Mutex<Registry>>,
    max_active: usize,
    max_terminal: usize,
}

fn lock(inner: &Mutex<Registry>) -> MutexGuard<'_, Registry> {
    inner
        .lock()
        .unwrap_or_else(std::sync::PoisonError::into_inner)
}

fn prune_terminal(registry: &mut Registry, max_terminal: usize) {
    let mut terminal: Vec<(Option<Instant>, usize, String)> = registry
        .jobs
        .values()
        .filter(|j| TERMINAL.contains(&j.state.as_str()))
        .map(|j| (j.finished, j.seq, j.id.clone()))
        .collect();
    // Python sorts by (finished_at or inf, id).
    terminal.sort_by(|a, b| match (a.0, b.0) {
        (Some(x), Some(y)) => x.cmp(&y).then(a.1.cmp(&b.1)),
        (Some(_), None) => std::cmp::Ordering::Less,
        (None, Some(_)) => std::cmp::Ordering::Greater,
        (None, None) => a.1.cmp(&b.1),
    });
    let excess = terminal.len().saturating_sub(max_terminal);
    for (_, _, id) in terminal.into_iter().take(excess) {
        registry.jobs.remove(&id);
    }
}

impl JobManager {
    pub fn new(max_active: usize, max_terminal: usize) -> Self {
        Self {
            inner: Arc::new(Mutex::new(Registry::default())),
            max_active: max_active.max(1),
            max_terminal: max_terminal.max(1),
        }
    }

    pub fn start(&self, operation: &str, runner: Runner) -> RpcResult<String> {
        let (id, cancel) = {
            let mut registry = lock(&self.inner);
            let active = registry
                .jobs
                .values()
                .filter(|j| !TERMINAL.contains(&j.state.as_str()))
                .count();
            if active >= self.max_active {
                return Err(RpcError::invalid(format!(
                    "active job limit reached: {}",
                    self.max_active
                )));
            }
            registry.seq += 1;
            let seq = registry.seq;
            let id = format!("job-{seq}");
            let cancel = Arc::new(AtomicBool::new(false));
            registry.jobs.insert(
                id.clone(),
                Job {
                    id: id.clone(),
                    operation: operation.into(),
                    seq,
                    state: "queued".into(),
                    stage: "queued".into(),
                    completed: 0,
                    total: 0,
                    started: None,
                    finished: None,
                    result: None,
                    error: None,
                    cancel_requested: false,
                    cancel: Arc::clone(&cancel),
                },
            );
            (id, cancel)
        };
        let inner = Arc::clone(&self.inner);
        let max_terminal = self.max_terminal;
        let job_id = id.clone();
        let spawned = std::thread::Builder::new()
            .name(format!("MonoOLED-{id}"))
            .spawn(move || {
                {
                    let mut registry = lock(&inner);
                    if let Some(job) = registry.jobs.get_mut(&job_id) {
                        job.state = "running".into();
                        job.stage = "starting".into();
                        job.started = Some(Instant::now());
                    }
                }
                let progress_inner = Arc::clone(&inner);
                let progress_id = job_id.clone();
                let progress_cancel = Arc::clone(&cancel);
                let mut progress = move |stage: &str, done: usize, total: usize| -> bool {
                    let mut registry = lock(&progress_inner);
                    if let Some(job) = registry.jobs.get_mut(&progress_id) {
                        job.stage = stage.into();
                        job.completed = done;
                        job.total = total;
                    }
                    !progress_cancel.load(Ordering::SeqCst)
                };
                let outcome = runner(&mut progress);
                // V1: cancelled when the runner stopped for the cancellation (or
                // finished after it was requested); any other error is a failure.
                let cancelled = cancel.load(Ordering::SeqCst)
                    && match &outcome {
                        Ok(_) => true,
                        Err(error) => is_cancellation(error),
                    };
                let mut registry = lock(&inner);
                if let Some(job) = registry.jobs.get_mut(&job_id) {
                    match outcome {
                        _ if cancelled => {
                            job.state = "cancelled".into();
                            job.stage = "cancelled".into();
                            job.error = Some(json!({"code": "CANCELLED", "message": "job cancellation requested"}));
                        }
                        Ok(result) => {
                            job.result = Some(result);
                            job.state = "completed".into();
                            job.stage = "completed".into();
                            if job.total == 0 {
                                job.total = 1;
                            }
                            job.completed = job.total;
                        }
                        Err(error) => {
                            let code = match error {
                                RpcError::NotFound(_) => "KeyError",
                                _ => "ValueError",
                            };
                            job.state = "failed".into();
                            job.stage = "failed".into();
                            job.error = Some(json!({"code": code, "message": error.message()}));
                        }
                    }
                    job.finished = Some(Instant::now());
                }
                prune_terminal(&mut registry, max_terminal);
            });
        if spawned.is_err() {
            lock(&self.inner).jobs.remove(&id);
            return Err(RpcError::invalid("could not start job thread"));
        }
        Ok(id)
    }

    fn with_job<T>(&self, id: &str, f: impl FnOnce(&mut Job) -> T) -> RpcResult<T> {
        let mut registry = lock(&self.inner);
        let job = registry
            .jobs
            .get_mut(id)
            .ok_or_else(|| RpcError::key(format!("unknown job id: {id}")))?;
        Ok(f(job))
    }

    pub fn status(&self, id: &str) -> RpcResult<Value> {
        self.with_job(id, |job| {
            let percent = if job.state == "completed" {
                100.0
            } else if job.total == 0 {
                0.0
            } else {
                (job.completed as f64 * 100.0 / job.total as f64).min(100.0)
            };
            let elapsed = job.started.map_or(0, |start| {
                job.finished
                    .unwrap_or_else(Instant::now)
                    .duration_since(start)
                    .as_millis() as u64
            });
            json!({
                "job_id": job.id,
                "operation": job.operation,
                "state": job.state,
                "stage": job.stage,
                "progress": {"completed": job.completed, "total": job.total, "percent": percent},
                "elapsed_ms": elapsed,
                "cancel_requested": job.cancel_requested,
                "error": job.error.clone(),
            })
        })
    }

    pub fn result(&self, id: &str) -> RpcResult<Value> {
        self.with_job(id, |job| {
            json!({
                "job_id": job.id,
                "operation": job.operation,
                "state": job.state,
                "result": job.result.clone(),
                "error": job.error.clone(),
            })
        })
    }

    pub fn cancel(&self, id: &str) -> RpcResult<Value> {
        self.with_job(id, |job| {
            if TERMINAL.contains(&job.state.as_str()) {
                return json!({"job_id": job.id, "state": job.state, "cancel_requested": false});
            }
            job.cancel_requested = true;
            job.cancel.store(true, Ordering::SeqCst);
            json!({"job_id": job.id, "state": job.state, "cancel_requested": true})
        })
    }

    pub fn release(&self, id: &str) -> RpcResult<Value> {
        let mut registry = lock(&self.inner);
        let job = registry
            .jobs
            .get(id)
            .ok_or_else(|| RpcError::key(format!("unknown job id: {id}")))?;
        if !TERMINAL.contains(&job.state.as_str()) {
            return Err(RpcError::invalid(format!(
                "cannot release active job: {id}"
            )));
        }
        registry.jobs.remove(id);
        Ok(json!({"job_id": id, "released": true}))
    }

    /// True when every registered job reached a terminal state.
    pub fn all_terminal(&self) -> bool {
        lock(&self.inner)
            .jobs
            .values()
            .all(|j| TERMINAL.contains(&j.state.as_str()))
    }
}

#[cfg(test)]
mod tests {
    #![allow(clippy::unwrap_used)]
    use super::*;

    fn wait(manager: &JobManager) {
        while !manager.all_terminal() {
            std::thread::sleep(std::time::Duration::from_millis(2));
        }
    }

    #[test]
    fn completed_job_reports_full_progress_and_can_be_released() {
        let manager = JobManager::new(4, 16);
        let id = manager
            .start(
                "render.all_states",
                Box::new(|progress| {
                    for i in 1..=3 {
                        progress("render", i, 3);
                    }
                    Ok(json!({"cases": 3}))
                }),
            )
            .unwrap();
        wait(&manager);
        let status = manager.status(&id).unwrap();
        assert_eq!(status["state"], "completed");
        assert_eq!(status["progress"]["percent"], json!(100.0));
        assert_eq!(manager.result(&id).unwrap()["result"]["cases"], 3);
        assert_eq!(manager.release(&id).unwrap()["released"], true);
        assert!(manager.status(&id).is_err());
    }

    #[test]
    fn cancellation_and_failures_are_terminal_with_evidence() {
        let manager = JobManager::new(4, 16);
        let gate = Arc::new(AtomicBool::new(false));
        let g = Arc::clone(&gate);
        let id = manager
            .start(
                "export.all",
                Box::new(move |progress| {
                    while !g.load(Ordering::SeqCst) {
                        std::thread::sleep(std::time::Duration::from_millis(1));
                    }
                    if !progress("export", 1, 2) {
                        return Err(RpcError::invalid("job cancellation requested"));
                    }
                    Ok(json!({}))
                }),
            )
            .unwrap();
        assert_eq!(manager.cancel(&id).unwrap()["cancel_requested"], true);
        assert!(manager.release(&id).is_err());
        gate.store(true, Ordering::SeqCst);
        wait(&manager);
        assert_eq!(manager.status(&id).unwrap()["state"], "cancelled");
        let failed = manager
            .start("x", Box::new(|_| Err(RpcError::key("boom"))))
            .unwrap();
        wait(&manager);
        assert_eq!(
            manager.status(&failed).unwrap()["error"]["code"],
            "KeyError"
        );
    }

    #[test]
    fn terminal_jobs_are_pruned_oldest_first() {
        let manager = JobManager::new(4, 2);
        let mut ids = Vec::new();
        for _ in 0..3 {
            ids.push(manager.start("x", Box::new(|_| Ok(json!({})))).unwrap());
            wait(&manager);
        }
        assert!(manager.status(&ids[0]).is_err());
        assert!(manager.status(&ids[2]).is_ok());
    }
}
