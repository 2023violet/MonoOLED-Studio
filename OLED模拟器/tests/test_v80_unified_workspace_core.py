from pathlib import Path
import json
import pytest

from selection_model import SelectionModel
from selection_tools import align_to, selection_metrics
from pixel_studio import PixelDocument
from font_pack import FontPack, GlyphMetrics, create_font_pack
from workspace_host import EditorRegistry
from automation_service import StudioAutomationService, StaleRevisionError, PermissionDeniedError


class G:
    def __init__(self,x,y,w,h): self.x=x;self.y=y;self.w=w;self.h=h
class FakeSession:
    def __init__(self): self.g={'a':G(1,2,3,4),'b':G(10,4,2,2),'c':G(20,8,4,3)}
    def geometry(self,e): return self.g[e]
    def set_geometry(self,e,**kw):
        g=self.g[e]
        for k,v in kw.items(): setattr(g,k,v)


def test_selection_model_preserves_selection_order_and_primary():
    s=SelectionModel(['a','b'])
    assert s.ids == ('a','b') and s.primary_id=='b'
    s.toggle('c'); assert s.ids==('a','b','c') and s.primary_id=='c'
    s.toggle('b'); assert s.ids==('a','c') and s.primary_id=='c'
    s.toggle('c'); assert s.ids==('a',) and s.primary_id=='a'
    s.replace(['c','a'], primary='c'); assert s.ids==('c','a') and s.primary_id=='c'


def test_align_to_primary_canvas_and_selection_bounds():
    ss=FakeSession()
    align_to(ss,['a','b'],'left',reference='primary',primary_id='b')
    assert ss.g['a'].x==10 and ss.g['b'].x==10
    ss=FakeSession(); align_to(ss,['a','b'],'hcenter',reference='canvas',canvas=(32,16))
    assert ss.g['a'].x==14 and ss.g['b'].x==15
    ss=FakeSession(); align_to(ss,['a','b'],'right',reference='selection')
    assert ss.g['a'].x==9 and ss.g['b'].x==10


def test_selection_metrics_reports_bounds_and_gaps():
    ss=FakeSession(); m=selection_metrics(ss,['a','b','c'])
    assert m.bounds==(1,2,23,9)
    assert m.horizontal_gaps==(6,8)
    assert m.equal_horizontal_spacing is False


def test_pixel_document_resize_anchor_rotate_and_crop_are_undoable():
    d=PixelDocument(3,2,[[1,0,0],[0,1,0]])
    d.resize_canvas(5,4,anchor='center')
    assert (d.width,d.height)==(5,4) and d.get(1,1)==1 and d.get(2,2)==1
    assert d.undo() and (d.width,d.height)==(3,2)
    d.rotate180(); assert d.pixels==[[0,1,0],[0,0,1]]
    d.crop(1,0,2,2); assert (d.width,d.height)==(2,2)


def test_editor_registry_reuses_document_and_routes_active_commands():
    events=[]
    class E:
        def __init__(self,id): self.document_id=id; self.title=id; self.dirty=False
        def save(self): events.append(('save',self.document_id))
        def undo(self): events.append(('undo',self.document_id)); return True
        def redo(self): events.append(('redo',self.document_id)); return True
    r=EditorRegistry(); a=E('scene:main'); b=E('asset:a')
    assert r.open(a) is a and r.open(b) is b
    assert r.open(E('asset:a')) is b
    r.activate('asset:a'); r.save(); r.undo(); r.redo()
    assert events==[('save','asset:a'),('undo','asset:a'),('redo','asset:a')]


def test_font_pack_round_trip_and_ascii_safe_glyph_names(tmp_path):
    pack=create_font_pack(tmp_path/'font','Clinical 5x7',cell=(5,8),baseline=6,advance=6)
    pack.set_glyph('A', [[1,0,1,0,1]]*8, GlyphMetrics(0,0,6))
    pack.save(); loaded=FontPack.load(pack.root)
    assert loaded.name=='Clinical 5x7'
    assert loaded.glyph('A').metrics.advance==6
    assert (pack.root/'glyphs'/'U+0041.png').exists()


def _scene(tmp_path):
    p=tmp_path/'scene.json'
    p.write_text(json.dumps({'canvas':{'w':16,'h':8},'states':{},'elements':[{'id':'a','type':'placeholder','x':1,'y':1,'w':2,'h':2,'draft':True,'allow_draft_export':True}]}),encoding='utf-8')
    return p


