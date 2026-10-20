//! MonoOLED Studio Automation API 1.3.0 (ADR-005 G4e): the V1 JSON-RPC
//! contract re-implemented on the Rust core, replayed against the frozen V1
//! automation corpus (`fixtures/golden/automation.json`).

pub mod bridge;
pub mod dispatch;
pub mod error;
pub mod jobs;
pub mod ops;
pub mod service;

pub use bridge::{Bridge, dispatch_json_rpc};
pub use error::{RpcError, RpcResult};
pub use service::{API_VERSION, Service};
