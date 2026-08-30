from __future__ import annotations

from scene import init_state


def clinical_states(scene: dict, *, seconds: int | None = None, battery: int | None = None) -> dict[str, dict]:
    """Return every mode × phase state declared by the scene.

    Non-mode/phase state variables keep their scene initial values. Optional
    seconds/battery overrides are applied uniformly to each generated state.
    """
    base = init_state(scene)
    if seconds is not None and 'seconds' in base:
        base['seconds'] = int(seconds)
    if battery is not None and 'battery' in base:
        base['battery'] = int(battery)

    modes = list(scene['states']['mode']['values'])
    phases = list(scene['states']['phase']['values'])
    return {
        f'{mode.lower()}_{phase}': {**base, 'mode': mode, 'phase': phase}
        for mode in modes
        for phase in phases
    }
