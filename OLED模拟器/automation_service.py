from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import base64
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
from threading import RLock
import time
import zipfile

from PIL import Image, ImageDraw

from atomic_io import atomic_write_bytes, atomic_write_json
from automation_jobs import AutomationJobCancelled, AutomationJobManager
from assets import load_bitmap
from batch_validate import build_state_matrix
from c_export import write_c_header
from editor_model import EditorSession
from exporter import export_scene
from font_pack import FontPack, GlyphMetrics, create_font_pack, rasterize_characters
from handoff import build_handoff_package
from pixel_diff import diff_framebuffers
from pixel_studio import PixelDocument
from project_workspace import ProjectWorkspace, resolve_under_root
from render import render_scene
from scene import init_state, load_scene
from state_schema import apply_state_schema, schema_from_scene, validate_state, validate_state_schema
from selection_model import SelectionModel
from selection_tools import align_to, distribute, measure, selection_metrics
from validate import has_blockers, validate_scene


AUTOMATION_API_VERSION = '1.2.0'


class StaleRevisionError(RuntimeError):
    pass


class PermissionDeniedError(PermissionError):
    pass


class UnsavedChangesError(RuntimeError):
    pass


class TransactionError(RuntimeError):
    pass


class JobCancelledError(RuntimeError):
    pass


@dataclass
class _Transaction:
    id: str
    scene: dict
    selection: tuple[str, ...]
    primary: str | None
    base_revision: int



def _param(type_name: str, *, required: bool, **extra) -> dict:
    return {'type': type_name, 'required': bool(required), **extra}


STATE_SCHEMA_PARAM = {
    'type': 'object',
    'required': True,
    'properties': {
        'variables': {
            'type': 'object<string,state-variable>',
            'required': True,
            'variants': [
                {
                    'type': 'int',
                    'fields': {
                        'type': {'const': 'int'},
                        'init': {'type': 'int', 'required': True},
                        'values': {'type': 'int[]', 'required': False, 'meaning': 'explicit discrete domain; mutually exclusive with min/max'},
                        'min': {'type': 'int', 'required': False},
                        'max': {'type': 'int', 'required': False},
                    },
                },
                {
                    'type': 'enum',
                    'fields': {
                        'type': {'const': 'enum'},
                        'init': {'type': 'json-scalar', 'required': True},
                        'values': {'type': 'json-scalar[]', 'required': True},
                    },
                },
            ],
            'notes': ['default is accepted as an input alias for init; normalized output always uses init'],
        },
        'relations': {
            'type': 'array',
            'required': False,
            'items': {
                'type': 'object',
                'properties': {
                    'left': {'type': 'state-variable-name', 'required': True},
                    'operator': {'type': 'string', 'required': True, 'enum': ['<', '<=', '==', '!=', '>=', '>']},
                    'right': {'type': 'state-variable-name', 'required': True},
                },
            },
        },
    },
}


def _method(permission: str, summary: str, params: dict | None = None, *, transaction: bool = False, returns: dict | None = None) -> dict:
    return {
        'permission': permission,
        'summary': summary,
        'params': dict(params or {}),
        'returns': dict(returns or {}),
        'transaction_supported': bool(transaction),
    }


