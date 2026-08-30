from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from assets import BitmapAsset, load_bitmap, load_mode_font
from framebuffer import FrameBuffer
from scene import resolve, subst, when_match
from font_pack import FontPack
from resource_cache import RenderResources


@dataclass(frozen=True)
class RenderResult:
    framebuffer: FrameBuffer
    resolved_elements: tuple[dict, ...]
    used_assets: tuple[BitmapAsset, ...]
    used_files: tuple[Path, ...]


def _asset_path(template: str, state: dict, scene: dict, *, lower: bool = False) -> Path:
    return resolve(subst(template, state, lower=lower), scene=scene)


def _remember_asset(asset: BitmapAsset, cache: dict[str, BitmapAsset]) -> BitmapAsset:
    cache[str(asset.path)] = asset
    return asset


def _render_image(fb: FrameBuffer, element: dict, state: dict, cache: dict[str, BitmapAsset], scene: dict, resources: RenderResources) -> dict:
    path = _asset_path(element["asset"], state, scene, lower=bool(element.get("var_lower")))
    asset = _remember_asset(resources._bitmap_resolved(path), cache)
    x, y = int(element["x"]), int(element["y"])
    fb.or_mask(asset.pixels, x, y)
    return {
        "id": element["id"], "type": "image", "visible": True,
        "x": x, "y": y,
        "w": int(element.get("w", asset.width)), "h": int(element.get("h", asset.height)),
        "native_w": asset.width, "native_h": asset.height,
        "assets": [asset.path.as_posix()],
        "blend": element.get("blend", "or"),
        "resize_policy": element.get("resize_policy", "native_only"),
    }


def _render_image_seq(fb: FrameBuffer, element: dict, state: dict, cache: dict[str, BitmapAsset], scene: dict, resources: RenderResources) -> dict:
    name = element["bind"]
    value = int(state[name])
    filename = element["pattern"].replace("{n}", str(value))
    path = (resolve(element["dir"], scene=scene) / filename).resolve()
    asset = _remember_asset(resources._bitmap_resolved(path), cache)
    x, y = int(element["x"]), int(element["y"])
    fb.or_mask(asset.pixels, x, y)
    return {
        "id": element["id"], "type": "image_seq", "visible": True,
        "x": x, "y": y,
        "w": int(element.get("w", asset.width)), "h": int(element.get("h", asset.height)),
        "native_w": asset.width, "native_h": asset.height,
        "bind": name, "value": value,
        "assets": [asset.path.as_posix()],
        "blend": element.get("blend", "or"),
        "resize_policy": element.get("resize_policy", "native_only"),
    }


def _render_digits(fb: FrameBuffer, element: dict, state: dict, cache: dict[str, BitmapAsset], scene: dict, resources: RenderResources) -> dict:
    name = element["bind"]
    raw = str(state[name])
    min_digits = int(element.get("min_digits", 1))
    if raw.isdigit() and len(raw) < min_digits:
        raw = raw.rjust(min_digits, str(element.get("pad_char", "0")))
    x0, y = int(element["x"]), int(element["y"])
    digit_w = int(element["digit_w"])
    digit_h = int(element["digit_h"])
    tracking = int(element.get("tracking", 0))
    paths: list[str] = []
    for index, ch in enumerate(raw):
        filename = element["pattern"].replace("{d}", ch)
        path = (resolve(element["dir"], scene=scene) / filename).resolve()
        asset = _remember_asset(resources._bitmap_resolved(path), cache)
        paths.append(asset.path.as_posix())
        fb.or_mask(asset.pixels, x0 + index * (digit_w + tracking), y)
    width = 0 if not raw else len(raw) * digit_w + (len(raw) - 1) * tracking
    return {
        "id": element["id"], "type": "digits", "visible": True,
        "x": x0, "y": y, "w": width, "h": digit_h,
        "native_w": width, "native_h": digit_h,
        "bind": name, "text": raw,
        "assets": paths,
        "blend": element.get("blend", "or"),
        "resize_policy": element.get("resize_policy", "native_only"),
    }


def _render_placeholder(element: dict) -> dict:
    return {
        "id": element["id"], "type": "placeholder", "visible": True,
        "x": int(element["x"]), "y": int(element["y"]),
        "w": int(element["w"]), "h": int(element["h"]),
        "label": str(element.get("label", element["id"])),
        "assets": [], "placeholder": True, "rendered": False,
        "blend": "none", "resize_policy": "draft",
    }


