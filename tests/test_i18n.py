import sys
from pathlib import Path

SIM = Path(__file__).resolve().parents[1] / 'src'
sys.path.insert(0, str(SIM))

from i18n import Translator, CATALOGS, DEFAULT_LANGUAGE, SUPPORTED_LANGUAGES


def test_catalogs_have_identical_keys_and_supported_languages():
    assert SUPPORTED_LANGUAGES == ('zh_CN', 'en_US')
    assert DEFAULT_LANGUAGE == 'zh_CN'
    assert set(CATALOGS['zh_CN']) == set(CATALOGS['en_US'])
    assert len(CATALOGS['zh_CN']) >= 50


def test_translator_switches_language_without_changing_key_contract():
    t = Translator('zh_CN')
    assert t('app.title') == 'MonoOLED Studio'
    assert t('panel.properties') == '属性'

    t.set_language('en_US')
    assert t('panel.properties') == 'Properties'
    assert t('action.export_all') == 'Export State Matrix'


def test_translator_formats_named_values_and_rejects_unknown_language():
    t = Translator('en_US')
    assert t('status.frame', bytes=512, lit=42) == 'Framebuffer 512 B · 42 lit pixels'
    try:
        t.set_language('fr_FR')
    except ValueError as exc:
        assert 'unsupported language' in str(exc)
    else:
        raise AssertionError('unsupported language must raise')


def test_primary_gui_does_not_hardcode_common_dialog_button_copy():
    gui = (SIM / 'gui.py').read_text(encoding='utf-8')
    assert "QPushButton('Cancel'" not in gui
    assert "QPushButton('OK'" not in gui
    assert "addMenu('Language')" not in gui
    assert "Images (*.png *.bmp);;All Files (*)" not in gui
