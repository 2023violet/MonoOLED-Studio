from pathlib import Path

from automation_service import StudioAutomationService
from c_export import framebuffer_to_c_header
from project_workspace import ProjectWorkspace, create_project
from scene import load_scene


def _service(tmp_path):
    project = create_project(tmp_path / 'demo', name='Output Demo', canvas=(10, 16))
    scene = load_scene(project.screen_path('main'), project_root=project.root)
    return project, StudioAutomationService(
        scene,
        source_path=project.screen_path('main'),
        permission='full',
        copy_scene=False,
        project_workspace=project,
    )


def test_api_130_advertises_output_workbench_methods(tmp_path):
    _, service = _service(tmp_path)

    capabilities = service.call('automation.capabilities', {})
    methods = {item['method'] for item in capabilities['methods']}

    assert capabilities['api_version'] == '1.3.0'
    assert {
        'output.list_profiles', 'output.get_profile', 'output.upsert_profile',
        'output.delete_profile', 'output.set_active_profile', 'output.preview',
        'export.bitmap_data', 'export.font_data',
    } <= methods


def test_profile_crud_persists_and_advances_revision(tmp_path):
    project, service = _service(tmp_path)
    baseline_revision = service.revision
    default = service.call('output.get_profile', {'profile_id': 'ssd1306_vlsb_c'})['profile']

    custom = dict(default)
    custom['name'] = 'My row format'
    custom['encoding'] = dict(custom['encoding'], bit_axis='horizontal', group_order='row_major')
    created = service.call('output.upsert_profile', {
        'profile_id': 'my_row', 'profile': custom, 'activate': True,
    })

    assert created['active_profile'] == 'my_row'
    assert service.revision == baseline_revision + 1
    reopened = ProjectWorkspace.load(project.path)
    active, profiles = reopened.get_output_profiles()
    assert active == 'my_row'
    assert profiles['my_row'].encoding.bit_axis == 'horizontal'

    service.call('output.set_active_profile', {'profile_id': 'ssd1306_vlsb_c'})
    service.call('output.delete_profile', {'profile_id': 'my_row'})
    listing = service.call('output.list_profiles', {})
    assert listing['active_profile'] == 'ssd1306_vlsb_c'
    assert {'ssd1306_vlsb_c', 'row_msb_c51', 'raw_hex', 'raw_decimal', 'legacy_pixel_c'} == {item['id'] for item in listing['profiles']}


def test_preview_accepts_saved_profile_and_unsaved_draft(tmp_path):
    _, service = _service(tmp_path)
    saved = service.call('output.preview', {
        'source': {'kind': 'current_scene'},
        'profile_id': 'ssd1306_vlsb_c',
        'symbol': 'preview frame',
    })
    assert saved['byte_count'] == 20
    assert saved['data_sha256']
    assert saved['preview_truncated'] is False
    assert 'preview_frame' in saved['preview_text']

    draft = service.call('output.get_profile', {'profile_id': 'ssd1306_vlsb_c'})['profile']
    draft['name'] = 'Draft decimal'
    draft['text'].update({'radix': 'decimal', 'data_prefix': '', 'minimal_data': True})
    preview = service.call('output.preview', {
        'source': {'kind': 'current_scene'}, 'profile': draft,
    })
    assert preview['profile_id'] is None
    assert '0,' in preview['preview_text']


def test_bitmap_export_supports_pixel_document_and_binary(tmp_path):
    project, service = _service(tmp_path)
    made = service.call('pixel.create', {'path': 'assets/icon.png', 'width': 10, 'height': 10})
    service.call('pixel.paint', {'document_id': made['document_id'], 'x': 0, 'y': 0, 'value': 1})
    profile = service.call('output.get_profile', {'profile_id': 'ssd1306_vlsb_c'})['profile']
    profile['name'] = 'Binary'
    profile['text']['container'] = 'binary'

    result = service.call('export.bitmap_data', {
        'source': {'kind': 'pixel_document', 'document_id': made['document_id']},
        'profile': profile,
        'path': 'exports/icon.bin',
    })

    target = Path(result['path'])
    assert target == project.root / 'exports/icon.bin'
    assert target.read_bytes() == bytes([1] + [0] * 9 + [0] * 10)
    assert result['byte_count'] == 20
    assert result['sha256']


def test_legacy_c_header_remains_byte_for_byte_compatible(tmp_path):
    project, service = _service(tmp_path)
    _, rendered, _ = service._render(None)
    expected = framebuffer_to_c_header(rendered.framebuffer, name='legacy_frame')

    result = service.call('export.c_header', {
        'path': 'exports/legacy.h', 'symbol': 'legacy_frame',
    })

    assert Path(result['path']).read_text(encoding='utf-8') == expected
    assert Path(result['path']).is_relative_to(project.root)


def test_font_export_preserves_requested_order_and_writes_sidecar_index(tmp_path):
    _, service = _service(tmp_path)
    made = service.call('font.create_pack', {'path': 'fonts/demo', 'name': 'Demo', 'cell': [8, 8], 'baseline': 7, 'advance': 8})
    for char, x in (('A', 0), ('B', 1)):
        pixels = [[0] * 8 for _ in range(8)]
        pixels[0][x] = 1
        service.call('font.update_glyph', {'font_id': made['font_id'], 'char': char, 'pixels': pixels, 'metrics': {'advance': 8}})
    profile = service.call('output.get_profile', {'profile_id': 'ssd1306_vlsb_c'})['profile']
    profile['name'] = 'Indexed font'
    profile['text']['index_mode'] = 'sidecar'

    result = service.call('export.font_data', {
        'font_id': made['font_id'], 'characters': 'BAAB', 'profile': profile,
        'path': 'exports/demo_font.h', 'symbol': 'demo_font',
    })

    assert [(row['codepoint'], row['offset'], row['byte_length']) for row in result['index']] == [(ord('B'), 0, 8), (ord('A'), 8, 8)]
    assert Path(result['index_path']).name == 'demo_font_index.h'
    assert result['index_sha256']
