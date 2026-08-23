from __future__ import annotations

from copy import deepcopy
import os
from pathlib import Path
import sys

from PIL import Image

SIM=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(SIM))


def _bmp(path: Path, xy=(1,1)):
    img=Image.new('1',(8,8),0); img.putpixel(xy,255); img.save(path)


def test_render_resource_bitmap_cache_reuses_decode_and_detects_same_stat_change(tmp_path):
    from resource_cache import RenderResources
    p=tmp_path/'x.bmp'; _bmp(p,(1,1)); st=p.stat(); r=RenderResources()
    a=r.bitmap(p); b=r.bitmap(p)
    assert a is b
    assert r.stats.bitmap_misses==1 and r.stats.bitmap_hits==1
    _bmp(p,(2,2)); assert p.stat().st_size==st.st_size
    os.utime(p,ns=(st.st_atime_ns,st.st_mtime_ns))
    c=r.bitmap(p)
    assert c.sha256!=a.sha256
    assert c is not a
    assert r.stats.bitmap_misses==2


def test_editor_session_reuses_resources_across_renders():
    from editor_model import EditorSession
    from gui import _load_source
    root=SIM.parent
    _project,scene=_load_source(str(root/'CuringLite.project.oled.json'))
    session=EditorSession(scene)
    first=session.render().framebuffer.to_vlsb()
    misses=session.resources.stats.bitmap_misses+session.resources.stats.font_misses
    second=session.render().framebuffer.to_vlsb()
    assert second==first
    assert session.resources.stats.bitmap_hits+session.resources.stats.font_hits>0
    assert session.resources.stats.bitmap_misses+session.resources.stats.font_misses==misses


def _scene(tmp_path):
    p=tmp_path/'scene.json'
    scene={'_path':str(p),'_root':str(tmp_path),'canvas':{'w':128,'h':32},'states':{},'timeline':[],'elements':[
      {'id':'a','type':'placeholder','x':1,'y':1,'w':4,'h':4},
      {'id':'b','type':'placeholder','x':10,'y':2,'w':4,'h':4},
      {'id':'c','type':'placeholder','x':20,'y':3,'w':4,'h':4},
    ]}
    return scene


def test_batch_move_multi_selection_is_one_undo(tmp_path):
    from editor_model import EditorSession
    scene=_scene(tmp_path); before=deepcopy(scene['elements']); s=EditorSession(scene)
    s.batch_move(['a','b','c'],2,3)
    assert len(s._undo)==1
    assert s.undo()
    assert scene['elements']==before


def test_coalesced_batch_move_gesture_is_one_undo(tmp_path):
    from editor_model import EditorSession
    scene=_scene(tmp_path); before=deepcopy(scene['elements']); s=EditorSession(scene)
    s.batch_move(['a','b'],1,0,coalesce=True)
    s.batch_move(['a','b'],1,0,coalesce=True)
    s.batch_move(['a','b'],1,0,coalesce=True)
    s.end_coalesced_edit()
    assert len(s._undo)==1
    assert s.geometry('a').x==4 and s.geometry('b').x==13
    assert s.undo()
    assert scene['elements']==before


def test_windows_launcher_source_has_gui_startup_validation_and_runtime_env_priority():
    source=(SIM/'windows_launcher.c').read_text(encoding='utf-8')
    assert '.venv-runtime' in source
    assert '--startup-smoke' in source
    assert 'startup_smoke_ok' in source
    assert 'WaitForSingleObject' in source
    assert 'GUI startup validation failed' in source


def test_fontpack_and_atomic_io_leave_no_partial_tmp_files(tmp_path):
    from font_pack import create_font_pack, GlyphMetrics
    pack=create_font_pack(tmp_path/'font','T',cell=(3,3),baseline=2,advance=4)
    pack.set_glyph('A',[[0,1,0],[1,1,1],[1,0,1]],GlyphMetrics(0,0,4)); pack.save()
    assert (pack.root/'fontpack.json').exists()
    assert not list(pack.root.rglob('*.tmp'))


def test_diagnostic_logging_writes_rotating_runtime_log(tmp_path):
    from diagnostics import configure_diagnostics, get_logger
    logger=configure_diagnostics(tmp_path); get_logger('test').error('diagnostic-probe')
    for h in logger.handlers: h.flush()
    text=(tmp_path/'monooled_runtime.log').read_text(encoding='utf-8')
    assert 'diagnostic-probe' in text
