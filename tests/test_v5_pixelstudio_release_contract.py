from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

from pixel_studio import PixelDocument


def test_pixel_document_exports_c_header_for_non_page_aligned_height():
    doc = PixelDocument(3, 10)
    doc.pencil(0, 0)
    doc.pencil(2, 9)
    text = doc.to_c_header('test_icon')
    assert '#define TEST_ICON_WIDTH 3' in text
    assert '#define TEST_ICON_HEIGHT 10' in text
    assert 'static const unsigned char test_icon[]' in text
    assert '0x01' in text
    assert '0x02' in text


def test_pixel_studio_qt_is_bilingual_and_has_import_export_contract():
    source = (Path(__file__).resolve().parents[1] / 'src' / 'pixel_studio_qt.py').read_text(encoding='utf-8')
    assert 'Translator' in source
    assert 'language:' in source
    assert 'ImageImportDialog' in source
    assert 'save_c_header' in source
    assert "pixel.action.export_c" in source


def test_designer_has_user_toggle_for_zone_overlay():
    source = (Path(__file__).resolve().parents[1] / 'src' / 'gui.py').read_text(encoding='utf-8')
    assert 'zones_check' in source
    assert "toggle.zones" in source
    assert "self.scene.get('zones',[]) if self.zones_check.isChecked() else []" in source
