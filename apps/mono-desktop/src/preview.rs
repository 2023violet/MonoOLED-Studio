//! Preview playback and the runtime event feed.
//!
//! The scene schema has only `states` + `timeline` (`visible_when` for
//! conditionals); it has no key or hardware model. So this is a wall-clock
//! stepper over the timeline, not a device or firmware simulator, and the UI
//! says so.

use std::time::{Duration, Instant};

use mono_core::pyvalue::py_str;
use mono_core::runtime::RuntimeRecord;
use serde_json::{Map, Value};

/// Records the feed keeps; older ones are dropped.
pub const MAX_EVENTS: usize = 200;

#[derive(Debug, Clone, PartialEq)]
pub struct PreviewEvent {
    pub at: i64,
    pub kind: String,
    pub name: String,
    pub before: String,
    pub after: String,
    pub source: String,
}

pub struct Preview {
    pub playing: bool,
    pub last_step: Option<Instant>,
    pub interval: Duration,
    pub events: Vec<PreviewEvent>,
}

impl Default for Preview {
    fn default() -> Self {
        Self {
            playing: false,
            last_step: None,
            interval: Duration::from_millis(500),
            events: Vec::new(),
        }
    }
}

impl Preview {
    pub fn absorb(&mut self, records: Vec<RuntimeRecord>) {
        for record in records {
            let at = record
                .payload
                .get("elapsed")
                .and_then(Value::as_i64)
                .unwrap_or(0);
            let field = |key: &str| record.payload.get(key).map(py_str).unwrap_or_default();
            self.events.push(PreviewEvent {
                at,
                kind: record.event.clone(),
                name: field("name"),
                before: field("before"),
                after: field("after"),
                source: field("source"),
            });
        }
        if self.events.len() > MAX_EVENTS {
            let drop = self.events.len() - MAX_EVENTS;
            self.events.drain(..drop);
        }
    }

    pub fn clear(&mut self) {
        self.events.clear();
    }

    pub fn pause(&mut self) {
        self.playing = false;
        self.last_step = None;
    }

    /// True when a tick should advance the timeline.
    pub fn due(&self, now: Instant) -> bool {
        self.playing
            && self
                .last_step
                .is_none_or(|last| now.duration_since(last) >= self.interval)
    }
}

/// True while the timeline still has work after `elapsed`: a later `at` action
/// or any recurring `every` action.
pub fn timeline_continues(scene: &Map<String, Value>, elapsed: i64) -> bool {
    scene
        .get("timeline")
        .and_then(Value::as_array)
        .into_iter()
        .flatten()
        .filter_map(Value::as_object)
        .any(|action| {
            if action.get("every").is_some_and(|v| !v.is_null()) {
                return true;
            }
            action
                .get("at")
                .and_then(Value::as_i64)
                .is_some_and(|at| at > elapsed)
        })
}

#[cfg(test)]
mod tests {
    #![allow(clippy::unwrap_used)]

    use super::*;
    use serde_json::json;

    #[test]
    fn timeline_continues_while_an_at_or_every_action_remains() {
        let scene = json!({"timeline": [{"at": 1}, {"every": 2}]})
            .as_object()
            .cloned()
            .unwrap();
        assert!(timeline_continues(&scene, 0));
        assert!(timeline_continues(&scene, 100));

        let finite = json!({"timeline": [{"at": 3}]})
            .as_object()
            .cloned()
            .unwrap();
        assert!(timeline_continues(&finite, 2));
        assert!(!timeline_continues(&finite, 3));
    }

    #[test]
    fn absorb_keeps_the_newest_records_and_reads_the_payload() {
        let mut preview = Preview::default();
        preview.absorb(vec![RuntimeRecord {
            event: "STATE".into(),
            payload: json!({"name": "mode", "before": "idle", "after": "run", "elapsed": 4, "source": "timeline:at=4"})
                .as_object()
                .cloned()
                .unwrap(),
        }]);
        assert_eq!(preview.events[0].at, 4);
        assert_eq!(preview.events[0].name, "mode");
        assert_eq!(preview.events[0].after, "run");
        assert_eq!(preview.events[0].source, "timeline:at=4");
    }

    #[test]
    fn due_respects_the_interval_and_pause() {
        let mut preview = Preview::default();
        let now = Instant::now();
        assert!(!preview.due(now));
        preview.playing = true;
        assert!(preview.due(now));
        preview.last_step = Some(now);
        assert!(!preview.due(now));
        assert!(preview.due(now + preview.interval));
        preview.pause();
        assert!(!preview.due(now + preview.interval));
    }
}
