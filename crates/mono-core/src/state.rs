//! Scene state schema, validation and export matrix (V1 `state_schema.py`,
//! `batch_validate.build_state_matrix`, `batch_validate.case_name`, `scene.py` helpers).

use serde_json::{Map, Value, json};

use crate::error::{CoreError, CoreResult};
use crate::pyvalue::{is_py_int, py_cmp, py_eq, py_in, py_int, py_repr, py_str};

pub type State = Map<String, Value>;

const RELATION_OPERATORS: [&str; 6] = ["<", "<=", "==", "!=", ">=", ">"];

fn error(code: &str, path: impl Into<String>, message: impl Into<String>) -> Value {
    json!({"code": code, "path": path.into(), "message": message.into()})
}

fn is_identifier(name: &str) -> bool {
    let mut chars = name.chars();
    matches!(chars.next(), Some(c) if c.is_ascii_alphabetic() || c == '_')
        && chars.all(|c| c.is_ascii_alphanumeric() || c == '_')
}

/// V1 `schema_from_scene`.
pub fn schema_from_scene(scene: &Map<String, Value>) -> Value {
    json!({
        "variables": scene.get("states").cloned().unwrap_or_else(|| json!({})),
        "relations": scene.get("state_relations").cloned().unwrap_or_else(|| json!([])),
    })
}

fn unique_ints(values: &[Value]) -> bool {
    let mut seen: Vec<&Value> = Vec::new();
    for value in values {
        if seen.iter().any(|v| py_eq(v, value)) {
            return false;
        }
        seen.push(value);
    }
    true
}

fn normalize_spec(name: &str, raw: &Value, errors: &mut Vec<Value>) -> Value {
    let path = format!("variables.{name}");
    let Value::Object(raw_map) = raw else {
        errors.push(error(
            "SPEC_TYPE",
            path,
            "state variable spec must be an object",
        ));
        return json!({});
    };
    let mut spec = raw_map.clone();
    if spec.contains_key("default") && !spec.contains_key("init") {
        if let Some(value) = spec.shift_remove("default") {
            spec.insert("init".into(), value);
        }
    }
    let kind = spec
        .get("type")
        .and_then(Value::as_str)
        .unwrap_or("")
        .to_string();
    if kind != "int" && kind != "enum" {
        errors.push(error(
            "STATE_TYPE",
            format!("{path}.type"),
            "state type must be int or enum",
        ));
        return Value::Object(spec);
    }
    let Some(init) = spec.get("init").cloned() else {
        errors.push(error(
            "MISSING_INIT",
            format!("{path}.init"),
            "state variable requires init/default",
        ));
        return Value::Object(spec);
    };
    if kind == "int" {
        if !is_py_int(&init) {
            errors.push(error(
                "INIT_TYPE",
                format!("{path}.init"),
                "int state init must be an integer",
            ));
        }
        if spec.contains_key("values") {
            match spec.get("values").cloned() {
                Some(Value::Array(values)) if !values.is_empty() => {
                    if values.iter().any(|v| !is_py_int(v)) {
                        errors.push(error(
                            "VALUES_TYPE",
                            format!("{path}.values"),
                            "discrete int values must contain integers only",
                        ));
                    }
                    if !unique_ints(&values) {
                        errors.push(error(
                            "VALUES_DUPLICATE",
                            format!("{path}.values"),
                            "discrete int values must be unique",
                        ));
                    }
                    if is_py_int(&init) && !py_in(&init, &values) {
                        errors.push(error(
                            "INIT_DOMAIN",
                            format!("{path}.init"),
                            "init must be one of discrete values",
                        ));
                    }
                }
                _ => errors.push(error(
                    "VALUES",
                    format!("{path}.values"),
                    "discrete int values must be a non-empty array",
                )),
            }
            spec.shift_remove("min");
            spec.shift_remove("max");
        } else {
            let lo = spec.get("min").cloned().unwrap_or(Value::Null);
            let hi = spec.get("max").cloned().unwrap_or(Value::Null);
            if !is_py_int(&lo) {
                errors.push(error(
                    "MIN_TYPE",
                    format!("{path}.min"),
                    "int state min must be an integer",
                ));
            }
            if !is_py_int(&hi) {
                errors.push(error(
                    "MAX_TYPE",
                    format!("{path}.max"),
                    "int state max must be an integer",
                ));
            }
            if let (Some(lo), Some(hi)) = (
                lo.as_i64().filter(|_| is_py_int(&lo)),
                hi.as_i64().filter(|_| is_py_int(&hi)),
            ) {
                if lo > hi {
                    errors.push(error("RANGE", path.clone(), "int state min must be <= max"));
                }
                if let Some(i) = init.as_i64().filter(|_| is_py_int(&init)) {
                    if !(lo <= i && i <= hi) {
                        errors.push(error(
                            "INIT_DOMAIN",
                            format!("{path}.init"),
                            "init must be within min/max",
                        ));
                    }
                }
            }
        }
    } else {
        match spec.get("values") {
            Some(Value::Array(values)) if !values.is_empty() => {
                let encoded: Vec<String> = values.iter().map(py_repr).collect();
                let mut unique = encoded.clone();
                unique.sort();
                unique.dedup();
                if unique.len() != encoded.len() {
                    errors.push(error(
                        "VALUES_DUPLICATE",
                        format!("{path}.values"),
                        "enum values must be unique",
                    ));
                }
                if !py_in(&init, values) {
                    errors.push(error(
                        "INIT_DOMAIN",
                        format!("{path}.init"),
                        "init must be one of enum values",
                    ));
                }
            }
            _ => errors.push(error(
                "VALUES",
                format!("{path}.values"),
                "enum values must be a non-empty array",
            )),
        }
    }
    Value::Object(spec)
}

