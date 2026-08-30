from __future__ import annotations
from dataclasses import dataclass

@dataclass(frozen=True)
class SceneDiff:
    added: tuple[str,...]
    removed: tuple[str,...]
    changed: dict[str,dict[str,tuple[object,object]]]


def diff_scenes(before:dict,after:dict)->SceneDiff:
    a={str(e.get('id')):e for e in before.get('elements',[])}
    b={str(e.get('id')):e for e in after.get('elements',[])}
    added=tuple(sorted(set(b)-set(a)))
    removed=tuple(sorted(set(a)-set(b)))
    changed={}
    ignored={'id'}
    for eid in sorted(set(a)&set(b)):
        fields={}
        for key in sorted((set(a[eid])|set(b[eid]))-ignored):
            av=a[eid].get(key); bv=b[eid].get(key)
            if av!=bv: fields[key]=(av,bv)
        if fields: changed[eid]=fields
    return SceneDiff(added,removed,changed)
