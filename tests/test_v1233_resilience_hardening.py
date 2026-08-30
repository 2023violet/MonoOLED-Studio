from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / 'src'

def read(name: str) -> str:
    return (SRC / name).read_text(encoding='utf-8')


def test_corrupt_image_is_normalized_to_stable_value_error_without_hiding_missing_file(tmp_path):
    from pixel_studio import PixelDocument
    bad = tmp_path / 'broken.png'
    bad.write_bytes(b'not-an-image')
    with pytest.raises(ValueError, match='unsupported or corrupt image'):
        PixelDocument.from_image(bad)
    with pytest.raises(FileNotFoundError):
        PixelDocument.from_image(tmp_path / 'missing.png')


def test_pixel_open_and_file_outputs_handle_user_visible_io_errors_instead_of_leaking_from_qt_slots():
    source = read('pixel_studio_qt.py')
    opened = source.split('    def open_image(self):',1)[1].split('\n    def ',1)[0]
    assert 'except (OSError, ValueError) as exc' in opened
    for name in ('save_png','save_bin','save_c_header'):
        body = source.split(f'    def {name}(self):',1)[1].split('\n    def ',1)[0]
        assert 'except (OSError, ValueError) as exc' in body, name
        assert 'QMessageBox.warning' in body, name


def test_font_lab_save_failure_is_non_destructive_and_blocks_glyph_switch():
    source = read('font_lab_qt.py')
    save = source.split('    def save(self):',1)[1].split('\n    def ',1)[0]
    assert 'except (OSError, ValueError) as exc' in save
    assert 'QMessageBox.warning' in save
    select = source.split('    def _select_glyph(self,ch):',1)[1].split('\n    def ',1)[0]
    assert 'ifnotself.save():' in ''.join(select.split())
    assert 'return' in select


def test_autosave_write_failure_is_non_modal_visible_and_does_not_escape_timer_slot():
    source = read('gui.py')
    body = source.split('        def _autosave_tick(self,force=False):',1)[1].split('\n        def ',1)[0]
    assert 'try:' in body and 'except (OSError, ValueError) as exc' in body
    assert "status.autosave_failed" in body
    assert 'self.app_status.setToolTip' in body
    assert "self.logger.log('AUTOSAVE_FAIL'" in body
    i18n = read('i18n.py')
    assert '"status.autosave_failed": "自动保存失败"' in i18n
    assert '"status.autosave_failed": "Autosave failed"' in i18n


def test_pixel_binary_save_is_atomic_and_preserves_existing_target_on_replace_failure(tmp_path, monkeypatch):
    import atomic_io
    from pixel_studio import PixelDocument
    target = tmp_path / 'asset.bin'
    target.write_bytes(b'OLD-BINARY')
    doc = PixelDocument(8, 8)
    doc.pencil(0, 0, 1)
    monkeypatch.setattr(atomic_io.os, 'replace', lambda *_: (_ for _ in ()).throw(OSError('disk failure')))
    with pytest.raises(OSError, match='disk failure'):
        doc.save_bin(target)
    assert target.read_bytes() == b'OLD-BINARY'
    assert not target.with_name(target.name + '.tmp').exists()


def test_pixel_png_save_is_atomic_and_preserves_existing_target_on_replace_failure(tmp_path, monkeypatch):
    import atomic_io
    from pixel_studio import PixelDocument
    target = tmp_path / 'asset.png'
    target.write_bytes(b'OLD-PNG-SENTINEL')
    doc = PixelDocument(8, 8)
    doc.pencil(0, 0, 1)
    monkeypatch.setattr(atomic_io.os, 'replace', lambda *_: (_ for _ in ()).throw(OSError('disk failure')))
    with pytest.raises(OSError, match='disk failure'):
        doc.save_png(target)
    assert target.read_bytes() == b'OLD-PNG-SENTINEL'
    assert doc.dirty is True
    assert not target.with_name(target.name + '.tmp').exists()
