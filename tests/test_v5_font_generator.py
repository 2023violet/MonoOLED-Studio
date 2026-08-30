from pathlib import Path
import json, sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from font_generator import generate_glyphs


def test_generate_glyphs_default_font(tmp_path):
    result=generate_glyphs('A0', output_dir=tmp_path, cell=(12,16))
    assert result.count==2
    manifest=json.loads((tmp_path/'glyph_manifest.json').read_text(encoding='utf-8'))
    assert set(manifest['glyphs'])=={'A','0'}
    for meta in manifest['glyphs'].values():
        p=tmp_path/meta['file']; assert p.exists(); assert meta['w']==12 and meta['h']==16
    assert (tmp_path/'glyphs.h').exists()
