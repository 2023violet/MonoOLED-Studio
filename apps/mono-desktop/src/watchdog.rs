//! Debug-build UI-thread watchdog (spec §5: a single UI-thread block must stay
//! within 16 ms; debug builds report every block that exceeds it).
//!
//! A helper thread posts a probe to the event loop every few milliseconds and
//! the probe measures how long it waited to run. Waiting longer than the
//! budget means the UI thread was busy (a synchronous handler, layout or
//! render) for at least that long. Measuring queue latency rather than timer
//! gaps keeps the result independent of the OS timer resolution.

use std::sync::Arc;
use std::sync::atomic::{AtomicBool, Ordering};
use std::time::{Duration, Instant};

pub const BUDGET: Duration = Duration::from_millis(16);
const PROBE_INTERVAL: Duration = Duration::from_millis(5);

/// Start the watchdog (debug builds only); it stops with the event loop.
pub fn start() {
    if !cfg!(debug_assertions) {
        return;
    }
    let in_flight = Arc::new(AtomicBool::new(false));
    std::thread::spawn(move || {
        loop {
            std::thread::sleep(PROBE_INTERVAL);
            // One probe at a time: a long block is reported once, not per probe.
            if in_flight.swap(true, Ordering::AcqRel) {
                continue;
            }
            let sent = Instant::now();
            let flag = Arc::clone(&in_flight);
            let posted = slint::invoke_from_event_loop(move || {
                let waited = sent.elapsed();
                flag.store(false, Ordering::Release);
                if let Some(text) = report(waited) {
                    eprintln!("{text}");
                }
            });
            if posted.is_err() {
                return;
            }
        }
    });
}

/// The report for a probe that waited `waited`, or None within budget.
pub fn report(waited: Duration) -> Option<String> {
    (waited > BUDGET).then(|| {
        format!(
            "[watchdog] UI thread blocked for at least {:.1} ms (budget {} ms)",
            waited.as_secs_f64() * 1000.0,
            BUDGET.as_millis()
        )
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn reports_only_blocks_over_the_budget() {
        assert_eq!(report(Duration::from_millis(16)), None);
        let text = report(Duration::from_millis(40)).unwrap_or_default();
        assert!(text.contains("40.0 ms"), "{text}");
    }
}
