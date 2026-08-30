from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class EditorChromeState:
    segment_index: int
    settings_active: bool


def editor_chrome_state(document_id: str | None, workspace_mode: str) -> EditorChromeState:
    doc = str(document_id or '')
    mode = str(workspace_mode or 'design').lower()
    if doc == 'settings:preferences':
        return EditorChromeState(-1, True)
    if doc.startswith('asset:') or doc.startswith('pixel:'):
        return EditorChromeState(1, False)
    if doc == 'scene:active':
        return EditorChromeState({'design': 0, 'pixel': 1, 'review': 2}.get(mode, 0), False)
    # Font/other auxiliary editors are not workspace modes. Clear the segment so
    # the header never lies about the active editor.
    return EditorChromeState(-1, False)


def canvas_context_actions(selected_ids, workspace_mode: str, locked_states) -> tuple[str, ...]:
    ids = tuple(str(v) for v in (selected_ids or ()))
    if not ids or str(workspace_mode or '').lower() != 'design':
        return ()
    locks = tuple(bool(v) for v in (locked_states or ()))
    lock_action = 'unlock' if locks and len(locks) == len(ids) and all(locks) else 'lock'
    return ('duplicate', lock_action)
