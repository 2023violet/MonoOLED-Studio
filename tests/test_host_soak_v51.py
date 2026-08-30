from __future__ import annotations
from support import load_curing_scene

from copy import deepcopy
from pathlib import Path
import sys

SIM=Path(__file__).resolve().parents[1] / 'src'
sys.path.insert(0,str(SIM))

from editor_model import EditorSession
from pixel_studio import PixelDocument
from scene import load_scene


def test_editor_host_soak_keeps_render_deterministic_and_history_bounded():
    scene=load_curing_scene()
    session=EditorSession(scene,max_history=80)
    target=next(e['id'] for e in scene['elements'] if e.get('id')=='battery')
    base=session.geometry(target).x
    for i in range(400):
        session.set_geometry(target,x=base+(i&1))
        session.end_coalesced_edit()
        raw=session.render().framebuffer.to_vlsb()
        assert len(raw)==512
    assert len(session._undo)<=80
    session.set_geometry(target,x=base); session.end_coalesced_edit()
    baseline=session.render().framebuffer.to_vlsb()
    clone=EditorSession(load_curing_scene()).render().framebuffer.to_vlsb()
    assert baseline==clone


def test_pixel_studio_soak_keeps_bounded_history_and_valid_vlsb():
    doc=PixelDocument(128,32,max_undo=60)
    for i in range(500):
        x=i%128; y=(i//128)%32
        doc.pencil(x,y,i&1)
        if i%17==0: doc.invert()
        assert len(doc.to_vlsb())==512
    assert len(doc._undo)<=60
    for _ in range(75): doc.undo()
    assert len(doc.to_vlsb())==512
