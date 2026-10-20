//! JSON-RPC entry point and the localhost transport (V1 `agent_bridge.py` +
//! `automation_qt.QtAutomationBridge`).
//!
//! Connections are served on background threads, but every request is executed
//! by the owner of the `Service` (the UI thread in the desktop app) through
//! `Bridge::drain`, exactly like V1's queued bridge: a caller may time out only
//! while its request is still queued, never after the edit started.

use std::collections::hash_map::RandomState;
use std::hash::{BuildHasher, Hasher};
use std::io::{BufRead, BufReader, Write};
use std::net::{TcpListener, TcpStream};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::mpsc::{Receiver, Sender, channel};
use std::sync::{Arc, Condvar, Mutex};
use std::thread::JoinHandle;
use std::time::Duration;

use mono_core::pyvalue::py_str;
use serde_json::{Map, Value, json};

use crate::error::RpcError;
use crate::service::Service;

/// V1 `dispatch_json_rpc`.
pub fn dispatch_json_rpc(service: &mut Service, request: &Value) -> Value {
    let id = request.get("id").cloned().unwrap_or(Value::Null);
    let outcome = (|| -> Result<Value, RpcError> {
        if request.get("jsonrpc") != Some(&json!("2.0")) {
            return Err(RpcError::invalid("jsonrpc must be 2.0"));
        }
        let method = request
            .get("method")
            .map(py_str)
            .ok_or_else(|| RpcError::key("method"))?;
        let mut params: Map<String, Value> = match request.get("params") {
            None | Some(Value::Null) => Map::new(),
            Some(Value::Object(map)) => map.clone(),
            Some(_) => return Err(RpcError::invalid("params must be an object")),
        };
        let expected = params.remove("_expected_revision");
        let tx = params
            .remove("_transaction")
            .filter(|v| !v.is_null())
            .map(|v| py_str(&v));
        match method.as_str() {
            "history.begin_transaction" => {
                let tid = service.begin_transaction(expected.as_ref())?;
                Ok(json!({"ok": true, "revision": service.revision, "transaction": tid}))
            }
            "history.commit" => {
                let tid = params
                    .get("transaction")
                    .map(py_str)
                    .ok_or_else(|| RpcError::key("transaction"))?;
                service.commit_transaction(&tid)
            }
            "history.rollback" => {
                let tid = params
                    .get("transaction")
                    .map(py_str)
                    .ok_or_else(|| RpcError::key("transaction"))?;
                service.rollback_transaction(&tid)
            }
            _ => service.call(&method, &params, expected.as_ref(), tx.as_deref()),
        }
    })();
    match outcome {
        Ok(result) => json!({"jsonrpc": "2.0", "id": id, "result": result}),
        Err(error) => json!({"jsonrpc": "2.0", "id": id, "error": error.to_json()}),
    }
}

