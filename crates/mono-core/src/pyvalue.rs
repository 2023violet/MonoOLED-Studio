//! Python value semantics needed for V1 parity on JSON data.
//!
//! V1 formats values with `str()`/`repr()` into user-visible names and
//! messages, and compares them with Python equality (`1 == 1.0 == True`).

use serde_json::Value;

/// Python `str(value)` for a JSON-decoded value.
pub fn py_str(value: &Value) -> String {
    match value {
        Value::String(s) => s.clone(),
        other => py_repr(other),
    }
}

fn repr_string(s: &str) -> String {
    let quote = if s.contains('\'') && !s.contains('"') {
        '"'
    } else {
        '\''
    };
    let mut out = String::with_capacity(s.len() + 2);
    out.push(quote);
    for ch in s.chars() {
        match ch {
            '\\' => out.push_str("\\\\"),
            '\n' => out.push_str("\\n"),
            '\r' => out.push_str("\\r"),
            '\t' => out.push_str("\\t"),
            c if c == quote => {
                out.push('\\');
                out.push(c);
            }
            c if (c as u32) < 0x20 || c as u32 == 0x7f => {
                out.push_str(&format!("\\x{:02x}", c as u32))
            }
            c => out.push(c),
        }
    }
    out.push(quote);
    out
}

fn repr_number(n: &serde_json::Number) -> String {
    if let Some(i) = n.as_i64() {
        return i.to_string();
    }
    if let Some(u) = n.as_u64() {
        return u.to_string();
    }
    let f = n.as_f64().unwrap_or(0.0);
    if f.is_finite() && f.fract() == 0.0 && f.abs() < 1e16 {
        format!("{f:.1}")
    } else {
        let text = format!("{f}");
        if text.contains('e') || text.contains('.') {
            text
        } else {
            format!("{text}.0")
        }
    }
}

/// Python `repr(value)` for a JSON-decoded value (dict keys keep insertion order).
pub fn py_repr(value: &Value) -> String {
    match value {
        Value::Null => "None".into(),
        Value::Bool(true) => "True".into(),
        Value::Bool(false) => "False".into(),
        Value::Number(n) => repr_number(n),
        Value::String(s) => repr_string(s),
        Value::Array(items) => format!(
            "[{}]",
            items.iter().map(py_repr).collect::<Vec<_>>().join(", ")
        ),
        Value::Object(map) => format!(
            "{{{}}}",
            map.iter()
                .map(|(k, v)| format!("{}: {}", repr_string(k), py_repr(v)))
                .collect::<Vec<_>>()
                .join(", ")
        ),
    }
}

/// Numeric view used by Python equality and ordering (`True == 1`).
fn as_number(value: &Value) -> Option<f64> {
    match value {
        Value::Bool(b) => Some(if *b { 1.0 } else { 0.0 }),
        Value::Number(n) => n.as_f64(),
        _ => None,
    }
}

/// Python `==` on JSON-decoded values.
pub fn py_eq(a: &Value, b: &Value) -> bool {
    if let (Some(x), Some(y)) = (as_number(a), as_number(b)) {
        if let (Value::Number(m), Value::Number(n)) = (a, b) {
            if let (Some(i), Some(j)) = (m.as_i64(), n.as_i64()) {
                return i == j;
            }
        }
        return x == y;
    }
    match (a, b) {
        (Value::Array(x), Value::Array(y)) => {
            x.len() == y.len() && x.iter().zip(y).all(|(p, q)| py_eq(p, q))
        }
        (Value::Object(x), Value::Object(y)) => {
            x.len() == y.len() && x.iter().all(|(k, v)| y.get(k).is_some_and(|w| py_eq(v, w)))
        }
        _ => a == b,
    }
}

/// Python `value in items`.
pub fn py_in(value: &Value, items: &[Value]) -> bool {
    items.iter().any(|item| py_eq(value, item))
}

/// Python ordering for the relation operators; `None` where Python would raise `TypeError`.
pub fn py_cmp(a: &Value, b: &Value) -> Option<std::cmp::Ordering> {
    if let (Some(x), Some(y)) = (as_number(a), as_number(b)) {
        if let (Value::Number(m), Value::Number(n)) = (a, b) {
            if let (Some(i), Some(j)) = (m.as_i64(), n.as_i64()) {
                return Some(i.cmp(&j));
            }
        }
        return x.partial_cmp(&y);
    }
    match (a, b) {
        (Value::String(x), Value::String(y)) => {
            // Python compares strings by code point.
            Some(x.chars().cmp(y.chars()))
        }
        _ => None,
    }
}

/// Python `bool(value)` for JSON values.
pub fn py_truthy(value: &Value) -> bool {
    match value {
        Value::Null => false,
        Value::Bool(b) => *b,
        Value::Number(n) => n.as_f64().is_some_and(|f| f != 0.0),
        Value::String(s) => !s.is_empty(),
        Value::Array(items) => !items.is_empty(),
        Value::Object(map) => !map.is_empty(),
    }
}

/// Python `isinstance(v, int) and not isinstance(v, bool)`.
pub fn is_py_int(value: &Value) -> bool {
    matches!(value, Value::Number(n) if n.is_i64() || n.is_u64())
}

/// Python `int(value)` for JSON numbers and numeric strings.
pub fn py_int(value: &Value) -> Option<i64> {
    match value {
        Value::Bool(b) => Some(i64::from(*b)),
        Value::Number(n) => n.as_i64().or_else(|| n.as_f64().map(|f| f.trunc() as i64)),
        Value::String(s) => s.trim().parse().ok(),
        _ => None,
    }
}
