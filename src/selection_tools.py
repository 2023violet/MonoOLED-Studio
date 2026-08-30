from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Measurement:
    dx: int
    dy: int
    horizontal_gap: int
    vertical_gap: int
    center_dx: float
    center_dy: float


def _geoms(session, ids):
    if len(ids) < 1:
        raise ValueError('at least one element is required')
    return [(element_id, session.geometry(element_id)) for element_id in ids]


def _apply_geometry_changes(session, changes: dict[str, dict[str, int]], *, label: str) -> None:
    changes = {eid: values for eid, values in changes.items() if values}
    if not changes:
        return
    batch = getattr(session, 'batch_set_geometry', None)
    if callable(batch):
        batch(changes, label=label)
        return
    for element_id, values in changes.items():
        session.set_geometry(element_id, **values)


def align(session, ids, mode: str) -> None:
    items = _geoms(session, ids)
    if len(items) < 2:
        return
    geoms = [g for _, g in items]; changes = {}
    if mode == 'left':
        target = min(g.x for g in geoms); changes = {eid:{'x':target} for eid,_g in items}
    elif mode == 'right':
        target = max(g.x + g.w for g in geoms); changes = {eid:{'x':target-g.w} for eid,g in items}
    elif mode == 'top':
        target = min(g.y for g in geoms); changes = {eid:{'y':target} for eid,_g in items}
    elif mode == 'bottom':
        target = max(g.y + g.h for g in geoms); changes = {eid:{'y':target-g.h} for eid,g in items}
    elif mode == 'hcenter':
        left=min(g.x for g in geoms); right=max(g.x+g.w for g in geoms); center=(left+right)/2
        changes={eid:{'x':round(center-g.w/2)} for eid,g in items}
    elif mode == 'vcenter':
        top=min(g.y for g in geoms); bottom=max(g.y+g.h for g in geoms); center=(top+bottom)/2
        changes={eid:{'y':round(center-g.h/2)} for eid,g in items}
    else:
        raise ValueError(f'unsupported alignment mode: {mode}')
    _apply_geometry_changes(session, changes, label=f'align:{mode}')


def distribute(session, ids, axis: str) -> None:
    items = _geoms(session, ids)
    if len(items) < 3:
        return
    changes = {}
    if axis == 'horizontal':
        ordered=sorted(items,key=lambda x:x[1].x); first=ordered[0][1]; last=ordered[-1][1]; step=(last.x-first.x)/(len(ordered)-1)
        changes={eid:{'x':round(first.x+step*index)} for index,(eid,_g) in enumerate(ordered[1:-1],1)}
    elif axis == 'vertical':
        ordered=sorted(items,key=lambda x:x[1].y); first=ordered[0][1]; last=ordered[-1][1]; step=(last.y-first.y)/(len(ordered)-1)
        changes={eid:{'y':round(first.y+step*index)} for index,(eid,_g) in enumerate(ordered[1:-1],1)}
    else:
        raise ValueError(f'unsupported distribution axis: {axis}')
    _apply_geometry_changes(session, changes, label=f'distribute:{axis}')


def snap_positions(session, ids, *, grid: int = 1) -> None:
    if not isinstance(grid, int) or grid <= 0:
        raise ValueError('grid must be a positive integer')
    changes={}
    for element_id,g in _geoms(session,ids):
        changes[element_id]={'x':round(g.x/grid)*grid,'y':round(g.y/grid)*grid}
    _apply_geometry_changes(session, changes, label=f'snap:{grid}')


def measure(session, first_id: str, second_id: str) -> Measurement:
    a = session.geometry(first_id); b = session.geometry(second_id)
    horizontal_gap = max(0, max(b.x - (a.x + a.w), a.x - (b.x + b.w)))
    vertical_gap = max(0, max(b.y - (a.y + a.h), a.y - (b.y + b.h)))
    return Measurement(
        dx=b.x - a.x,
        dy=b.y - a.y,
        horizontal_gap=horizontal_gap,
        vertical_gap=vertical_gap,
        center_dx=(b.x + b.w / 2) - (a.x + a.w / 2),
        center_dy=(b.y + b.h / 2) - (a.y + a.h / 2),
    )


