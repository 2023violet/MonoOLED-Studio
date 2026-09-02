"""Fixed-domain command handlers for the Studio automation API."""

from __future__ import annotations

import base64
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import shutil

from atomic_io import atomic_write_bytes
from assets import load_bitmap
from c_export import write_c_header
from editor_model import EditorSession
from exporter import export_scene
from font_pack import FontPack, GlyphMetrics, create_font_pack, rasterize_characters
from pixel_diff import diff_framebuffers
from pixel_studio import PixelDocument
from project_workspace import resolve_under_root
from scene import init_state
from state_schema import apply_state_schema, schema_from_scene, validate_state, validate_state_schema
from selection_tools import align_to, distribute, measure, selection_metrics
from validate import has_blockers, validate_scene


UNHANDLED = object()

API_AND_PROJECT = frozenset({
    'automation.capabilities', 'automation.describe_method', 'project.get_contract',
    'scene.get_schema', 'state.get_schema', 'state.list', 'state.validate_schema',
    'project.get', 'project.list_screens', 'project.list_assets',
    'project.open_screen', 'project.create_screen', 'project.duplicate_screen',
    'project.rename_screen', 'project.delete_screen', 'project.save', 'project.save_all',
})
SCENE_SELECTION_LAYOUT_STATE = frozenset({
    'scene.get', 'scene.list_elements', 'scene.update_element', 'scene.create_element',
    'scene.delete_elements', 'selection.get', 'selection.set', 'selection.toggle',
    'selection.clear', 'layout.align', 'layout.distribute', 'layout.measure',
    'state.set_schema', 'state.validate', 'state.enumerate', 'state.count',
})
RENDER_VALIDATE_PREVIEW = frozenset({
    'render.current', 'render.framebuffer', 'render.resolved_elements', 'render.png',
    'render.preview_file', 'render.annotated_preview', 'render.pixel_diff',
    'render.all_states', 'validate.current', 'validate.all_states',
})
RESOURCE_PIXEL_FONT_EXPORT = frozenset({
    'asset.create', 'asset.import', 'asset.copy', 'asset.rename', 'asset.delete',
    'pixel.create', 'pixel.open', 'pixel.get_document', 'pixel.paint', 'pixel.erase',
    'pixel.line', 'pixel.rect', 'pixel.fill', 'pixel.resize_canvas', 'pixel.rotate',
    'pixel.flip', 'pixel.undo', 'pixel.redo', 'pixel.save', 'pixel.close',
    'font.list', 'font.create_pack', 'font.get_pack', 'font.generate_glyphs',
    'font.get_glyph', 'font.update_glyph', 'font.set_metrics', 'export.current',
    'export.all', 'export.c_header', 'export.font_pack', 'export.code_ai_handoff',
})
JOBS_EVENTS_DIAGNOSTICS = frozenset({
    'job.start', 'job.status', 'job.result', 'job.cancel', 'job.release', 'session.events',
})