def test_automation_revision_guard_transaction_and_read_only(tmp_path):
    svc=StudioAutomationService.for_scene(_scene(tmp_path), permission='edit')
    r0=svc.revision
    result=svc.call('selection.set',{'ids':['a']},expected_revision=r0)
    assert result['ok'] and result['revision']==r0+1
    with pytest.raises(StaleRevisionError): svc.call('scene.update_element',{'id':'a','changes':{'x':3}},expected_revision=r0)
    tx=svc.begin_transaction(expected_revision=svc.revision)
    svc.call('scene.update_element',{'id':'a','changes':{'x':4}},transaction=tx)
    svc.rollback_transaction(tx)
    assert svc.call('scene.get',{})['scene']['elements'][0]['x']==1
    ro=StudioAutomationService.for_scene(_scene(tmp_path),permission='observe')
    with pytest.raises(PermissionDeniedError): ro.call('scene.update_element',{'id':'a','changes':{'x':2}})

def test_bitmap_text_element_renders_fontpack_without_changing_legacy_text(tmp_path):
    from render import render_scene
    pack=create_font_pack(tmp_path/'pack','Tiny',cell=(3,8),baseline=6,advance=4)
    pack.set_glyph('A',[[1,1,1],[1,0,1],[1,1,1],[1,0,1],[1,0,1],[0,0,0],[0,0,0],[0,0,0]],GlyphMetrics(0,0,4));pack.save()
    scene={'canvas':{'w':16,'h':8},'_root':tmp_path,'states':{},'elements':[{'id':'txt','type':'bitmap_text','text':'AA','font_pack':'pack','x':1,'y':0}]}
    result=render_scene(scene,{})
    item=result.resolved_elements[0]
    assert item['w']==7 and item['h']==8 and len(result.framebuffer.to_vlsb())==16

def test_automation_render_validate_layout_and_commit_transaction(tmp_path):
    scene_path=tmp_path/'scene.json'
    scene_path.write_text(json.dumps({'canvas':{'w':16,'h':8},'states':{},'elements':[{'id':'a','type':'placeholder','x':1,'y':1,'w':2,'h':2},{'id':'b','type':'placeholder','x':8,'y':3,'w':2,'h':2}]}),encoding='utf-8')
    svc=StudioAutomationService.for_scene(scene_path,permission='edit')
    svc.call('selection.set',{'ids':['a','b'],'primary_id':'b'},expected_revision=0)
    svc.call('layout.align',{'mode':'left','reference':'primary'},expected_revision=1)
    elems={e['id']:e for e in svc.call('scene.list_elements',{})['elements']}
    assert elems['a']['x']==8 and elems['b']['x']==8
    rendered=svc.call('render.current',{})
    assert rendered['framebuffer']['bytes']==16 and len(rendered['framebuffer']['sha256'])==64
    validation=svc.call('validate.current',{})
    assert validation['blockers']>=1  # placeholders are deliberately draft blockers
    r=svc.revision; tx=svc.begin_transaction(expected_revision=r)
    svc.call('scene.update_element',{'id':'a','changes':{'x':4}},transaction=tx)
    svc.call('scene.update_element',{'id':'b','changes':{'x':4}},transaction=tx)
    result=svc.commit_transaction(tx)
    assert result['revision']==r+1


def test_json_rpc_bridge_dispatches_structured_errors(tmp_path):
    from agent_bridge import dispatch_json_rpc
    svc=StudioAutomationService.for_scene(_scene(tmp_path),permission='observe')
    ok=dispatch_json_rpc(svc,{'jsonrpc':'2.0','id':1,'method':'scene.get','params':{}})
    assert ok['id']==1 and 'result' in ok
    denied=dispatch_json_rpc(svc,{'jsonrpc':'2.0','id':2,'method':'scene.update_element','params':{'id':'a','changes':{'x':2}}})
    assert denied['error']['code']=='PERMISSION_DENIED'