def smart_guides(session, moving_id: str, *, tolerance: int = 2) -> dict[str, tuple[int, ...]]:
    """Return nearby x/y alignment guides for a moving element.

    Guides include left/center/right and top/center/bottom alignments against
    every other element. They are editor-only and never affect framebuffer data.
    """
    moving = session.geometry(moving_id)
    mx = (moving.x, moving.x + moving.w // 2, moving.x + moving.w)
    my = (moving.y, moving.y + moving.h // 2, moving.y + moving.h)
    gx: set[int] = set(); gy: set[int] = set()
    for element in session.scene.get('elements', []):
        eid = str(element.get('id'))
        if eid == moving_id or element.get('hidden'):
            continue
        try:
            g = session.geometry(eid)
        except Exception:
            continue
        candidates_x = (g.x, g.x + g.w // 2, g.x + g.w)
        candidates_y = (g.y, g.y + g.h // 2, g.y + g.h)
        for a in mx:
            for b in candidates_x:
                if abs(a - b) <= tolerance:
                    gx.add(b)
        for a in my:
            for b in candidates_y:
                if abs(a - b) <= tolerance:
                    gy.add(b)
    return {'x': tuple(sorted(gx)), 'y': tuple(sorted(gy))}

@dataclass(frozen=True)
class SelectionMetrics:
    bounds: tuple[int, int, int, int]
    horizontal_gaps: tuple[int, ...]
    vertical_gaps: tuple[int, ...]
    equal_horizontal_spacing: bool
    equal_vertical_spacing: bool


def selection_metrics(session, ids) -> SelectionMetrics:
    items=_geoms(session,ids); geoms=[g for _,g in items]
    left=min(g.x for g in geoms); top=min(g.y for g in geoms)
    right=max(g.x+g.w for g in geoms); bottom=max(g.y+g.h for g in geoms)
    hs=[]
    ordered=sorted(geoms,key=lambda g:g.x)
    for a,b in zip(ordered,ordered[1:]): hs.append(max(0,b.x-(a.x+a.w)))
    vs=[]
    ordered_y=sorted(geoms,key=lambda g:g.y)
    for a,b in zip(ordered_y,ordered_y[1:]): vs.append(max(0,b.y-(a.y+a.h)))
    return SelectionMetrics(
        bounds=(left,top,right-left,bottom-top),
        horizontal_gaps=tuple(hs), vertical_gaps=tuple(vs),
        equal_horizontal_spacing=bool(hs) and len(set(hs))==1,
        equal_vertical_spacing=bool(vs) and len(set(vs))==1,
    )


def align_to(session, ids, mode: str, *, reference: str='selection', primary_id: str|None=None, canvas: tuple[int,int]|None=None) -> None:
    items=_geoms(session,ids)
    if not items:return
    geoms=[g for _,g in items]
    if reference=='primary':
        if not primary_id or primary_id not in {eid for eid,_ in items}: raise ValueError('primary_id must be selected')
        ref=session.geometry(primary_id); left,top,right,bottom=ref.x,ref.y,ref.x+ref.w,ref.y+ref.h; cx,cy=ref.x+ref.w/2,ref.y+ref.h/2
    elif reference=='canvas':
        if not canvas: raise ValueError('canvas size is required')
        w,h=map(int,canvas); left=top=0; right=w; bottom=h; cx=w/2; cy=h/2
    elif reference=='selection':
        left=min(g.x for g in geoms); top=min(g.y for g in geoms); right=max(g.x+g.w for g in geoms); bottom=max(g.y+g.h for g in geoms); cx=(left+right)/2; cy=(top+bottom)/2
    else: raise ValueError(f'unsupported alignment reference: {reference}')
    changes={}
    for eid,g in items:
        if reference=='primary' and eid==primary_id:continue
        if mode=='left': values={'x':left}
        elif mode=='right': values={'x':right-g.w}
        elif mode=='top': values={'y':top}
        elif mode=='bottom': values={'y':bottom-g.h}
        elif mode=='hcenter': values={'x':round(cx-g.w/2)}
        elif mode=='vcenter': values={'y':round(cy-g.h/2)}
        else: raise ValueError(f'unsupported alignment mode: {mode}')
        changes[eid]=values
    _apply_geometry_changes(session, changes, label=f'align_to:{reference}:{mode}')

