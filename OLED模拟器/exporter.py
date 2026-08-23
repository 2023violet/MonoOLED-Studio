from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from io import BytesIO
from pathlib import Path
from typing import Mapping

from PIL import Image

from assets import load_bitmap
from render import RenderResult, render_scene
from scene import ROOT, scene_root
from validate import Finding, has_blockers, validate_scene
from atomic_io import atomic_write_bytes, atomic_write_json


class ExportBlockedError(RuntimeError):
    pass


@dataclass(frozen=True)
class ExportSummary:
    output_dir: Path
    frame_count: int
    frame_hashes: dict[str, str]
    findings: dict[str, tuple[Finding, ...]]


def _relative(path: str | Path, root: str | Path | None = None) -> str:
    p = Path(path).resolve()
    base = Path(root).resolve() if root is not None else ROOT.resolve()
    try:
        return p.relative_to(base).as_posix()
    except ValueError:
        return p.as_posix()


def _write_json(path: Path, data) -> None:
    atomic_write_json(path,data,sort_keys=True)


def _save_png(result: RenderResult, path: Path) -> None:
    image = Image.new("1", (result.framebuffer.width, result.framebuffer.height), 0)
    for y, row in enumerate(result.framebuffer.to_rows()):
        for x, value in enumerate(row):
            if value:
                image.putpixel((x, y), 255)
    buf=BytesIO(); image.save(buf, format="PNG", optimize=False); atomic_write_bytes(path,buf.getvalue())


def _visible_element_contract(item: dict, project_root: Path) -> dict:
    out = {
        "id": item["id"],
        "type": item["type"],
        "visible": bool(item.get("visible")),
        "x": item.get("x"),
        "y": item.get("y"),
        "w": item.get("w"),
        "h": item.get("h"),
        "assets": [_relative(p, project_root) for p in item.get("assets", [])],
    }
    for key in ("bind", "value", "text", "blend", "resize_policy", "native_w", "native_h"):
        if key in item:
            out[key] = item[key]
    return out


def _asset_entry(path: Path, project_root: Path) -> dict:
    raw = path.read_bytes()
    entry = {
        "path": _relative(path, project_root),
        "sha256": sha256(raw).hexdigest(),
        "bytes": len(raw),
    }
    if path.suffix.lower() in {".png", ".bmp", ".jpg", ".jpeg"}:
        asset = load_bitmap(path)
        entry.update({
            "kind": "bitmap",
            "width": asset.width,
            "height": asset.height,
            "mode": asset.source_mode,
            "source_polarity": asset.source_polarity,
            "inverted_for_oled": asset.inverted,
            "normalized_semantics": "0=background, 1=OLED lit",
        })
    else:
        entry["kind"] = "file"
    return entry


