//! Deterministic UI-state timeline runner (V1 `runtime.SceneRuntime`); not an MCU simulator.

use serde_json::{Map, Value, json};

use crate::error::{CoreError, CoreResult};
use crate::pyvalue::{is_py_int, py_eq, py_int, py_str};
use crate::state::{State, clamp_state, eval_do, init_state, when_match};

/// Receives `(event, payload)` records; implemented by the session log.
pub trait RuntimeLog {
    fn log(&mut self, event: &str, payload: Map<String, Value>);
}

/// One captured record, for surfaces that show what the timeline did.
#[derive(Debug, Clone, PartialEq)]
pub struct RuntimeRecord {
    pub event: String,
    pub payload: Map<String, Value>,
}

/// Collects records in memory (`SessionLogger` writes JSONL to disk instead).
#[derive(Debug, Default)]
pub struct VecRuntimeLog {
    records: Vec<RuntimeRecord>,
}

impl VecRuntimeLog {
    pub fn records(&self) -> &[RuntimeRecord] {
        &self.records
    }

    pub fn take(&mut self) -> Vec<RuntimeRecord> {
        std::mem::take(&mut self.records)
    }
}

impl RuntimeLog for VecRuntimeLog {
    fn log(&mut self, event: &str, payload: Map<String, Value>) {
        self.records.push(RuntimeRecord {
            event: event.to_string(),
            payload,
        });
    }
}

pub struct SceneRuntime<'a> {
    scene: &'a Map<String, Value>,
    pub state: State,
    pub elapsed: i64,
    logger: Option<&'a mut dyn RuntimeLog>,
}

fn timeline(scene: &Map<String, Value>) -> Vec<Map<String, Value>> {
    scene
        .get("timeline")
        .and_then(Value::as_array)
        .into_iter()
        .flatten()
        .filter_map(|a| a.as_object().cloned())
        .collect()
}

fn sorted(state: &State) -> Value {
    let mut items: Vec<(&String, &Value)> = state.iter().collect();
    items.sort_by(|a, b| a.0.cmp(b.0));
    Value::Object(
        items
            .into_iter()
            .map(|(k, v)| (k.clone(), v.clone()))
            .collect(),
    )
}

impl<'a> SceneRuntime<'a> {
    pub fn new(
        scene: &'a Map<String, Value>,
        logger: Option<&'a mut dyn RuntimeLog>,
    ) -> CoreResult<Self> {
        let mut runtime = Self {
            scene,
            state: State::new(),
            elapsed: 0,
            logger,
        };
        runtime.reset()?;
        Ok(runtime)
    }

    /// Rebuild a runtime at a saved state without replaying `reset()`.
    ///
    /// `new()` always logs a RESET; an editor resuming from its current state
    /// must not record one that never happened.
    pub fn attach(
        scene: &'a Map<String, Value>,
        logger: Option<&'a mut dyn RuntimeLog>,
        state: State,
        elapsed: i64,
    ) -> CoreResult<Self> {
        let mut runtime = Self {
            scene,
            state,
            elapsed,
            logger,
        };
        clamp_state(scene, &mut runtime.state)?;
        Ok(runtime)
    }

    fn log_diff(&mut self, before: &State, source: &str, elapsed: i64) {
        let Some(logger) = self.logger.as_deref_mut() else {
            return;
        };
        let mut names: Vec<&String> = self.state.keys().collect();
        names.sort();
        for name in names {
            let old = before.get(name).cloned().unwrap_or(Value::Null);
            let new = self.state.get(name).cloned().unwrap_or(Value::Null);
            if !py_eq(&old, &new) {
                let mut payload = Map::new();
                payload.insert("name".into(), json!(name));
                payload.insert("before".into(), old);
                payload.insert("after".into(), new);
                payload.insert("source".into(), json!(source));
                payload.insert("elapsed".into(), json!(elapsed));
                logger.log("STATE", payload);
            }
        }
    }

    fn states(&self) -> Map<String, Value> {
        self.scene
            .get("states")
            .and_then(Value::as_object)
            .cloned()
            .unwrap_or_default()
    }

    fn apply_set(
        &mut self,
        values: &Map<String, Value>,
        source: &str,
        elapsed: i64,
    ) -> CoreResult<()> {
        let before = self.state.clone();
        let states = self.states();
        for (name, value) in values {
            if !states.contains_key(name) {
                return Err(CoreError::new(
                    "E-CORE-KEY",
                    format!("'timeline referenced unknown state: {name}'"),
                ));
            }
            self.state.insert(name.clone(), value.clone());
        }
        clamp_state(self.scene, &mut self.state)?;
        self.log_diff(&before, source, elapsed);
        Ok(())
    }

