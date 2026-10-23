//! JSON-RPC entry point and the localhost transport (V1 `agent_bridge.py` +
//! `automation_qt.QtAutomationBridge`).
//!
//! Connections are served on background threads, but every request is executed
//! by the owner of the `Service` (the UI thread in the desktop app) through
//! `Bridge::drain`, exactly like V1's queued bridge: a caller may time out only
//! while its request is still queued, never after the edit started. The
//! matrix-wide read/export methods (`Service::offload`) are guarded on the
//! draining thread and then computed on a worker thread from a snapshot, so a
//! synchronous `export.all` does not freeze the desktop UI.

use std::io::{BufRead, BufReader, Read, Write};
use std::net::{TcpListener, TcpStream};
use std::sync::atomic::{AtomicBool, AtomicUsize, Ordering};
use std::sync::mpsc::{Receiver, Sender, channel};
use std::sync::{Arc, Condvar, Mutex};
use std::thread::JoinHandle;
use std::time::Duration;

use mono_core::pyvalue::py_str;
use serde_json::{Map, Value, json};

use crate::error::RpcError;
use crate::service::Service;

/// V1 `dispatch_json_rpc`.
/// A parsed request: method, params, `_expected_revision`, `_transaction`.
type Parsed = (String, Map<String, Value>, Option<Value>, Option<String>);

fn parse(request: &Value) -> Result<Parsed, RpcError> {
    if request.get("jsonrpc") != Some(&json!("2.0")) {
        return Err(RpcError::invalid("jsonrpc must be 2.0"));
    }
    let method = request
        .get("method")
        .map(py_str)
        .ok_or_else(|| RpcError::key("method"))?;
    // V1 `dict(request.get('params') or {})`: every falsy value means no params.
    let mut params: Map<String, Value> = match request.get("params") {
        Some(Value::Object(map)) => map.clone(),
        Some(value) if mono_core::pyvalue::py_truthy(value) => {
            return Err(RpcError::invalid("params must be an object"));
        }
        _ => Map::new(),
    };
    let expected = params.remove("_expected_revision");
    let tx = params
        .remove("_transaction")
        .filter(|v| !v.is_null())
        .map(|v| py_str(&v));
    Ok((method, params, expected, tx))
}

fn respond(id: Value, outcome: Result<Value, RpcError>) -> Value {
    match outcome {
        Ok(result) => json!({"jsonrpc": "2.0", "id": id, "result": result}),
        Err(error) => json!({"jsonrpc": "2.0", "id": id, "error": error.to_json()}),
    }
}

/// The response now, or work that produces it on another thread.
pub enum Dispatch {
    Now(Value),
    Later(Box<dyn FnOnce() -> Value + Send>),
}

/// Like `dispatch_json_rpc`, but offloadable methods come back as `Later`.
pub fn dispatch_or_offload(service: &mut Service, request: &Value) -> Dispatch {
    if let Ok((method, params, expected, tx)) = parse(request) {
        if let Some(prepared) = service.offload(&method, &params, expected.as_ref(), tx.as_deref())
        {
            let id = request.get("id").cloned().unwrap_or(Value::Null);
            return match prepared {
                Ok(work) => Dispatch::Later(Box::new(move || respond(id, work()))),
                Err(error) => Dispatch::Now(respond(id, Err(error))),
            };
        }
    }
    Dispatch::Now(dispatch_json_rpc(service, request))
}

