from __future__ import annotations
from dataclasses import dataclass
from ui_metrics import build_ui_metrics

@dataclass(frozen=True)
class LayoutPlan:
    left_width:int
    canvas_width:int
    inspector_width:int
    diagnostics_height:int
    compact:bool


def plan_layout(window_width:int,window_height:int,density:str='comfortable',ui_scale:float=1.0)->LayoutPlan:
    w=max(720,int(window_width)); h=max(520,int(window_height)); m=build_ui_metrics(density,ui_scale)
    # Navigation and inspector scale with user UI scale instead of staying at
    # V8's fixed widths. Canvas keeps a usable floor and scrolls when needed.
    if w>=1440:
        left=max(m['nav_min'],280); right=max(m['inspector_min'],360); compact=False
    elif w>=1360:
        left=max(m['nav_min'],220); right=max(m['inspector_min'],320); compact=False
    else:
        left=max(m['nav_min'],180); right=max(m['inspector_min'],280); compact=True
    chrome=max(40,m['icon']*2)
    canvas=max(300,w-chrome-left-right)
    if left+right+canvas+chrome>w: canvas=300
    diagnostics=max(140,int(round((220 if h>=900 else 180 if h>=720 else 140)*max(.85,min(1.5,ui_scale)))))
    return LayoutPlan(left,canvas,right,diagnostics,compact)

@dataclass(frozen=True)
class HeaderPolicy:
    compact: bool
    show_subtitle: bool
    show_status: bool
    show_project: bool
    show_validate: bool
    show_save: bool
    show_handoff: bool


def header_policy(plan: LayoutPlan) -> HeaderPolicy:
    if plan.compact:
        return HeaderPolicy(True, False, False, False, False, True, True)
    return HeaderPolicy(False, True, True, True, True, True, True)
