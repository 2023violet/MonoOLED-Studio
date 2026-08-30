from support import load_curing_scene
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

from editor_model import EditorSession
from scene import load_scene
from selection_tools import smart_guides


def test_smart_guides_detect_edges_and_centers():
    scene = load_curing_scene()
    scene['canvas'] = {'w': 64, 'h': 32}
    scene['elements'] = [
        {'id':'a','type':'placeholder','x':4,'y':4,'w':8,'h':8},
        {'id':'b','type':'placeholder','x':20,'y':4,'w':8,'h':8},
    ]
    session=EditorSession(scene)
    guides=smart_guides(session,'a',tolerance=0)
    assert 4 in guides['y'] and 8 in guides['y'] and 12 in guides['y']


def test_gui_has_pixel_studio_and_branding_contract():
    source=(Path(__file__).resolve().parents[1] / 'src'/'gui.py').read_text(encoding='utf-8')
    assert "APP_TITLE = 'MonoOLED Studio'" in source
    assert 'open_pixel_studio' in source
    assert 'PixelStudioWindow' in source
    assert "action.pixel_studio" in source


def test_pixel_studio_qt_has_required_tools():
    source=(Path(__file__).resolve().parents[1] / 'src'/'pixel_studio_qt.py').read_text(encoding='utf-8')
    for token in ('Pencil','Eraser','Line','Rectangle','Fill','Select','save_png','save_bin'):
        assert token in source


def test_app_icon_assets_exist():
    root=Path(__file__).resolve().parents[1] / 'src'
    assert (root/'branding'/'monooled_studio.ico').is_file()
    assert (root/'branding'/'monooled_studio_256.png').is_file()


def test_windows_launcher_embeds_app_icon_resource_section():
    root=Path(__file__).resolve().parents[1]
    spec=(root/'tools'/'MonoOLEDStudio.spec').read_text(encoding='utf-8')
    assert "icon=str(ROOT / 'src' / 'branding' / 'monooled_studio.ico')" in spec
    assert not (root/'MonoOLEDStudio.exe').exists()