def _markdown_spec(scene: dict, frame_contracts: dict[str, dict]) -> str:
    project_name = str(scene.get("product") or scene.get("name") or "MonoOLED Project").strip()
    lines = [
        f"# {project_name} OLED UI Specification",
        "",
        "> Generated from scene JSON. Do not edit this document as the layout source of truth.",
        "",
        "## Global Contract",
        "",
        f"- Canvas: **{scene['canvas']['w']}×{scene['canvas']['h']}**, monochrome 1-bit.",
        "- Origin: `(0,0)` at top-left; X increases right, Y increases down.",
        "- Bounds: `[x, x+w) × [y, y+h)`.",
        f"- Storage: **{int(scene['canvas']['w']) * (int(scene['canvas']['h']) // 8)}-byte VLSB**, {int(scene['canvas']['h']) // 8} pages × {scene['canvas']['w']} columns; bit0 is the top pixel of each 8-pixel page.",
        "- Polarity: `1 = OLED lit`, `0 = background`.",
        "- Bitmap resize policy: `native_only` unless explicitly stated otherwise.",
        "- Bitmap source polarity is normalized at load time: opaque black-on-white assets are inverted in memory; source files are not rewritten.",
        "",
        "## Scene Element Definitions",
        "",
        "| ID | Type | X | Y | W | H | Binding / Text |",
        "|---|---|---:|---:|---:|---:|---|",
    ]
    for element in scene.get("elements", []):
        x = element.get("x", element.get("zone", {}).get("x", ""))
        y = element.get("y", element.get("zone", {}).get("y", ""))
        w = element.get("w", element.get("zone", {}).get("w", ""))
        h = element.get("h", element.get("zone", {}).get("h", ""))
        desc = element.get("bind") or element.get("text") or ""
        lines.append(f"| {element.get('id','')} | {element.get('type','')} | {x} | {y} | {w} | {h} | {desc} |")
    lines.append("")

    for name in sorted(frame_contracts):
        frame = frame_contracts[name]
        lines.extend([
            f"## {name.upper()}",
            "",
            "State: `" + ", ".join(f"{k}={v}" for k, v in sorted(frame["state"].items())) + "`",
            "",
            f"Golden BIN: `golden/{name}.bin`  ",
            f"Reference PNG: `reference/{name}.png`  ",
            f"SHA-256: `{frame['golden_sha256']}`",
            "",
            "| ID | Type | X | Y | W | H | Asset / Text |",
            "|---|---|---:|---:|---:|---:|---|",
        ])
        for item in frame["elements"]:
            if not item["visible"]:
                continue
            asset_or_text = item.get("text") or ", ".join(item.get("assets", []))
            lines.append(
                f"| {item['id']} | {item['type']} | {item['x']} | {item['y']} | {item['w']} | {item['h']} | {asset_or_text} |"
            )
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _validation_markdown(all_findings: dict[str, tuple[Finding, ...]]) -> str:
    lines = ["# OLED UI Validation Report", ""]
    total = sum(len(v) for v in all_findings.values())
    blockers = sum(1 for fs in all_findings.values() for f in fs if f.severity in {"ERROR", "BLOCKER"})
    lines.extend([f"- Frames checked: **{len(all_findings)}**", f"- Findings: **{total}**", f"- Blocking findings: **{blockers}**", ""])
    for name in sorted(all_findings):
        lines.append(f"## {name}")
        findings = all_findings[name]
        if not findings:
            lines.extend(["", "PASS — no findings.", ""])
            continue
        lines.append("")
        for f in findings:
            suffix = f" (`{f.element_id}`)" if f.element_id else ""
            lines.append(f"- **{f.severity} / {f.code}**{suffix}: {f.message}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def export_scene(scene: dict, output_dir: str | Path, states: Mapping[str, dict]) -> ExportSummary:
    output_dir = Path(output_dir)
    reference_dir = output_dir / "reference"
    golden_dir = output_dir / "golden"
    reference_dir.mkdir(parents=True, exist_ok=True)
    golden_dir.mkdir(parents=True, exist_ok=True)

    all_findings: dict[str, tuple[Finding, ...]] = {}
    for name, state in states.items():
        findings = tuple(validate_scene(scene, dict(state)))
        all_findings[name] = findings
    if any(has_blockers(list(fs)) for fs in all_findings.values()):
        report = _validation_markdown(all_findings)
        (output_dir / "validation_report.md").write_text(report, encoding="utf-8")
        raise ExportBlockedError(f"export blocked; see {output_dir / 'validation_report.md'}")

    frame_contracts: dict[str, dict] = {}
    used_files: set[Path] = set()
    frame_hashes: dict[str, str] = {}
    project_root = scene_root(scene)
    width = int(scene['canvas']['w']); height = int(scene['canvas']['h'])
    expected_bytes = width * (height // 8)

    for name in sorted(states):
        state = dict(states[name])
        result = render_scene(scene, state)
        raw = result.framebuffer.to_vlsb()
        if len(raw) != expected_bytes:
            raise ExportBlockedError(f"{name}: framebuffer length {len(raw)} != {expected_bytes}")
        bin_path = golden_dir / f"{name}.bin"
        png_path = reference_dir / f"{name}.png"
        bin_path.write_bytes(raw)
        _save_png(result, png_path)
        digest = sha256(raw).hexdigest()
        frame_hashes[name] = digest
        used_files.update(Path(p).resolve() for p in result.used_files)
        frame_contracts[name] = {
            "state": dict(sorted(state.items())),
            "golden": f"golden/{name}.bin",
            "reference": f"reference/{name}.png",
            "golden_sha256": digest,
            "lit_pixels": sum(sum(row) for row in result.framebuffer.to_rows()),
            "elements": [_visible_element_contract(item, project_root) for item in result.resolved_elements],
        }

    scene_input = {k: v for k, v in scene.items() if not str(k).startswith("_")}
    contract = {
        "schema_version": 1,
        "product": scene.get("product"),
        "coordinate_contract": {
            "origin": "top-left",
            "x_direction": "right",
            "y_direction": "down",
            "bounds": "[x, x+w) × [y, y+h)",
            "integer_coordinates": True,
        },
        "framebuffer_contract": {
            "width": width,
            "height": height,
            "bytes": expected_bytes,
            "layout": "VLSB page-major",
            "byte_offset": "(y // 8) * width + x",
            "bit": "1 << (y % 8)",
            "polarity": "1 = lit",
        },
        "scene": scene_input,
        "frames": frame_contracts,
    }
    _write_json(output_dir / "ui_contract.json", contract)

    manifest = {"schema_version": 1, "assets": [_asset_entry(p, project_root) for p in sorted(used_files, key=lambda p: _relative(p, project_root))]}
    _write_json(output_dir / "asset_manifest.json", manifest)

    (output_dir / "UI_SPEC.md").write_text(_markdown_spec(scene, frame_contracts), encoding="utf-8")
    (output_dir / "validation_report.md").write_text(_validation_markdown(all_findings), encoding="utf-8")

    return ExportSummary(
        output_dir=output_dir,
        frame_count=len(frame_contracts),
        frame_hashes=frame_hashes,
        findings=all_findings,
    )