/// 24 random bytes as URL-safe base64 (V1 `secrets.token_urlsafe(24)`).
/// `RandomState` keys are seeded from the OS random source on every platform.
pub fn session_token() -> String {
    const TABLE: &[u8; 64] = b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_";
    let mut bytes = Vec::with_capacity(24);
    for i in 0u64..3 {
        let mut hasher = RandomState::new().build_hasher();
        hasher.write_u64(i);
        hasher.write_u128(
            std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap_or_default()
                .as_nanos(),
        );
        bytes.extend_from_slice(&hasher.finish().to_le_bytes());
    }
    bytes
        .chunks(3)
        .flat_map(|c| {
            let n = (u32::from(c[0]) << 16) | (u32::from(c[1]) << 8) | u32::from(c[2]);
            (0..4).map(move |i| char::from(TABLE[((n >> (18 - 6 * i)) & 63) as usize]))
        })
        .collect()
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum CallState {
    Queued,
    Dispatching,
    Done,
    Expired,
}

struct Call {
    request: Value,
    state: Mutex<(CallState, Option<Value>)>,
    done: Condvar,
}

impl Call {
    fn claim(&self) -> bool {
        let mut guard = self
            .state
            .lock()
            .unwrap_or_else(std::sync::PoisonError::into_inner);
        if guard.0 != CallState::Queued {
            return false;
        }
        guard.0 = CallState::Dispatching;
        true
    }

    fn complete(&self, response: Value) {
        let mut guard = self
            .state
            .lock()
            .unwrap_or_else(std::sync::PoisonError::into_inner);
        if guard.0 == CallState::Expired {
            return;
        }
        *guard = (CallState::Done, Some(response));
        self.done.notify_all();
    }

    fn cancel_if_queued(&self, response: Value) {
        let mut guard = self
            .state
            .lock()
            .unwrap_or_else(std::sync::PoisonError::into_inner);
        if guard.0 == CallState::Queued {
            *guard = (CallState::Done, Some(response));
            self.done.notify_all();
        }
    }

    /// Wait up to `timeout` while queued; once claimed, wait for the real answer.
    fn wait(&self, timeout: Duration) -> Value {
        let id = self.request.get("id").cloned().unwrap_or(Value::Null);
        let guard = self
            .state
            .lock()
            .unwrap_or_else(std::sync::PoisonError::into_inner);
        let (mut guard, _) = self
            .done
            .wait_timeout_while(guard, timeout, |s| s.0 != CallState::Done)
            .unwrap_or_else(std::sync::PoisonError::into_inner);
        if guard.0 == CallState::Queued {
            guard.0 = CallState::Expired;
            return json!({"jsonrpc": "2.0", "id": id, "error": {"code": "TIMEOUT", "message": "UI thread did not process request"}});
        }
        let mut guard = self
            .done
            .wait_while(guard, |s| s.0 != CallState::Done)
            .unwrap_or_else(std::sync::PoisonError::into_inner);
        guard.1.take().unwrap_or(Value::Null)
    }
}

pub struct Bridge {
    pub port: u16,
    pub token: String,
    queue: Receiver<Arc<Call>>,
    stop: Arc<AtomicBool>,
    thread: Option<JoinHandle<()>>,
}

fn serve_connection(stream: TcpStream, token: &str, queue: &Sender<Arc<Call>>, stop: &AtomicBool) {
    let Ok(reader) = stream.try_clone() else {
        return;
    };
    let mut writer = stream;
    for line in BufReader::new(reader).lines() {
        if stop.load(Ordering::SeqCst) {
            break;
        }
        let Ok(line) = line else { break };
        if line.trim().is_empty() {
            continue;
        }
        let response = match serde_json::from_str::<Value>(&line) {
            Err(error) => {
                json!({"jsonrpc": "2.0", "id": null, "error": {"code": "INVALID_JSON", "message": error.to_string()}})
            }
            Ok(mut request) => {
                let supplied = request.as_object_mut().and_then(|m| m.remove("token"));
                if supplied.as_ref().and_then(Value::as_str) != Some(token) {
                    json!({"jsonrpc": "2.0", "id": request.get("id").cloned().unwrap_or(Value::Null), "error": {"code": "UNAUTHORIZED", "message": "invalid session token"}})
                } else {
                    let call = Arc::new(Call {
                        request,
                        state: Mutex::new((CallState::Queued, None)),
                        done: Condvar::new(),
                    });
                    if queue.send(Arc::clone(&call)).is_err() {
                        break;
                    }
                    call.wait(Duration::from_secs(10))
                }
            }
        };
        let mut text = serde_json::to_string(&response).unwrap_or_default();
        text.push('\n');
        if writer
            .write_all(text.as_bytes())
            .and_then(|()| writer.flush())
            .is_err()
        {
            break;
        }
    }
}

impl Bridge {
    /// Listen on `127.0.0.1:port` (0 = any free port).
    pub fn start(port: u16) -> std::io::Result<Self> {
        let listener = TcpListener::bind(("127.0.0.1", port))?;
        listener.set_nonblocking(true)?;
        let port = listener.local_addr()?.port();
        let token = session_token();
        let (sender, queue) = channel();
        let stop = Arc::new(AtomicBool::new(false));
        let (thread_token, thread_stop) = (token.clone(), Arc::clone(&stop));
        let thread = std::thread::Builder::new()
            .name("MonoOLED-AgentBridge".into())
            .spawn(move || {
                while !thread_stop.load(Ordering::SeqCst) {
                    match listener.accept() {
                        Ok((stream, _)) => {
                            let _ = stream.set_nonblocking(false);
                            let (t, s, st) = (
                                thread_token.clone(),
                                sender.clone(),
                                Arc::clone(&thread_stop),
                            );
                            let _ = std::thread::Builder::new()
                                .name("MonoOLED-AgentClient".into())
                                .spawn(move || serve_connection(stream, &t, &s, &st));
                        }
                        Err(_) => std::thread::sleep(Duration::from_millis(25)),
                    }
                }
            })?;
        Ok(Self {
            port,
            token,
            queue,
            stop,
            thread: Some(thread),
        })
    }

    pub fn endpoint(&self, permission: &str) -> Value {
        json!({"host": "127.0.0.1", "port": self.port, "token": self.token, "permission": permission, "automation_api": crate::service::API_VERSION})
    }

    /// Execute up to 32 queued requests; returns the responses (for UI refresh).
    pub fn drain(&self, service: &mut Service) -> Vec<Value> {
        let mut responses = Vec::new();
        for _ in 0..32 {
            let Ok(call) = self.queue.try_recv() else {
                break;
            };
            if !call.claim() {
                continue;
            }
            let response = dispatch_json_rpc(service, &call.request);
            call.complete(response.clone());
            responses.push(response);
        }
        responses
    }

    /// Stop listening and resolve queued callers with `BRIDGE_STOPPED`.
    pub fn stop(&mut self) {
        self.stop.store(true, Ordering::SeqCst);
        if let Some(thread) = self.thread.take() {
            let _ = thread.join();
        }
        while let Ok(call) = self.queue.try_recv() {
            let id = call.request.get("id").cloned().unwrap_or(Value::Null);
            call.cancel_if_queued(json!({"jsonrpc": "2.0", "id": id, "error": {"code": "BRIDGE_STOPPED", "message": "Agent bridge stopped"}}));
        }
    }
}

impl Drop for Bridge {
    fn drop(&mut self) {
        self.stop();
    }
}

#[cfg(test)]
mod tests {
    #![allow(clippy::unwrap_used)]
    use super::*;
    use std::io::Read;

    fn service() -> Service {
        let root = std::path::PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .join("../../test_assets/projects/curing_lite/project.oled.json");
        Service::for_project(&root, Some("main"), "observe").unwrap()
    }

    fn roundtrip(bridge: &Bridge, service: &mut Service, lines: &str) -> Vec<Value> {
        let mut stream = TcpStream::connect(("127.0.0.1", bridge.port)).unwrap();
        stream.write_all(lines.as_bytes()).unwrap();
        stream.shutdown(std::net::Shutdown::Write).unwrap();
        let reader = std::thread::spawn(move || {
            let mut text = String::new();
            stream.read_to_string(&mut text).unwrap();
            text
        });
        let deadline = std::time::Instant::now() + Duration::from_secs(10);
        while !reader.is_finished() && std::time::Instant::now() < deadline {
            bridge.drain(service);
            std::thread::sleep(Duration::from_millis(5));
        }
        let text = reader.join().unwrap();
        text.lines()
            .map(|l| serde_json::from_str(l).unwrap())
            .collect()
    }

    #[test]
    fn token_is_required_and_requests_run_on_the_draining_thread() {
        let mut bridge = Bridge::start(0).unwrap();
        let mut svc = service();
        let good = format!(
            "{}\n",
            json!({"jsonrpc": "2.0", "id": 1, "method": "project.get", "token": bridge.token})
        );
        let bad = format!(
            "{}\n",
            json!({"jsonrpc": "2.0", "id": 2, "method": "project.get", "token": "nope"})
        );
        let responses = roundtrip(&bridge, &mut svc, &format!("{good}{bad}not json\n"));
        assert_eq!(responses.len(), 3);
        assert_eq!(responses[0]["result"]["project_name"], "Curing-Lite OLED");
        assert_eq!(responses[1]["error"]["code"], "UNAUTHORIZED");
        assert_eq!(responses[2]["error"]["code"], "INVALID_JSON");
        bridge.stop();
    }

    #[test]
    fn session_tokens_are_url_safe_and_distinct() {
        let (a, b) = (session_token(), session_token());
        assert_eq!(a.len(), 32);
        assert_ne!(a, b);
        assert!(
            a.chars()
                .all(|c| c.is_ascii_alphanumeric() || c == '-' || c == '_')
        );
    }
}
