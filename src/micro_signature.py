from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


@dataclass(frozen=True)
class StateDotSpec:
    visible: bool
    diameter: int
    slot: int
    opacity: float


@dataclass(frozen=True)
class PrimaryCornerSpec:
    visible: bool
    arm: int
    stroke: int
    opacity: float


@dataclass(frozen=True)
class PixelHoverSpec:
    visible: bool
    stroke: int
    opacity: float


@dataclass(frozen=True)
class PopupSelectedDotSpec:
    visible: bool
    diameter: int
    right_margin: int
    opacity: float


def state_dot_spec(kind: str, *, active: bool) -> StateDotSpec:
    """Return the restrained state-marker contract used by V10.3.

    The reserved slot remains constant even when the dot is not painted, so
    dirty/clean and modified/unmodified transitions never move neighboring UI.
    """
    kind = str(kind or '')
    diameter = 5 if kind in {'dirty', 'modified', 'popup'} else 5
    return StateDotSpec(bool(active), diameter, 9, 0.94 if active else 0.0)


def _geometry_value(element: Mapping | None, key: str):
    if not isinstance(element, Mapping):
        return None
    zone = element.get('zone')
    if isinstance(zone, Mapping) and key in zone:
        try:
            return int(zone[key])
        except (TypeError, ValueError):
            return zone[key]
    if key in element:
        try:
            return int(element[key])
        except (TypeError, ValueError):
            return element[key]
    return None


def modified_geometry_fields(current: Mapping | None, baseline: Mapping | None) -> tuple[str, ...]:
    """Return geometry fields changed relative to the last saved element.

    Missing saved elements intentionally show no per-field marker; the document
    dirty dot already communicates an unsaved insertion without decorating all
    properties of a brand-new object.
    """
    if not isinstance(current, Mapping) or not isinstance(baseline, Mapping):
        return ()
    changed = []
    for key in ('x', 'y', 'w', 'h'):
        before = _geometry_value(baseline, key)
        after = _geometry_value(current, key)
        if before is not None and after is not None and before != after:
            changed.append(key)
    return tuple(changed)


def primary_corner_spec(*, zoom: int, selected: bool, primary: bool) -> PrimaryCornerSpec:
    active = bool(selected and primary)
    # Keep the L marker legible at low zoom without growing into decoration at
    # high zoom. It reinforces, rather than replaces, the existing selection box.
    arm = max(5, min(8, int(round(max(1, int(zoom)) * 0.75))))
    return PrimaryCornerSpec(active, arm, 2, 1.0 if active else 0.0)


def pixel_hover_spec(*, in_bounds: bool, drawing: bool) -> PixelHoverSpec:
    if not in_bounds:
        return PixelHoverSpec(False, 1, 0.0)
    return PixelHoverSpec(True, 1, 1.0 if drawing else 0.62)


def popup_selected_dot_spec(*, selected: bool) -> PopupSelectedDotSpec:
    return PopupSelectedDotSpec(bool(selected), 4, 10, 0.96 if selected else 0.0)


def smart_guide_anchor_points(
    guides: Mapping[str, tuple[int, ...] | list[int]],
    primary_geometry: tuple[int, int, int, int] | None,
) -> tuple[tuple[int, int], ...]:
    """Return minimal snap anchors in canvas pixel coordinates.

    With both axes active, only true intersections are shown. For a single-axis
    snap, the marker sits on that guide at the primary object's center. This
    avoids turning guide lines into a trail of decorative blue dots.
    """
    if not primary_geometry:
        return ()
    x, y, w, h = (int(v) for v in primary_geometry)
    xs = tuple(dict.fromkeys(int(v) for v in (guides.get('x') or ())))
    ys = tuple(dict.fromkeys(int(v) for v in (guides.get('y') or ())))
    cx = x + w // 2
    cy = y + h // 2
    if xs and ys:
        return tuple((gx, gy) for gx in xs for gy in ys)
    if xs:
        return tuple((gx, cy) for gx in xs)
    if ys:
        return tuple((cx, gy) for gy in ys)
    return ()
