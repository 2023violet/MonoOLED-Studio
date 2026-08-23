from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from PIL import Image

from framebuffer import FrameBuffer


@dataclass(frozen=True)
class PixelDiff:
    width: int
    height: int
    changed_pixels: int
    percent: float
    bbox: tuple[int, int, int, int] | None
    mask: tuple[tuple[int, ...], ...]
    added: tuple[tuple[int, ...], ...]
    removed: tuple[tuple[int, ...], ...]


def diff_framebuffers(before: FrameBuffer, after: FrameBuffer) -> PixelDiff:
    if (before.width, before.height) != (after.width, after.height):
        raise ValueError('framebuffers must have the same size')
    changed = 0
    xs: list[int] = []; ys: list[int] = []
    mask=[]; added=[]; removed=[]
    for y in range(before.height):
        mr=[]; ar=[]; rr=[]
        for x in range(before.width):
            a = before.get_pixel(x,y); b = after.get_pixel(x,y)
            d = 1 if a != b else 0
            mr.append(d); ar.append(1 if a == 0 and b == 1 else 0); rr.append(1 if a == 1 and b == 0 else 0)
            if d:
                changed += 1; xs.append(x); ys.append(y)
        mask.append(tuple(mr)); added.append(tuple(ar)); removed.append(tuple(rr))
    bbox = None if not xs else (min(xs), min(ys), max(xs)+1, max(ys)+1)
    total = before.width * before.height
    return PixelDiff(before.width, before.height, changed, (changed / total * 100) if total else 0.0, bbox, tuple(mask), tuple(added), tuple(removed))


def save_diff_png(diff: PixelDiff, path: str | Path, *, scale: int = 1) -> Path:
    scale = max(1, int(scale))
    image = Image.new('RGB', (diff.width, diff.height), (15, 23, 42))
    px = image.load()
    for y in range(diff.height):
        for x in range(diff.width):
            if diff.added[y][x]:
                px[x,y] = (255, 55, 95)
            elif diff.removed[y][x]:
                px[x,y] = (0, 113, 227)
    if scale != 1:
        image = image.resize((diff.width*scale, diff.height*scale), Image.Resampling.NEAREST)
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    image.save(target)
    return target
