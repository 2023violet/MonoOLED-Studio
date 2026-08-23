from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import itertools
import re

from assets import AssetFormatError, load_bitmap, load_mode_font
from font_pack import FontPack
from render import render_scene
from scene import init_state, resolve, subst


@dataclass(frozen=True)
class Finding:
    severity: str
    code: str
    message: str
    element_id: str | None = None


BLOCKING = {"ERROR", "BLOCKER"}
SUPPORTED_TYPES = {"image", "image_seq", "digits", "text", "bitmap_text", "placeholder"}
_TEMPLATE_RE = re.compile(r"\{(\w+)\}")


def has_blockers(findings: list[Finding] | tuple[Finding, ...]) -> bool:
    return any(f.severity in BLOCKING for f in findings)


def _add(findings, severity, code, message, element_id=None):
    findings.append(Finding(severity, code, message, element_id))


def _int_field(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _check_box(findings: list[Finding], element_id: str, x, y, w, h, cw: int, ch: int) -> None:
    if not all(_int_field(v) for v in (x, y, w, h)):
        _add(findings, "BLOCKER", "NON_INTEGER_COORDINATE", f"{element_id}: X/Y/W/H must be integers", element_id)
        return
    if w <= 0 or h <= 0:
        _add(findings, "BLOCKER", "INVALID_SIZE", f"{element_id}: W/H must be > 0", element_id)
        return
    if x < 0 or y < 0 or x + w > cw or y + h > ch:
        _add(findings, "BLOCKER", "OUT_OF_BOUNDS", f"{element_id}: ({x},{y},{w},{h}) outside {cw}x{ch}", element_id)


def _enum_template_paths(template: str, scene: dict, state: dict, lower: bool) -> list[Path]:
    keys = _TEMPLATE_RE.findall(template)
    if not keys:
        return [resolve(template, scene=scene).resolve()]
    domains = []
    for key in keys:
        if key not in scene["states"]:
            raise KeyError(key)
        spec = scene["states"][key]
        if spec["type"] == "enum":
            domains.append(list(spec["values"]))
        else:
            domains.append([state[key]])
    paths = []
    for values in itertools.product(*domains):
        local = dict(state)
        local.update(dict(zip(keys, values)))
        paths.append(resolve(subst(template, local, lower=lower), scene=scene).resolve())
    return paths


def _validate_bitmap_path(findings: list[Finding], path: Path, element: dict, expected_w=None, expected_h=None) -> None:
    eid = element["id"]
    if not path.exists():
        _add(findings, "BLOCKER", "ASSET_NOT_FOUND", f"{eid}: {path}", eid)
        return
    try:
        asset = load_bitmap(path)
    except (AssetFormatError, OSError, ValueError) as exc:
        _add(findings, "BLOCKER", "NON_BINARY_ASSET", f"{eid}: {exc}", eid)
        return
    if element.get("resize_policy", "native_only") == "native_only" and expected_w is not None and expected_h is not None:
        if (asset.width, asset.height) != (int(expected_w), int(expected_h)):
            _add(
                findings,
                "BLOCKER",
                "ASSET_SIZE_MISMATCH",
                f"{eid}: declared {expected_w}x{expected_h}, native {asset.width}x{asset.height}: {path}",
                eid,
            )


def validate_scene(scene: dict, state: dict | None = None) -> list[Finding]:
    findings: list[Finding] = []
    state = dict(init_state(scene) if state is None else state)

    canvas = scene.get("canvas", {})
    cw, ch = canvas.get("w"), canvas.get("h")
    if not _int_field(cw) or not _int_field(ch) or int(cw) <= 0 or int(ch) <= 0:
        _add(findings, "BLOCKER", "INVALID_CANVAS_SIZE", f"canvas must use positive integer dimensions, got {cw}x{ch}")
        return findings
    cw, ch = int(cw), int(ch)
    if ch % 8 != 0:
        _add(findings, "BLOCKER", "CANVAS_HEIGHT_NOT_PAGE_ALIGNED", f"VLSB canvas height must be divisible by 8, got {ch}")
        return findings
    expected_bytes = cw * (ch // 8)
    declared_bytes = scene.get("storage", {}).get("bytes_per_frame")
    if declared_bytes is not None and int(declared_bytes) != expected_bytes:
        _add(findings, "BLOCKER", "FRAMEBUFFER_SIZE_CONTRACT", f"storage.bytes_per_frame={declared_bytes}, expected {expected_bytes} for {cw}x{ch}")

    for key, spec in scene.get("states", {}).items():
        if key not in state:
            _add(findings, "BLOCKER", "MISSING_STATE", f"missing state value: {key}")
        elif spec.get("type") == "enum" and state[key] not in spec.get("values", []):
            _add(findings, "BLOCKER", "INVALID_STATE", f"{key}={state[key]!r} not in enum")
        elif spec.get("type") == "int" and not isinstance(state[key], int):
            _add(findings, "BLOCKER", "INVALID_STATE", f"{key} must be int")

    for element in scene.get("elements", []):
        eid = element.get("id", "<missing-id>")
        kind = element.get("type")
        if kind not in SUPPORTED_TYPES:
            _add(findings, "BLOCKER", "UNKNOWN_ELEMENT_TYPE", f"{eid}: {kind!r}", eid)
            continue
        bind = element.get("bind")
        if bind and bind not in scene.get("states", {}):
            _add(findings, "BLOCKER", "INVALID_BINDING", f"{eid}: unknown state {bind}", eid)
            continue

        if kind in {"image", "image_seq", "placeholder"}:
            _check_box(findings, eid, element.get("x"), element.get("y"), element.get("w"), element.get("h"), cw, ch)
            if kind == "placeholder":
                _add(
                    findings, "BLOCKER", "DRAFT_PLACEHOLDER",
                    f"{eid}: editor placeholder must be replaced by a production asset before export", eid,
                )
        elif kind == "digits":
            x, y = element.get("x"), element.get("y")
            dw, dh = element.get("digit_w"), element.get("digit_h")
            tracking = element.get("tracking", 0)
            if not all(_int_field(v) for v in (x, y, dw, dh, tracking)):
                _add(findings, "BLOCKER", "NON_INTEGER_COORDINATE", f"{eid}: digit geometry must be integer", eid)
            else:
                spec = scene["states"].get(bind, {})
                max_text = str(spec.get("max", state.get(bind, 0)))
                digits = max(len(max_text), int(element.get("min_digits", 1)))
                width = digits * dw + max(0, digits - 1) * tracking
                _check_box(findings, eid, x, y, width, dh, cw, ch)
        elif kind in {"text","bitmap_text"}:
            zone = element.get("zone")
            if zone:
                _check_box(findings, eid, zone.get("x"), zone.get("y"), zone.get("w"), zone.get("h"), cw, ch)
            else:
                _check_box(findings, eid, element.get("x"), element.get("y"), 1, int(element.get("cell_h", 7)), cw, ch)

        try:
            if kind == "image":
                for path in _enum_template_paths(element["asset"], scene, state, bool(element.get("var_lower"))):
                    _validate_bitmap_path(findings, path, element, element.get("w"), element.get("h"))
            elif kind == "image_seq":
                count = int(element.get("count", 0))
                if count <= 0:
                    _add(findings, "BLOCKER", "INVALID_SEQUENCE", f"{eid}: count must be > 0", eid)
                for n in range(max(0, count)):
                    filename = element["pattern"].replace("{n}", str(n))
                    path = (resolve(element["dir"], scene=scene) / filename).resolve()
                    _validate_bitmap_path(findings, path, element, element.get("w"), element.get("h"))
            elif kind == "digits":
                for d in "0123456789":
                    filename = element["pattern"].replace("{d}", d)
                    path = (resolve(element["dir"], scene=scene) / filename).resolve()
                    _validate_bitmap_path(findings, path, element, element.get("digit_w"), element.get("digit_h"))
            elif kind == "text":
                header = resolve(element["font_header"], scene=scene).resolve()
                if not header.exists():
                    _add(findings, "BLOCKER", "ASSET_NOT_FOUND", f"{eid}: {header}", eid)
                else:
                    try:
                        load_mode_font(header)
                    except (AssetFormatError, OSError, ValueError) as exc:
                        _add(findings, "BLOCKER", "FONT_INVALID", f"{eid}: {exc}", eid)
            elif kind == "bitmap_text":
                root = resolve(element["font_pack"], scene=scene).resolve()
                if not (root/"fontpack.json").exists():
                    _add(findings,"BLOCKER","ASSET_NOT_FOUND",f"{eid}: {root}/fontpack.json",eid)
                else:
                    try:
                        pack=FontPack.load(root); text=subst(str(element.get("text","")),state)
                        missing=[ch for ch in text if ch not in pack.characters()]
                        if missing:_add(findings,"BLOCKER","FONT_MISSING_GLYPH",f"{eid}: missing {missing!r}",eid)
                    except Exception as exc:_add(findings,"BLOCKER","FONT_INVALID",f"{eid}: {exc}",eid)
        except KeyError as exc:
            _add(findings, "BLOCKER", "UNRESOLVED_VARIABLE", f"{eid}: unresolved template/state {exc.args[0]}", eid)

    # Rendering current state catches dynamic geometry/template issues not covered statically.
    try:
        result = render_scene(scene, state)
        expected_bytes = cw * (ch // 8) if ch % 8 == 0 else None
        if expected_bytes is not None and len(result.framebuffer.to_vlsb()) != expected_bytes:
            _add(findings, "BLOCKER", "FRAMEBUFFER_SIZE", f"rendered framebuffer is not {expected_bytes} bytes")
        for item in result.resolved_elements:
            if item.get("visible") and all(item.get(k) is not None for k in ("x", "y", "w", "h")):
                _check_box(findings, item["id"], item["x"], item["y"], item["w"], item["h"], cw, ch)
    except Exception as exc:
        _add(findings, "BLOCKER", "RENDER_FAILED", str(exc))

    return findings