def _render_text(fb: FrameBuffer, element: dict, state: dict, used_files: set[Path], scene: dict, resources: RenderResources) -> dict:
    text = subst(element["text"], state).upper()
    header = resolve(element["font_header"], scene=scene)
    font = resources._mode_font_resolved(header)
    used_files.add(header)
    cell_w = int(element.get("cell_w", 5))
    cell_h = int(element.get("cell_h", 7))
    advance = int(element.get("advance", cell_w + 1))
    width = 0 if not text else (len(text) - 1) * advance + cell_w
    zone = element.get("zone")
    if zone:
        align = element.get("align", "left")
        if align == "left":
            x = int(zone["x"])
        elif align == "center":
            x = int(zone["x"]) + (int(zone["w"]) - width) // 2
        elif align == "right":
            x = int(zone["x"]) + int(zone["w"]) - width
        else:
            raise ValueError(f"unknown text align: {align}")
        y = int(element.get("y", zone["y"]))
    else:
        x, y = int(element["x"]), int(element["y"])
    for index, ch in enumerate(text):
        if ch not in font:
            raise ValueError(f"font does not contain {ch!r} for element {element['id']}")
        fb.or_mask(font[ch], x + index * advance, y)
    return {
        "id": element["id"], "type": "text", "visible": True,
        "x": x, "y": y, "w": width, "h": cell_h,
        "native_w": width, "native_h": cell_h,
        "text": text, "assets": [header.as_posix()],
        "blend": element.get("blend", "or"),
        "resize_policy": "native_only",
    }


def _render_bitmap_text(fb: FrameBuffer, element: dict, state: dict, used_files: set[Path], scene: dict, resources: RenderResources) -> dict:
    text=subst(str(element.get("text","")),state)
    pack_root=resolve(element["font_pack"],scene=scene).resolve(); pack=resources.font_pack(pack_root)
    x0,y=int(element.get("x",0)),int(element.get("y",0)); x=x0; assets=[]
    for ch in text:
        if ch not in pack.characters(): raise ValueError(f"font pack does not contain {ch!r} for element {element['id']}")
        glyph=pack.glyph(ch); fb.or_mask(glyph.pixels,x+glyph.metrics.bearing_x,y+glyph.metrics.bearing_y); assets.append((pack_root/'glyphs'/f'U+{ord(ch):04X}.png').as_posix()); x+=glyph.metrics.advance
    width=0 if not text else max(0,x-x0-(pack.glyph(text[-1]).metrics.advance-pack.cell[0]))
    used_files.add((pack_root/'fontpack.json').resolve()); used_files.update(Path(a).resolve() for a in assets)
    return {"id":element["id"],"type":"bitmap_text","visible":True,"x":x0,"y":y,"w":width,"h":pack.cell[1],"native_w":width,"native_h":pack.cell[1],"text":text,"font_pack":pack_root.as_posix(),"assets":assets,"blend":element.get("blend","or"),"resize_policy":"native_only"}


def render_scene(scene: dict, state: dict, *, resources: RenderResources | None = None) -> RenderResult:
    canvas = scene["canvas"]
    fb = FrameBuffer(int(canvas["w"]), int(canvas["h"]))
    resolved: list[dict] = []
    asset_cache: dict[str, BitmapAsset] = {}
    used_files: set[Path] = set()
    resources = resources or RenderResources()

    for element in scene["elements"]:
        if element.get("hidden") or not when_match(element.get("visible_when"), state):
            resolved.append({
                "id": element["id"], "type": element["type"], "visible": False,
                "x": element.get("x", element.get("zone", {}).get("x")),
                "y": element.get("y", element.get("zone", {}).get("y")),
                "w": element.get("w", element.get("zone", {}).get("w")),
                "h": element.get("h", element.get("zone", {}).get("h")),
                "assets": [],
            })
            continue
        kind = element["type"]
        if kind == "image":
            item = _render_image(fb, element, state, asset_cache, scene, resources)
        elif kind == "image_seq":
            item = _render_image_seq(fb, element, state, asset_cache, scene, resources)
        elif kind == "digits":
            item = _render_digits(fb, element, state, asset_cache, scene, resources)
        elif kind == "text":
            item = _render_text(fb, element, state, used_files, scene, resources)
        elif kind == "bitmap_text":
            item = _render_bitmap_text(fb, element, state, used_files, scene, resources)
        elif kind == "placeholder":
            item = _render_placeholder(element)
        else:
            raise ValueError(f"unsupported element type: {kind}")
        resolved.append(item)

    used_files.update(asset.path for asset in asset_cache.values())
    return RenderResult(
        framebuffer=fb,
        resolved_elements=tuple(resolved),
        used_assets=tuple(asset_cache.values()),
        used_files=tuple(sorted(used_files, key=lambda p: p.as_posix())),
    )