pub fn dispatch_json_rpc(service: &mut Service, request: &Value) -> Value {
    let id = request.get("id").cloned().unwrap_or(Value::Null);
    let outcome = (|| -> Result<Value, RpcError> {
        let (method, params, expected, tx) = parse(request)?;
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
    respond(id, outcome)
}

/// 24 random bytes from the OS CSPRNG as URL-safe base64 (V1
/// `secrets.token_urlsafe(24)`).
pub fn session_token() -> String {
    const TABLE: &[u8; 64] = b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_";
    let mut bytes = [0u8; 24];
    if getrandom::fill(&mut bytes).is_err() {
        // No OS randomness: refuse to hand out a guessable token.
        return String::new();
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

/// Longest accepted request line; longer lines close the connection.
pub const MAX_LINE: usize = 16 * 1024 * 1024;
/// Concurrent client connections; more are refused.
pub const MAX_CONNECTIONS: usize = 32;
/// Idle connections are closed after this long without a request.
pub const IDLE_TIMEOUT: Duration = Duration::from_secs(300);

fn reply(writer: &mut TcpStream, response: &Value) -> bool {
    let mut text = serde_json::to_string(response).unwrap_or_default();
    text.push('\n');
    writer
        .write_all(text.as_bytes())
        .and_then(|()| writer.flush())
        .is_ok()
}

fn serve_connection(stream: TcpStream, token: &str, queue: &Sender<Arc<Call>>, stop: &AtomicBool) {
    let _ = stream.set_read_timeout(Some(IDLE_TIMEOUT));
    let Ok(reader) = stream.try_clone() else {
        return;
    };
    let mut writer = stream;
    let mut reader = BufReader::new(reader);
    loop {
        if stop.load(Ordering::SeqCst) {
            break;
        }
        // Bounded read: a peer cannot make us buffer an unbounded line.
        let mut line = Vec::new();
        match (&mut reader)
            .take(MAX_LINE as u64 + 1)
            .read_until(b'\n', &mut line)
        {
            Ok(0) | Err(_) => break,
            Ok(_) => {}
        }
        if line.len() > MAX_LINE && !line.ends_with(b"\n") {
            let _ = reply(
                &mut writer,
                &json!({"jsonrpc": "2.0", "id": null, "error": {"code": "INVALID_JSON", "message": format!("request line exceeds {MAX_LINE} bytes")}}),
            );
            break;
        }
        let text = String::from_utf8_lossy(&line);
        if text.trim().is_empty() {
            continue;
        }
        let response = match serde_json::from_str::<Value>(&text) {
            Err(error) => {
                json!({"jsonrpc": "2.0", "id": null, "error": {"code": "INVALID_JSON", "message": error.to_string()}})
            }
            // V1 `req.pop('token')` fails for non-objects inside the INVALID_JSON branch.
            Ok(request) if !request.is_object() => {
                json!({"jsonrpc": "2.0", "id": null, "error": {"code": "INVALID_JSON", "message": "request must be a JSON object"}})
            }
            Ok(mut request) => {
                let supplied = request.as_object_mut().and_then(|m| m.remove("token"));
                if token.is_empty() || supplied.as_ref().and_then(Value::as_str) != Some(token) {
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
        if !reply(&mut writer, &response) {
            break;
        }
    }
}

/// Decrements the live-connection count when a client thread ends.
struct ConnectionSlot(Arc<AtomicUsize>);

impl Drop for ConnectionSlot {
    fn drop(&mut self) {
        self.0.fetch_sub(1, Ordering::SeqCst);
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
        let live = Arc::new(AtomicUsize::new(0));
        let thread = std::thread::Builder::new()
            .name("MonoOLED-AgentBridge".into())
            .spawn(move || {
                while !thread_stop.load(Ordering::SeqCst) {
                    match listener.accept() {
                        Ok((mut stream, _)) => {
                            let _ = stream.set_nonblocking(false);
                            if live.fetch_add(1, Ordering::SeqCst) >= MAX_CONNECTIONS {
                                live.fetch_sub(1, Ordering::SeqCst);
                                let _ = reply(
                                    &mut stream,
                                    &json!({"jsonrpc": "2.0", "id": null, "error": {"code": "BUSY", "message": "too many agent connections"}}),
                                );
                                continue;
                            }
                            let slot = ConnectionSlot(Arc::clone(&live));
                            let (t, s, st) = (
                                thread_token.clone(),
                                sender.clone(),
                                Arc::clone(&thread_stop),
                            );
                            let _ = std::thread::Builder::new()
                                .name("MonoOLED-AgentClient".into())
                                .spawn(move || {
                                    let _slot = slot;
                                    serve_connection(stream, &t, &s, &st);
                                });
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
            match dispatch_or_offload(service, &call.request) {
                Dispatch::Now(response) => {
                    call.complete(response.clone());
                    responses.push(response);
                }
                Dispatch::Later(work) => {
                    // Guarded already; the snapshot work answers the caller
                    // from a worker thread while the UI keeps draining.
                    let worker = Arc::clone(&call);
                    let spawned = std::thread::Builder::new()
                        .name("automation-offload".into())
                        .spawn(move || worker.complete(work()));
                    if spawned.is_err() {
                        let id = call.request.get("id").cloned().unwrap_or(Value::Null);
                        call.complete(respond(
                            id,
                            Err(RpcError::invalid("could not start a worker thread")),
                        ));
                    }
                }
            }
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
    #![allow(clippy::unwrap_used, clippy::panic)]
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
    fn envelope_matches_v1_for_non_objects_and_falsy_params() {
        let mut bridge = Bridge::start(0).unwrap();
        let mut svc = service();
        let ok = json!({"jsonrpc": "2.0", "id": 4, "method": "project.get", "params": [], "token": bridge.token});
        let responses = roundtrip(
            &bridge,
            &mut svc,
            &format!(
                "[]
5
{ok}
"
            ),
        );
        assert_eq!(responses[0]["error"]["code"], "INVALID_JSON");
        assert_eq!(responses[1]["error"]["code"], "INVALID_JSON");
        assert_eq!(responses[2]["result"]["ok"], true);
        bridge.stop();
    }

    #[test]
    fn oversized_lines_and_extra_connections_are_refused() {
        let mut bridge = Bridge::start(0).unwrap();
        let mut svc = service();
        let huge = "x".repeat(MAX_LINE + 10);
        let responses = roundtrip(&bridge, &mut svc, &huge);
        assert_eq!(responses.len(), 1);
        assert_eq!(responses[0]["error"]["code"], "INVALID_JSON");
        let held: Vec<TcpStream> = (0..MAX_CONNECTIONS)
            .map(|_| TcpStream::connect(("127.0.0.1", bridge.port)).unwrap())
            .collect();
        std::thread::sleep(Duration::from_millis(200));
        let mut extra = TcpStream::connect(("127.0.0.1", bridge.port)).unwrap();
        extra
            .set_read_timeout(Some(Duration::from_secs(5)))
            .unwrap();
        let mut line = String::new();
        BufReader::new(&mut extra).read_line(&mut line).unwrap();
        assert_eq!(
            serde_json::from_str::<Value>(&line).unwrap()["error"]["code"],
            "BUSY"
        );
        drop(held);
        bridge.stop();
    }

    #[test]
    fn matrix_calls_are_answered_off_the_draining_thread_with_the_same_result() {
        let mut bridge = Bridge::start(0).unwrap();
        let mut svc = service();
        let request = json!({"jsonrpc": "2.0", "id": 7, "method": "validate.all_states", "params": {"integer_policy": "boundaries"}});
        // Offloaded: drain returns without a response for it.
        assert!(matches!(
            dispatch_or_offload(&mut svc, &request),
            Dispatch::Later(_)
        ));
        // Identical apart from the measured run time.
        let timeless = |mut v: Value| {
            v["result"]["elapsed_ms"] = Value::Null;
            v
        };
        let expected = timeless(dispatch_json_rpc(&mut svc, &request));
        let mut line = request.clone();
        line["token"] = json!(bridge.token);
        let responses = roundtrip(&bridge, &mut svc, &format!("{line}\n"));
        assert_eq!(
            responses.into_iter().map(timeless).collect::<Vec<_>>(),
            vec![expected]
        );
        // Guards still apply up front: observe may not export.
        let export = json!({"jsonrpc": "2.0", "id": 8, "method": "export.all", "params": {}});
        match dispatch_or_offload(&mut svc, &export) {
            Dispatch::Now(response) => assert_eq!(response["error"]["code"], "PERMISSION_DENIED"),
            Dispatch::Later(_) => panic!("observe must not start an export"),
        }
        bridge.stop();
    }

    #[test]
    fn session_tokens_are_url_safe_and_distinct() {
        let (a, b) = (session_token(), session_token());
        assert!(!a.is_empty());
        assert_eq!(a.len(), 32);
        assert_ne!(a, b);
        assert!(
            a.chars()
                .all(|c| c.is_ascii_alphanumeric() || c == '-' || c == '_')
        );
    }
}
