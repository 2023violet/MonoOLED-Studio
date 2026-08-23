from __future__ import annotations

class SelectionModel:
    """Ordered selection with one explicit primary object.

    The order records user intent, not scene z-order. The primary selection is
    normally the most recently added object and is used by align-to-primary.
    """
    def __init__(self, ids=(), *, primary: str | None = None):
        self._ids: list[str] = []
        self._primary: str | None = None
        self.replace(ids, primary=primary)

    @property
    def ids(self) -> tuple[str, ...]:
        return tuple(self._ids)

    @property
    def primary_id(self) -> str | None:
        return self._primary

    def clear(self) -> None:
        self._ids.clear(); self._primary=None

    def replace(self, ids, *, primary: str | None = None) -> None:
        unique=[]
        for value in ids:
            sid=str(value)
            if sid not in unique: unique.append(sid)
        self._ids=unique
        if primary is not None and str(primary) in unique:
            self._primary=str(primary)
        else:
            self._primary=unique[-1] if unique else None

    def add(self, element_id: str) -> None:
        eid=str(element_id)
        if eid in self._ids: self._ids.remove(eid)
        self._ids.append(eid); self._primary=eid

    def remove(self, element_id: str) -> None:
        eid=str(element_id)
        if eid not in self._ids: return
        self._ids.remove(eid)
        if self._primary==eid: self._primary=self._ids[-1] if self._ids else None

    def toggle(self, element_id: str) -> bool:
        eid=str(element_id)
        if eid in self._ids:
            self.remove(eid); return False
        self.add(eid); return True

    def contains(self, element_id: str) -> bool:
        return str(element_id) in self._ids
