from __future__ import annotations
from dataclasses import dataclass
from io import BytesIO
import json
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

from atomic_io import atomic_write_bytes, atomic_write_text

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
    chars=list(dict.fromkeys(str(characters)))
    if not chars: raise ValueError('characters must not be empty')
    font_size=int(font_size); threshold=int(threshold)
    if font_size<=0: raise ValueError('font_size must be greater than 0')
    if not 0<=threshold<=255: raise ValueError('threshold must be between 0 and 255')
    w,h=map(int,cell)
    if w<=0 or h<=0 or h%8: raise ValueError('cell must be positive and height a multiple of 8')
    out=Path(output_dir); out.mkdir(parents=True,exist_ok=True); font=_font(font_path,font_size)
    previous_managed: set[str]=set()
    previous_manifest=out/'glyph_manifest.json'
    if previous_manifest.exists():
        try:
            previous=json.loads(previous_manifest.read_text(encoding='utf-8'))
            for meta in (previous.get('glyphs',{}) if isinstance(previous,dict) else {}).values():
                filename=meta.get('file') if isinstance(meta,dict) else None
                if isinstance(filename,str) and Path(filename).name==filename and filename.startswith('U+') and filename.endswith('.png'):
                    previous_managed.add(filename)
        except (OSError, UnicodeError, json.JSONDecodeError):
            previous_managed=set()
    manifest={'cell':{'w':w,'h':h},'font_size':font_size,'glyphs':{}}
    arrays=[]; png_payloads: dict[str,bytes]={}
    for ch in chars:
        img=Image.new('L',(w,h),0); d=ImageDraw.Draw(img)
        bbox=d.textbbox((0,0),ch,font=font)
        tw=bbox[2]-bbox[0]; th=bbox[3]-bbox[1]
        x=(w-tw)//2-bbox[0]; y=(h-th)//2-bbox[1]
        d.text((x,y),ch,font=font,fill=255)
        img=img.point(lambda p:255 if p>=threshold else 0,mode='1')
        filename=f'U+{ord(ch):04X}.png'
        buf=BytesIO(); img.save(buf,format='PNG',optimize=False); png_payloads[filename]=buf.getvalue()
        raw=_vlsb_from_image(img)
        name=f'glyph_{ord(ch):04X}'
        arrays.append(f'static const unsigned char {name}[{len(raw)}] = {{'+','.join(f'0x{b:02X}' for b in raw)+'};')
        manifest['glyphs'][ch]={'file':filename,'w':w,'h':h,'bytes':len(raw),'symbol':name}
    for filename,payload in png_payloads.items(): atomic_write_bytes(out/filename,payload)
    atomic_write_text(out/'glyph_manifest.json',json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    atomic_write_text(out/'glyphs.h','#pragma once\n\n'+'\n'.join(arrays)+'\n')
    expected=set(png_payloads)
    for filename in sorted(previous_managed-expected):
        (out/filename).unlink(missing_ok=True)
    return GlyphResult(len(chars),out)