METHOD_SPECS = {
    'automation.capabilities': _method('observe', 'List Automation API 1.2 methods and contracts.'),
    'automation.describe_method': _method('observe', 'Describe one Automation API method.', {'method': 'string'}),
    'project.get': _method('observe', 'Observe the active project/scene identity.'),
    'project.get_contract': _method('observe', 'Return project coordinate/framebuffer/schema contract.'),
    'project.list_screens': _method('observe', 'List screens in the active OLED project.'),
    'project.list_assets': _method('observe', 'List project-owned bitmap assets.'),
    'project.open_screen': _method('edit', 'Switch the active project screen without silently discarding unsaved changes.', {
        'screen_id': _param('string', required=True),
        'save_current': _param('bool', required=False, default=False),
        'discard_current': _param('bool', required=False, default=False),
    }),
    'project.create_screen': _method('edit', 'Create a new project screen.', {'screen_id': 'string', 'label': 'string?', 'open': 'bool?', 'save_current': 'bool?', 'discard_current': 'bool?'}),
    'project.duplicate_screen': _method('edit', 'Duplicate a project screen.', {'screen_id': 'string', 'new_id': 'string', 'label': 'string?', 'open': 'bool?', 'save_current': 'bool?', 'discard_current': 'bool?'}),
    'project.rename_screen': _method('edit', 'Rename a project screen and its scene file.', {'screen_id': 'string', 'new_id': 'string', 'label': 'string?'}),
    'project.delete_screen': _method('edit', 'Delete a project screen while preserving at least one screen.', {'screen_id': 'string', 'save_current': 'bool?', 'discard_current': 'bool?'}),
    'project.save': _method('edit', 'Atomically save the active scene and project manifest.'),
    'project.save_all': _method('edit', 'Save active scene, open pixel documents and project manifest.'),
    'scene.get': _method('observe', 'Read the active scene.'),
    'scene.get_schema': _method('observe', 'Describe supported scene element types and coordinate rules.'),
    'scene.list_elements': _method('observe', 'List scene elements.'),
    'scene.update_element': _method('edit', 'Update fields on one scene element.', {'id': 'string', 'changes': 'object'}, transaction=True),
    'scene.create_element': _method('edit', 'Create a scene element.', {'element': 'object'}, transaction=True),
    'scene.delete_elements': _method('edit', 'Delete scene elements.', {'ids': 'string[]'}, transaction=True),
    'selection.get': _method('observe', 'Read selected ids and primary selection.'),
    'selection.set': _method('edit', 'Replace selection.', {'ids': 'string[]', 'primary_id': 'string?'}, transaction=True),
    'selection.toggle': _method('edit', 'Toggle one element in selection.', {'id': 'string'}, transaction=True),
    'selection.clear': _method('edit', 'Clear selection.', transaction=True),
    'layout.align': _method('edit', 'Align selected elements to selection/primary/canvas.', {'mode': 'string', 'reference': 'selection|primary|canvas'}, transaction=True),
    'layout.distribute': _method('edit', 'Distribute selected elements.', {'axis': 'horizontal|vertical'}, transaction=True),
    'layout.measure': _method('observe', 'Measure selected elements.', {'ids': 'string[]?'}),
    'state.get_schema': _method('observe', 'Return the active scene state schema.'),
    'state.list': _method('observe', 'List state variables and their domains.'),
    'state.validate_schema': _method(
        'observe',
        'Validate a proposed root-level state schema without mutating the project.',
        {'schema': deepcopy(STATE_SCHEMA_PARAM)},
        returns={'valid': 'bool', 'errors': 'validation-error[]', 'schema': 'normalized state-schema'},
    ),
    'state.set_schema': _method(
        'edit',
        'Atomically replace the active scene state schema after validation.',
        {'schema': deepcopy(STATE_SCHEMA_PARAM)},
        transaction=True,
        returns={'schema': 'normalized state-schema', 'changed': 'bool'},
    ),
    'state.validate': _method(
        'observe',
        'Validate one concrete state against domains and relational constraints.',
        {'state': _param('object', required=True)},
        returns={'valid': 'bool', 'violations': 'state-violation[]'},
    ),
    'state.enumerate': _method('observe', 'Enumerate a deterministic legal state matrix.', {'integer_policy': 'representative|boundaries|full', 'include_states': 'bool?', 'summary_only': 'bool?', 'max_cases': 'int?', 'allow_large_matrix': 'bool?'}),
    'state.count': _method('observe', 'Count legal state combinations before starting a long matrix operation.', {'integer_policy': 'representative|boundaries|full', 'max_cases': 'int?', 'allow_large_matrix': 'bool?'}),
    'render.current': _method('observe', 'Render one state to canonical framebuffer truth.', {'state': 'object?'}),
    'render.framebuffer': _method('observe', 'Return VLSB framebuffer bytes/sha for one state.', {'state': 'object?'}),
    'render.resolved_elements': _method('observe', 'Return renderer-resolved element geometry.', {'state': 'object?'}),
    'render.png': _method('observe', 'Return canonical PNG as base64.', {'state': 'object?'}),
    'render.preview_file': _method('observe', 'Write canonical PNG preview under the project root.', {'path': 'relative path', 'state': 'object?'}),
    'render.annotated_preview': _method('observe', 'Write enlarged preview with resolved element boxes/ids.', {'path': 'relative path', 'state': 'object?', 'scale': 'int?'}),
    'render.pixel_diff': _method('observe', 'Compare two rendered states.', {'before_state': 'object', 'after_state': 'object'}),
    'render.all_states': _method('observe', 'Render every state in a deterministic state matrix.', {'integer_policy': 'representative|boundaries|full', 'summary_only': 'bool?', 'include_frames': 'bool?', 'max_cases': 'int?', 'allow_large_matrix': 'bool?'}),
    'validate.current': _method('observe', 'Validate one state.', {'state': 'object?'}),
    'validate.all_states': _method('observe', 'Validate a deterministic state matrix.', {'integer_policy': 'representative|boundaries|full', 'summary_only': 'bool?', 'include_cases': 'bool?', 'max_cases': 'int?', 'allow_large_matrix': 'bool?'}),
    'asset.create': _method('edit', 'Create a blank project bitmap.', {'path': 'relative path', 'width': 'int', 'height': 'int', 'value': '0|1?'}),
    'asset.import': _method('edit', 'Import an external bitmap into the project.', {'source': 'path', 'target': 'relative path'}),
    'asset.copy': _method('edit', 'Copy a project bitmap.', {'path': 'relative path', 'target': 'relative path'}),
    'asset.rename': _method('edit', 'Rename a project bitmap.', {'path': 'relative path', 'target': 'relative path'}),
    'asset.delete': _method('edit', 'Delete a project bitmap.', {'path': 'relative path'}),
    'pixel.create': _method('edit', 'Create an in-memory blank PixelDocument bound to a project path.', {'path': 'relative path', 'width': 'int', 'height': 'int'}),
    'pixel.open': _method('observe', 'Open a project bitmap as a PixelDocument.', {'path': 'relative path'}),
    'pixel.get_document': _method('observe', 'Read a PixelDocument.', {'document_id': 'string'}),
    'pixel.paint': _method('edit', 'Paint pixels.', {'document_id': 'string', 'x': 'int', 'y': 'int', 'value': '0|1'}),
    'pixel.erase': _method('edit', 'Erase pixels.', {'document_id': 'string', 'x': 'int', 'y': 'int'}),
    'pixel.line': _method('edit', 'Draw a pixel-exact line.'),
    'pixel.rect': _method('edit', 'Draw a pixel-exact rectangle.'),
    'pixel.fill': _method('edit', 'Flood fill a PixelDocument.'),
    'pixel.resize_canvas': _method('edit', 'Resize PixelDocument canvas with anchor.'),
    'pixel.rotate': _method('edit', 'Rotate PixelDocument by 0/90/180/270.'),
    'pixel.flip': _method('edit', 'Flip PixelDocument horizontally/vertically.'),
    'pixel.undo': _method('edit', 'Undo PixelDocument edit.'),
    'pixel.redo': _method('edit', 'Redo PixelDocument edit.'),
    'pixel.save': _method('edit', 'Save PixelDocument to project PNG.'),
    'font.list': _method('observe', 'List FontPack assets.'),
    'font.create_pack': _method(
        'edit', 'Create FontPack.',
        {
            'path': _param('relative path', required=True),
            'name': _param('string', required=False),
            'cell': _param('[width:int,height:int]', required=False),
            'baseline': _param('int', required=False),
            'advance': _param('int', required=False),
        },
        returns={'font_id': 'relative dir', 'name': 'string', 'cell': '[int,int]'},
    ),
    'font.get_pack': _method(
        'observe', 'Read FontPack metrics/characters.',
        {'font_id': _param('relative dir', required=True)},
        returns={'font_id': 'relative dir', 'name': 'string', 'cell': '[int,int]', 'baseline': 'int', 'advance': 'int', 'characters': 'string[]'},
    ),
    'font.generate_glyphs': _method(
        'edit', 'Rasterize characters into FontPack.',
        {
            'font_id': _param('relative dir', required=True),
            'characters': _param('string', required=True),
            'font_path': _param('path|null', required=False),
            'font_size': _param('int', required=False, minimum=1, default=12),
            'threshold': _param('int', required=False, minimum=0, maximum=255, default=128),
            'offset': _param('[x:int,y:int]', required=False, default=[0, 0]),
        },
        returns={'font_id': 'relative dir', 'count': 'int'},
    ),
    'font.get_glyph': _method(
        'observe', 'Read one bitmap glyph.',
        {'font_id': _param('relative dir', required=True), 'char': _param('single character', required=True)},
        returns={'font_id': 'relative dir', 'char': 'string', 'pixels': 'int[][]', 'metrics': 'object'},
    ),
    'font.update_glyph': _method(
        'edit', 'Update one bitmap glyph.',
        {
            'font_id': _param('relative dir', required=True),
            'char': _param('single character', required=True),
            'pixels': _param('int[][]', required=True),
            'metrics': _param('{bearing_x:int?,bearing_y:int?,advance:int?}', required=False),
        },
        returns={'font_id': 'relative dir', 'char': 'string'},
    ),
    'font.set_metrics': _method(
        'edit', 'Update FontPack baseline/advance.',
        {
            'font_id': _param('relative dir', required=True),
            'baseline': _param('int', required=False),
            'advance': _param('int', required=False),
        },
        returns={'font_id': 'relative dir', 'baseline': 'int', 'advance': 'int'},
    ),
    'export.current': _method('edit', 'Export current state through the canonical Studio exporter.', {'output_dir': 'relative dir', 'state': 'object?'}),
    'export.all': _method('edit', 'Export deterministic state matrix through the canonical Studio exporter.', {'output_dir': 'relative dir', 'integer_policy': 'representative|boundaries|full', 'summary_only': 'bool?', 'include_hashes': 'bool?', 'max_cases': 'int?', 'allow_large_matrix': 'bool?'}),
    'export.c_header': _method('edit', 'Export current framebuffer C header.', {'path': 'relative path', 'symbol': 'string?'}),
    'export.font_pack': _method('edit', 'Create deterministic ZIP of a FontPack.', {'font_id': 'relative dir', 'path': 'relative zip path'}),
    'export.code_ai_handoff': _method('edit', 'Generate deterministic Code AI handoff from Studio truth.', {'path': 'relative zip path', 'integer_policy': 'representative|boundaries|full', 'summary_only': 'bool?', 'max_cases': 'int?', 'allow_large_matrix': 'bool?'}),
    'history.begin_transaction': _method('edit', 'Begin one undoable Agent scene transaction.'),
    'history.commit': _method('edit', 'Commit Agent transaction as one Designer undo.', {'transaction': _param('string', required=True)}),
    'history.rollback': _method('edit', 'Rollback Agent transaction.', {'transaction': _param('string', required=True)}),
    'job.start': _method('edit', 'Start one server-owned long-running Automation operation.', {'operation': _param('string', required=True), 'arguments': _param('object', required=False)}),
    'job.status': _method('observe', 'Read long-running Automation job progress.', {'job_id': _param('string', required=True)}),
    'job.result': _method('observe', 'Read terminal long-running Automation job result.', {'job_id': _param('string', required=True)}),
    'job.cancel': _method('edit', 'Request cooperative cancellation of a long-running Automation job.', {'job_id': _param('string', required=True)}),
    'session.events': _method('observe', 'Read semantic Agent event stream.', {'since': 'int?'}),
}