    fn apply_do(&mut self, expr: &str, source: &str, elapsed: i64) -> CoreResult<()> {
        let before = self.state.clone();
        eval_do(expr, &mut self.state)?;
        clamp_state(self.scene, &mut self.state)?;
        self.log_diff(&before, source, elapsed);
        Ok(())
    }

    pub fn reset(&mut self) -> CoreResult<State> {
        self.state = init_state(self.scene);
        self.elapsed = 0;
        for action in timeline(self.scene) {
            if action.get("at").is_some_and(|v| py_eq(v, &json!(0))) {
                if let Some(Value::Object(set)) = action.get("set") {
                    self.apply_set(set, "timeline:at=0", 0)?;
                }
            }
        }
        clamp_state(self.scene, &mut self.state)?;
        let state = sorted(&self.state);
        if let Some(logger) = self.logger.as_deref_mut() {
            let mut payload = Map::new();
            payload.insert("elapsed".into(), json!(0));
            payload.insert("state".into(), state);
            logger.log("RESET", payload);
        }
        Ok(self.state.clone())
    }

    pub fn set_state(&mut self, name: &str, value: Value) -> CoreResult<()> {
        if !self.states().contains_key(name) {
            return Err(CoreError::new(
                "E-CORE-KEY",
                format!("'unknown state: {name}'"),
            ));
        }
        let before = self.state.clone();
        self.state.insert(name.into(), value);
        clamp_state(self.scene, &mut self.state)?;
        let elapsed = self.elapsed;
        self.log_diff(&before, "manual", elapsed);
        Ok(())
    }

    pub fn step(&mut self, amount: &Value) -> CoreResult<State> {
        if !is_py_int(amount) || amount.as_i64().unwrap_or(-1) < 0 {
            return Err(CoreError::invalid(
                "step amount must be a non-negative integer",
            ));
        }
        for _ in 0..amount.as_i64().unwrap_or(0) {
            let now = self.elapsed + 1;
            let actions = timeline(self.scene);
            // Recurring actions observe the state of the preceding step (V1 contract).
            for action in &actions {
                let Some(every) = action
                    .get("every")
                    .filter(|v| !v.is_null())
                    .and_then(py_int)
                else {
                    continue;
                };
                if every <= 0 || now % every != 0 || !when_match(action.get("when"), &self.state)? {
                    continue;
                }
                let source = format!("timeline:every={every}");
                if let Some(expr) = action.get("do") {
                    self.apply_do(&py_str(expr), &source, now)?;
                } else if let Some(Value::Object(set)) = action.get("set") {
                    self.apply_set(set, &source, now)?;
                }
            }
            for action in &actions {
                if !action.get("at").is_some_and(|v| py_eq(v, &json!(now))) {
                    continue;
                }
                let source = format!("timeline:at={now}");
                if let Some(Value::Object(set)) = action.get("set") {
                    self.apply_set(set, &source, now)?;
                } else if let Some(expr) = action.get("do") {
                    self.apply_do(&py_str(expr), &source, now)?;
                }
            }
            self.elapsed = now;
        }
        Ok(self.state.clone())
    }
}

#[cfg(test)]
mod tests {
    #![allow(clippy::unwrap_used)]

    use super::*;

    fn scene() -> Map<String, Value> {
        json!({
            "canvas": {"w": 8, "h": 8, "preview_scale": 1},
            "storage": {"layout": "vlsb", "bytes_per_frame": 8, "polarity": "lit"},
            "states": {"mode": {"type": "enum", "values": ["idle", "run"], "init": "idle"}},
            "elements": [],
            "timeline": [{"at": 1, "set": {"mode": "run"}}]
        })
        .as_object()
        .cloned()
        .unwrap()
    }

    #[test]
    fn recording_log_captures_reset_and_state_changes() {
        let scene = scene();
        let mut log = VecRuntimeLog::default();
        let mut runtime = SceneRuntime::new(&scene, Some(&mut log)).unwrap();
        runtime.step(&json!(1)).unwrap();
        let events: Vec<&str> = log.records().iter().map(|r| r.event.as_str()).collect();
        assert_eq!(events, ["RESET", "STATE"]);
        assert_eq!(log.records()[1].payload["name"], "mode");
        assert_eq!(log.records()[1].payload["after"], "run");
    }

    #[test]
    fn attach_does_not_emit_a_spurious_reset() {
        let scene = scene();
        let start = SceneRuntime::new(&scene, None).unwrap();
        let mut log = VecRuntimeLog::default();
        let mut runtime =
            SceneRuntime::attach(&scene, Some(&mut log), start.state.clone(), start.elapsed)
                .unwrap();
        runtime.step(&json!(1)).unwrap();
        let events: Vec<&str> = log.records().iter().map(|r| r.event.as_str()).collect();
        assert_eq!(events, ["STATE"]);
    }
}
