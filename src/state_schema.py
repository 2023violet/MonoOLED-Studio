from __future__ import annotations

from copy import deepcopy
import re
from typing import Any


_NAME_RE = re.compile(r'^[A-Za-z_][A-Za-z0-9_]*$')
_RELATION_OPERATORS = {'<', '<=', '==', '!=', '>=', '>'}


def schema_from_scene(scene: dict) -> dict:
    return {
        'variables': deepcopy(scene.get('states', {})),
        'relations': deepcopy(scene.get('state_relations', [])),
    }


def _error(code: str, path: str, message: str) -> dict:
    return {'code': code, 'path': path, 'message': message}


def _normalize_spec(name: str, raw: Any, errors: list[dict]) -> dict:
    path = f'variables.{name}'
    if not isinstance(raw, dict):
        errors.append(_error('SPEC_TYPE', path, 'state variable spec must be an object'))
        return {}
    spec = deepcopy(raw)
    if 'default' in spec and 'init' not in spec:
        spec['init'] = spec.pop('default')
    kind = spec.get('type')
    if kind not in {'int', 'enum'}:
        errors.append(_error('STATE_TYPE', f'{path}.type', 'state type must be int or enum'))
        return spec
    if 'init' not in spec:
        errors.append(_error('MISSING_INIT', f'{path}.init', 'state variable requires init/default'))
        return spec

    if kind == 'int':
        init = spec.get('init')
        if not isinstance(init, int) or isinstance(init, bool):
            errors.append(_error('INIT_TYPE', f'{path}.init', 'int state init must be an integer'))
        if 'values' in spec:
            values = spec.get('values')
            if not isinstance(values, list) or not values:
                errors.append(_error('VALUES', f'{path}.values', 'discrete int values must be a non-empty array'))
            else:
                if any(not isinstance(v, int) or isinstance(v, bool) for v in values):
                    errors.append(_error('VALUES_TYPE', f'{path}.values', 'discrete int values must contain integers only'))
                if len(values) != len(set(values)):
                    errors.append(_error('VALUES_DUPLICATE', f'{path}.values', 'discrete int values must be unique'))
                spec['values'] = list(values)
                if isinstance(init, int) and not isinstance(init, bool) and init not in values:
                    errors.append(_error('INIT_DOMAIN', f'{path}.init', 'init must be one of discrete values'))
            spec.pop('min', None)
            spec.pop('max', None)
        else:
            lo = spec.get('min')
            hi = spec.get('max')
            if not isinstance(lo, int) or isinstance(lo, bool):
                errors.append(_error('MIN_TYPE', f'{path}.min', 'int state min must be an integer'))
            if not isinstance(hi, int) or isinstance(hi, bool):
                errors.append(_error('MAX_TYPE', f'{path}.max', 'int state max must be an integer'))
            if isinstance(lo, int) and isinstance(hi, int) and not isinstance(lo, bool) and not isinstance(hi, bool):
                if lo > hi:
                    errors.append(_error('RANGE', path, 'int state min must be <= max'))
                if isinstance(init, int) and not isinstance(init, bool) and not (lo <= init <= hi):
                    errors.append(_error('INIT_DOMAIN', f'{path}.init', 'init must be within min/max'))
    else:
        values = spec.get('values')
        if not isinstance(values, list) or not values:
            errors.append(_error('VALUES', f'{path}.values', 'enum values must be a non-empty array'))
        else:
            encoded = [repr(v) for v in values]
            if len(encoded) != len(set(encoded)):
                errors.append(_error('VALUES_DUPLICATE', f'{path}.values', 'enum values must be unique'))
            if spec.get('init') not in values:
                errors.append(_error('INIT_DOMAIN', f'{path}.init', 'init must be one of enum values'))
    return spec


