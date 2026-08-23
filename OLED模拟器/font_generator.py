from __future__ import annotations
from dataclasses import dataclass
import json
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

@dataclass(frozen=True)
class GlyphResult:
    count: int
    output_dir: Path


def _font(font_path: str | Path | None, size: int):
    if font_path:
        return ImageFont.truetype(str(font_path), size=size)
    try:
        return ImageFont.truetype('DejaVuSans.ttf', size=size)
    except OSError:
        return ImageFont.load_default()


def _vlsb_from_image(img: Image.Image) -> bytes:
    w,h=img.size
    if h % 8: raise ValueError('glyph cell height must be a multiple of 8')
    px=img.load(); out=bytearray(w*(h//8))
    for y in range(h):
        for x in range(w):
            if px[x,y]: out[(y//8)*w+x] |= 1<<(y%8)
    return bytes(out)


def generate_glyphs(characters: str, *, output_dir: str | Path, font_path: str | Path | None = None,
                    font_size: int = 12, cell: tuple[int,int] = (12,16), threshold: int = 128) -> GlyphResult:
    chars=list(dict.fromkeys(characters))
    if not chars: raise ValueError('characters must not be empty')
    w,h=map(int,cell)
    if w<=0 or h<=0 or h%8: raise ValueError('cell must be positive and height a multiple of 8')
    out=Path(output_dir); out.mkdir(parents=True,exist_ok=True); font=_font(font_path,font_size)
    manifest={'cell':{'w':w,'h':h},'font_size':font_size,'glyphs':{}}
    arrays=[]
    for ch in chars:
        img=Image.new('L',(w,h),0); d=ImageDraw.Draw(img)
        bbox=d.textbbox((0,0),ch,font=font)
        tw=bbox[2]-bbox[0]; th=bbox[3]-bbox[1]
        x=(w-tw)//2-bbox[0]; y=(h-th)//2-bbox[1]
        d.text((x,y),ch,font=font,fill=255)
        img=img.point(lambda p:255 if p>=threshold else 0,mode='1')
        filename=f'U+{ord(ch):04X}.png'; img.save(out/filename)
        raw=_vlsb_from_image(img)
        name=f'glyph_{ord(ch):04X}'
        arrays.append(f'static const unsigned char {name}[{len(raw)}] = {{'+','.join(f'0x{b:02X}' for b in raw)+'};')
        manifest['glyphs'][ch]={'file':filename,'w':w,'h':h,'bytes':len(raw),'symbol':name}
    (out/'glyph_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    (out/'glyphs.h').write_text('#pragma once\n\n'+'\n'.join(arrays)+'\n',encoding='utf-8')
    return GlyphResult(len(chars),out)
