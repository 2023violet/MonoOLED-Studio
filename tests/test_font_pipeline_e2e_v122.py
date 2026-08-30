from __future__ import annotations

import json
from pathlib import Path
import zipfile

import pytest
from PIL import Image

from automation_service import StudioAutomationService
from font_pack import FontPack, GlyphMetrics, create_font_pack, rasterize_characters
from pixel_studio import PixelDocument, insert_fontpack_text
from project_workspace import create_project
from render import render_scene
from scene import load_scene


def _project_service(tmp_path):
    project = create_project(tmp_path / 'font_project', name='Font Pipeline', canvas=(64, 16))
    scene = load_scene(project.screen_path('main'), project_root=project.root)
    scene['_project_path'] = str(project.path)
    scene['_asset_dirs'] = list(project.asset_dirs)
    scene['_design_rules'] = {}
    return project, StudioAutomationService(
        scene,
        source_path=project.screen_path('main'),
        permission='full',
        copy_scene=False,
        project_workspace=project,
    )


def test_font_pack_rejects_invalid_cell_baseline_and_advance(tmp_path):
    with pytest.raises(ValueError, match='cell'):
        create_font_pack(tmp_path / 'bad-cell', 'Bad', cell=(0, 8), baseline=6, advance=5)
    with pytest.raises(ValueError, match='baseline'):
        create_font_pack(tmp_path / 'bad-baseline', 'Bad', cell=(5, 8), baseline=8, advance=5)
    with pytest.raises(ValueError, match='advance'):
        create_font_pack(tmp_path / 'bad-advance', 'Bad', cell=(5, 8), baseline=6, advance=0)


def test_font_pack_load_rejects_manifest_asset_escape(tmp_path):
    outside = tmp_path / 'outside.png'
    Image.new('1', (3, 8), 1).save(outside)
    root = tmp_path / 'pack'
    root.mkdir()
    (root / 'fontpack.json').write_text(json.dumps({
        'schema': 1,
        'name': 'Escape',
        'cell': {'w': 3, 'h': 8},
        'baseline': 6,
        'advance': 4,
        'glyphs': {'A': {'asset': '../outside.png', 'advance': 4}},
    }), encoding='utf-8')
    with pytest.raises(ValueError, match='inside font pack'):
        FontPack.load(root)


def test_rasterize_rejects_invalid_generation_parameters(tmp_path):
    pack = create_font_pack(tmp_path / 'pack', 'Safe', cell=(8, 16), baseline=12, advance=8)
    with pytest.raises(ValueError, match='font_size'):
        rasterize_characters(pack, 'A', font_size=0)
    with pytest.raises(ValueError, match='threshold'):
        rasterize_characters(pack, 'A', threshold=-1)
    with pytest.raises(ValueError, match='threshold'):
        rasterize_characters(pack, 'A', threshold=256)
    with pytest.raises(ValueError, match='offset'):
        rasterize_characters(pack, 'A', offset=(1, 2, 3))


def test_font_pack_roundtrip_edit_compose_and_pixel_insert(tmp_path):
    pack = create_font_pack(tmp_path / 'font', 'Roundtrip', cell=(8, 16), baseline=12, advance=9)
    count = rasterize_characters(pack, 'A0A', font_size=12, threshold=128)
    assert count == 2
    reopened = FontPack.load(pack.root)
    assert reopened.characters() == ('A', '0')
    glyph = reopened.glyph('A')
    edited = [row[:] for row in glyph.pixels]
    edited[0][0] = 1 - edited[0][0]
    reopened.set_glyph('A', edited, GlyphMetrics(1, 0, 9))
    reopened.save()
    again = FontPack.load(pack.root)
    assert again.glyph('A').pixels[0][0] == edited[0][0]
    assert again.glyph('A').metrics.bearing_x == 1
    bitmap = again.compose_text('A0', tracking=1)
    assert len(bitmap) == 16 and len(bitmap[0]) > 8
    doc = PixelDocument(48, 16)
    width, height = insert_fontpack_text(doc, again, 'A0', 2, 0, tracking=1)
    assert (width, height) == (len(bitmap[0]), 16)
    assert doc.dirty is True and any(any(row) for row in doc.pixels)
    assert doc.undo() is True
    assert not any(any(row) for row in doc.pixels)