def test_agent_transaction_is_one_designer_undo_step(tmp_path):
    from editor_model import EditorSession
    scene={'canvas':{'w':16,'h':8},'states':{},'elements':[{'id':'a','type':'placeholder','x':1,'y':1,'w':2,'h':2},{'id':'b','type':'placeholder','x':8,'y':3,'w':2,'h':2}]}
    session=EditorSession(scene)
    svc=StudioAutomationService.for_editor(scene,selection_model=SelectionModel(['a','b']),editor_session=session,permission='edit')
    tx=svc.begin_transaction(expected_revision=0)
    svc.call('scene.update_element',{'id':'a','changes':{'x':4}},transaction=tx)
    svc.call('scene.update_element',{'id':'b','changes':{'x':4}},transaction=tx)
    svc.commit_transaction(tx)
    assert scene['elements'][0]['x']==4 and scene['elements'][1]['x']==4
    assert session.undo() is True
    assert scene['elements'][0]['x']==1 and scene['elements'][1]['x']==8
    assert session.undo() is False

def test_single_agent_scene_edit_is_undoable_in_designer():
    from editor_model import EditorSession
    scene={'canvas':{'w':16,'h':8},'states':{},'elements':[{'id':'a','type':'placeholder','x':1,'y':1,'w':2,'h':2}]}
    session=EditorSession(scene);svc=StudioAutomationService.for_editor(scene,editor_session=session,permission='edit')
    svc.call('scene.update_element',{'id':'a','changes':{'x':7}},expected_revision=0)
    assert scene['elements'][0]['x']==7 and session.undo()
    assert scene['elements'][0]['x']==1

def test_automation_pixel_and_font_surfaces(tmp_path):
    from PIL import Image
    img=Image.new('1',(8,8),0); img.putpixel((1,1),255); img.save(tmp_path/'a.png')
    scene_path=tmp_path/'scene.json'; scene_path.write_text(json.dumps({'canvas':{'w':16,'h':8},'states':{},'elements':[]}),encoding='utf-8')
    svc=StudioAutomationService.for_scene(scene_path,permission='full')
    opened=svc.call('pixel.open',{'path':'a.png'}); did=opened['document_id']
    svc.call('pixel.paint',{'document_id':did,'x':2,'y':2,'value':1})
    got=svc.call('pixel.get_document',{'document_id':did})
    assert got['pixels'][2][2]==1
    svc.call('pixel.resize_canvas',{'document_id':did,'width':16,'height':8,'anchor':'left'})
    svc.call('pixel.save',{'document_id':did,'path':'assets/a_edit.png'})
    assert (tmp_path/'assets/a_edit.png').exists()
    made=svc.call('font.create_pack',{'path':'.oled/fonts/ai','name':'AI Font','cell':[5,8],'baseline':6,'advance':6})
    svc.call('font.generate_glyphs',{'font_id':made['font_id'],'characters':'AB','font_size':8})
    listing=svc.call('font.list',{})
    assert any(x['font_id']==made['font_id'] for x in listing['fonts'])
    glyph=svc.call('font.get_glyph',{'font_id':made['font_id'],'char':'A'})
    assert len(glyph['pixels'])==8 and len(glyph['pixels'][0])==5

def test_automation_render_surfaces_include_png_framebuffer_resolved_and_diff(tmp_path):
    import base64
    from PIL import Image
    asset=Image.new('1',(3,3),1); asset.save(tmp_path/'box.png')
    scene_path=tmp_path/'scene.json'
    scene_path.write_text(json.dumps({
        'canvas':{'w':16,'h':8},
        'states':{'phase':{'values':['standby','running'],'default':'standby'}},
        'elements':[{'id':'box','type':'image','asset':'box.png','x':1,'y':1,'visible_when':{'phase':'running'}}],
    }),encoding='utf-8')
    svc=StudioAutomationService.for_scene(scene_path,permission='observe')
    png=svc.call('render.png',{'state':{'phase':'running'}})
    assert base64.b64decode(png['png_base64']).startswith(b'\x89PNG\r\n\x1a\n')
    fb=svc.call('render.framebuffer',{'state':{'phase':'running'}})
    assert fb['framebuffer']['bytes']==16 and len(fb['framebuffer']['sha256'])==64
    resolved=svc.call('render.resolved_elements',{'state':{'phase':'running'}})
    assert resolved['resolved_elements'][0]['id']=='box'
    diff=svc.call('render.pixel_diff',{'before_state':{'phase':'standby'},'after_state':{'phase':'running'}})
    assert diff['changed_pixels']>0 and diff['bbox'] is not None