def dispatch_api_and_project(service, method, params, transaction, external_before):
    if method not in API_AND_PROJECT:
        return UNHANDLED
    if method == 'automation.capabilities':
        methods = [{'method': name, **deepcopy(spec)} for name, spec in sorted(service.method_specs.items())]
        return service._result(api_version=service.api_version, transport='JSON-RPC 2.0 / localhost', permissions=('observe', 'edit', 'full'), methods=methods)
    if method == 'automation.describe_method':
        name = str(params['method'])
        if name not in service.method_specs:
            raise KeyError(name)
        return service._result(api_version=service.api_version, method={'method': name, **deepcopy(service.method_specs[name])})
    if method == 'project.get_contract':
        width = int(service.scene['canvas']['w']); height = int(service.scene['canvas']['h'])
        return service._result(automation_api=service.api_version, project_schema_version=int(service.project.data.get('schema_version', 1)) if service.project else None, scene_schema_version=int(service.scene.get('schema_version', 1)), coordinate_contract={'origin': 'top-left', 'x_direction': 'right', 'y_direction': 'down', 'bounds': '[x,x+w) x [y,y+h)', 'integer_pixels': True}, framebuffer_contract={'width': width, 'height': height, 'bytes': width * ((height + 7) // 8), 'layout': 'VLSB page-major', 'byte_offset': '(y // 8) * width + x', 'bit': '1 << (y % 8)', 'polarity': '1 = OLED lit'}, product_truth={'renderer': 'render.py/render_scene', 'scene': str(service.source_path) if service.source_path else None})
    if method == 'scene.get_schema':
        return service._result(schema={'schema_version': int(service.scene.get('schema_version', 1)), 'element_types': ('placeholder', 'image', 'image_seq', 'digits', 'text', 'bitmap_text'), 'common_fields': {'id': 'unique string', 'type': 'element type', 'x': 'integer px', 'y': 'integer px', 'visible_when': 'state predicate?'}, 'image': {'asset': 'project-relative path', 'resize_policy': 'native_only by default'}, 'bitmap_text': {'text': 'string', 'font_pack': 'project-relative FontPack', 'x': 'int', 'y': 'int'}})
    if method in {'state.get_schema', 'state.list'}:
        schema = schema_from_scene(service.scene)
        return service._result(states=deepcopy(schema['variables']), relations=deepcopy(schema['relations']), schema=schema)
    if method == 'state.validate_schema':
        return service._result(**validate_state_schema(params.get('schema')))
    if method == 'project.get':
        return service._result(project_root=str(service.project_root), project_path=str(service.project.path) if service.project else None, project_name=service.project.name if service.project else None, active_screen=service.project.active_screen if service.project else None, scene_path=str(service.source_path) if service.source_path else None, canvas=deepcopy(service.scene.get('canvas', {})), dirty=service._is_scene_dirty())
    if method == 'project.list_screens':
        if service.project is not None:
            return service._result(screens=[{'id': screen.id, 'label': screen.label, 'path': screen.path, 'active': screen.id == service.project.active_screen} for screen in service.project.screens])
        screens = []
        for manifest in sorted(service.project_root.glob('*.project.oled.json')):
            try:
                raw = json.loads(manifest.read_text(encoding='utf-8'))
                for item in raw.get('screens', []):
                    screens.append({'project': manifest.name, 'id': str(item.get('id', '')), 'label': str(item.get('label', '')), 'path': str(item.get('path', ''))})
            except Exception:
                continue
        return service._result(screens=screens)
    if method == 'project.list_assets':
        assets = []
        for ext in ('*.png', '*.bmp', '*.jpg', '*.jpeg'):
            for path in service.project_root.rglob(ext):
                if any(part in {'.git', '__pycache__', '.pytest_cache', '.venv', '.venv-build', 'build', 'dist', 'release'} for part in path.parts):
                    continue
                try:
                    assets.append(path.relative_to(service.project_root).as_posix())
                except ValueError:
                    continue
        return service._result(assets=sorted(set(assets)))
    if method == 'project.open_screen':
        target = str(params['screen_id']); service._handle_unsaved_policy(params, target_screen=target)
        return service._open_project_screen(target)
    if method == 'project.create_screen':
        project = service._require_project(); wants_open = bool(params.get('open', False))
        if wants_open: service._handle_unsaved_policy(params, target_screen=str(params['screen_id']))
        ref = project.add_screen(str(params['screen_id']), label=params.get('label'), canvas=(int(service.scene['canvas']['w']), int(service.scene['canvas']['h'])))
        if wants_open: return service._open_project_screen(ref.id, event='project.create_screen')
        service.revision += 1; service._notify('project.create_screen', screen_id=ref.id)
        return service._result(screen_id=ref.id, label=ref.label, path=ref.path, active_screen=project.active_screen, project_structure_changed=True)
    if method == 'project.duplicate_screen':
        project = service._require_project(); wants_open = bool(params.get('open', False))
        if wants_open: service._handle_unsaved_policy(params, target_screen=str(params['new_id']))
        ref = project.duplicate_screen(str(params['screen_id']), new_id=str(params['new_id']), label=params.get('label'))
        if wants_open: return service._open_project_screen(ref.id, event='project.duplicate_screen')
        service.revision += 1; service._notify('project.duplicate_screen', screen_id=ref.id)
        return service._result(screen_id=ref.id, label=ref.label, path=ref.path, active_screen=project.active_screen, project_structure_changed=True)
    if method == 'project.rename_screen':
        project = service._require_project(); old = str(params['screen_id']); was_active = project.active_screen == old
        ref = project.rename_screen(old, new_id=str(params['new_id']), label=params.get('label'))
        if was_active:
            service.source_path = project.screen_path(ref.id); service.scene['_path'] = str(service.source_path); service.scene['_project_path'] = str(project.path)
        service.revision += 1; service._notify('project.rename_screen', screen_id=ref.id)
        return service._result(screen_id=ref.id, label=ref.label, path=ref.path, active_screen=project.active_screen, project_structure_changed=True)
    if method == 'project.delete_screen':
        project = service._require_project(); sid = str(params['screen_id']); was_active = project.active_screen == sid
        if was_active: service._handle_unsaved_policy(params, target_screen='<delete-current>')
        project.remove_screen(sid)
        if was_active:
            result = service._open_project_screen(project.active_screen, event='project.delete_screen'); result['deleted_screen'] = sid
            return result
        service.revision += 1; service._notify('project.delete_screen', screen_id=sid)
        return service._result(deleted_screen=sid, active_screen=project.active_screen, project_structure_changed=True)
    if method == 'project.save':
        target = service._save_current_scene()
        if service.project is not None: service.project.save()
        service._notify('project.saved')
        return service._result(saved=True, path=str(target))
    if method == 'project.save_all':
        target = service._save_current_scene(); saved_pixels = []
        for did, doc in list(service.pixel_documents.items()):
            path = service.pixel_paths.get(did)
            if path is not None and doc.dirty:
                doc.save_png(path); saved_pixels.append(path.relative_to(service.project_root).as_posix())
        if service.project is not None: service.project.save()
        service._notify('project.saved_all')
        return service._result(saved=True, path=str(target), pixel_documents=saved_pixels)
    return UNHANDLED


def dispatch_scene_selection_layout_state(service, method, params, transaction, external_before):
    if method not in SCENE_SELECTION_LAYOUT_STATE:
        return UNHANDLED
    if method == 'scene.get': return service._result(scene=deepcopy(service.scene))
    if method == 'scene.list_elements': return service._result(elements=deepcopy(service.scene.get('elements', [])))
    if method == 'scene.update_element':
        service._element(params['id']).update(deepcopy(params.get('changes', {}))); service._changed(method, transaction, external_before)
        return service._result(changed_elements=[str(params['id'])])
    if method == 'scene.create_element':
        element = deepcopy(params['element']); eid = str(element.get('id', ''))
        if not eid or any(str(item.get('id')) == eid for item in service.scene.get('elements', [])): raise ValueError('empty or duplicate element id')
        if element.get('type') == 'image' and ('w' not in element or 'h' not in element):
            asset = load_bitmap(resolve_under_root(service.project_root, str(element['asset']), label='image asset')); element.setdefault('w', int(asset.width)); element.setdefault('h', int(asset.height))
        service.scene.setdefault('elements', []).append(element); service._changed(method, transaction, external_before)
        return service._result(changed_elements=[eid])
    if method == 'scene.delete_elements':
        ids = {str(value) for value in params.get('ids', ())}; before = len(service.scene.get('elements', []))
        service.scene['elements'] = [element for element in service.scene.get('elements', []) if str(element.get('id')) not in ids]
        if len(service.scene['elements']) != before:
            service.selection.replace([eid for eid in service.selection.ids if eid not in ids]); service._changed(method, transaction, external_before)
        return service._result(changed_elements=sorted(ids))
    if method == 'selection.get': return service._result(ids=service.selection.ids, primary_id=service.selection.primary_id)
    if method == 'selection.set':
        service.selection.replace(params.get('ids', ()), primary=params.get('primary_id')); service._changed(method, transaction, external_before)
        return service._result(ids=service.selection.ids, primary_id=service.selection.primary_id)
    if method == 'selection.toggle':
        service.selection.toggle(params['id']); service._changed(method, transaction, external_before)
        return service._result(ids=service.selection.ids, primary_id=service.selection.primary_id)
    if method == 'selection.clear':
        service.selection.clear(); service._changed(method, transaction, external_before); return service._result(ids=(), primary_id=None)
    if method == 'layout.align':
        ids = list(params.get('ids') or service.selection.ids); session = EditorSession(service.scene)
        align_to(session, ids, str(params['mode']), reference=str(params.get('reference', 'selection')), primary_id=str(params.get('primary_id') or service.selection.primary_id or '') or None, canvas=(int(service.scene['canvas']['w']), int(service.scene['canvas']['h'])))
        service._changed(method, transaction, external_before); return service._result(changed_elements=ids)
    if method == 'layout.distribute':
        ids = list(params.get('ids') or service.selection.ids); distribute(EditorSession(service.scene), ids, str(params['axis']))
        service._changed(method, transaction, external_before); return service._result(changed_elements=ids)
    if method == 'layout.measure':
        ids = list(params.get('ids') or service.selection.ids); session = EditorSession(service.scene)
        if len(ids) == 2:
            measured = measure(session, *ids); return service._result(measurement={'dx': measured.dx, 'dy': measured.dy, 'horizontal_gap': measured.horizontal_gap, 'vertical_gap': measured.vertical_gap, 'center_dx': measured.center_dx, 'center_dy': measured.center_dy})
        measured = selection_metrics(session, ids); return service._result(measurement={'bounds': measured.bounds, 'horizontal_gaps': measured.horizontal_gaps, 'vertical_gaps': measured.vertical_gaps, 'equal_horizontal_spacing': measured.equal_horizontal_spacing, 'equal_vertical_spacing': measured.equal_vertical_spacing})
    if method == 'state.set_schema':
        checked = validate_state_schema(params.get('schema'))
        if not checked['valid']: raise ValueError('invalid state schema: ' + json.dumps(checked['errors'], ensure_ascii=False, sort_keys=True))
        before_scene = deepcopy(service.scene); normalized = checked['schema']; changed = schema_from_scene(service.scene) != normalized
        if changed:
            apply_state_schema(service.scene, normalized)
            if service.editor_session is not None:
                service.editor_session.runtime.reset(); service.editor_session.document.dirty = True
            if transaction is None:
                if service.editor_session is not None: service.editor_session.record_external_scene(before_scene, label='agent_state_set_schema')
                service.revision += 1; service._notify(method)
        return service._result(schema=schema_from_scene(service.scene), changed=changed)
    if method == 'state.validate':
        violations = validate_state(schema_from_scene(service.scene), params.get('state')); return service._result(valid=not violations, violations=violations)
    if method == 'state.enumerate':
        matrix = service._state_matrix(params); payload = {'cases': len(matrix), 'integer_policy': str(params.get('integer_policy', 'representative')), 'warning': 'LARGE_STATE_MATRIX' if len(matrix) > 10000 else None}
        if bool(params.get('include_states', not bool(params.get('summary_only', False)))): payload['states'] = matrix
        return service._result(**payload)
    if method == 'state.count':
        count_params = dict(params); count_params.setdefault('max_cases', 100000); matrix = service._state_matrix_for_scene(service.scene, count_params, default_limit=100000)
        return service._result(cases=len(matrix), integer_policy=str(params.get('integer_policy', 'representative')), warning='LARGE_STATE_MATRIX' if len(matrix) > 10000 else None)
    return UNHANDLED


def dispatch_render_validate_preview(service, method, params, transaction, external_before):
    if method not in RENDER_VALIDATE_PREVIEW:
        return UNHANDLED
    if method in {'render.current', 'render.framebuffer', 'render.resolved_elements', 'render.png'}:
        state, result, raw = service._render(params.get('state')); frame = {'width': result.framebuffer.width, 'height': result.framebuffer.height, 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest(), 'vlsb_hex': raw.hex()}
        if method == 'render.framebuffer': return service._result(framebuffer=frame, state=state)
        if method == 'render.resolved_elements': return service._result(resolved_elements=deepcopy(result.resolved_elements), state=state)
        if method == 'render.png':
            png = service._framebuffer_png_bytes(result.framebuffer); return service._result(png_base64=base64.b64encode(png).decode('ascii'), png_sha256=hashlib.sha256(png).hexdigest(), width=result.framebuffer.width, height=result.framebuffer.height, state=state)
        return service._result(framebuffer=frame, resolved_elements=deepcopy(result.resolved_elements), state=state)
    if method == 'render.preview_file':
        state, result, _ = service._render(params.get('state')); target = resolve_under_root(service.project_root, params.get('path', '.oled/agent/preview/current.png'), label='preview file')
        if target.suffix.lower() != '.png': raise ValueError('preview file must end in .png')
        raw = service._framebuffer_png_bytes(result.framebuffer); atomic_write_bytes(target, raw)
        return service._result(path=str(target), sha256=hashlib.sha256(raw).hexdigest(), state=state)
    if method == 'render.annotated_preview':
        state, result, _ = service._render(params.get('state')); target = resolve_under_root(service.project_root, params.get('path', '.oled/agent/preview/annotated.png'), label='annotated preview')
        if target.suffix.lower() != '.png': raise ValueError('annotated preview must end in .png')
        raw = service._annotated_preview_bytes(result, scale=int(params.get('scale', 6))); atomic_write_bytes(target, raw)
        return service._result(path=str(target), sha256=hashlib.sha256(raw).hexdigest(), state=state, resolved_elements=deepcopy(result.resolved_elements))
    if method == 'render.pixel_diff':
        before_state, before, _ = service._render(params.get('before_state')); after_state, after, _ = service._render(params.get('after_state')); diff = diff_framebuffers(before.framebuffer, after.framebuffer)
        return service._result(before_state=before_state, after_state=after_state, changed_pixels=diff.changed_pixels, percent=diff.percent, bbox=diff.bbox)
    if method == 'render.all_states': return service._result(**service._render_all_states_payload(service.scene, params))
    if method == 'validate.current':
        state = dict(params.get('state') or init_state(service.scene)); findings = validate_scene(service.scene, state); rows = [{'severity': finding.severity, 'code': finding.code, 'message': finding.message, 'element_id': finding.element_id} for finding in findings]
        return service._result(findings=rows, blockers=sum(1 for finding in findings if finding.severity in {'BLOCKER', 'ERROR'}), valid=not has_blockers(findings))
    if method == 'validate.all_states': return service._result(**service._validate_all_states_payload(service.scene, params))
    return UNHANDLED


def dispatch_resource_pixel_font_export(service, method, params, transaction, external_before):
    if method not in RESOURCE_PIXEL_FONT_EXPORT:
        return UNHANDLED
    if method == 'asset.create':
        path = service._asset_path(params['path'], label='asset create'); doc = PixelDocument(int(params['width']), int(params['height']))
        if int(params.get('value', 0)): doc.clear(1)
        doc.save_png(path); service.revision += 1; service._notify(method, path=path.relative_to(service.project_root).as_posix())
        return service._result(**service._file_result(path, service.project_root))
    if method == 'asset.import':
        source = Path(str(params['source'])).expanduser().resolve()
        if not source.exists() or not source.is_file(): raise FileNotFoundError(source)
        target = service._asset_path(params['target'], label='asset import target'); target.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(source, target); PixelDocument.from_image(target)
        service.revision += 1; service._notify(method, path=target.relative_to(service.project_root).as_posix()); return service._result(**service._file_result(target, service.project_root))
    if method == 'asset.copy':
        source = service._asset_path(params['path'], label='asset source'); target = service._asset_path(params['target'], label='asset target')
        if not source.exists(): raise FileNotFoundError(source)
        if target.exists(): raise FileExistsError(target)
        target.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(source, target); service.revision += 1; service._notify(method, path=target.relative_to(service.project_root).as_posix()); return service._result(**service._file_result(target, service.project_root))
    if method == 'asset.rename':
        source = service._asset_path(params['path'], label='asset source'); target = service._asset_path(params['target'], label='asset target')
        if not source.exists(): raise FileNotFoundError(source)
        if target.exists(): raise FileExistsError(target)
        target.parent.mkdir(parents=True, exist_ok=True); os.replace(source, target)
        for did, path in list(service.pixel_paths.items()):
            if path == source: service.pixel_paths[did] = target
        service.revision += 1; service._notify(method, path=target.relative_to(service.project_root).as_posix()); return service._result(**service._file_result(target, service.project_root))
    if method == 'asset.delete':
        path = service._asset_path(params['path'], label='asset delete')
        if not path.exists(): raise FileNotFoundError(path)
        path.unlink()
        for did, open_path in list(service.pixel_paths.items()):
            if open_path == path: service.pixel_paths.pop(did, None); service.pixel_documents.pop(did, None)
        service.revision += 1; service._notify(method, path=path.relative_to(service.project_root).as_posix()); return service._result(deleted=True, path=path.relative_to(service.project_root).as_posix())
    if method == 'pixel.create':
        path = service._asset_path(params['path'], label='pixel asset')
        if path.exists() and not bool(params.get('overwrite', False)): raise FileExistsError(path)
        doc = PixelDocument(int(params['width']), int(params['height'])); did = 'pixel:' + path.relative_to(service.project_root).as_posix(); service._register_pixel_doc(did, doc, path); return service._pixel_result(did, doc)
    if method == 'pixel.open':
        path = service._asset_path(params['path'], label='pixel asset'); doc = PixelDocument.from_image(path); did = 'pixel:' + path.relative_to(service.project_root).as_posix(); service._register_pixel_doc(did, doc, path); return service._pixel_result(did, doc)
    if method == 'pixel.get_document':
        did = str(params['document_id']); return service._pixel_result(did, service._pixel_doc(did))
    if method in {'pixel.paint', 'pixel.erase', 'pixel.line', 'pixel.rect', 'pixel.fill', 'pixel.resize_canvas', 'pixel.rotate', 'pixel.flip', 'pixel.undo', 'pixel.redo', 'pixel.save', 'pixel.close'}:
        return _dispatch_pixel_edit(service, method, params, transaction)
    if method == 'font.list':
        fonts = []
        for manifest in sorted(service.project_root.rglob('fontpack.json')):
            try:
                rel = manifest.parent.relative_to(service.project_root).as_posix(); pack = FontPack.load(manifest.parent); fonts.append({'font_id': rel, 'name': pack.name, 'cell': pack.cell, 'glyph_count': len(pack.characters())})
            except Exception:
                continue
        return service._result(fonts=fonts)
    if method == 'font.create_pack':
        root = resolve_under_root(service.project_root, params['path'], label='font pack'); cell = tuple(map(int, params.get('cell', (5, 8)))); pack = create_font_pack(root, str(params.get('name', root.name)), cell=cell, baseline=int(params.get('baseline', cell[1] - 1)), advance=int(params.get('advance', cell[0] + 1))); pack.save(); service._changed(method, transaction); return service._result(font_id=root.relative_to(service.project_root).as_posix(), name=pack.name, cell=pack.cell)
    if method == 'font.get_pack':
        root = service._font_root(params['font_id']); pack = FontPack.load(root); return service._result(font_id=root.relative_to(service.project_root).as_posix(), name=pack.name, cell=pack.cell, baseline=pack.baseline, advance=pack.advance, characters=pack.characters())
    if method == 'font.generate_glyphs':
        root = service._font_root(params['font_id']); pack = FontPack.load(root); count = rasterize_characters(pack, str(params.get('characters', '')), font_path=params.get('font_path'), font_size=int(params.get('font_size', 12)), threshold=int(params.get('threshold', 128)), offset=tuple(params.get('offset', (0, 0)))); service._changed(method, transaction); return service._result(font_id=root.relative_to(service.project_root).as_posix(), count=count)
    if method == 'font.get_glyph':
        root = service._font_root(params['font_id']); pack = FontPack.load(root); char = str(params['char']); glyph = pack.glyph(char); return service._result(font_id=root.relative_to(service.project_root).as_posix(), char=char, pixels=deepcopy(glyph.pixels), metrics={'bearing_x': glyph.metrics.bearing_x, 'bearing_y': glyph.metrics.bearing_y, 'advance': glyph.metrics.advance})
    if method == 'font.update_glyph':
        root = service._font_root(params['font_id']); pack = FontPack.load(root); char = str(params['char']); metrics = params.get('metrics', {}); pack.set_glyph(char, params['pixels'], GlyphMetrics(int(metrics.get('bearing_x', 0)), int(metrics.get('bearing_y', 0)), int(metrics.get('advance', pack.advance)))); pack.save(); service._changed(method, transaction); return service._result(font_id=root.relative_to(service.project_root).as_posix(), char=char)
    if method == 'font.set_metrics':
        root = service._font_root(params['font_id']); pack = FontPack.load(root); pack.set_metrics(baseline=int(params.get('baseline', pack.baseline)), advance=int(params.get('advance', pack.advance))); pack.save(); service._changed(method, transaction); return service._result(font_id=root.relative_to(service.project_root).as_posix(), baseline=pack.baseline, advance=pack.advance)
    if method == 'export.current':
        output = resolve_under_root(service.project_root, params.get('output_dir', 'exports/agent_current'), label='export directory'); state = dict(params.get('state') or init_state(service.scene)); summary = export_scene(service.scene, output, {'current': state}); return service._result(output_dir=str(output), frame_count=summary.frame_count, frame_hashes=summary.frame_hashes)
    if method == 'export.all': return service._result(**service._export_all_payload(service.scene, service.project_root, params))
    if method == 'export.c_header':
        target = resolve_under_root(service.project_root, params.get('path', 'exports/current.h'), label='C header'); _, result, _ = service._render(params.get('state')); write_c_header(result.framebuffer, target, name=str(params.get('symbol', 'oled_frame'))); return service._result(path=str(target), sha256=hashlib.sha256(target.read_bytes()).hexdigest())
    if method == 'export.font_pack':
        root = service._font_root(params['font_id']); FontPack.load(root); target = resolve_under_root(service.project_root, params.get('path', f'exports/{root.name}.fontpack.zip'), label='font export')
        if target.suffix.lower() != '.zip': raise ValueError('font export must end in .zip')
        service._deterministic_zip(root, target); return service._result(path=str(target), sha256=hashlib.sha256(target.read_bytes()).hexdigest())
    if method == 'export.code_ai_handoff': return service._result(**service._handoff_payload(service.scene, service.project_root, params))
    return UNHANDLED


def _dispatch_pixel_edit(service, method, params, transaction):
    did = str(params['document_id']); doc = service._pixel_doc(did)
    if method == 'pixel.paint': doc.brush(int(params['x']), int(params['y']), int(params.get('value', 1)), size=int(params.get('size', 1)))
    elif method == 'pixel.erase': doc.brush(int(params['x']), int(params['y']), 0, size=int(params.get('size', 1)))
    elif method == 'pixel.line': doc.line(int(params['x0']), int(params['y0']), int(params['x1']), int(params['y1']), value=int(params.get('value', 1)))
    elif method == 'pixel.rect': doc.rectangle(int(params['x0']), int(params['y0']), int(params['x1']), int(params['y1']), filled=bool(params.get('filled', False)), value=int(params.get('value', 1)))
    elif method == 'pixel.fill': doc.flood_fill(int(params['x']), int(params['y']), int(params.get('value', 1)))
    elif method == 'pixel.resize_canvas': doc.resize_canvas(int(params['width']), int(params['height']), anchor=str(params.get('anchor', 'center')))
    elif method == 'pixel.rotate':
        angle = int(params.get('angle', 90)) % 360
        if angle == 90: doc.rotate90()
        elif angle == 180: doc.rotate180()
        elif angle == 270: doc.rotate270()
        elif angle != 0: raise ValueError('pixel rotation supports 0/90/180/270 only')
    elif method == 'pixel.flip':
        axis = str(params.get('axis', 'horizontal'))
        if axis == 'horizontal': doc.flip_horizontal()
        elif axis == 'vertical': doc.flip_vertical()
        else: raise ValueError('axis must be horizontal/vertical')
    elif method == 'pixel.undo':
        if doc.undo(): service._changed(method, transaction)
        return service._pixel_result(did, doc)
    elif method == 'pixel.redo':
        if doc.redo(): service._changed(method, transaction)
        return service._pixel_result(did, doc)
    elif method == 'pixel.save':
        target_param = params.get('path')
        if target_param is None:
            if did not in service.pixel_paths: raise ValueError('pixel document has no target path')
            target = service.pixel_paths[did]
        else: target = service._asset_path(target_param, label='pixel save')
        doc.save_png(target); service.pixel_paths[did] = target
    elif method == 'pixel.close':
        if doc.dirty and not bool(params.get('discard', False)): raise service.unsaved_changes_error(f'unsaved pixel document: {did}; save first or use discard=true')
        service.pixel_documents.pop(did, None); service.pixel_paths.pop(did, None); return service._result(document_id=did, closed=True)
    service._changed(method, transaction)
    return service._pixel_result(did, doc)


def dispatch_jobs_events_diagnostics(service, method, params, transaction, external_before):
    if method not in JOBS_EVENTS_DIAGNOSTICS:
        return UNHANDLED
    if method == 'job.start':
        operation = str(params['operation']); allowed = {'render.all_states', 'validate.all_states', 'export.all', 'export.code_ai_handoff'}
        if operation not in allowed: raise ValueError(f'unsupported long-running operation: {operation}')
        if service.permission == 'observe' and operation.startswith('export.'): raise service.permission_denied_error(operation)
        arguments = dict(params.get('arguments') or {}); snapshot = {'scene': deepcopy(service.scene), 'project_root': str(service.project_root), 'revision': service.revision}; jid = service._jobs.start(operation, arguments, snapshot, service._run_long_job)
        return service._result(job_id=jid, operation=operation, state='queued')
    if method == 'job.status': return service._result(**service._jobs.status(str(params['job_id'])))
    if method == 'job.result': return service._result(**service._jobs.result(str(params['job_id'])))
    if method == 'job.cancel': return service._result(**service._jobs.cancel(str(params['job_id'])))
    if method == 'job.release': return service._result(**service._jobs.release(str(params['job_id'])))
    if method == 'session.events':
        since = max(0, int(params.get('since', 0))); retained_from = service._event_base; dropped_before = max(0, retained_from - since); start = max(0, since - retained_from); next_cursor = retained_from + len(service.events)
        return service._result(events=deepcopy(service.events[start:]), retained_from=retained_from, dropped_before=dropped_before, next_cursor=next_cursor)
    return UNHANDLED


DISPATCHERS = (
    dispatch_api_and_project,
    dispatch_scene_selection_layout_state,
    dispatch_render_validate_preview,
    dispatch_resource_pixel_font_export,
    dispatch_jobs_events_diagnostics,
)
