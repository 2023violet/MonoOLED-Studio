from __future__ import annotations


def preview_capabilities(scene: dict) -> tuple[str, ...]:
    """Return explicitly enabled, product-neutral preview capabilities.

    Raw ``states``/``timeline`` data belongs to renderer/project truth and must
    not automatically leak product-specific runtime semantics into the generic
    workbench UI. Projects opt in through ``preview.capabilities``.
    """
    capabilities = ['frame']
    if isinstance(scene, dict):
        preview = scene.get('preview')
        declared = preview.get('capabilities') if isinstance(preview, dict) else None
        declared = tuple(str(v).lower() for v in declared) if isinstance(declared, (list, tuple)) else ()
        states = scene.get('states')
        timeline = scene.get('timeline')
        if 'state' in declared and isinstance(states, dict) and bool(states):
            capabilities.append('state')
        if 'timeline' in declared and isinstance(timeline, list) and bool(timeline):
            capabilities.append('timeline')
    capabilities.append('validation')
    return tuple(capabilities)


def timeline_metadata(scene: dict) -> dict[str, object]:
    """Resolve optional project timeline metadata without assuming seconds."""
    preview = scene.get('preview') if isinstance(scene, dict) else None
    raw = preview.get('timeline') if isinstance(preview, dict) else None
    raw = raw if isinstance(raw, dict) else {}
    try:
        step = int(raw.get('step', 1))
    except (TypeError, ValueError):
        step = 1
    step = max(1, step)
    unit = str(raw.get('unit', 'step') or 'step')
    label = str(raw.get('label', 'Step') or 'Step')
    return {'step': step, 'unit': unit, 'label': label}