def test_font_pack_renderer_and_automation_export_are_end_to_end_and_deterministic(tmp_path):
    project, service = _project_service(tmp_path)
    made = service.call('font.create_pack', {
        'path': '.oled/fonts/ui', 'name': 'UI Font', 'cell': [8, 16], 'baseline': 12, 'advance': 9,
    })
    generated = service.call('font.generate_glyphs', {
        'font_id': made['font_id'], 'characters': 'AB01', 'font_size': 12, 'threshold': 128,
    })
    assert generated['count'] == 4
    glyph = service.call('font.get_glyph', {'font_id': made['font_id'], 'char': 'A'})
    pixels = glyph['pixels']
    pixels[0][0] = 1 - pixels[0][0]
    service.call('font.update_glyph', {
        'font_id': made['font_id'], 'char': 'A', 'pixels': pixels,
        'metrics': {'bearing_x': 0, 'bearing_y': 0, 'advance': 9},
    })
    service.call('font.set_metrics', {'font_id': made['font_id'], 'baseline': 12, 'advance': 9})

    scene = {
        'canvas': {'w': 64, 'h': 16}, '_root': project.root, 'states': {},
        'elements': [{'id': 'label', 'type': 'bitmap_text', 'text': 'AB01', 'font_pack': made['font_id'], 'x': 1, 'y': 0}],
    }
    rendered = render_scene(scene, {})
    assert rendered.resolved_elements[0]['w'] > 0
    assert len(rendered.framebuffer.to_vlsb()) == 128

    first = service.call('export.font_pack', {'font_id': made['font_id'], 'path': 'exports/ui-a.zip'})
    second = service.call('export.font_pack', {'font_id': made['font_id'], 'path': 'exports/ui-b.zip'})
    assert first['sha256'] == second['sha256']
    first_path, second_path = Path(first['path']), Path(second['path'])
    assert first_path.read_bytes() == second_path.read_bytes()
    with zipfile.ZipFile(first_path) as zf:
        names = zf.namelist()
        assert 'fontpack.json' in names
        assert any(name.startswith('glyphs/U+') and name.endswith('.png') for name in names)


def test_automation_font_boundaries_reject_bad_metrics_and_missing_glyph(tmp_path):
    _, service = _project_service(tmp_path)
    with pytest.raises(ValueError, match='baseline'):
        service.call('font.create_pack', {'path': '.oled/fonts/bad', 'cell': [5, 8], 'baseline': 9, 'advance': 6})
    made = service.call('font.create_pack', {'path': '.oled/fonts/ok', 'cell': [5, 8], 'baseline': 6, 'advance': 6})
    with pytest.raises(KeyError):
        service.call('font.get_glyph', {'font_id': made['font_id'], 'char': 'Z'})
    with pytest.raises(ValueError, match='advance'):
        service.call('font.set_metrics', {'font_id': made['font_id'], 'advance': 0})


def test_font_pack_save_removes_stale_glyph_assets_after_regeneration(tmp_path):
    root = tmp_path / 'font'
    pack = create_font_pack(root, 'Clean', cell=(8, 16), baseline=12, advance=8)
    rasterize_characters(pack, 'ABC', font_size=12)
    assert (root / 'glyphs' / 'U+0043.png').exists()
    replacement = create_font_pack(root, 'Clean', cell=(8, 16), baseline=12, advance=8)
    rasterize_characters(replacement, 'AB', font_size=12)
    assert not (root / 'glyphs' / 'U+0043.png').exists()


def test_legacy_font_generator_validates_ranges_and_keeps_unicode_manifest(tmp_path):
    from font_generator import generate_glyphs
    with pytest.raises(ValueError, match='font_size'):
        generate_glyphs('A', output_dir=tmp_path / 'bad-size', font_size=0)
    with pytest.raises(ValueError, match='threshold'):
        generate_glyphs('A', output_dir=tmp_path / 'bad-threshold', threshold=300)
    result = generate_glyphs('A中0A', output_dir=tmp_path / 'unicode', cell=(12, 16), font_size=12)
    assert result.count == 3
    manifest = json.loads((result.output_dir / 'glyph_manifest.json').read_text(encoding='utf-8'))
    assert set(manifest['glyphs']) == {'A', '中', '0'}
    assert manifest['glyphs']['中']['file'] == 'U+4E2D.png'
    assert manifest['glyphs']['中']['bytes'] == 24
    header = (result.output_dir / 'glyphs.h').read_text(encoding='utf-8')
    assert 'glyph_4E2D[24]' in header


def test_font_lab_enforces_metric_bounds_and_reports_generation_errors():
    source = (Path(__file__).resolve().parents[1] / 'src' / 'font_lab_qt.py').read_text(encoding='utf-8')
    assert 'self.baseline.setRange(0,max(0,self.pack.cell[1]-1))' in source
    assert 'self.cell_h.valueChanged.connect(self._cell_height_changed)' in source
    assert 'def _cell_height_changed' in source
    assert 'except (OSError, ValueError) as exc:' in source
    assert 'QMessageBox.warning' in source
    assert 'self.pack.set_metrics(' in source


def test_font_pack_global_advance_updates_existing_glyph_spacing(tmp_path):
    pack = create_font_pack(tmp_path / 'font-advance', 'Spacing', cell=(8, 16), baseline=12, advance=8)
    rasterize_characters(pack, 'AB', font_size=12)
    before = len(pack.compose_text('AB')[0])
    pack.set_metrics(advance=11)
    pack.save()
    reopened = FontPack.load(pack.root)
    assert reopened.glyph('A').metrics.advance == 11
    assert reopened.glyph('B').metrics.advance == 11
    assert len(reopened.compose_text('AB')[0]) == before + 3


def test_font_pack_rejects_nonpositive_per_glyph_advance(tmp_path):
    pack = create_font_pack(tmp_path / 'font-glyph-metrics', 'Glyph Metrics', cell=(5, 8), baseline=6, advance=6)
    pixels = [[0] * 5 for _ in range(8)]
    with pytest.raises(ValueError, match='glyph advance'):
        pack.set_glyph('A', pixels, GlyphMetrics(0, 0, 0))
