from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import json
from io import BytesIO
from PIL import Image
from atomic_io import atomic_write_bytes, atomic_write_json

@dataclass(frozen=True)
class GlyphMetrics:
    bearing_x: int=0
    bearing_y: int=0
    advance: int=0

@dataclass
class Glyph:
    char: str
    pixels: list[list[int]]
    metrics: GlyphMetrics

class FontPack:
    SCHEMA=1
    def __init__(self, root: str|Path, name: str, *, cell: tuple[int,int], baseline: int, advance: int):
        self.root=Path(root); self.name=str(name); self.cell=tuple(map(int,cell)); self.baseline=int(baseline); self.advance=int(advance); self._glyphs={}
    @property
    def manifest_path(self): return self.root/'fontpack.json'
    def set_glyph(self,char,pixels,metrics:GlyphMetrics|None=None):
        if len(char)!=1: raise ValueError('glyph key must be one Unicode character')
        w,h=self.cell
        rows=[[1 if v else 0 for v in row] for row in pixels]
        if len(rows)!=h or any(len(row)!=w for row in rows): raise ValueError('glyph dimensions do not match font cell')
        self._glyphs[char]=Glyph(char,rows,metrics or GlyphMetrics(0,0,self.advance))
    def glyph(self,char): return self._glyphs[char]
    def characters(self): return tuple(self._glyphs)
    def compose_text(self,text: str,*,tracking: int=0) -> list[list[int]]:
        """Compose exact stored glyph pixels into one monochrome bitmap."""
        text=str(text)
        if not text:return [[] for _ in range(self.cell[1])]
        missing=[ch for ch in text if ch not in self._glyphs]
        if missing:raise KeyError(f'missing glyphs: {missing}')
        starts=[];cursor=0;right=0
        for i,ch in enumerate(text):
            glyph=self._glyphs[ch];start=cursor+glyph.metrics.bearing_x;starts.append((start,glyph));right=max(right,start+self.cell[0])
            cursor+=glyph.metrics.advance+(int(tracking) if i<len(text)-1 else 0)
        left=min(0,min(start for start,_ in starts));width=max(0,right-left);rows=[[0 for _ in range(width)] for __ in range(self.cell[1])]
        for start,glyph in starts:
            x0=start-left;y0=glyph.metrics.bearing_y
            for gy,row in enumerate(glyph.pixels):
                ty=gy+y0
                if not 0<=ty<len(rows):continue
                for gx,value in enumerate(row):
                    tx=x0+gx
                    if value and 0<=tx<width:rows[ty][tx]=1
        return rows
    def save(self):
        self.root.mkdir(parents=True,exist_ok=True); gd=self.root/'glyphs'; gd.mkdir(exist_ok=True)
        manifest={'schema':self.SCHEMA,'name':self.name,'cell':{'w':self.cell[0],'h':self.cell[1]},'baseline':self.baseline,'advance':self.advance,'glyphs':{}}
        for ch,g in self._glyphs.items():
            fn=f'U+{ord(ch):04X}.png'; img=Image.new('1',self.cell,0); px=img.load()
            for y,row in enumerate(g.pixels):
                for x,v in enumerate(row): px[x,y]=255 if v else 0
            buf=BytesIO(); img.save(buf,format='PNG',optimize=False); atomic_write_bytes(gd/fn,buf.getvalue())
            manifest['glyphs'][ch]={'asset':f'glyphs/{fn}','bearing_x':g.metrics.bearing_x,'bearing_y':g.metrics.bearing_y,'advance':g.metrics.advance}
        atomic_write_json(self.manifest_path,manifest)
        return self.manifest_path
    @classmethod
    def load(cls, root):
        root=Path(root); data=json.loads((root/'fontpack.json').read_text(encoding='utf-8'))
        pack=cls(root,data['name'],cell=(data['cell']['w'],data['cell']['h']),baseline=data.get('baseline',data['cell']['h']-1),advance=data.get('advance',data['cell']['w']))
        for ch,meta in data.get('glyphs',{}).items():
            with Image.open(root/meta['asset']) as im: img=im.convert('1'); rows=[[1 if img.getpixel((x,y)) else 0 for x in range(img.width)] for y in range(img.height)]
            pack.set_glyph(ch,rows,GlyphMetrics(int(meta.get('bearing_x',0)),int(meta.get('bearing_y',0)),int(meta.get('advance',pack.advance))))
        return pack

def create_font_pack(root,name,*,cell=(5,8),baseline=7,advance=None):
    return FontPack(root,name,cell=cell,baseline=baseline,advance=int(advance if advance is not None else cell[0]))

def rasterize_characters(pack: FontPack, characters: str, *, font_path: str|Path|None=None, font_size: int=12, threshold: int=128, offset: tuple[int,int]=(0,0), weight: str='normal') -> int:
    """Rasterize unique characters into an existing FontPack deterministically."""
    from PIL import ImageDraw, ImageFont
    chars=list(dict.fromkeys(str(characters)))
    if not chars:return 0
    if font_path:
        font=ImageFont.truetype(str(font_path),size=int(font_size))
    else:
        try:font=ImageFont.truetype('DejaVuSans.ttf',size=int(font_size))
        except OSError:font=ImageFont.load_default()
    w,h=pack.cell; ox,oy=map(int,offset)
    for ch in chars:
        img=Image.new('L',(w,h),0); d=ImageDraw.Draw(img); bbox=d.textbbox((0,0),ch,font=font)
        tw=bbox[2]-bbox[0]; th=bbox[3]-bbox[1]
        x=(w-tw)//2-bbox[0]+ox; y=(h-th)//2-bbox[1]+oy
        d.text((x,y),ch,font=font,fill=255)
        rows=[[1 if img.getpixel((x,y))>=int(threshold) else 0 for x in range(w)] for y in range(h)]
        pack.set_glyph(ch,rows,GlyphMetrics(0,0,pack.advance))
    pack.save();return len(chars)