def test_agent_bridge_socket_requires_token_and_roundtrips_jsonrpc(tmp_path):
    import json as _json, socket, threading
    from agent_bridge import LocalAgentBridgeServer, dispatch_json_rpc
    svc=StudioAutomationService.for_scene(_scene(tmp_path),permission='observe')
    server=LocalAgentBridgeServer(lambda req:dispatch_json_rpc(svc,req),port=0,session_token='secret-token')
    thread=threading.Thread(target=server.serve_forever,daemon=True); thread.start()
    try:
        with socket.create_connection(('127.0.0.1',server.server_address[1]),timeout=2) as sock:
            f=sock.makefile('rwb')
            f.write((_json.dumps({'jsonrpc':'2.0','id':1,'method':'scene.get','params':{},'token':'bad'})+'\n').encode());f.flush()
            denied=_json.loads(f.readline());assert denied['error']['code']=='UNAUTHORIZED'
            f.write((_json.dumps({'jsonrpc':'2.0','id':2,'method':'scene.get','params':{},'token':'secret-token'})+'\n').encode());f.flush()
            ok=_json.loads(f.readline());assert ok['id']==2 and ok['result']['ok'] is True
    finally:
        server.shutdown();server.server_close();thread.join(timeout=2)

def test_fontpack_compose_text_produces_exact_bitmap_for_pixel_insertion(tmp_path):
    pack=create_font_pack(tmp_path/'pack','Tiny',cell=(3,8),baseline=6,advance=4)
    a=[[1,0,1],[0,1,0],[1,1,1],[0,0,0],[0,0,0],[0,0,0],[0,0,0],[0,0,0]]
    pack.set_glyph('A',a,GlyphMetrics(0,0,4));pack.save()
    bitmap=pack.compose_text('AA',tracking=0)
    assert len(bitmap)==8 and len(bitmap[0])==7
    assert bitmap[0]==[1,0,1,0,1,0,1]
    doc=PixelDocument(16,8);doc.paste_region(2,0,bitmap)
    assert doc.pixels[0][2:9]==bitmap[0]

def test_pixel_document_can_insert_fontpack_text_as_one_undo_step(tmp_path):
    from pixel_studio import insert_fontpack_text
    pack=create_font_pack(tmp_path/'pack','Tiny',cell=(3,8),baseline=6,advance=4)
    pack.set_glyph('A',[[1,1,1],[1,0,1],[1,1,1],[1,0,1],[1,0,1],[0,0,0],[0,0,0],[0,0,0]],GlyphMetrics(0,0,4));pack.save()
    doc=PixelDocument(16,8)
    insert_fontpack_text(doc,pack,'AA',2,0)
    assert any(doc.pixels[y][x] for y in range(8) for x in range(2,9))
    assert doc.undo() is True
    assert all(v==0 for row in doc.pixels for v in row)
    assert doc.undo() is False

def test_automation_project_observation_and_save_surface(tmp_path):
    scene_path=tmp_path/'scene.json'
    scene_path.write_text(json.dumps({'canvas':{'w':16,'h':8},'states':{},'elements':[]}),encoding='utf-8')
    svc=StudioAutomationService.for_scene(scene_path,permission='edit')
    info=svc.call('project.get',{})
    assert info['project_root']==str(tmp_path.resolve()) and info['scene_path']==str(scene_path.resolve())
    svc.call('scene.create_element',{'element':{'id':'a','type':'placeholder','x':1,'y':1,'w':2,'h':2}},expected_revision=0)
    saved=svc.call('project.save',{},expected_revision=1)
    assert saved['saved'] is True
    raw=json.loads(scene_path.read_text(encoding='utf-8'))
    assert raw['elements'][0]['id']=='a' and '_root' not in raw and '_path' not in raw

def test_v80_new_workspace_i18n_keys_exist_in_both_languages():
    from i18n import ZH, EN
    keys={
        'panel.fonts','action.new_font','action.open_font','action.bitmap_text','align.reference','align.selection_bounds','align.primary','align.canvas',
        'pixel.section.text_font','pixel.action.insert_bitmap_text','pixel.section.transform','pixel.action.canvas_size','pixel.action.rotate90','pixel.action.rotate180','pixel.action.rotate270','pixel.action.crop_selection',
        'font.title','font.characters','font.source','font.generate','font.save_glyph','font.cell_width','font.cell_height','font.baseline','font.advance','font.threshold',
        'agent.off','agent.connected'
    }
    assert keys <= set(ZH) and keys <= set(EN)
    assert all(ZH[k] and EN[k] and ZH[k]!=k and EN[k]!=k for k in keys)