def normalize_state_schema(raw_schema: Any) -> tuple[dict, list[dict]]:
    errors: list[dict] = []
    if not isinstance(raw_schema, dict):
        return {'variables': {}, 'relations': []}, [_error('SCHEMA_TYPE', 'schema', 'state schema must be an object')]

    raw_variables = raw_schema.get('variables', raw_schema.get('states'))
    if raw_variables is None:
        raw_variables = {}
    if not isinstance(raw_variables, dict):
        errors.append(_error('VARIABLES_TYPE', 'variables', 'variables must be an object'))
        raw_variables = {}

    variables: dict[str, dict] = {}
    for raw_name, raw_spec in raw_variables.items():
        name = str(raw_name)
        if not _NAME_RE.match(name):
            errors.append(_error('STATE_NAME', f'variables.{name}', 'state variable name must be an identifier'))
        variables[name] = _normalize_spec(name, raw_spec, errors)

    raw_relations = raw_schema.get('relations', [])
    if not isinstance(raw_relations, list):
        errors.append(_error('RELATIONS_TYPE', 'relations', 'relations must be an array'))
        raw_relations = []
    relations: list[dict] = []
    for index, raw in enumerate(raw_relations):
        path = f'relations.{index}'
        if not isinstance(raw, dict):
            errors.append(_error('RELATION_TYPE', path, 'relation must be an object'))
            continue
        relation = {
            'left': str(raw.get('left', '')),
            'operator': str(raw.get('operator', '')),
            'right': str(raw.get('right', '')),
        }
        if relation['left'] not in variables:
            errors.append(_error('RELATION_LEFT', f'{path}.left', f"unknown state variable: {relation['left']}"))
        if relation['right'] not in variables:
            errors.append(_error('RELATION_RIGHT', f'{path}.right', f"unknown state variable: {relation['right']}"))
        if relation['operator'] not in _RELATION_OPERATORS:
            errors.append(_error('RELATION_OPERATOR', f'{path}.operator', f"unsupported relation operator: {relation['operator']}"))
        relations.append(relation)

    normalized = {'variables': variables, 'relations': relations}
    if not errors:
        initial = {name: spec['init'] for name, spec in variables.items()}
        initial_violations = validate_state(normalized, initial)
        relation_violations = [v for v in initial_violations if v['code'] == 'RELATION']
        for violation in relation_violations:
            errors.append(_error('INIT_RELATION', 'relations', violation['message']))
    return normalized, errors


def validate_state_schema(raw_schema: Any) -> dict:
    normalized, errors = normalize_state_schema(raw_schema)
    return {'valid': not errors, 'errors': errors, 'schema': normalized}


def _relation_holds(left: Any, operator: str, right: Any) -> bool:
    if operator == '<':
        return left < right
    if operator == '<=':
        return left <= right
    if operator == '==':
        return left == right
    if operator == '!=':
        return left != right
    if operator == '>=':
        return left >= right
    if operator == '>':
        return left > right
    return False


def validate_state(schema: dict, state: Any) -> list[dict]:
    violations: list[dict] = []
    if not isinstance(state, dict):
        return [{'code': 'STATE_TYPE', 'path': 'state', 'message': 'state must be an object'}]
    variables = schema.get('variables', {}) if isinstance(schema, dict) else {}
    for name, spec in variables.items():
        if name not in state:
            violations.append({'code': 'MISSING', 'path': name, 'message': f'missing state variable: {name}'})
            continue
        value = state[name]
        kind = spec.get('type')
        if kind == 'int':
            if not isinstance(value, int) or isinstance(value, bool):
                violations.append({'code': 'TYPE', 'path': name, 'message': f'{name} must be an integer'})
            elif 'values' in spec and value not in spec.get('values', []):
                violations.append({'code': 'DOMAIN', 'path': name, 'message': f'{name} must be one of {spec.get("values", [])}'})
            elif 'values' not in spec and not (int(spec.get('min', value)) <= value <= int(spec.get('max', value))):
                violations.append({'code': 'DOMAIN', 'path': name, 'message': f'{name} must be within [{spec.get("min")}, {spec.get("max")}]'})
        elif kind == 'enum' and value not in spec.get('values', []):
            violations.append({'code': 'DOMAIN', 'path': name, 'message': f'{name} must be one of {spec.get("values", [])}'})

    for name in state:
        if name not in variables:
            violations.append({'code': 'UNKNOWN', 'path': name, 'message': f'unknown state variable: {name}'})

    if not [v for v in violations if v['code'] in {'MISSING', 'TYPE', 'DOMAIN', 'UNKNOWN'}]:
        for index, relation in enumerate(schema.get('relations', [])):
            left_name = relation['left']
            right_name = relation['right']
            left = state[left_name]
            right = state[right_name]
            operator = relation['operator']
            if not _relation_holds(left, operator, right):
                violations.append({
                    'code': 'RELATION',
                    'path': f'relations.{index}',
                    'message': f'{left_name} {operator} {right_name} is not satisfied ({left!r} {operator} {right!r})',
                    'relation': deepcopy(relation),
                })
    return violations


def apply_state_schema(scene: dict, normalized_schema: dict) -> None:
    scene['states'] = deepcopy(normalized_schema.get('variables', {}))
    relations = deepcopy(normalized_schema.get('relations', []))
    if relations:
        scene['state_relations'] = relations
    else:
        scene.pop('state_relations', None)
