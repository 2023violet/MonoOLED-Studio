from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from editor_model import EditorSession
from pixel_studio import PixelDocument
from scene import load_scene


def test_branding_constants_are_monoled_studio():
    import gui
    assert gui.APP_TITLE == 'MonoOLED Studio'
    assert gui.APP_VERSION == (Path(__file__).resolve().parents[1] / 'VERSION').read_text(encoding='utf-8').strip()


def test_native_only_image_locks_width_height():
    scene = load_scene('main_scene')
    session = EditorSession(scene)
    image = next(e for e in scene['elements'] if e.get('type') == 'image')
    g = session.geometry(str(image['id']))
    assert g.editable['x'] is True
    assert g.editable['y'] is True
    assert g.editable['w'] is False
    assert g.editable['h'] is False


def test_pixel_document_draw_undo_redo_and_vlsb():
    doc = PixelDocument(8, 8)
    doc.pencil(1, 1)
    doc.line(0, 0, 3, 0)
    assert doc.get(1, 1) == 1
    assert doc.get(2, 0) == 1
    before = doc.to_vlsb()
    assert len(before) == 8
    assert doc.undo() is True
    assert doc.get(2, 0) == 0
    assert doc.redo() is True
    assert doc.to_vlsb() == before


def test_pixel_document_rectangle_fill_transform_and_region():
    doc = PixelDocument(8, 8)
    doc.rectangle(1, 1, 4, 4, filled=False)
    assert doc.get(1, 1) == 1 and doc.get(2, 2) == 0
    doc.flood_fill(2, 2, 1)
    assert doc.get(2, 2) == 1
    region = doc.copy_region(1, 1, 2, 2)
    doc.clear()
    doc.paste_region(4, 4, region)
    assert doc.get(4, 4) == 1
    doc.flip_horizontal()
    assert doc.get(3, 4) == 1


def test_pixel_document_png_roundtrip(tmp_path):
    doc = PixelDocument(8, 8)
    doc.line(0, 0, 7, 7)
    path = tmp_path / 'asset.png'
    doc.save_png(path)
    loaded = PixelDocument.from_image(path)
    assert loaded.width == 8 and loaded.height == 8
    assert loaded.to_vlsb() == doc.to_vlsb()

def test_pixel_document_supports_non_page_aligned_asset_height(tmp_path):
    from PIL import Image
    p=tmp_path/'24x12.png'; Image.new('1',(24,12),255).save(p)
    doc=PixelDocument.from_image(p)
    assert (doc.width,doc.height)==(24,12)
    assert len(doc.to_vlsb())==24*2

def test_pixel_stroke_coalesces_to_one_undo_step():
    doc=PixelDocument(16,8)
    doc.begin_gesture()
    for x in range(6): doc.pencil(x,2)
    doc.end_gesture()
    assert all(doc.get(x,2)==1 for x in range(6))
    assert doc.undo() is True
    assert all(doc.get(x,2)==0 for x in range(6))
    assert doc.undo() is False
