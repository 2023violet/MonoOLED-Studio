from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class WorkspaceMode(str, Enum):
    DESIGN = 'design'
    PIXEL = 'pixel'
    REVIEW = 'review'


@dataclass(frozen=True)
class WorkspacePlan:
    mode: WorkspaceMode
    compact: bool
    left_visible: bool
    inspector_visible: bool
    bottom_drawer_default: bool
    left_width: int
    tool_rail_width: int
    inspector_width: int
    canvas_width: int
    canvas_fraction: float


def workspace_plan(width: int, height: int, mode: WorkspaceMode = WorkspaceMode.DESIGN) -> WorkspacePlan:
    """Allocate desktop-editor chrome while preserving a canvas-first workspace."""
    w = max(720, int(width))
    _h = max(520, int(height))
    compact = w < 1360
    if mode == WorkspaceMode.PIXEL:
        tool = 56
        left = 0
        inspector = 280 if w >= 1200 else 240
        canvas = max(420, w - tool - inspector - 32)
        return WorkspacePlan(mode, compact, False, True, False, left, tool, inspector, canvas, canvas / w)
    if mode == WorkspaceMode.REVIEW:
        left = 0 if compact else 200
        inspector = 260 if w >= 1200 else 220
        canvas = max(420, w - left - inspector - 32)
        return WorkspacePlan(mode, compact, not compact, True, True, left, 0, inspector, canvas, canvas / w)

    # Design: hide the left navigation rail in compact mode before sacrificing
    # the canvas. The rail remains accessible through the View menu.
    left = 0 if compact else 200
    inspector = 260 if compact else 280
    canvas = max(420, w - left - inspector - 36)
    return WorkspacePlan(mode, compact, not compact, True, False, left, 0, inspector, canvas, canvas / w)
