from __future__ import annotations


def editor_is_dirty(editor) -> bool:
    if editor is None:
        return False
    state=getattr(editor,'dirty',None)
    if state is not None:
        return bool(state() if callable(state) else state)
    document=getattr(editor,'document',None)
    return bool(getattr(document,'dirty',False))

class EditorRegistry:
    """UI-neutral active-document registry and command router."""
    def __init__(self): self._editors={}; self._active=None
    @property
    def active_id(self): return self._active
    @property
    def active(self): return self._editors.get(self._active)
    def open(self, editor):
        key=str(editor.document_id)
        if key not in self._editors: self._editors[key]=editor
        self._active=key
        return self._editors[key]
    def close(self, document_id):
        key=str(document_id); obj=self._editors.pop(key,None)
        if self._active==key: self._active=next(reversed(self._editors),None) if self._editors else None
        return obj
    def activate(self, document_id):
        key=str(document_id)
        if key not in self._editors: raise KeyError(key)
        self._active=key; return self._editors[key]
    def rekey(self, editor):
        old_key=next((key for key,value in self._editors.items() if value is editor),None)
        if old_key is None: raise KeyError('editor is not registered')
        new_key=str(editor.document_id)
        if new_key==old_key:return new_key
        occupant=self._editors.get(new_key)
        if occupant is not None and occupant is not editor: raise ValueError(f'editor identity already open: {new_key}')
        del self._editors[old_key]; self._editors[new_key]=editor
        if self._active==old_key:self._active=new_key
        return new_key
    def get(self, document_id): return self._editors.get(str(document_id))
    def editors(self): return tuple(self._editors.values())
    def _call(self,name,*args,**kw):
        editor=self.active
        if editor is None: return None
        fn=getattr(editor,name,None)
        return fn(*args,**kw) if callable(fn) else None
    def save(self): return self._call('save')
    def undo(self): return self._call('undo')
    def redo(self): return self._call('redo')
    def apply_runtime_delta(self, delta):
        count=0
        for editor in tuple(self._editors.values()):
            fn=getattr(editor,'apply_runtime_delta',None)
            if callable(fn):
                fn(delta); count+=1
        return count

class CallbackEditor:
    def __init__(self, document_id, title, *, save=None, undo=None, redo=None, dirty=None):
        self.document_id=str(document_id); self.title=str(title); self._save=save; self._undo=undo; self._redo=redo; self._dirty=dirty
    @property
    def dirty(self): return bool(self._dirty()) if callable(self._dirty) else False
    def save(self): return self._save() if callable(self._save) else None
    def undo(self): return self._undo() if callable(self._undo) else None
    def redo(self): return self._redo() if callable(self._redo) else None
