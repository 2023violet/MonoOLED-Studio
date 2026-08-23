from __future__ import annotations

from collections import deque
from copy import deepcopy
from pathlib import Path
from typing import Iterable

from PIL import Image


class PixelDocument:
    def __init__(self, width: int, height: int, pixels: list[list[int]] | None = None, *, max_undo: int = 200):
        if width <= 0 or height <= 0:
            raise ValueError('width and height must be positive')
        self.width = int(width); self.height = int(height)
        self.pixels = pixels if pixels is not None else [[0] * self.width for _ in range(self.height)]
        self.max_undo = max(1, int(max_undo))
        self._undo: list[tuple[int, int, list[list[int]]]] = []
        self._redo: list[tuple[int, int, list[list[int]]]] = []
        self._gesture_before: tuple[int, int, list[list[int]]] | None = None
        self.dirty = False

    @classmethod
    def from_image(cls, path: str | Path, *, threshold: int = 128, invert: bool = False, max_pixels: int = 4_194_304, max_dimension: int = 4096) -> 'PixelDocument':
        with Image.open(path) as source:
            w, h = source.size
            if w <= 0 or h <= 0 or w > int(max_dimension) or h > int(max_dimension) or w * h > int(max_pixels):
                raise ValueError(f'image too large for Pixel Studio: {w}x{h}')
            img = source.convert('L')
        rows=[]
        for y in range(h):
            row=[]
            for x in range(w):
                value = 1 if img.getpixel((x,y)) >= threshold else 0
                row.append(1-value if invert else value)
            rows.append(row)
        return cls(w,h,rows)

    def begin_gesture(self):
        if self._gesture_before is None:
            self._gesture_before = self._state()

    def end_gesture(self):
        if self._gesture_before is None:
            return
        before=self._gesture_before; self._gesture_before=None
        if before != self._state():
            self._push_undo(before); self._redo.clear(); self.dirty=True

    def _state(self) -> tuple[int, int, list[list[int]]]:
        return self.width, self.height, deepcopy(self.pixels)

    def _restore_state(self, state: tuple[int, int, list[list[int]]]) -> None:
        self.width, self.height, pixels = state
        self.pixels = deepcopy(pixels)

    def _push_undo(self, state: tuple[int, int, list[list[int]]]) -> None:
        self._undo.append(state)
        if len(self._undo) > self.max_undo:
            del self._undo[:len(self._undo) - self.max_undo]

    def _snapshot(self):
        if self._gesture_before is not None:
            self.dirty=True; return
        self._push_undo(self._state()); self._redo.clear(); self.dirty = True


    def set_max_undo(self, limit: int) -> None:
        self.max_undo = max(1, int(limit))
        if len(self._undo) > self.max_undo:
            del self._undo[:len(self._undo) - self.max_undo]
        if len(self._redo) > self.max_undo:
            del self._redo[:len(self._redo) - self.max_undo]

    def stroke_segment(self, x0: int, y0: int, x1: int, y1: int, value: int = 1) -> None:
        """Rasterize a continuous mouse stroke segment with integer Bresenham.

        When called inside begin_gesture()/end_gesture(), any number of segments
        still produce exactly one undo transaction.
        """
        self.line(x0, y0, x1, y1, value=value)

    def _brush_raw(self, x: int, y: int, value: int, size: int) -> None:
        size=max(1,int(size)); left=(size-1)//2; right=size//2
        for yy in range(y-left,y+right+1):
            for xx in range(x-left,x+right+1):
                self._set_raw(xx,yy,value)

    def brush(self, x: int, y: int, value: int = 1, *, size: int = 1) -> None:
        self._snapshot(); self._brush_raw(x,y,value,size)

    def brush_segment(self, x0: int, y0: int, x1: int, y1: int, value: int = 1, *, size: int = 1) -> None:
        """Continuous Bresenham stroke with a square brush footprint."""
        self._snapshot()
        dx=abs(x1-x0); sx=1 if x0<x1 else -1; dy=-abs(y1-y0); sy=1 if y0<y1 else -1; err=dx+dy
        while True:
            self._brush_raw(x0,y0,value,size)
            if x0==x1 and y0==y1: break
            e2=2*err
            if e2>=dy: err+=dy; x0+=sx
            if e2<=dx: err+=dx; y0+=sy

    def get(self, x: int, y: int) -> int:
        return self.pixels[y][x]

    def _set_raw(self, x: int, y: int, value: int):
        if 0 <= x < self.width and 0 <= y < self.height:
            self.pixels[y][x] = 1 if value else 0

    def pencil(self, x: int, y: int, value: int = 1):
        self._snapshot(); self._set_raw(x,y,value)

    def erase(self, x: int, y: int):
        self.pencil(x,y,0)

    def line(self, x0: int, y0: int, x1: int, y1: int, value: int = 1):
        self._snapshot()
        dx=abs(x1-x0); sx=1 if x0<x1 else -1; dy=-abs(y1-y0); sy=1 if y0<y1 else -1; err=dx+dy
        while True:
            self._set_raw(x0,y0,value)
            if x0==x1 and y0==y1: break
            e2=2*err
            if e2>=dy: err+=dy; x0+=sx
            if e2<=dx: err+=dx; y0+=sy

    def rectangle(self, x0: int, y0: int, x1: int, y1: int, *, filled: bool = False, value: int = 1):
        self._snapshot(); xa,xb=sorted((x0,x1)); ya,yb=sorted((y0,y1))
        for y in range(ya,yb+1):
            for x in range(xa,xb+1):
                if filled or x in (xa,xb) or y in (ya,yb): self._set_raw(x,y,value)

    def flood_fill(self, x: int, y: int, value: int):
        target=self.get(x,y); value=1 if value else 0
        if target==value: return
        self._snapshot(); q=deque([(x,y)])
        while q:
            cx,cy=q.popleft()
            if not (0<=cx<self.width and 0<=cy<self.height) or self.pixels[cy][cx]!=target: continue
            self.pixels[cy][cx]=value
            q.extend(((cx+1,cy),(cx-1,cy),(cx,cy+1),(cx,cy-1)))

    def clear(self, value: int = 0):
        self._snapshot(); self.pixels=[[1 if value else 0]*self.width for _ in range(self.height)]

    def invert(self):
        self._snapshot(); self.pixels=[[1-v for v in row] for row in self.pixels]

    def flip_horizontal(self):
        self._snapshot(); self.pixels=[list(reversed(row)) for row in self.pixels]

    def flip_vertical(self):
        self._snapshot(); self.pixels=list(reversed(self.pixels))

    def rotate90(self):
        if self.width % 8:
            raise ValueError('rotated height must be a multiple of 8')
        self._snapshot(); old=self.pixels; old_w=self.width; old_h=self.height
        self.pixels=[[old[old_h-1-y][x] for y in range(old_h)] for x in range(old_w)]
        self.width,self.height=old_h,old_w

    def copy_region(self, x: int, y: int, w: int, h: int) -> list[list[int]]:
        return [[self.get(x+cx,y+cy) for cx in range(w)] for cy in range(h)]

    def paste_region(self, x: int, y: int, region: Iterable[Iterable[int]]):
        self._snapshot()
        for ry,row in enumerate(region):
            for rx,value in enumerate(row): self._set_raw(x+rx,y+ry,int(value))

    def move_region(self, x: int, y: int, w: int, h: int, dx: int, dy: int) -> None:
        if w <= 0 or h <= 0 or (dx == 0 and dy == 0):
            return
        region = self.copy_region(x, y, w, h)
        self._snapshot()
        for yy in range(y, y + h):
            for xx in range(x, x + w):
                self._set_raw(xx, yy, 0)
        for ry, row in enumerate(region):
            for rx, value in enumerate(row):
                self._set_raw(x + dx + rx, y + dy + ry, int(value))

    def resize_canvas(self, width: int, height: int, *, anchor: str = "center") -> None:
        width=int(width); height=int(height)
        if width<=0 or height<=0: raise ValueError("width and height must be positive")
        anchors={
            "top-left":(0,0), "top":(0.5,0), "top-right":(1,0),
            "left":(0,0.5), "center":(0.5,0.5), "right":(1,0.5),
            "bottom-left":(0,1), "bottom":(0.5,1), "bottom-right":(1,1),
        }
        if anchor not in anchors: raise ValueError("unsupported anchor")
        ax,ay=anchors[anchor]
        self._snapshot(); old=self.pixels; ow,oh=self.width,self.height
        dx=round((width-ow)*ax); dy=round((height-oh)*ay)
        new=[[0]*width for _ in range(height)]
        for y,row in enumerate(old):
            for x,value in enumerate(row):
                nx,ny=x+dx,y+dy
                if 0<=nx<width and 0<=ny<height: new[ny][nx]=value
        self.width,self.height,self.pixels=width,height,new

    def rotate180(self) -> None:
        self._snapshot(); self.pixels=[list(reversed(row)) for row in reversed(self.pixels)]

    def rotate270(self) -> None:
        self._snapshot(); old=self.pixels; ow,oh=self.width,self.height
        self.pixels=[[old[y][ow-1-x] for y in range(oh)] for x in range(ow)]
        self.width,self.height=oh,ow

    def crop(self, x: int, y: int, w: int, h: int) -> None:
        x=int(x); y=int(y); w=int(w); h=int(h)
        if w<=0 or h<=0: raise ValueError("crop width and height must be positive")
        if x<0 or y<0 or x+w>self.width or y+h>self.height: raise ValueError("crop outside document")
        self._snapshot(); self.pixels=[row[x:x+w] for row in self.pixels[y:y+h]]; self.width,self.height=w,h

    def undo(self) -> bool:
        if not self._undo: return False
        self._redo.append(self._state())
        self._restore_state(self._undo.pop())
        self.dirty=True
        return True

    def redo(self) -> bool:
        if not self._redo: return False
        self._push_undo(self._state())
        self._restore_state(self._redo.pop())
        self.dirty=True
        return True

    def to_vlsb(self) -> bytes:
        out=bytearray(self.width*((self.height+7)//8))
        for y,row in enumerate(self.pixels):
            page=y//8; bit=y%8
            for x,value in enumerate(row):
                if value: out[page*self.width+x] |= 1<<bit
        return bytes(out)

    def to_c_header(self, symbol: str = 'oled_bitmap') -> str:
        clean=''.join(ch if ch.isascii() and (ch.isalnum() or ch=='_') else '_' for ch in str(symbol)).strip('_') or 'oled_bitmap'
        if clean[0].isdigit(): clean='bitmap_'+clean
        macro=clean.upper()
        raw=self.to_vlsb()
        lines=[]
        for i in range(0,len(raw),12):
            lines.append('    '+', '.join(f'0x{b:02X}' for b in raw[i:i+12])+',')
        body='\n'.join(lines)
        return (f'#define {macro}_WIDTH {self.width}\n'
                f'#define {macro}_HEIGHT {self.height}\n'
                f'#define {macro}_BYTES {len(raw)}\n\n'
                f'static const unsigned char {clean}[] = {{\n{body}\n}};\n')

    def save_c_header(self, path: str | Path, symbol: str = 'oled_bitmap') -> Path:
        target=Path(path); target.parent.mkdir(parents=True,exist_ok=True); target.write_text(self.to_c_header(symbol),encoding='utf-8'); return target

    def save_png(self, path: str | Path) -> Path:
        target=Path(path); target.parent.mkdir(parents=True,exist_ok=True)
        img=Image.new('1',(self.width,self.height),0); px=img.load()
        for y,row in enumerate(self.pixels):
            for x,v in enumerate(row): px[x,y]=255 if v else 0
        img.save(target); self.dirty=False; return target

    def save_bin(self, path: str | Path) -> Path:
        target=Path(path); target.parent.mkdir(parents=True,exist_ok=True); target.write_bytes(self.to_vlsb()); return target


def insert_fontpack_text(document: PixelDocument, font_pack, text: str, x: int, y: int, *, tracking: int = 0) -> tuple[int,int]:
    """Raster-paste exact FontPack glyphs as one undoable PixelDocument edit."""
    bitmap=font_pack.compose_text(str(text),tracking=int(tracking))
    width=len(bitmap[0]) if bitmap and bitmap[0] else 0
    height=len(bitmap)
    if width and height:document.paste_region(int(x),int(y),bitmap)
    return width,height
