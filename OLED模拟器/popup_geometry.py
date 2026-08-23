from __future__ import annotations
from dataclasses import dataclass

@dataclass(frozen=True)
class Size:
    w:int; h:int

@dataclass(frozen=True)
class Rect:
    x:int; y:int; w:int; h:int
    @property
    def right(self): return self.x+self.w
    @property
    def bottom(self): return self.y+self.h


def place_popup(anchor:Rect, desired:Size, screen:Rect, *, gap:int=4, margin:int=4)->Rect:
    left=screen.x+margin; top=screen.y+margin; right=screen.right-margin; bottom=screen.bottom-margin
    max_w=max(1,right-left); max_h=max(1,bottom-top)
    w=min(max(1,int(desired.w)),max_w); h=min(max(1,int(desired.h)),max_h)
    x=min(max(anchor.x,left),max(left,right-w))
    below=anchor.bottom+gap
    above=anchor.y-gap-h
    if below+h<=bottom:
        y=below
    elif above>=top:
        y=above
    else:
        below_space=max(0,bottom-below); above_space=max(0,anchor.y-gap-top)
        if below_space>=above_space:
            y=below; h=max(1,min(h,below_space))
        else:
            h=max(1,min(h,above_space)); y=anchor.y-gap-h
    y=min(max(y,top),max(top,bottom-h))
    return Rect(int(x),int(y),int(w),int(h))


def content_popup_width(anchor_width:int, text_widths, *, horizontal_padding:int=34, minimum:int=72, maximum:int=360)->int:
    """Content-aware popup width without a global legacy 180px floor.

    ``text_widths`` are measured by the active UI font in production and can
    be injected directly by host tests.  The popup never becomes narrower
    than its anchor, but short enumerations remain compact.
    """
    anchor=max(1,int(anchor_width))
    minimum=max(1,int(minimum)); maximum=max(minimum,int(maximum))
    widest=max([0,*[max(0,int(v)) for v in text_widths]])
    desired=max(anchor,minimum,widest+max(0,int(horizontal_padding)))
    return min(desired,maximum)