/// V1 `normalize_state_schema`: returns `(normalized, errors)`.
pub fn normalize_state_schema(raw: &Value) -> (Value, Vec<Value>) {
    let mut errors = Vec::new();
    let Value::Object(raw_schema) = raw else {
        return (
            json!({"variables": {}, "relations": []}),
            vec![error(
                "SCHEMA_TYPE",
                "schema",
                "state schema must be an object",
            )],
        );
    };
    let raw_variables = raw_schema
        .get("variables")
        .or_else(|| raw_schema.get("states"))
        .cloned()
        .unwrap_or(Value::Null);
    let raw_variables = match raw_variables {
        Value::Null => Map::new(),
        Value::Object(map) => map,
        _ => {
            errors.push(error(
                "VARIABLES_TYPE",
                "variables",
                "variables must be an object",
            ));
            Map::new()
        }
    };
    let mut variables = Map::new();
    for (name, raw_spec) in &raw_variables {
        if !is_identifier(name) {
            errors.push(error(
                "STATE_NAME",
                format!("variables.{name}"),
                "state variable name must be an identifier",
            ));
        }
        let spec = normalize_spec(name, raw_spec, &mut errors);
        variables.insert(name.clone(), spec);
    }
    let raw_relations = match raw_schema.get("relations") {
        None => Vec::new(),
        Some(Value::Array(items)) => items.clone(),
        Some(_) => {
            errors.push(error(
                "RELATIONS_TYPE",
                "relations",
                "relations must be an array",
            ));
            Vec::new()
        }
    };
    let mut relations = Vec::new();
    for (index, raw) in raw_relations.iter().enumerate() {
        let path = format!("relations.{index}");
        let Value::Object(map) = raw else {
            errors.push(error("RELATION_TYPE", path, "relation must be an object"));
            continue;
        };
        let field = |key: &str| map.get(key).map(py_str).unwrap_or_default();
        let (left, operator, right) = (field("left"), field("operator"), field("right"));
        if !variables.contains_key(&left) {
            errors.push(error(
                "RELATION_LEFT",
                format!("{path}.left"),
                format!("unknown state variable: {left}"),
            ));
        }
        if !variables.contains_key(&right) {
            errors.push(error(
                "RELATION_RIGHT",
                format!("{path}.right"),
                format!("unknown state variable: {right}"),
            ));
        }
        if !RELATION_OPERATORS.contains(&operator.as_str()) {
            errors.push(error(
                "RELATION_OPERATOR",
                format!("{path}.operator"),
                format!("unsupported relation operator: {operator}"),
            ));
        }
        relations.push(json!({"left": left, "operator": operator, "right": right}));
    }
    let normalized = json!({"variables": variables, "relations": relations});
    if errors.is_empty() {
        let mut initial = Map::new();
        for (name, spec) in &variables {
            initial.insert(
                name.clone(),
                spec.get("init").cloned().unwrap_or(Value::Null),
            );
        }
        for violation in validate_state(&normalized, &Value::Object(initial)) {
            if violation["code"] == "RELATION" {
                errors.push(error(
                    "INIT_RELATION",
                    "relations",
                    violation["message"].as_str().unwrap_or_default(),
                ));
            }
        }
    }
    (normalized, errors)
}

