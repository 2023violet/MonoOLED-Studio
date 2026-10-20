//! JSON-RPC error classes (V1 `agent_bridge.dispatch_json_rpc` exception map).

use mono_core::CoreError;
use mono_core::pyvalue::py_repr;
use serde_json::{Value, json};

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum RpcError {
    PermissionDenied(String),
    StaleRevision(String),
    Transaction(String),
    Unsaved(String),
    /// Python `KeyError`: the message is already `repr()`-quoted.
    NotFound(String),
    Invalid(String),
}

impl RpcError {
    /// `KeyError(text)` → `str(exc)` is `repr(text)`.
    pub fn key(text: impl Into<String>) -> Self {
        Self::NotFound(py_repr(&Value::String(text.into())))
    }

    pub fn invalid(text: impl Into<String>) -> Self {
        Self::Invalid(text.into())
    }

    pub fn code(&self) -> &'static str {
        match self {
            Self::PermissionDenied(_) => "PERMISSION_DENIED",
            Self::StaleRevision(_) => "STALE_REVISION",
            Self::Transaction(_) => "TRANSACTION_ERROR",
            Self::Unsaved(_) => "UNSAVED_CHANGES",
            Self::NotFound(_) => "METHOD_OR_FIELD_NOT_FOUND",
            Self::Invalid(_) => "INVALID_REQUEST",
        }
    }

    pub fn message(&self) -> &str {
        match self {
            Self::PermissionDenied(m)
            | Self::StaleRevision(m)
            | Self::Transaction(m)
            | Self::Unsaved(m)
            | Self::NotFound(m)
            | Self::Invalid(m) => m,
        }
    }

    pub fn to_json(&self) -> Value {
        json!({"code": self.code(), "message": self.message()})
    }
}

impl From<CoreError> for RpcError {
    fn from(error: CoreError) -> Self {
        match error.code {
            // Core key errors already carry the Python `repr()` form.
            "E-CORE-KEY" | "KeyError" => Self::NotFound(error.message),
            _ => Self::Invalid(error.message),
        }
    }
}

pub type RpcResult<T> = Result<T, RpcError>;
