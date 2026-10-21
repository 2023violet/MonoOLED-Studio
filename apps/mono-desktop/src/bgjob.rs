//! Background delivery jobs: export, Code AI handoff, batch validation and the
//! thumbnail wall run on a worker thread over a snapshot of the scene, so the
//! UI thread never blocks on them (spec §5: no single UI-thread block over
//! 16 ms). The 60 ms job timer polls progress and applies the result.

use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex, PoisonError};

use mono_core::CoreError;

/// What a finished job reports back to the UI thread.
#[derive(Debug, Default)]
pub struct Outcome {
    pub status: String,
    /// Lines for the session log (e.g. batch validation findings).
    pub log: Vec<String>,
    /// Findings or files changed: refresh the panels.
    pub refresh: bool,
}

#[derive(Default)]
struct Shared {
    stage: String,
    done: usize,
    total: usize,
    result: Option<Result<Outcome, CoreError>>,
}

/// Snapshot of a running job for the status bar.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Progress {
    pub stage: String,
    pub done: usize,
    pub total: usize,
}

pub enum Poll {
    Running(Progress),
    Finished(Result<Outcome, CoreError>),
}

pub struct BackgroundJob {
    pub label: String,
    shared: Arc<Mutex<Shared>>,
    cancel: Arc<AtomicBool>,
}

impl BackgroundJob {
    /// Run `work` on a worker thread. It receives the `mono_project` progress
    /// callback (`(stage, done, total) -> keep going`).
    pub fn spawn<F>(label: String, work: F) -> Self
    where
        F: FnOnce(&mut dyn FnMut(&str, usize, usize) -> bool) -> Result<Outcome, CoreError>
            + Send
            + 'static,
    {
        let shared = Arc::new(Mutex::new(Shared::default()));
        let cancel = Arc::new(AtomicBool::new(false));
        let (state, stop) = (Arc::clone(&shared), Arc::clone(&cancel));
        std::thread::spawn(move || {
            let report = Arc::clone(&state);
            let mut progress = move |stage: &str, done: usize, total: usize| {
                let mut s = report.lock().unwrap_or_else(PoisonError::into_inner);
                s.stage = stage.to_string();
                s.done = done;
                s.total = total;
                !stop.load(Ordering::Relaxed)
            };
            let result = work(&mut progress);
            state.lock().unwrap_or_else(PoisonError::into_inner).result = Some(result);
        });
        Self {
            label,
            shared,
            cancel,
        }
    }

    pub fn cancel(&self) {
        self.cancel.store(true, Ordering::Relaxed);
    }

    /// Progress, or the result once (the job is finished after `Finished`).
    pub fn poll(&self) -> Poll {
        let mut s = self.shared.lock().unwrap_or_else(PoisonError::into_inner);
        match s.result.take() {
            Some(result) => Poll::Finished(result),
            None => Poll::Running(Progress {
                stage: s.stage.clone(),
                done: s.done,
                total: s.total,
            }),
        }
    }
}

#[cfg(test)]
mod tests {
    #![allow(clippy::unwrap_used, clippy::panic)]
    use super::*;
    use std::time::{Duration, Instant};

    fn wait(job: &BackgroundJob) -> Result<Outcome, CoreError> {
        let deadline = Instant::now() + Duration::from_secs(10);
        loop {
            if let Poll::Finished(result) = job.poll() {
                return result;
            }
            assert!(Instant::now() < deadline, "job did not finish");
            std::thread::sleep(Duration::from_millis(5));
        }
    }

    #[test]
    fn reports_progress_then_the_result_once() {
        let (go, gate) = std::sync::mpsc::channel::<()>();
        let job = BackgroundJob::spawn("export".into(), move |progress| {
            progress("export.render", 1, 2);
            gate.recv().unwrap();
            Ok(Outcome {
                status: "done".into(),
                ..Outcome::default()
            })
        });
        let deadline = Instant::now() + Duration::from_secs(10);
        loop {
            match job.poll() {
                Poll::Running(p) if p.done == 1 => {
                    assert_eq!((p.stage.as_str(), p.total), ("export.render", 2));
                    break;
                }
                Poll::Running(_) => {}
                Poll::Finished(_) => panic!("finished before the gate opened"),
            }
            assert!(Instant::now() < deadline);
            std::thread::sleep(Duration::from_millis(5));
        }
        go.send(()).unwrap();
        assert_eq!(wait(&job).unwrap().status, "done");
        assert!(matches!(job.poll(), Poll::Running(_)));
    }

    #[test]
    fn cancel_makes_progress_return_false() {
        let (go, gate) = std::sync::mpsc::channel::<()>();
        let job = BackgroundJob::spawn("validate".into(), move |progress| {
            gate.recv().unwrap();
            if progress("validation", 1, 10) {
                Ok(Outcome::default())
            } else {
                Err(CoreError::invalid("cancelled"))
            }
        });
        job.cancel();
        go.send(()).unwrap();
        assert!(wait(&job).is_err());
    }
}
