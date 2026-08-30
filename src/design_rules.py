from __future__ import annotations
from validate import Finding


def _rect(element):
    zone=element.get('zone') if isinstance(element.get('zone'),dict) else None
    src=zone or element
    try:return tuple(int(src[k]) for k in ('x','y','w','h'))
    except (KeyError,TypeError,ValueError):return None


def check_design_rules(scene: dict, rules: dict | None=None) -> list[Finding]:
    """Apply optional project-specific product grammar without changing the renderer."""
    rules=rules or {}
    findings=[]; by_id={str(e.get('id')):e for e in scene.get('elements',[]) if e.get('id')}
    for element_id in rules.get('required_elements',[]):
        if element_id not in by_id:
            findings.append(Finding('WARNING','REQUIRED_ELEMENT_MISSING',f'required design element {element_id!r} is missing',str(element_id)))
    for element_id,zone in (rules.get('zones') or {}).items():
        element=by_id.get(str(element_id)); rect=_rect(element) if element else None
        if not rect: continue
        x,y,w,h=rect; zx,zy,zw,zh=(int(zone[k]) for k in ('x','y','w','h'))
        if x<zx or y<zy or x+w>zx+zw or y+h>zy+zh:
            findings.append(Finding('WARNING','ELEMENT_OUTSIDE_ZONE',f'{element_id} lies outside configured design zone',str(element_id)))
    for group in rules.get('baseline_groups',[]):
        ids=[str(v) for v in group.get('ids',[])]; axis=str(group.get('axis','y')); values=[]
        for eid in ids:
            r=_rect(by_id.get(eid)) if eid in by_id else None
            if r: values.append((eid,r[1] if axis=='y' else r[0]))
        if values and len({v for _,v in values})>1:
            findings.append(Finding('WARNING','BASELINE_MISMATCH',f'{axis}-baseline mismatch: {values}',None))
    return findings
