from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import hashlib
import io
import json
from pathlib import Path
from threading import RLock
import time
import zipfile

from PIL import Image, ImageDraw

from atomic_io import atomic_write_json
from automation_dispatch import DISPATCHERS, UNHANDLED
from automation_jobs import AutomationJobCancelled, AutomationJobManager
from exporter import export_scene
from handoff import build_handoff_package
from export_matrix import build_export_states, case_name
from pixel_studio import PixelDocument
from project_workspace import ProjectWorkspace, resolve_under_root
from render import render_scene
from scene import init_state, load_scene
from selection_model import SelectionModel
from validate import validate_scene


AUTOMATION_API_VERSION = '1.3.0'


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
    'automation.capabilities': _method('observe', 'List Automation API 1.3 methods and contracts.'),
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
    'pixel.close': _method('edit', 'Close an in-memory PixelDocument; dirty documents require discard=true.', {'document_id': _param('string', required=True), 'discard': _param('bool', required=False)}),
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
            'alignment': _param('font_set|glyph_width', required=False, default='glyph_width'),
            'antialias_scale': _param('1|2|4', required=False, default=1),
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
    'output.list_profiles': _method('observe', 'List project output profiles and the active profile.'),
    'output.get_profile': _method('observe', 'Read one project output profile.', {'profile_id': 'string'}),
    'output.upsert_profile': _method('edit', 'Create or replace one project output profile.', {'profile_id': 'string', 'profile': 'object', 'activate': 'bool?'}),
    'output.delete_profile': _method('edit', 'Delete one project output profile.', {'profile_id': 'string'}),
    'output.set_active_profile': _method('edit', 'Select the active project output profile.', {'profile_id': 'string'}),
    'output.preview': _method('observe', 'Encode and format a source without writing files.', {'source': 'object', 'profile_id': 'string?', 'profile': 'object?', 'symbol': 'string?'}),
    'export.current': _method('edit', 'Export current state through the canonical Studio exporter.', {'output_dir': 'relative dir', 'state': 'object?'}),
    'export.all': _method('edit', 'Export deterministic state matrix through the canonical Studio exporter.', {'output_dir': 'relative dir', 'integer_policy': 'representative|boundaries|full', 'summary_only': 'bool?', 'include_hashes': 'bool?', 'max_cases': 'int?', 'allow_large_matrix': 'bool?'}),
    'export.c_header': _method('edit', 'Export current framebuffer C header.', {'path': 'relative path', 'symbol': 'string?'}),
    'export.bitmap_data': _method('edit', 'Encode a scene or PixelDocument through an output profile.', {'source': 'object', 'profile_id': 'string?', 'profile': 'object?', 'path': 'relative path', 'symbol': 'string?'}),
    'export.font_data': _method('edit', 'Encode FontPack glyphs and optional index through an output profile.', {'font_id': 'relative dir', 'characters': 'string?', 'profile_id': 'string?', 'profile': 'object?', 'path': 'relative path', 'symbol': 'string?'}),
    'export.font_pack': _method('edit', 'Create deterministic ZIP of a FontPack.', {'font_id': 'relative dir', 'path': 'relative zip path'}),
    'export.code_ai_handoff': _method('edit', 'Generate deterministic Code AI handoff from Studio truth.', {'path': 'relative zip path', 'integer_policy': 'representative|boundaries|full', 'summary_only': 'bool?', 'max_cases': 'int?', 'allow_large_matrix': 'bool?'}),
    'history.begin_transaction': _method('edit', 'Begin one undoable Agent scene transaction.'),
    'history.commit': _method('edit', 'Commit Agent transaction as one Designer undo.', {'transaction': _param('string', required=True)}),
    'history.rollback': _method('edit', 'Rollback Agent transaction.', {'transaction': _param('string', required=True)}),
    'job.start': _method('edit', 'Start one server-owned long-running Automation operation.', {'operation': _param('string', required=True), 'arguments': _param('object', required=False)}),
    'job.status': _method('observe', 'Read long-running Automation job progress.', {'job_id': _param('string', required=True)}),
    'job.result': _method('observe', 'Read terminal long-running Automation job result.', {'job_id': _param('string', required=True)}),
    'job.cancel': _method('edit', 'Request cooperative cancellation of a long-running Automation job.', {'job_id': _param('string', required=True)}),
    'job.release': _method('edit', 'Release one terminal Automation job result from server memory.', {'job_id': _param('string', required=True)}),
    'session.events': _method('observe', 'Read bounded semantic Agent event stream using an absolute cursor.', {'since': 'int?'}),
}


class StudioAutomationService:
    """Semantic automation surface shared by Code AI, tests and transport adapters.

    The API intentionally manipulates project/scene/pixel/font concepts rather than
    GUI coordinates.  Automation API 1.1 keeps the project orchestration of 1.0 and adds
    atomic product-state authoring, relational legal-state proof and Studio-owned export so an Agent can complete a
    multi-screen OLED project without inventing a second source of truth.
    """

    api_version = AUTOMATION_API_VERSION
    method_specs = METHOD_SPECS
    permission_denied_error = PermissionDeniedError
    unsaved_changes_error = UnsavedChangesError
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
        max_transactions: int = 16,
        event_limit: int = 4096,
        job_active_limit: int = 4,
        job_terminal_limit: int = 16,
        pixel_document_limit: int = 64,
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
        self._max_transactions = max(1, int(max_transactions))
        self.events = []
        self._event_limit = max(1, int(event_limit))
        self._event_base = 0
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
        self._pixel_document_limit = max(1, int(pixel_document_limit))
        self._pixel_seq = 0
        self._jobs = AutomationJobManager(max_active_jobs=job_active_limit, max_terminal_jobs=job_terminal_limit)
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
        overflow = len(self.events) - self._event_limit
        if overflow > 0:
            del self.events[:overflow]
            self._event_base += overflow
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
            if len(self._tx) >= self._max_transactions:
                raise TransactionError(f'active transaction limit reached: {self._max_transactions}')
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

    def _register_pixel_doc(self, document_id: str, doc: PixelDocument, path: Path) -> None:
        did = str(document_id)
        if did not in self.pixel_documents and len(self.pixel_documents) >= self._pixel_document_limit:
            raise ValueError(f'pixel document limit reached: {self._pixel_document_limit}')
        self.pixel_documents[did] = doc
        self.pixel_paths[did] = path

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
        return case_name(index, state)

    def _state_matrix_for_scene(self, scene: dict, params: dict, *, default_limit: int = 5000) -> list[dict]:
        policy = str(params.get('integer_policy', 'representative'))
        states = build_export_states(
            scene,
            integer_policy=policy,
            max_cases=int(params.get('max_cases', default_limit)),
            allow_large_matrix=bool(params.get('allow_large_matrix', False)),
        )
        return list(states.values())

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
            integer_policy=str(params.get('integer_policy', 'representative')),
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
            for dispatcher in DISPATCHERS:
                result = dispatcher(self, method, params, transaction, external_before)
                if result is not UNHANDLED:
                    return result
            raise KeyError(method)
