from __future__ import annotations
import re
from pathlib import Path
from framebuffer import FrameBuffer
from atomic_io import atomic_write_text


def _ident(name: str) -> str:
    value=re.sub(r'[^A-Za-z0-9_]+','_',str(name)).strip('_') or 'oled_frame'
    if value[0].isdigit(): value='_'+value
    return value


def framebuffer_to_c_header(framebuffer: FrameBuffer, name: str='oled_frame') -> str:
    ident=_ident(name)
    raw=framebuffer.to_vlsb()
    lines=[]
    for i in range(0,len(raw),16):
        lines.append('    '+', '.join(f'0x{b:02X}' for b in raw[i:i+16])+',')
    return (
        '#pragma once\n#include <stdint.h>\n\n'
        f'static const uint16_t {ident}_width = {framebuffer.width};\n'
        f'static const uint16_t {ident}_height = {framebuffer.height};\n'
        f'static const uint16_t {ident}_bytes = {len(raw)};\n'
        f'static const uint8_t {ident}[{len(raw)}] = {{\n'+'\n'.join(lines)+'\n};\n'
    )


def write_c_header(framebuffer: FrameBuffer, path: str | Path, name: str='oled_frame') -> Path:
    path=Path(path); path.parent.mkdir(parents=True,exist_ok=True)
    atomic_write_text(path,framebuffer_to_c_header(framebuffer,name),encoding='utf-8')
    return path
