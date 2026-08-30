import re
import sys
from pathlib import Path

SIM = Path(__file__).resolve().parents[1] / 'src'
sys.path.insert(0, str(SIM))

from i18n import CATALOGS


def test_all_gui_translation_keys_exist_in_both_catalogs():
    gui = (SIM / 'gui.py').read_text(encoding='utf-8')
    keys = set(re.findall(r"(?:\btr|\bt)\(\s*['\"]([^'\"]+)['\"]", gui))
    for language, catalog in CATALOGS.items():
        missing = sorted(keys - set(catalog))
        assert not missing, f'{language} missing GUI keys: {missing}'


def test_diff_copy_accepts_exact_gui_format_arguments():
    from i18n import Translator
    for lang in ('zh_CN','en_US'):
        t=Translator(lang)
        assert '42' in t('diff.status',pixels=42,percent=1.25)
        assert '(1, 2, 3, 4)' in t('diff.bbox',bbox='(1, 2, 3, 4)')


def test_asset_health_copy_accepts_gui_arguments():
    from i18n import Translator
    for lang in ('zh_CN','en_US'):
        t=Translator(lang)
        text=t('asset.health_summary',count=12,duplicates=1,unused=2,invalid=0)
        assert '12' in text
