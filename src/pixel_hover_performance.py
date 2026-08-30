from __future__ import annotations


def _damage_rect(pixel, zoom: int):
    if pixel is None:
        return None
    z=max(1,int(zoom)); x,y=(int(pixel[0]),int(pixel[1]))
    # One-pixel safety halo covers the 1px hover stroke without repainting the
    # entire zoomed canvas.
    return (x*z-1, y*z-1, z+2, z+2)


def hover_damage_rects(previous, current, zoom: int) -> tuple[tuple[int,int,int,int], ...]:
    if previous == current:
        return ()
    out=[]
    for pixel in (previous,current):
        rect=_damage_rect(pixel,zoom)
        if rect is not None and rect not in out:
            out.append(rect)
    return tuple(out)
