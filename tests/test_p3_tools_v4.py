import sys
from pathlib import Path
from PIL import Image
SIM=Path(__file__).resolve().parents[1] / 'src'; sys.path.insert(0,str(SIM))
from asset_convert import convert_bitmap
from assets import load_bitmap
from c_export import framebuffer_to_c_header
from framebuffer import FrameBuffer
from thumbnail_wall import build_thumbnail_wall
from design_rules import check_design_rules


def test_asset_converter_writes_canonical_black_background_white_lit_png(tmp_path):
    src=tmp_path/'src.png'; out=tmp_path/'out.png'
    im=Image.new('RGB',(3,3),'white'); im.putpixel((1,1),(0,0,0)); im.save(src)
    convert_bitmap(src,out)
    a=load_bitmap(out)
    assert a.source_polarity=='white_on_black'
    assert a.pixels[1][1]==1 and a.pixels[0][0]==0


def test_c_header_exports_dynamic_vlsb_bytes():
    fb=FrameBuffer(8,8); fb.set_pixel(0,0,True); fb.set_pixel(7,7,True)
    text=framebuffer_to_c_header(fb,'demo')
    assert 'demo_width = 8' in text and 'demo_height = 8' in text
    assert '0x01' in text and '0x80' in text


def test_thumbnail_wall_builds_contact_sheet(tmp_path):
    a=Image.new('1',(8,8),0); a.putpixel((0,0),1); a.save(tmp_path/'a.png')
    b=Image.new('1',(8,8),0); b.putpixel((7,7),1); b.save(tmp_path/'b.png')
    out=tmp_path/'wall.png'
    build_thumbnail_wall([tmp_path/'a.png',tmp_path/'b.png'],out,columns=2,scale=4)
    with Image.open(out) as im:
        assert im.width>=64 and im.height>=32


def test_design_rules_support_optional_required_elements_and_safe_zones():
    scene={'canvas':{'w':32,'h':16},'elements':[{'id':'hero','type':'placeholder','x':2,'y':2,'w':8,'h':8}]}
    rules={'required_elements':['hero','battery'],'zones':{'hero':{'x':0,'y':0,'w':16,'h':16}}}
    findings=check_design_rules(scene,rules)
    assert any(f.code=='REQUIRED_ELEMENT_MISSING' for f in findings)
    assert not any(f.code=='ELEMENT_OUTSIDE_ZONE' and f.element_id=='hero' for f in findings)
