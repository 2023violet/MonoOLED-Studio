"""Schema-driven state editor metadata for the Designer runtime panel."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from state_schema import validate_state_schema


@dataclass(frozen=True)
class StateEditorSpec:
    """Normalized metadata used to construct one state editor."""

    name: str
    label: str
    spec: dict[str, Any]
    editor_kind: str
    values: tuple[Any, ...]
    minimum: int | None
    maximum: int | None
    initial: Any


@dataclass(frozen=True)
class StateEditorSchema:
    """Validation result and ordered editor metadata for a scene schema."""

    valid: bool
    fields: tuple[StateEditorSpec, ...]
    errors: tuple[dict[str, Any], ...]


def format_state_label(name: str) -> str:
    """Format an identifier for display without assigning product semantics."""

    return str(name).replace('_', ' ').strip().title()


def build_state_editor_specs(raw_schema: Any) -> StateEditorSchema:
    """Validate a raw schema and produce ordered, generic editor metadata."""

    checked = validate_state_schema(raw_schema)
    errors = tuple(checked['errors'])
    if errors:
        return StateEditorSchema(valid=False, fields=(), errors=errors)

    fields: list[StateEditorSpec] = []
    for name, spec in checked['schema']['variables'].items():
        values = tuple(spec.get('values', ()))
        if spec['type'] == 'enum' or values:
            editor_kind = 'combo'
            minimum = maximum = None
        else:
            editor_kind = 'spin'
            minimum = int(spec['min'])
            maximum = int(spec['max'])
        fields.append(StateEditorSpec(
            name=str(name),
            label=format_state_label(str(name)),
            spec=spec,
            editor_kind=editor_kind,
            values=values,
            minimum=minimum,
            maximum=maximum,
            initial=spec['init'],
        ))
    return StateEditorSchema(valid=True, fields=tuple(fields), errors=())


def coerce_editor_value(field: StateEditorSpec, value: Any) -> tuple[bool, Any]:
    """Return a type-preserving value only when it belongs to the field domain."""

    if field.editor_kind == 'combo':
        return (True, value) if value in field.values else (False, None)
    if isinstance(value, bool):
        return False, None
    try:
        candidate = int(value)
    except (TypeError, ValueError, OverflowError):
        return False, None
    if field.minimum is None or field.maximum is None:
        return False, None
    if not field.minimum <= candidate <= field.maximum:
        return False, None
    return True, candidate
