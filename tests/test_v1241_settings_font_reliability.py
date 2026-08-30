from __future__ import annotations

import inspect
from pathlib import Path
from time import perf_counter

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / 'src'
SYSTEM_FONT = ROOT / 'test_assets' / 'fonts' / 'DejaVuSans.ttf'

from font_pack import FontPack, GlyphMetrics, create_font_pack, rasterize_characters


DEFAULT_CHARS = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789/'


def _source(name: str) -> str:
    return (SRC / name).read_text(encoding='utf-8')


def test_setting_row_uses_dedicated_text_column_instead_of_grid_row_spans():
    source = _source('preferences_qt.py')
    body = source.split('class SettingRow(QWidget):', 1)[1].split('\n\nclass PreferencesView', 1)[0]
    assert 'QBoxLayout' in body
    assert 'self._text_column' in body
    assert 'self._text_layout' in body
    assert 'self._control_column' in body
    assert 'def refresh_geometry' in body
    assert 'QGridLayout(self._content)' not in body


def test_builtin_5x7_module_exists_and_covers_default_clinical_charset():
    module_path = SRC / 'builtin_oled_font.py'
    assert module_path.is_file()
    import builtin_oled_font as builtin

    assert builtin.DEFAULT_CHARACTERS == DEFAULT_CHARS
    assert set(DEFAULT_CHARS) <= set(builtin.BUILTIN_5X7)
    assert builtin.recommended_baseline((5, 8)) == 6
    assert builtin.recommended_advance((5, 8)) == 6


@pytest.mark.parametrize(
    ('char', 'expected'),
    [
        ('A', ('01110','10001','10001','11111','10001','10001','10001')),
        ('B', ('11110','10001','10001','11110','10001','10001','11110')),
        ('E', ('11111','10000','10000','11110','10000','10000','11111')),
        ('N', ('10001','11001','10101','10011','10001','10001','10001')),
        ('0', ('01110','10001','10011','10101','11001','10001','01110')),
        ('8', ('01110','10001','10001','01110','10001','10001','01110')),
        ('/', ('00001','00010','00100','01000','10000','00000','00000')),
    ],
)
def test_builtin_5x7_representative_glyphs_are_canonical_and_recognizable(char, expected):
    module_path = SRC / 'builtin_oled_font.py'
    assert module_path.is_file()
    import builtin_oled_font as builtin

    assert builtin.BUILTIN_5X7[char] == expected


def test_default_5x8_generation_uses_builtin_font_and_never_emits_empty_default_glyphs(tmp_path):
    pack = create_font_pack(tmp_path / 'clinical', 'Clinical 5x7', cell=(5, 8), baseline=6, advance=6)
    count = rasterize_characters(pack, DEFAULT_CHARS, font_size=7)
    assert count == len(DEFAULT_CHARS)
    assert set(pack.characters()) == set(DEFAULT_CHARS)
    for ch in DEFAULT_CHARS:
        assert any(any(row) for row in pack.glyph(ch).pixels), ch

    # Built-in 5x7 occupies the seven rows ending on the shared baseline.
    a = pack.glyph('A').pixels
    assert [''.join('1' if px else '0' for px in row) for row in a[:7]] == [
        '01110','10001','10001','11111','10001','10001','10001'
    ]
    assert a[7] == [0, 0, 0, 0, 0]


def test_font_pack_changed_char_save_does_not_rewrite_unchanged_pngs(tmp_path, monkeypatch):
    import font_pack as module

    pack = create_font_pack(tmp_path / 'pack', 'Selective', cell=(5, 8), baseline=6, advance=6)
    blank = [[0] * 5 for _ in range(8)]
    a = [row[:] for row in blank]; a[0][0] = 1
    b = [row[:] for row in blank]; b[0][1] = 1
    pack.set_glyph('A', a, GlyphMetrics(0, 0, 6))
    pack.set_glyph('B', b, GlyphMetrics(0, 0, 6))
    pack.save()

    calls = []
    real_write = module.atomic_write_bytes

    def tracking_write(path, payload):
        calls.append(Path(path).name)
        return real_write(path, payload)

    monkeypatch.setattr(module, 'atomic_write_bytes', tracking_write)
    a[1][1] = 1
    pack.set_glyph('A', a, GlyphMetrics(0, 0, 6))
    signature = inspect.signature(FontPack.save)
    assert 'changed_chars' in signature.parameters
    pack.save(changed_chars={'A'})
    assert calls == ['U+0041.png']


