//! Minimal long-task worker for the validation slice.
//!
//! std::thread only (no async runtime): one churn loop that encodes a
//! `PixelDocument` to VLSB and hashes the bytes, checks a stop signal every
//! iteration, and reports progress through a bounded channel whose full slots
//! drop progress instead of blocking the worker.

use mono_core::pixel::PixelDocument;
use sha2::{Digest, Sha256};
use std::sync::mpsc::{Receiver, Sender, channel, sync_channel};
use std::thread::JoinHandle;
use std::time::{Duration, Instant};

/// Progress messages travel through a `sync_channel(1)`; when the reader is
/// not keeping up, `try_send` drops the update so the worker never blocks.
#[derive(Debug, Clone, Copy)]
pub struct ProgressMsg {
    #[allow(dead_code)]
    pub iterations: u64,
    #[allow(dead_code)]
    pub elapsed: Duration,
}

#[allow(dead_code)]
pub struct WorkerOutcome {
    pub iterations: u64,
    pub final_encode_sha256: String,
    pub stopped_by_request: bool,
    pub elapsed: Duration,
}

pub struct WorkerConfig {
    pub document: PixelDocument,
    pub target_runtime: Duration,
}

pub struct WorkerHandle {
    stop: Sender<()>,
    handle: Option<JoinHandle<WorkerOutcome>>,
}

impl WorkerHandle {
    /// Spawns a finite churn worker that runs at least `target_runtime`
    /// (or until stopped) and then finishes on its own.
    pub fn spawn_finite(config: WorkerConfig) -> (Self, Receiver<ProgressMsg>) {
        let (stop, stop_rx) = channel::<()>();
        let (progress_tx, progress_rx) = sync_channel::<ProgressMsg>(1);
        let handle = std::thread::spawn(move || {
            let started = Instant::now();
            let mut iterations = 0u64;
            let mut stopped_by_request = false;
            let mut digest: [u8; 32] = [0; 32];
            loop {
                let bytes = config.document.to_vlsb().expect("valid churn document");
                digest.copy_from_slice(&Sha256::digest(&bytes));
                iterations += 1;
                if stop_rx.try_recv() == Ok(()) {
                    stopped_by_request = true;
                    break;
                }
                if started.elapsed() >= config.target_runtime {
                    break;
                }
                if iterations.is_multiple_of(64) {
                    // Bounded channel: drop progress when the reader lags.
                    let _ = progress_tx.try_send(ProgressMsg {
                        iterations,
                        elapsed: started.elapsed(),
                    });
                }
            }
            WorkerOutcome {
                iterations,
                final_encode_sha256: digest.iter().map(|byte| format!("{byte:02x}")).collect(),
                stopped_by_request,
                elapsed: started.elapsed(),
            }
        });
        (
            Self {
                stop,
                handle: Some(handle),
            },
            progress_rx,
        )
    }

    /// Joins a worker that is expected to finish on its own.
    pub fn join(&mut self, timeout: Duration) -> Option<WorkerOutcome> {
        let handle = self.handle.take()?;
        let started = Instant::now();
        loop {
            if handle.is_finished() {
                return handle.join().ok();
            }
            if started.elapsed() >= timeout {
                self.handle = Some(handle);
                return None;
            }
            std::thread::sleep(Duration::from_millis(5));
        }
    }

    /// Sends the stop signal and joins within `timeout`.
    /// Returns `None` when the worker did not terminate in time.
    pub fn request_stop_and_join(mut self, timeout: Duration) -> Option<WorkerOutcome> {
        let _ = self.stop.send(());
        self.join(timeout)
    }
}
