from __future__ import annotations

from batch_validate import build_state_matrix, case_name
from state_schema import schema_from_scene, validate_state_schema


def _schema_error(scene: dict) -> str | None:
    result = validate_state_schema(schema_from_scene(scene))
    if result.get("valid"):
        return None
    details = []
    for error in result.get("errors", []):
        path = error.get("path", "schema")
        message = error.get("message", "invalid schema")
        details.append(f"{path}: {message}")
    return "; ".join(details) or "schema validation failed"


def _validate_limits(count: int, *, max_cases: int, allow_large_matrix: bool) -> None:
    try:
        limit = int(max_cases)
    except (TypeError, ValueError) as exc:
        raise ValueError("max_cases must be a positive integer") from exc
    if limit <= 0:
        raise ValueError("max_cases must be a positive integer")
    if count > 100000 and not allow_large_matrix:
        raise ValueError(
            f"state matrix has {count} cases; set allow_large_matrix=true only after explicit review"
        )
    if count > limit:
        raise ValueError(f"state matrix has {count} cases; max_cases={limit}")


def build_export_states(
    scene: dict,
    *,
    integer_policy: str = "representative",
    max_cases: int = 5000,
    allow_large_matrix: bool = False,
) -> dict[str, dict]:
    error = _schema_error(scene)
    if error:
        raise ValueError(f"invalid state schema: {error}")
    matrix = build_state_matrix(scene, integer_policy=integer_policy)
    _validate_limits(len(matrix), max_cases=max_cases, allow_large_matrix=allow_large_matrix)
    return {case_name(index, state): dict(state) for index, state in enumerate(matrix)}


def select_export_states(
    scene: dict,
    tokens: list[str],
    *,
    integer_policy: str = "representative",
    max_cases: int = 5000,
    allow_large_matrix: bool = False,
) -> dict[str, dict]:
    states = build_export_states(
        scene,
        integer_policy=integer_policy,
        max_cases=max_cases,
        allow_large_matrix=allow_large_matrix,
    )
    raw_tokens = [str(token).strip() for token in tokens]
    if not raw_tokens or any(token.lower() == "all" for token in raw_tokens):
        if len(raw_tokens) == 1 and raw_tokens[0].lower() == "all":
            return states
        raise ValueError("'all' cannot be combined with individual state cases")

    names = list(states)
    selected: dict[str, dict] = {}
    examples = ", ".join(names[:3])
    for token in raw_tokens:
        if not token:
            continue
        if token.isdigit():
            index = int(token)
            if index >= len(names):
                raise ValueError(f"unknown state index {index}; available cases={len(names)}")
            name = names[index]
        else:
            name = token
            if name not in states:
                raise ValueError(
                    f"unknown state {token!r}; available cases={len(names)}; examples: {examples}"
                )
        selected[name] = states[name]
    if not selected:
        raise ValueError("at least one state case is required")
    return selected