def test_default_builtin_generation_is_one_manifest_commit_and_fast(tmp_path, monkeypatch):
    import font_pack as module

    commits = []
    real_json = module.atomic_write_json

    def tracking_json(path, value):
        commits.append(Path(path).name)
        return real_json(path, value)

    monkeypatch.setattr(module, 'atomic_write_json', tracking_json)
    pack = create_font_pack(tmp_path / 'fast', 'Fast', cell=(5, 8), baseline=6, advance=6)
    started = perf_counter()
    rasterize_characters(pack, DEFAULT_CHARS, font_size=7)
    elapsed = perf_counter() - started
    assert commits == ['fontpack.json']
    assert elapsed < 2.0


def test_imported_font_auto_fit_helper_keeps_representative_glyphs_inside_shared_baseline_cell(tmp_path):
    from PIL import ImageFont
    import font_pack as module

    assert hasattr(module, 'fit_font_size_for_cell')
    path = str(SYSTEM_FONT)
    if not SYSTEM_FONT.is_file():
        pytest.skip('test font unavailable')

    fitted = module.fit_font_size_for_cell(path, (10, 12), 8, 'Agjp', 24)
    assert 4 <= fitted < 24
    pack = create_font_pack(tmp_path / 'fit', 'Fit', cell=(10, 12), baseline=8, advance=10)
    rasterize_characters(pack, 'Agjp', font_path=path, font_size=24)
    bounds = {}
    for ch in 'Agjp':
        ys = [y for y, row in enumerate(pack.glyph(ch).pixels) if any(row)]
        assert ys, ch
        bounds[ch] = (min(ys), max(ys))
    assert bounds['g'][1] >= bounds['A'][1]
    assert bounds['p'][1] >= bounds['A'][1]



def test_imported_font_recommended_layout_centers_family_with_one_shared_baseline():
    from PIL import ImageFont
    import font_pack as module

    assert hasattr(module, 'recommended_truetype_layout')
    path = str(SYSTEM_FONT)
    if not SYSTEM_FONT.is_file():
        pytest.skip('test font unavailable')
    size, baseline = module.recommended_truetype_layout(path, (24, 24), 'ABEN08Agjp', 18)
    assert 4 <= size <= 18
    assert 0 <= baseline < 24
    font = ImageFont.truetype(path, size)
    boxes = [font.getbbox(ch, anchor='ls') for ch in 'ABEN08Agjp']
    top = baseline + min(box[1] for box in boxes)
    bottom = baseline + max(box[3] for box in boxes)
    assert 0 <= top < bottom <= 24
    ink_center = (top + bottom - 1) / 2
    cell_center = (24 - 1) / 2
    assert abs(ink_center - cell_center) <= 1.5

def test_font_lab_source_contract_has_auto_baseline_default_source_and_throttled_progress():
    source = _source('font_lab_qt.py')
    assert 'recommended_baseline' in source
    assert 'recommended_advance' in source
    assert 'recommended_truetype_layout' in source
    assert '_apply_auto_font_layout' in source
    assert '_baseline_user_override' in source
    assert '_font_size_user_override' in source
    assert 'font.source_builtin' in source
    assert 'DEFAULT_CHARACTERS' in source
    worker = source.split('class _FontGenerateWorker', 1)[1].split('\n\nclass FontLabEditor', 1)[0]
    assert '_emit_progress' in worker
    assert 'max_progress_updates' in worker


def test_windows_build_doc_tracks_current_release_and_all_critical_smokes():
    version = (SRC / 'VERSION').read_text(encoding='utf-8').strip()
    doc = (ROOT / 'docs' / 'WINDOWS_BUILD.md').read_text(encoding='utf-8')
    assert f'# Windows Build and Release — V{version}' in doc
    assert 'startup/layout/settings/font/interaction/soak gates' in doc


def test_v1241_font_reliability_contract_remains_part_of_current_release():
    import json
    version = (SRC / 'VERSION').read_text(encoding='utf-8').strip()
    manifest = json.loads((ROOT / 'DELIVERY_MANIFEST.json').read_text(encoding='utf-8'))
    assert manifest['version'] == version
    assert manifest['release_version'] == version
    assert manifest['font_pipeline'].endswith('v1241')
    verifier = (ROOT / 'VERIFY_PACKAGE.py').read_text(encoding='utf-8')
    assert 'EXPECTED_PRODUCTION_MODULES=77' in verifier
    assert "'V12_4_1_SETTINGS_FONT_RELIABILITY.md'" in verifier