class StudioAutomationService:
    """Semantic automation surface shared by Code AI, tests and transport adapters.

    The API intentionally manipulates project/scene/pixel/font concepts rather than
    GUI coordinates.  Automation API 1.1 keeps the project orchestration of 1.0 and adds
    atomic product-state authoring, relational legal-state proof and Studio-owned export so an Agent can complete a
    multi-screen OLED project without inventing a second source of truth.
    """

    READ_METHODS = {name for name, spec in METHOD_SPECS.items() if spec['permission'] == 'observe'}
    WRITE_METHODS = set(METHOD_SPECS) - READ_METHODS
    _IMAGE_EXTS = {'.png', '.bmp', '.jpg', '.jpeg'}

    def __init__(
        self,
        scene: dict,
        *,
        source_path: Path | None = None,
        permission: str = 'edit',
        copy_scene: bool = True,
        on_change=None,
        editor_session=None,
        project_workspace: ProjectWorkspace | None = None,
    ):
        if permission not in {'observe', 'edit', 'full'}:
            raise ValueError('permission must be observe/edit/full')
        self.scene = deepcopy(scene) if copy_scene else scene
        self.source_path = Path(source_path).resolve() if source_path else None
        self.permission = permission
        self.selection = SelectionModel()
        self.revision = 0
        self._tx: dict[str, _Transaction] = {}
        self._tx_seq = 0
        self.events = []
        self._lock = RLock()
        self.on_change = on_change
        self.editor_session = editor_session
        self.project = project_workspace or self._discover_project_workspace()
        self.project_root = (
            self.project.root
            if self.project is not None
            else Path(self.scene.get('_root') or (self.source_path.parent if self.source_path else Path.cwd())).resolve()
        )
        self.pixel_documents: dict[str, PixelDocument] = {}
        self.pixel_paths: dict[str, Path] = {}
        self._pixel_seq = 0
        self._jobs = AutomationJobManager()
        self._saved_scene_fingerprint = self._scene_fingerprint()

    @classmethod
    def for_scene(cls, path, *, permission='edit'):
        p = Path(path).resolve()
        raw = load_scene(p)
        return cls(raw, source_path=p, permission=permission)

    @classmethod
    def for_editor(
        cls,
        scene,
        *,
        source_path=None,
        selection_model=None,
        editor_session=None,
        permission='edit',
        on_change=None,
        project_workspace=None,
    ):
        obj = cls(
            scene,
            source_path=Path(source_path).resolve() if source_path else None,
            permission=permission,
            copy_scene=False,
            on_change=on_change,
            editor_session=editor_session,
            project_workspace=project_workspace,
        )
        if selection_model is not None:
            obj.selection = selection_model
        return obj

    def _discover_project_workspace(self) -> ProjectWorkspace | None:
        candidates = []
        raw = self.scene.get('_project_path')
        if raw:
            candidates.append(Path(str(raw)))
        root = Path(self.scene.get('_root') or (self.source_path.parent if self.source_path else Path.cwd())).resolve()
        candidates.extend((root / 'project.oled.json', root.parent / 'project.oled.json'))
        if self.source_path is not None:
            candidates.extend((self.source_path.parent / 'project.oled.json', self.source_path.parent.parent / 'project.oled.json'))
        seen = set()
        for candidate in candidates:
            candidate = candidate.resolve()
            if candidate in seen:
                continue
            seen.add(candidate)
            if candidate.exists():
                try:
                    return ProjectWorkspace.load(candidate)
                except Exception:
                    continue
        return None

    def _require_project(self) -> ProjectWorkspace:
        if self.project is None:
            raise ValueError('current scene is not attached to an OLED project manifest')
        return self.project

    @staticmethod
    def _persistent_scene(scene: dict) -> dict:
        return {k: deepcopy(v) for k, v in scene.items() if not str(k).startswith('_')}

    def _scene_fingerprint(self, scene: dict | None = None) -> str:
        payload = self._persistent_scene(self.scene if scene is None else scene)
        raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf-8')
        return hashlib.sha256(raw).hexdigest()

    def _is_scene_dirty(self) -> bool:
        by_content = self._scene_fingerprint() != self._saved_scene_fingerprint
        by_editor = bool(getattr(getattr(self.editor_session, 'document', None), 'dirty', False))
        return bool(by_content or by_editor)

    def _refresh_saved_baseline(self) -> None:
        self._saved_scene_fingerprint = self._scene_fingerprint()
        if self.editor_session is not None:
            self.editor_session.document.dirty = False

    def _handle_unsaved_policy(self, params: dict, *, target_screen: str) -> None:
        save_current = bool(params.get('save_current', False))
        discard_current = bool(params.get('discard_current', False))
        if save_current and discard_current:
            raise ValueError('save_current and discard_current are mutually exclusive')
        if not self._is_scene_dirty():
            return
        if save_current:
            self._save_current_scene()
            if self.project is not None:
                self.project.save()
            return
        if discard_current:
            return
        current = self.project.active_screen if self.project is not None else None
        raise UnsavedChangesError(
            f'UNSAVED_CHANGES: current screen {current!r} has unsaved changes; '
            f'use save_current=true or discard_current=true before opening {target_screen!r}'
        )

    def _check_revision(self, expected):
        if expected is not None and int(expected) != self.revision:
            raise StaleRevisionError(f'expected revision {expected}, current {self.revision}')

    def _write_guard(self, method):
        if self.permission == 'observe' and method not in self.READ_METHODS:
            raise PermissionDeniedError(method)

    def _element(self, eid):
        for element in self.scene.get('elements', []):
            if str(element.get('id')) == str(eid):
                return element
        raise KeyError(eid)

    def _notify(self, event, **extra):
        payload = {'event': event, 'revision': self.revision, **extra}
        self.events.append(payload)
        if callable(self.on_change):
            self.on_change(payload)

    @staticmethod
    def _json_safe(value):
        if isinstance(value, Path):
            return str(value)
        if isinstance(value, dict):
            return {str(k): StudioAutomationService._json_safe(v) for k, v in value.items()}
        if isinstance(value, (list, tuple)):
            return [StudioAutomationService._json_safe(v) for v in value]
        return value

    def _result(self, **extra):
        return self._json_safe({'ok': True, 'revision': self.revision, **extra})

    def _render(self, state=None):
        resolved_state = dict(state or init_state(self.scene))
        result = render_scene(self.scene, resolved_state)
        raw = result.framebuffer.to_vlsb()
        return resolved_state, result, raw

    @staticmethod
    def _framebuffer_png_bytes(framebuffer):
        image = Image.new('1', (framebuffer.width, framebuffer.height), 0)
        px = image.load()
        for y, row in enumerate(framebuffer.to_rows()):
            for x, value in enumerate(row):
                px[x, y] = 255 if value else 0
        buf = io.BytesIO()
        image.save(buf, format='PNG', optimize=False)
        return buf.getvalue()

    def _changed(self, method, transaction, before_elements=None):
        if transaction is None:
            if self.editor_session is not None and before_elements is not None:
                self.editor_session.record_external_batch(before_elements, label='agent_' + method.replace('.', '_'))
            self.revision += 1
            self._notify(method)

    def begin_transaction(self, *, expected_revision=None):
        with self._lock:
            self._check_revision(expected_revision)
            self._write_guard('history.begin_transaction')
            self._tx_seq += 1
            tid = f'tx-{self._tx_seq}'
            self._tx[tid] = _Transaction(tid, deepcopy(self.scene), self.selection.ids, self.selection.primary_id, self.revision)
            return tid

    def commit_transaction(self, tid):
        with self._lock:
            tx = self._tx.pop(tid, None)
            if tx is None:
                raise TransactionError(tid)
            if self.editor_session is not None:
                self.editor_session.record_external_scene(tx.scene, label='agent_transaction')
            self.revision += 1
            self._notify('transaction.committed')
            return self._result()

    def rollback_transaction(self, tid):
        with self._lock:
            tx = self._tx.pop(tid, None)
            if tx is None:
                raise TransactionError(tid)
            self.scene.clear()
            self.scene.update(deepcopy(tx.scene))
            if self.editor_session is not None:
                self.editor_session.reset_scene(self.scene)
            self.selection.replace(tx.selection, primary=tx.primary)
            self._notify('transaction.rolled_back')
            return self._result()

    def _pixel_doc(self, document_id):
        try:
            return self.pixel_documents[str(document_id)]
        except KeyError:
            raise KeyError(f'unknown pixel document: {document_id}')

    def _font_root(self, font_id):
        return resolve_under_root(self.project_root, str(font_id), label='font pack')

    def _pixel_result(self, did, doc):
        raw = doc.to_vlsb()
        return self._result(
            document_id=did,
            width=doc.width,
            height=doc.height,
            bytes=len(raw),
            sha256=hashlib.sha256(raw).hexdigest(),
            pixels=deepcopy(doc.pixels),
            dirty=doc.dirty,
        )

    def _asset_path(self, member, *, label='asset') -> Path:
        path = resolve_under_root(self.project_root, member, label=label)
        if path.suffix.lower() not in self._IMAGE_EXTS:
            raise ValueError(f'{label} must be a supported bitmap file: {path.suffix}')
        return path

    @staticmethod
    def _file_result(path: Path, root: Path) -> dict:
        raw = path.read_bytes()
        return {
            'path': path.relative_to(root).as_posix(),
            'bytes': len(raw),
            'sha256': hashlib.sha256(raw).hexdigest(),
        }

    def _project_scene_payload(self, screen_id: str) -> dict:
        project = self._require_project()
        scene = load_scene(project.screen_path(screen_id), project_root=project.root)
        scene['_project_path'] = str(project.path)
        scene['_asset_dirs'] = list(project.asset_dirs)
        scene['_design_rules'] = dict(project.data.get('design_rules') or {})
        return scene

    def _open_project_screen(self, screen_id: str, *, event: str = 'project.open_screen') -> dict:
        project = self._require_project()
        project.screen(screen_id)
        project.set_active_screen(screen_id)
        project.save()
        loaded = self._project_scene_payload(screen_id)
        self.scene.clear()
        self.scene.update(loaded)
        self.source_path = project.screen_path(screen_id)
        self.project_root = project.root
        self.selection.clear()
        self._tx.clear()
        if self.editor_session is not None:
            self.editor_session.reset_scene(self.scene)
        self._refresh_saved_baseline()
        self.revision += 1
        self._notify(event, active_screen=screen_id)
        return self._result(active_screen=screen_id, scene_path=str(self.source_path), active_screen_changed=True, project_structure_changed=True)

    def _save_current_scene(self) -> Path:
        if self.source_path is None:
            raise ValueError('current scene has no writable source path')
        data = {k: deepcopy(v) for k, v in self.scene.items() if not str(k).startswith('_')}
        atomic_write_json(self.source_path, data)
        self._refresh_saved_baseline()
        return self.source_path

    @staticmethod
    def _case_name(index: int, state: dict) -> str:
        if not state:
            return 'case_0000'
        slug = '__'.join(f'{k}-{v}' for k, v in state.items())
        safe = ''.join(ch if ch.isalnum() or ch in '-_.' else '_' for ch in slug)
        return f'case_{index:04d}__{safe}'

    def _state_matrix_for_scene(self, scene: dict, params: dict, *, default_limit: int = 5000) -> list[dict]:
        policy = str(params.get('integer_policy', 'representative'))
        matrix = build_state_matrix(scene, integer_policy=policy)
        count = len(matrix)
        if count > 100000 and not bool(params.get('allow_large_matrix', False)):
            raise ValueError(
                f'state matrix has {count} cases; set allow_large_matrix=true only after explicit review'
            )
        limit = int(params.get('max_cases', default_limit))
        if count > limit:
            raise ValueError(f'state matrix has {count} cases; max_cases={limit}')
        return matrix

    def _state_matrix(self, params: dict) -> list[dict]:
        return self._state_matrix_for_scene(self.scene, params)

    @staticmethod
    def _cancelled(cancel_event) -> bool:
        return bool(cancel_event is not None and cancel_event.is_set())

    def _render_all_states_payload(self, scene: dict, params: dict, *, progress=None, cancel_event=None) -> dict:
        matrix = self._state_matrix_for_scene(scene, params)
        include_frames = bool(params.get('include_frames', not bool(params.get('summary_only', False))))
        frames = []
        expected = None
        started = time.perf_counter()
        total = len(matrix)
        for index, state in enumerate(matrix):
            if self._cancelled(cancel_event):
                raise AutomationJobCancelled('job cancellation requested')
            result = render_scene(scene, dict(state))
            raw = result.framebuffer.to_vlsb()
            expected = len(raw) if expected is None else expected
            if len(raw) != expected:
                raise RuntimeError('framebuffer size changed across state matrix')
            if include_frames:
                frames.append({
                    'name': self._case_name(index, state),
                    'state': deepcopy(state),
                    'sha256': hashlib.sha256(raw).hexdigest(),
                    'lit_pixels': sum(sum(row) for row in result.framebuffer.to_rows()),
                })
            if callable(progress):
                progress('render', index + 1, total)
        payload = {
            'cases': total,
            'framebuffer_bytes': int(expected or (int(scene['canvas']['w']) * ((int(scene['canvas']['h']) + 7) // 8))),
            'deterministic': True,
            'elapsed_ms': int(round((time.perf_counter() - started) * 1000.0)),
        }
        if include_frames:
            payload['frames'] = frames
        return payload

    def _validate_all_states_payload(self, scene: dict, params: dict, *, progress=None, cancel_event=None) -> dict:
        matrix = self._state_matrix_for_scene(scene, params)
        include_cases = bool(params.get('include_cases', not bool(params.get('summary_only', False))))
        failures = []
        total_findings = blockers = 0
        started = time.perf_counter()
        total = len(matrix)
        for index, state in enumerate(matrix):
            if self._cancelled(cancel_event):
                raise AutomationJobCancelled('job cancellation requested')
            findings = validate_scene(scene, dict(state))
            total_findings += len(findings)
            case_blockers = sum(1 for f in findings if f.severity in {'BLOCKER', 'ERROR'})
            blockers += case_blockers
            if include_cases and findings:
                failures.append({
                    'name': self._case_name(index, state),
                    'state': deepcopy(state),
                    'blockers': case_blockers,
                    'findings': [
                        {'severity': f.severity, 'code': f.code, 'message': f.message, 'element_id': f.element_id}
                        for f in findings
                    ],
                })
            if callable(progress):
                progress('validation', index + 1, total)
        payload = {
            'cases': total,
            'findings': total_findings,
            'blockers': blockers,
            'valid': blockers == 0,
            'elapsed_ms': int(round((time.perf_counter() - started) * 1000.0)),
        }
        if include_cases:
            payload['cases_with_findings'] = failures
        return payload

    def _export_all_payload(self, scene: dict, project_root: Path, params: dict, *, progress=None, cancel_event=None) -> dict:
        output = resolve_under_root(project_root, params.get('output_dir', 'exports/agent_all'), label='export directory')
        matrix = self._state_matrix_for_scene(scene, params)
        states = {self._case_name(i, state): state for i, state in enumerate(matrix)}
        started = time.perf_counter()
        summary = export_scene(
            scene,
            output,
            states,
            progress=progress,
            cancel=(cancel_event.is_set if cancel_event is not None else None),
        )
        payload = {
            'output_dir': str(output),
            'frame_count': summary.frame_count,
            'elapsed_ms': int(round((time.perf_counter() - started) * 1000.0)),
        }
        if bool(params.get('include_hashes', not bool(params.get('summary_only', False)))):
            payload['frame_hashes'] = summary.frame_hashes
        return payload

    def _handoff_payload(self, scene: dict, project_root: Path, params: dict, *, progress=None, cancel_event=None) -> dict:
        target = resolve_under_root(project_root, params.get('path', 'exports/code_ai_handoff.zip'), label='Code AI handoff')
        if target.suffix.lower() != '.zip':
            raise ValueError('Code AI handoff must end in .zip')
        matrix = self._state_matrix_for_scene(scene, params)
        states = {self._case_name(i, state): state for i, state in enumerate(matrix)}
        started = time.perf_counter()
        summary = build_handoff_package(
            scene,
            target,
            states=states,
            progress=progress,
            cancel=(cancel_event.is_set if cancel_event is not None else None),
        )
        return {
            'path': str(target),
            'sha256': hashlib.sha256(target.read_bytes()).hexdigest(),
            'frame_count': summary.frame_count,
            'elapsed_ms': int(round((time.perf_counter() - started) * 1000.0)),
        }

    def _run_long_job(self, operation: str, arguments: dict, snapshot: dict, progress, cancel_event) -> dict:
        scene = deepcopy(snapshot['scene'])
        project_root = Path(snapshot['project_root']).resolve()
        revision = int(snapshot['revision'])
        if operation == 'render.all_states':
            payload = self._render_all_states_payload(scene, arguments, progress=progress, cancel_event=cancel_event)
        elif operation == 'validate.all_states':
            payload = self._validate_all_states_payload(scene, arguments, progress=progress, cancel_event=cancel_event)
        elif operation == 'export.all':
            payload = self._export_all_payload(scene, project_root, arguments, progress=progress, cancel_event=cancel_event)
        elif operation == 'export.code_ai_handoff':
            payload = self._handoff_payload(scene, project_root, arguments, progress=progress, cancel_event=cancel_event)
        else:
            raise ValueError(f'unsupported long-running operation: {operation}')
        return self._json_safe({'ok': True, 'revision': revision, **payload})

    def _annotated_preview_bytes(self, result, *, scale: int = 6) -> bytes:
        scale = max(1, min(32, int(scale)))
        base = Image.open(io.BytesIO(self._framebuffer_png_bytes(result.framebuffer))).convert('RGB')
        image = base.resize((base.width * scale, base.height * scale), Image.Resampling.NEAREST)
        draw = ImageDraw.Draw(image)
        for item in result.resolved_elements:
            if not item.get('visible', True):
                continue
            try:
                x = int(item.get('x', 0)) * scale
                y = int(item.get('y', 0)) * scale
                w = int(item.get('w', 0)) * scale
                h = int(item.get('h', 0)) * scale
            except (TypeError, ValueError):
                continue
            if w <= 0 or h <= 0:
                continue
            draw.rectangle((x, y, x + w - 1, y + h - 1), outline=(255, 0, 0), width=max(1, scale // 3))
            draw.text((x + 1, y + 1), str(item.get('id', '')), fill=(255, 0, 0))
        buf = io.BytesIO()
        image.save(buf, format='PNG', optimize=False)
        return buf.getvalue()

    @staticmethod
    def _deterministic_zip(source: Path, target: Path) -> None:
        target.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(target, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
            for path in sorted((p for p in source.rglob('*') if p.is_file()), key=lambda p: p.relative_to(source).as_posix()):
                rel = path.relative_to(source).as_posix()
                info = zipfile.ZipInfo(rel, date_time=(1980, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o100644 << 16
                zf.writestr(info, path.read_bytes())

    def call(self, method, params=None, *, expected_revision=None, transaction=None):
        with self._lock:
            params = dict(params or {})
            self._check_revision(expected_revision)
            self._write_guard(method)
            if method not in METHOD_SPECS:
                raise KeyError(method)
            if transaction is not None and transaction not in self._tx:
                raise TransactionError(transaction)
            if transaction is not None and not METHOD_SPECS[method]['transaction_supported']:
                raise TransactionError(f'{method} is not transaction-safe')
            external_before = (
                deepcopy(self.scene.get('elements', []))
                if self.editor_session is not None
                and transaction is None
                and method in {'scene.update_element', 'scene.create_element', 'scene.delete_elements', 'layout.align', 'layout.distribute'}
                else None
            )

            # ---- API discovery / contracts ----
            if method == 'automation.capabilities':
                methods = [
                    {'method': name, **deepcopy(spec)}
                    for name, spec in sorted(METHOD_SPECS.items())
                ]
                return self._result(api_version=AUTOMATION_API_VERSION, transport='JSON-RPC 2.0 / localhost', permissions=('observe', 'edit', 'full'), methods=methods)
            if method == 'automation.describe_method':
                name = str(params['method'])
                if name not in METHOD_SPECS:
                    raise KeyError(name)
                return self._result(api_version=AUTOMATION_API_VERSION, method={'method': name, **deepcopy(METHOD_SPECS[name])})
            if method == 'project.get_contract':
                width = int(self.scene['canvas']['w'])
                height = int(self.scene['canvas']['h'])
                return self._result(
                    automation_api=AUTOMATION_API_VERSION,
                    project_schema_version=int(self.project.data.get('schema_version', 1)) if self.project else None,
                    scene_schema_version=int(self.scene.get('schema_version', 1)),
                    coordinate_contract={'origin': 'top-left', 'x_direction': 'right', 'y_direction': 'down', 'bounds': '[x,x+w) x [y,y+h)', 'integer_pixels': True},
                    framebuffer_contract={'width': width, 'height': height, 'bytes': width * ((height + 7) // 8), 'layout': 'VLSB page-major', 'byte_offset': '(y // 8) * width + x', 'bit': '1 << (y % 8)', 'polarity': '1 = OLED lit'},
                    product_truth={'renderer': 'render.py/render_scene', 'scene': str(self.source_path) if self.source_path else None},
                )
            if method == 'scene.get_schema':
                return self._result(schema={
                    'schema_version': int(self.scene.get('schema_version', 1)),
                    'element_types': ('placeholder', 'image', 'image_seq', 'digits', 'text', 'bitmap_text'),
                    'common_fields': {'id': 'unique string', 'type': 'element type', 'x': 'integer px', 'y': 'integer px', 'visible_when': 'state predicate?'},
                    'image': {'asset': 'project-relative path', 'resize_policy': 'native_only by default'},
                    'bitmap_text': {'text': 'string', 'font_pack': 'project-relative FontPack', 'x': 'int', 'y': 'int'},
                })
            if method in {'state.get_schema', 'state.list'}:
                schema = schema_from_scene(self.scene)
                return self._result(states=deepcopy(schema['variables']), relations=deepcopy(schema['relations']), schema=schema)
            if method == 'state.validate_schema':
                checked = validate_state_schema(params.get('schema'))
                return self._result(**checked)

            # ---- Project orchestration ----
            if method == 'project.get':
                return self._result(
                    project_root=str(self.project_root),
                    project_path=str(self.project.path) if self.project else None,
                    project_name=self.project.name if self.project else None,
                    active_screen=self.project.active_screen if self.project else None,
                    scene_path=str(self.source_path) if self.source_path else None,
                    canvas=deepcopy(self.scene.get('canvas', {})),
                    dirty=self._is_scene_dirty(),
                )
            if method == 'project.list_screens':
                if self.project is not None:
                    return self._result(screens=[{'id': s.id, 'label': s.label, 'path': s.path, 'active': s.id == self.project.active_screen} for s in self.project.screens])
                screens = []
                for manifest in sorted(self.project_root.glob('*.project.oled.json')):
                    try:
                        raw = json.loads(manifest.read_text(encoding='utf-8'))
                        for item in raw.get('screens', []):
                            screens.append({'project': manifest.name, 'id': str(item.get('id', '')), 'label': str(item.get('label', '')), 'path': str(item.get('path', ''))})
                    except Exception:
                        continue
                return self._result(screens=screens)
            if method == 'project.list_assets':
                assets = []
                for ext in ('*.png', '*.bmp', '*.jpg', '*.jpeg'):
                    for path in self.project_root.rglob(ext):
                        if any(part in {'.git', '__pycache__', '.pytest_cache', '.venv', '.venv-build', 'build', 'dist', 'release'} for part in path.parts):
                            continue
                        try:
                            assets.append(path.relative_to(self.project_root).as_posix())
                        except ValueError:
                            continue
                return self._result(assets=sorted(set(assets)))
            if method == 'project.open_screen':
                target = str(params['screen_id'])
                self._handle_unsaved_policy(params, target_screen=target)
                return self._open_project_screen(target)
            if method == 'project.create_screen':
                project = self._require_project()
                wants_open = bool(params.get('open', False))
                if wants_open:
                    self._handle_unsaved_policy(params, target_screen=str(params['screen_id']))
                ref = project.add_screen(str(params['screen_id']), label=params.get('label'), canvas=(int(self.scene['canvas']['w']), int(self.scene['canvas']['h'])))
                if wants_open:
                    return self._open_project_screen(ref.id, event='project.create_screen')
                self.revision += 1
                self._notify('project.create_screen', screen_id=ref.id)
                return self._result(screen_id=ref.id, label=ref.label, path=ref.path, active_screen=project.active_screen, project_structure_changed=True)
            if method == 'project.duplicate_screen':
                project = self._require_project()
                wants_open = bool(params.get('open', False))
                if wants_open:
                    self._handle_unsaved_policy(params, target_screen=str(params['new_id']))
                ref = project.duplicate_screen(str(params['screen_id']), new_id=str(params['new_id']), label=params.get('label'))
                if wants_open:
                    return self._open_project_screen(ref.id, event='project.duplicate_screen')
                self.revision += 1
                self._notify('project.duplicate_screen', screen_id=ref.id)
                return self._result(screen_id=ref.id, label=ref.label, path=ref.path, active_screen=project.active_screen, project_structure_changed=True)
            if method == 'project.rename_screen':
                project = self._require_project()
                old = str(params['screen_id'])
                was_active = project.active_screen == old
                ref = project.rename_screen(old, new_id=str(params['new_id']), label=params.get('label'))
                if was_active:
                    self.source_path = project.screen_path(ref.id)
                    self.scene['_path'] = str(self.source_path)
                    self.scene['_project_path'] = str(project.path)
                self.revision += 1
                self._notify('project.rename_screen', screen_id=ref.id)
                return self._result(screen_id=ref.id, label=ref.label, path=ref.path, active_screen=project.active_screen, project_structure_changed=True)
            if method == 'project.delete_screen':
                project = self._require_project()
                sid = str(params['screen_id'])
                was_active = project.active_screen == sid
                if was_active:
                    self._handle_unsaved_policy(params, target_screen='<delete-current>')
                project.remove_screen(sid)
                if was_active:
                    result = self._open_project_screen(project.active_screen, event='project.delete_screen')
                    result['deleted_screen'] = sid
                    return result
                self.revision += 1
                self._notify('project.delete_screen', screen_id=sid)
                return self._result(deleted_screen=sid, active_screen=project.active_screen, project_structure_changed=True)
            if method == 'project.save':
                target = self._save_current_scene()
                if self.project is not None:
                    self.project.save()
                self._notify('project.saved')
                return self._result(saved=True, path=str(target))
            if method == 'project.save_all':
                target = self._save_current_scene()
                saved_pixels = []
                for did, doc in list(self.pixel_documents.items()):
                    path = self.pixel_paths.get(did)
                    if path is not None and doc.dirty:
                        doc.save_png(path)
                        saved_pixels.append(path.relative_to(self.project_root).as_posix())
                if self.project is not None:
                    self.project.save()
                self._notify('project.saved_all')
                return self._result(saved=True, path=str(target), pixel_documents=saved_pixels)

            # ---- Scene / selection / layout ----
            if method == 'scene.get':
                return self._result(scene=deepcopy(self.scene))
            if method == 'scene.list_elements':
                return self._result(elements=deepcopy(self.scene.get('elements', [])))
            if method == 'scene.update_element':
                self._element(params['id']).update(deepcopy(params.get('changes', {})))
                self._changed(method, transaction, external_before)
                return self._result(changed_elements=[str(params['id'])])
            if method == 'scene.create_element':
                element = deepcopy(params['element'])
                eid = str(element.get('id', ''))
                if not eid or any(str(e.get('id')) == eid for e in self.scene.get('elements', [])):
                    raise ValueError('empty or duplicate element id')
                # Agents should not need to guess native bitmap geometry.  The scene
                # validator requires integer W/H, so derive them from the Studio asset
                # loader when an image element omits explicit dimensions.
                if element.get('type') == 'image' and ('w' not in element or 'h' not in element):
                    asset_path = resolve_under_root(self.project_root, str(element['asset']), label='image asset')
                    asset = load_bitmap(asset_path)
                    element.setdefault('w', int(asset.width))
                    element.setdefault('h', int(asset.height))
                self.scene.setdefault('elements', []).append(element)
                self._changed(method, transaction, external_before)
                return self._result(changed_elements=[eid])
            if method == 'scene.delete_elements':
                ids = {str(v) for v in params.get('ids', ())}
                before = len(self.scene.get('elements', []))
                self.scene['elements'] = [e for e in self.scene.get('elements', []) if str(e.get('id')) not in ids]
                if len(self.scene['elements']) != before:
                    self.selection.replace([e for e in self.selection.ids if e not in ids])
                    self._changed(method, transaction, external_before)
                return self._result(changed_elements=sorted(ids))
            if method == 'selection.get':
                return self._result(ids=self.selection.ids, primary_id=self.selection.primary_id)
            if method == 'selection.set':
                self.selection.replace(params.get('ids', ()), primary=params.get('primary_id'))
                self._changed(method, transaction, external_before)
                return self._result(ids=self.selection.ids, primary_id=self.selection.primary_id)
            if method == 'selection.toggle':
                self.selection.toggle(params['id'])
                self._changed(method, transaction, external_before)
                return self._result(ids=self.selection.ids, primary_id=self.selection.primary_id)
            if method == 'selection.clear':
                self.selection.clear()
                self._changed(method, transaction, external_before)
                return self._result(ids=(), primary_id=None)
            if method == 'layout.align':
                ids = list(params.get('ids') or self.selection.ids)
                session = EditorSession(self.scene)
                align_to(session, ids, str(params['mode']), reference=str(params.get('reference', 'selection')), primary_id=str(params.get('primary_id') or self.selection.primary_id or '') or None, canvas=(int(self.scene['canvas']['w']), int(self.scene['canvas']['h'])))
                self._changed(method, transaction, external_before)
                return self._result(changed_elements=ids)
            if method == 'layout.distribute':
                ids = list(params.get('ids') or self.selection.ids)
                session = EditorSession(self.scene)
                distribute(session, ids, str(params['axis']))
                self._changed(method, transaction, external_before)
                return self._result(changed_elements=ids)
            if method == 'layout.measure':
                ids = list(params.get('ids') or self.selection.ids)
                session = EditorSession(self.scene)
                if len(ids) == 2:
                    m = measure(session, *ids)
                    return self._result(measurement={'dx': m.dx, 'dy': m.dy, 'horizontal_gap': m.horizontal_gap, 'vertical_gap': m.vertical_gap, 'center_dx': m.center_dx, 'center_dy': m.center_dy})
                m = selection_metrics(session, ids)
                return self._result(measurement={'bounds': m.bounds, 'horizontal_gaps': m.horizontal_gaps, 'vertical_gaps': m.vertical_gaps, 'equal_horizontal_spacing': m.equal_horizontal_spacing, 'equal_vertical_spacing': m.equal_vertical_spacing})

            # ---- State / render / validation ----
            if method == 'state.set_schema':
                checked = validate_state_schema(params.get('schema'))
                if not checked['valid']:
                    raise ValueError('invalid state schema: ' + json.dumps(checked['errors'], ensure_ascii=False, sort_keys=True))
                before_scene = deepcopy(self.scene)
                normalized = checked['schema']
                changed = schema_from_scene(self.scene) != normalized
                if changed:
                    apply_state_schema(self.scene, normalized)
                    if self.editor_session is not None:
                        self.editor_session.runtime.reset()
                        self.editor_session.document.dirty = True
                    if transaction is None:
                        if self.editor_session is not None:
                            self.editor_session.record_external_scene(before_scene, label='agent_state_set_schema')
                        self.revision += 1
                        self._notify(method)
                return self._result(schema=schema_from_scene(self.scene), changed=changed)
            if method == 'state.validate':
                schema = schema_from_scene(self.scene)
                violations = validate_state(schema, params.get('state'))
                return self._result(valid=not violations, violations=violations)
            if method == 'state.enumerate':
                matrix = self._state_matrix(params)
                include_states = bool(params.get('include_states', not bool(params.get('summary_only', False))))
                payload = {
                    'cases': len(matrix),
                    'integer_policy': str(params.get('integer_policy', 'representative')),
                    'warning': 'LARGE_STATE_MATRIX' if len(matrix) > 10000 else None,
                }
                if include_states:
                    payload['states'] = matrix
                return self._result(**payload)
            if method == 'state.count':
                count_params = dict(params)
                count_params.setdefault('max_cases', 100000)
                matrix = self._state_matrix_for_scene(self.scene, count_params, default_limit=100000)
                return self._result(
                    cases=len(matrix),
                    integer_policy=str(params.get('integer_policy', 'representative')),
                    warning='LARGE_STATE_MATRIX' if len(matrix) > 10000 else None,
                )
            if method in {'render.current', 'render.framebuffer', 'render.resolved_elements', 'render.png'}:
                state, result, raw = self._render(params.get('state'))
                frame = {'width': result.framebuffer.width, 'height': result.framebuffer.height, 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest(), 'vlsb_hex': raw.hex()}
                if method == 'render.framebuffer':
                    return self._result(framebuffer=frame, state=state)
                if method == 'render.resolved_elements':
                    return self._result(resolved_elements=deepcopy(result.resolved_elements), state=state)
                if method == 'render.png':
                    png = self._framebuffer_png_bytes(result.framebuffer)
                    return self._result(png_base64=base64.b64encode(png).decode('ascii'), png_sha256=hashlib.sha256(png).hexdigest(), width=result.framebuffer.width, height=result.framebuffer.height, state=state)
                return self._result(framebuffer=frame, resolved_elements=deepcopy(result.resolved_elements), state=state)
            if method == 'render.preview_file':
                state, result, _ = self._render(params.get('state'))
                target = resolve_under_root(self.project_root, params.get('path', '.oled/agent/preview/current.png'), label='preview file')
                if target.suffix.lower() != '.png':
                    raise ValueError('preview file must end in .png')
                raw = self._framebuffer_png_bytes(result.framebuffer)
                atomic_write_bytes(target, raw)
                return self._result(path=str(target), sha256=hashlib.sha256(raw).hexdigest(), state=state)
            if method == 'render.annotated_preview':
                state, result, _ = self._render(params.get('state'))
                target = resolve_under_root(self.project_root, params.get('path', '.oled/agent/preview/annotated.png'), label='annotated preview')
                if target.suffix.lower() != '.png':
                    raise ValueError('annotated preview must end in .png')
                raw = self._annotated_preview_bytes(result, scale=int(params.get('scale', 6)))
                atomic_write_bytes(target, raw)
                return self._result(path=str(target), sha256=hashlib.sha256(raw).hexdigest(), state=state, resolved_elements=deepcopy(result.resolved_elements))
            if method == 'render.pixel_diff':
                before_state, before, _ = self._render(params.get('before_state'))
                after_state, after, _ = self._render(params.get('after_state'))
                diff = diff_framebuffers(before.framebuffer, after.framebuffer)
                return self._result(before_state=before_state, after_state=after_state, changed_pixels=diff.changed_pixels, percent=diff.percent, bbox=diff.bbox)
            if method == 'render.all_states':
                return self._result(**self._render_all_states_payload(self.scene, params))
            if method == 'validate.current':
                state = dict(params.get('state') or init_state(self.scene))
                findings = validate_scene(self.scene, state)
                rows = [{'severity': f.severity, 'code': f.code, 'message': f.message, 'element_id': f.element_id} for f in findings]
                return self._result(findings=rows, blockers=sum(1 for f in findings if f.severity in {'BLOCKER', 'ERROR'}), valid=not has_blockers(findings))
            if method == 'validate.all_states':
                return self._result(**self._validate_all_states_payload(self.scene, params))

            # ---- Asset / pixel lifecycle ----
            if method == 'asset.create':
                path = self._asset_path(params['path'], label='asset create')
                doc = PixelDocument(int(params['width']), int(params['height']))
                if int(params.get('value', 0)):
                    doc.clear(1)
                doc.save_png(path)
                self.revision += 1
                self._notify(method, path=path.relative_to(self.project_root).as_posix())
                return self._result(**self._file_result(path, self.project_root))
            if method == 'asset.import':
                source = Path(str(params['source'])).expanduser().resolve()
                if not source.exists() or not source.is_file():
                    raise FileNotFoundError(source)
                target = self._asset_path(params['target'], label='asset import target')
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
                PixelDocument.from_image(target)  # fail closed on unsupported/corrupt image
                self.revision += 1
                self._notify(method, path=target.relative_to(self.project_root).as_posix())
                return self._result(**self._file_result(target, self.project_root))
            if method == 'asset.copy':
                source = self._asset_path(params['path'], label='asset source')
                target = self._asset_path(params['target'], label='asset target')
                if not source.exists():
                    raise FileNotFoundError(source)
                if target.exists():
                    raise FileExistsError(target)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
                self.revision += 1
                self._notify(method, path=target.relative_to(self.project_root).as_posix())
                return self._result(**self._file_result(target, self.project_root))
            if method == 'asset.rename':
                source = self._asset_path(params['path'], label='asset source')
                target = self._asset_path(params['target'], label='asset target')
                if not source.exists():
                    raise FileNotFoundError(source)
                if target.exists():
                    raise FileExistsError(target)
                target.parent.mkdir(parents=True, exist_ok=True)
                os.replace(source, target)
                for did, path in list(self.pixel_paths.items()):
                    if path == source:
                        self.pixel_paths[did] = target
                self.revision += 1
                self._notify(method, path=target.relative_to(self.project_root).as_posix())
                return self._result(**self._file_result(target, self.project_root))
            if method == 'asset.delete':
                path = self._asset_path(params['path'], label='asset delete')
                if not path.exists():
                    raise FileNotFoundError(path)
                path.unlink()
                for did, open_path in list(self.pixel_paths.items()):
                    if open_path == path:
                        self.pixel_paths.pop(did, None)
                        self.pixel_documents.pop(did, None)
                self.revision += 1
                self._notify(method, path=path.relative_to(self.project_root).as_posix())
                return self._result(deleted=True, path=path.relative_to(self.project_root).as_posix())
            if method == 'pixel.create':
                path = self._asset_path(params['path'], label='pixel asset')
                if path.exists() and not bool(params.get('overwrite', False)):
                    raise FileExistsError(path)
                doc = PixelDocument(int(params['width']), int(params['height']))
                did = 'pixel:' + path.relative_to(self.project_root).as_posix()
                self.pixel_documents[did] = doc
                self.pixel_paths[did] = path
                return self._pixel_result(did, doc)
            if method == 'pixel.open':
                path = self._asset_path(params['path'], label='pixel asset')
                doc = PixelDocument.from_image(path)
                did = 'pixel:' + path.relative_to(self.project_root).as_posix()
                self.pixel_documents[did] = doc
                self.pixel_paths[did] = path
                return self._pixel_result(did, doc)
            if method == 'pixel.get_document':
                did = str(params['document_id'])
                return self._pixel_result(did, self._pixel_doc(did))
            if method == 'pixel.paint':
                did = str(params['document_id']); doc = self._pixel_doc(did); doc.brush(int(params['x']), int(params['y']), int(params.get('value', 1)), size=int(params.get('size', 1))); self._changed(method, transaction); return self._pixel_result(did, doc)
            if method == 'pixel.erase':
                did = str(params['document_id']); doc = self._pixel_doc(did); doc.brush(int(params['x']), int(params['y']), 0, size=int(params.get('size', 1))); self._changed(method, transaction); return self._pixel_result(did, doc)
            if method == 'pixel.line':
                did = str(params['document_id']); doc = self._pixel_doc(did); doc.line(int(params['x0']), int(params['y0']), int(params['x1']), int(params['y1']), value=int(params.get('value', 1))); self._changed(method, transaction); return self._pixel_result(did, doc)
            if method == 'pixel.rect':
                did = str(params['document_id']); doc = self._pixel_doc(did); doc.rectangle(int(params['x0']), int(params['y0']), int(params['x1']), int(params['y1']), filled=bool(params.get('filled', False)), value=int(params.get('value', 1))); self._changed(method, transaction); return self._pixel_result(did, doc)
            if method == 'pixel.fill':
                did = str(params['document_id']); doc = self._pixel_doc(did); doc.flood_fill(int(params['x']), int(params['y']), int(params.get('value', 1))); self._changed(method, transaction); return self._pixel_result(did, doc)
            if method == 'pixel.resize_canvas':
                did = str(params['document_id']); doc = self._pixel_doc(did); doc.resize_canvas(int(params['width']), int(params['height']), anchor=str(params.get('anchor', 'center'))); self._changed(method, transaction); return self._pixel_result(did, doc)
            if method == 'pixel.rotate':
                did = str(params['document_id']); doc = self._pixel_doc(did); angle = int(params.get('angle', 90)) % 360
                if angle == 90: doc.rotate90()
                elif angle == 180: doc.rotate180()
                elif angle == 270: doc.rotate270()
                elif angle != 0: raise ValueError('pixel rotation supports 0/90/180/270 only')
                self._changed(method, transaction); return self._pixel_result(did, doc)
            if method == 'pixel.flip':
                did = str(params['document_id']); doc = self._pixel_doc(did); axis = str(params.get('axis', 'horizontal'))
                if axis == 'horizontal': doc.flip_horizontal()
                elif axis == 'vertical': doc.flip_vertical()
                else: raise ValueError('axis must be horizontal/vertical')
                self._changed(method, transaction); return self._pixel_result(did, doc)
            if method == 'pixel.undo':
                did = str(params['document_id']); doc = self._pixel_doc(did); changed = doc.undo(); self._changed(method, transaction) if changed else None; return self._pixel_result(did, doc)
            if method == 'pixel.redo':
                did = str(params['document_id']); doc = self._pixel_doc(did); changed = doc.redo(); self._changed(method, transaction) if changed else None; return self._pixel_result(did, doc)
            if method == 'pixel.save':
                did = str(params['document_id']); doc = self._pixel_doc(did)
                target_param = params.get('path')
                if target_param is None:
                    if did not in self.pixel_paths:
                        raise ValueError('pixel document has no target path')
                    target = self.pixel_paths[did]
                else:
                    target = self._asset_path(target_param, label='pixel save')
                doc.save_png(target); self.pixel_paths[did] = target; self._changed(method, transaction); return self._pixel_result(did, doc)

            # ---- Font lifecycle ----
            if method == 'font.list':
                fonts = []
                for manifest in sorted(self.project_root.rglob('fontpack.json')):
                    try:
                        rel = manifest.parent.relative_to(self.project_root).as_posix(); pack = FontPack.load(manifest.parent); fonts.append({'font_id': rel, 'name': pack.name, 'cell': pack.cell, 'glyph_count': len(pack.characters())})
                    except Exception:
                        continue
                return self._result(fonts=fonts)
            if method == 'font.create_pack':
                root = resolve_under_root(self.project_root, params['path'], label='font pack'); cell = tuple(map(int, params.get('cell', (5, 8)))); pack = create_font_pack(root, str(params.get('name', root.name)), cell=cell, baseline=int(params.get('baseline', cell[1] - 1)), advance=int(params.get('advance', cell[0] + 1))); pack.save(); self._changed(method, transaction); return self._result(font_id=root.relative_to(self.project_root).as_posix(), name=pack.name, cell=pack.cell)
            if method == 'font.get_pack':
                root = self._font_root(params['font_id']); pack = FontPack.load(root); return self._result(font_id=root.relative_to(self.project_root).as_posix(), name=pack.name, cell=pack.cell, baseline=pack.baseline, advance=pack.advance, characters=pack.characters())
            if method == 'font.generate_glyphs':
                root = self._font_root(params['font_id']); pack = FontPack.load(root); count = rasterize_characters(pack, str(params.get('characters', '')), font_path=params.get('font_path'), font_size=int(params.get('font_size', 12)), threshold=int(params.get('threshold', 128)), offset=tuple(params.get('offset', (0, 0)))); self._changed(method, transaction); return self._result(font_id=root.relative_to(self.project_root).as_posix(), count=count)
            if method == 'font.get_glyph':
                root = self._font_root(params['font_id']); pack = FontPack.load(root); ch = str(params['char']); g = pack.glyph(ch); return self._result(font_id=root.relative_to(self.project_root).as_posix(), char=ch, pixels=deepcopy(g.pixels), metrics={'bearing_x': g.metrics.bearing_x, 'bearing_y': g.metrics.bearing_y, 'advance': g.metrics.advance})
            if method == 'font.update_glyph':
                root = self._font_root(params['font_id']); pack = FontPack.load(root); ch = str(params['char']); m = params.get('metrics', {}); pack.set_glyph(ch, params['pixels'], GlyphMetrics(int(m.get('bearing_x', 0)), int(m.get('bearing_y', 0)), int(m.get('advance', pack.advance)))); pack.save(); self._changed(method, transaction); return self._result(font_id=root.relative_to(self.project_root).as_posix(), char=ch)
            if method == 'font.set_metrics':
                root = self._font_root(params['font_id']); pack = FontPack.load(root); pack.baseline = int(params.get('baseline', pack.baseline)); pack.advance = int(params.get('advance', pack.advance)); pack.save(); self._changed(method, transaction); return self._result(font_id=root.relative_to(self.project_root).as_posix(), baseline=pack.baseline, advance=pack.advance)

            # ---- Studio-owned exports ----
            if method == 'export.current':
                output = resolve_under_root(self.project_root, params.get('output_dir', 'exports/agent_current'), label='export directory')
                state = dict(params.get('state') or init_state(self.scene))
                summary = export_scene(self.scene, output, {'current': state})
                return self._result(output_dir=str(output), frame_count=summary.frame_count, frame_hashes=summary.frame_hashes)
            if method == 'export.all':
                return self._result(**self._export_all_payload(self.scene, self.project_root, params))
            if method == 'export.c_header':
                target = resolve_under_root(self.project_root, params.get('path', 'exports/current.h'), label='C header')
                _, result, _ = self._render(params.get('state'))
                write_c_header(result.framebuffer, target, name=str(params.get('symbol', 'oled_frame')))
                return self._result(path=str(target), sha256=hashlib.sha256(target.read_bytes()).hexdigest())
            if method == 'export.font_pack':
                root = self._font_root(params['font_id'])
                FontPack.load(root)  # validate before packaging
                target = resolve_under_root(self.project_root, params.get('path', f'exports/{root.name}.fontpack.zip'), label='font export')
                if target.suffix.lower() != '.zip':
                    raise ValueError('font export must end in .zip')
                self._deterministic_zip(root, target)
                return self._result(path=str(target), sha256=hashlib.sha256(target.read_bytes()).hexdigest())
            if method == 'export.code_ai_handoff':
                return self._result(**self._handoff_payload(self.scene, self.project_root, params))

            # ---- Long-running server-owned jobs ----
            if method == 'job.start':
                operation = str(params['operation'])
                allowed = {'render.all_states', 'validate.all_states', 'export.all', 'export.code_ai_handoff'}
                if operation not in allowed:
                    raise ValueError(f'unsupported long-running operation: {operation}')
                if self.permission == 'observe' and operation.startswith('export.'):
                    raise PermissionDeniedError(operation)
                arguments = dict(params.get('arguments') or {})
                snapshot = {
                    'scene': deepcopy(self.scene),
                    'project_root': str(self.project_root),
                    'revision': self.revision,
                }
                jid = self._jobs.start(operation, arguments, snapshot, self._run_long_job)
                return self._result(job_id=jid, operation=operation, state='queued')
            if method == 'job.status':
                return self._result(**self._jobs.status(str(params['job_id'])))
            if method == 'job.result':
                return self._result(**self._jobs.result(str(params['job_id'])))
            if method == 'job.cancel':
                return self._result(**self._jobs.cancel(str(params['job_id'])))

            if method == 'session.events':
                return self._result(events=deepcopy(self.events[int(params.get('since', 0)):]))
            raise KeyError(method)