/// V1 `validate_state_schema`.
pub fn validate_state_schema(raw: &Value) -> Value {
    let (schema, errors) = normalize_state_schema(raw);
    json!({"valid": errors.is_empty(), "errors": errors, "schema": schema})
}

fn relation_holds(left: &Value, operator: &str, right: &Value) -> bool {
    use std::cmp::Ordering::{Equal, Greater, Less};
    match operator {
        "==" => py_eq(left, right),
        "!=" => !py_eq(left, right),
        _ => match (operator, py_cmp(left, right)) {
            ("<", Some(Less))
            | ("<=", Some(Less | Equal))
            | (">=", Some(Greater | Equal))
            | (">", Some(Greater)) => true,
            _ => false,
        },
    }
}

/// V1 `validate_state`: list of violation objects.
pub fn validate_state(schema: &Value, state: &Value) -> Vec<Value> {
    let Value::Object(state) = state else {
        return vec![
            json!({"code": "STATE_TYPE", "path": "state", "message": "state must be an object"}),
        ];
    };
    let mut violations = Vec::new();
    let empty = Map::new();
    let variables = schema
        .get("variables")
        .and_then(Value::as_object)
        .unwrap_or(&empty);
    for (name, spec) in variables {
        let Some(value) = state.get(name) else {
            violations.push(json!({"code": "MISSING", "path": name, "message": format!("missing state variable: {name}")}));
            continue;
        };
        let kind = spec.get("type").and_then(Value::as_str).unwrap_or("");
        let values = spec.get("values").and_then(Value::as_array);
        if kind == "int" {
            if !is_py_int(value) {
                violations.push(json!({"code": "TYPE", "path": name, "message": format!("{name} must be an integer")}));
            } else if spec.get("values").is_some() {
                let items = values.cloned().unwrap_or_default();
                if !py_in(value, &items) {
                    violations.push(json!({"code": "DOMAIN", "path": name, "message": format!("{name} must be one of {}", py_repr(&Value::Array(items)))}));
                }
            } else {
                let v = value.as_i64().unwrap_or(0);
                let lo = spec.get("min").and_then(py_int).unwrap_or(v);
                let hi = spec.get("max").and_then(py_int).unwrap_or(v);
                if !(lo <= v && v <= hi) {
                    let show =
                        |key: &str| spec.get(key).map(py_repr).unwrap_or_else(|| "None".into());
                    violations.push(json!({"code": "DOMAIN", "path": name, "message": format!("{name} must be within [{}, {}]", show("min"), show("max"))}));
                }
            }
        } else if kind == "enum" {
            let items = values.cloned().unwrap_or_default();
            if !py_in(value, &items) {
                violations.push(json!({"code": "DOMAIN", "path": name, "message": format!("{name} must be one of {}", py_repr(&Value::Array(items)))}));
            }
        }
    }
    for name in state.keys() {
        if !variables.contains_key(name) {
            violations.push(json!({"code": "UNKNOWN", "path": name, "message": format!("unknown state variable: {name}")}));
        }
    }
    if violations.is_empty() {
        let relations = schema
            .get("relations")
            .and_then(Value::as_array)
            .cloned()
            .unwrap_or_default();
        for (index, relation) in relations.iter().enumerate() {
            let left_name = relation["left"].as_str().unwrap_or("");
            let right_name = relation["right"].as_str().unwrap_or("");
            let operator = relation["operator"].as_str().unwrap_or("");
            let left = state.get(left_name).cloned().unwrap_or(Value::Null);
            let right = state.get(right_name).cloned().unwrap_or(Value::Null);
            if !relation_holds(&left, operator, &right) {
                violations.push(json!({
                    "code": "RELATION",
                    "path": format!("relations.{index}"),
                    "message": format!("{left_name} {operator} {right_name} is not satisfied ({} {operator} {})", py_repr(&left), py_repr(&right)),
                    "relation": relation.clone(),
                }));
            }
        }
    }
    violations
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum IntegerPolicy {
    Boundaries,
    Representative,
    Full,
}

impl IntegerPolicy {
    pub fn parse(value: &str) -> CoreResult<Self> {
        match value {
            "boundaries" => Ok(Self::Boundaries),
            "representative" => Ok(Self::Representative),
            "full" => Ok(Self::Full),
            other => Err(CoreError::invalid(format!(
                "unsupported integer policy: {other}"
            ))),
        }
    }
}

fn int_values(spec: &Map<String, Value>, policy: IntegerPolicy) -> CoreResult<Vec<Value>> {
    if let Some(values) = spec.get("values") {
        return Ok(values.as_array().cloned().unwrap_or_default());
    }
    let lo = spec.get("min").and_then(py_int).unwrap_or(0);
    let hi = spec.get("max").and_then(py_int).unwrap_or(lo);
    let init = spec.get("init").and_then(py_int).unwrap_or(lo);
    let mut out: Vec<i64> = match policy {
        IntegerPolicy::Boundaries => vec![lo, (lo + hi).div_euclid(2), init, hi],
        IntegerPolicy::Representative => {
            if hi - lo <= 12 {
                (lo..=hi).collect()
            } else {
                let mut candidates = vec![lo, hi.min(lo + 1), init, hi];
                candidates.extend(
                    [9, 10, 99, 100, 300, 999]
                        .into_iter()
                        .filter(|v| lo <= *v && *v <= hi),
                );
                candidates
            }
        }
        IntegerPolicy::Full => {
            if hi - lo > 2000 {
                return Err(CoreError::invalid("full integer range too large"));
            }
            (lo..=hi).collect()
        }
    };
    out.sort_unstable();
    out.dedup();
    Ok(out.into_iter().map(Value::from).collect())
}

/// V1 `build_state_matrix`: cartesian product (last variable fastest) filtered by validity.
pub fn build_state_matrix(
    scene: &Map<String, Value>,
    policy: IntegerPolicy,
) -> CoreResult<Vec<State>> {
    let empty = Map::new();
    let states = scene
        .get("states")
        .and_then(Value::as_object)
        .unwrap_or(&empty);
    let mut names = Vec::new();
    let mut domains: Vec<Vec<Value>> = Vec::new();
    for (name, spec) in states {
        names.push(name.clone());
        let spec_map = spec.as_object().cloned().unwrap_or_default();
        match spec_map.get("type").and_then(Value::as_str) {
            Some("enum") => domains.push(
                spec_map
                    .get("values")
                    .and_then(Value::as_array)
                    .cloned()
                    .unwrap_or_default(),
            ),
            Some("int") => domains.push(int_values(&spec_map, policy)?),
            _ => domains.push(vec![spec_map.get("init").cloned().unwrap_or(Value::Null)]),
        }
    }
    if names.is_empty() {
        return Ok(vec![Map::new()]);
    }
    let schema = schema_from_scene(scene);
    let mut matrix = Vec::new();
    if domains.iter().any(Vec::is_empty) {
        return Ok(matrix);
    }
    let mut indices = vec![0usize; domains.len()];
    loop {
        let mut state = Map::new();
        for (i, name) in names.iter().enumerate() {
            state.insert(name.clone(), domains[i][indices[i]].clone());
        }
        let candidate = Value::Object(state);
        if validate_state(&schema, &candidate).is_empty() {
            if let Value::Object(state) = candidate {
                matrix.push(state);
            }
        }
        let mut position = domains.len();
        loop {
            if position == 0 {
                return Ok(matrix);
            }
            position -= 1;
            indices[position] += 1;
            if indices[position] < domains[position].len() {
                break;
            }
            indices[position] = 0;
        }
    }
}

/// V1 `case_name`.
pub fn case_name(index: usize, state: &State) -> String {
    if state.is_empty() {
        return format!("case_{index:04}");
    }
    let fields: Vec<String> = state
        .iter()
        .map(|(name, value)| {
            let safe: String = py_str(value)
                .chars()
                .map(|c| {
                    if c.is_ascii_alphanumeric() || "_.-".contains(c) {
                        c
                    } else {
                        '_'
                    }
                })
                .collect();
            let safe = safe.replace("..", "__");
            format!(
                "{name}-{}",
                if safe.is_empty() {
                    "_".to_string()
                } else {
                    safe
                }
            )
        })
        .collect();
    format!("case_{index:04}__{}", fields.join("__"))
}

/// V1 `export_matrix._schema_error`.
pub fn schema_error(scene: &Map<String, Value>) -> Option<String> {
    let result = validate_state_schema(&schema_from_scene(scene));
    if result["valid"] == true {
        return None;
    }
    let details: Vec<String> = result["errors"]
        .as_array()
        .map(|errors| {
            errors
                .iter()
                .map(|e| {
                    format!(
                        "{}: {}",
                        e["path"].as_str().unwrap_or("schema"),
                        e["message"].as_str().unwrap_or("invalid schema")
                    )
                })
                .collect()
        })
        .unwrap_or_default();
    Some(if details.is_empty() {
        "schema validation failed".into()
    } else {
        details.join("; ")
    })
}

/// V1 `export_matrix.build_export_states`: ordered `(case name, state)` pairs.
pub fn build_export_states(
    scene: &Map<String, Value>,
    policy: IntegerPolicy,
    max_cases: usize,
    allow_large_matrix: bool,
) -> CoreResult<Vec<(String, State)>> {
    if let Some(message) = schema_error(scene) {
        return Err(CoreError::invalid(format!(
            "invalid state schema: {message}"
        )));
    }
    let matrix = build_state_matrix(scene, policy)?;
    let count = matrix.len();
    if max_cases == 0 {
        return Err(CoreError::invalid("max_cases must be a positive integer"));
    }
    if count > 100_000 && !allow_large_matrix {
        return Err(CoreError::invalid(format!(
            "state matrix has {count} cases; set allow_large_matrix=true only after explicit review"
        )));
    }
    if count > max_cases {
        return Err(CoreError::invalid(format!(
            "state matrix has {count} cases; max_cases={max_cases}"
        )));
    }
    Ok(matrix
        .into_iter()
        .enumerate()
        .map(|(i, state)| (case_name(i, &state), state))
        .collect())
}

/// V1 `scene.subst`: replace `{name}` with `str(state[name])`, optionally lowercased.
pub fn subst(text: &str, state: &State, lower: bool) -> CoreResult<String> {
    let mut out = String::with_capacity(text.len());
    let mut rest = text;
    while let Some(start) = rest.find('{') {
        let after = &rest[start + 1..];
        let end = after.find('}');
        let name = end.map(|e| &after[..e]);
        match name {
            Some(name)
                if !name.is_empty() && name.chars().all(|c| c.is_alphanumeric() || c == '_') =>
            {
                let value = state
                    .get(name)
                    .ok_or_else(|| CoreError::new("E-CORE-KEY", format!("'{name}'")))?;
                let text = py_str(value);
                out.push_str(&rest[..start]);
                out.push_str(&if lower { text.to_lowercase() } else { text });
                rest = &after[name.len() + 1..];
            }
            _ => {
                out.push_str(&rest[..=start]);
                rest = after;
            }
        }
    }
    out.push_str(rest);
    Ok(out)
}

/// V1 `scene.when_match`.
pub fn when_match(when: Option<&Value>, state: &State) -> CoreResult<bool> {
    let Some(Value::Object(conditions)) = when else {
        return Ok(true);
    };
    for (key, expected) in conditions {
        let value = state
            .get(key)
            .ok_or_else(|| CoreError::new("E-CORE-KEY", format!("'{key}'")))?;
        if !py_eq(value, expected) {
            return Ok(false);
        }
    }
    Ok(true)
}

/// V1 `scene.init_state`.
pub fn init_state(scene: &Map<String, Value>) -> State {
    let mut state = Map::new();
    if let Some(Value::Object(states)) = scene.get("states") {
        for (name, spec) in states {
            state.insert(
                name.clone(),
                spec.get("init").cloned().unwrap_or(Value::Null),
            );
        }
    }
    state
}
