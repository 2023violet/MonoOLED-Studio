from __future__ import annotations

from pathlib import Path
import tempfile
import zipfile

from asset_library import AssetLibrary
from batch_validate import build_state_matrix, validate_matrix, write_matrix_report
from exporter import ExportSummary, export_scene
from render import render_scene
from scene import scene_root
from c_export import write_c_header
from design_rules import check_design_rules
from thumbnail_wall import build_thumbnail_wall


def _used_asset_paths(scene: dict, states: dict[str, dict]) -> set[str]:
    root = scene_root(scene)
    used: set[str] = set()
    for state in states.values():
        result = render_scene(scene, dict(state))
        for path in result.used_files:
            try: used.add(Path(path).resolve().relative_to(root).as_posix())
            except ValueError: pass
    return used


def _deterministic_zip(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(target, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for path in sorted((p for p in source.rglob('*') if p.is_file()), key=lambda p: p.relative_to(source).as_posix()):
            rel = path.relative_to(source).as_posix()
            info = zipfile.ZipInfo(rel, date_time=(1980,1,1,0,0,0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            zf.writestr(info, path.read_bytes())


def build_handoff_package(scene: dict, output_zip: str | Path, *, states: dict[str, dict]) -> ExportSummary:
    output_zip = Path(output_zip)
    with tempfile.TemporaryDirectory(prefix='oled_handoff_') as td:
        root = Path(td)
        summary = export_scene(scene, root, states)
        matrix = build_state_matrix(scene, integer_policy='boundaries')
        matrix_summary = validate_matrix(scene, matrix)
        write_matrix_report(matrix_summary, root / 'batch_validation.md')

        # Human overview + firmware-friendly frame arrays are generated from the
        # same canonical renderer output used for Golden BIN.
        reference_paths=[root/'reference'/f'{name}.png' for name in states]
        if reference_paths:
            build_thumbnail_wall(reference_paths, root/'thumbnail_wall.png', columns=min(4, max(1, len(reference_paths))), scale=4)
        c_dir=root/'c_headers'; c_dir.mkdir(parents=True, exist_ok=True)
        for name,state in states.items():
            write_c_header(render_scene(scene, dict(state)).framebuffer, c_dir/f'{name}.h', name=f'oled_{name}')

        rule_findings=check_design_rules(scene, scene.get('_design_rules') or {})
        rule_lines=['# Design Rule Check','',f'- Findings: **{len(rule_findings)}**','']
        if rule_findings:
            for finding in rule_findings:
                rule_lines.append(f'- **{finding.severity}/{finding.code}**' + (f' [{finding.element_id}]' if finding.element_id else '') + f': {finding.message}')
        else:
            rule_lines.append('PASS — no configured design-rule findings.')
        (root/'design_rules.md').write_text('\n'.join(rule_lines).rstrip()+'\n',encoding='utf-8')

        project_root = scene_root(scene)
        asset_dirs = list(scene.get('_asset_dirs') or (['assets'] if (project_root / 'assets').exists() else []))
        if asset_dirs:
            library = AssetLibrary(project_root, asset_dirs)
            library.scan()
            health = library.health_report(used_paths=_used_asset_paths(scene, states))
            lines = ['# Asset Health', '', f'- Duplicate groups: **{len(health.duplicates)}**', f'- Unused assets: **{len(health.unused)}**', f'- Invalid assets: **{len(health.invalid)}**', '']
            for group in health.duplicates:
                lines.append('- Duplicate: ' + ', '.join(f'`{p}`' for p in group))
            (root/'asset_health.md').write_text('\n'.join(lines).rstrip()+'\n',encoding='utf-8')

        (root / 'HANDOFF_README.md').write_text(
            '# OLED UI Code AI Handoff\n\n'
            'Implementation truth order:\n\n'
            '1. `ui_contract.json` — machine-readable geometry/state contract.\n'
            '2. `golden/*.bin` — pixel truth; compare framebuffer byte-for-byte.\n'
            '3. `UI_SPEC.md` — human-readable implementation guide.\n'
            '4. `validation_report.md`, `batch_validation.md`, and `design_rules.md` — release gates.\n'
            '5. `thumbnail_wall.png` — fast visual review; never use it to infer coordinates.\n'
            '6. `c_headers/*.h` — optional VLSB asset/frame arrays generated from Golden truth.\n\n'
            'Do not infer coordinates from screenshots when contract JSON is available.\n',
            encoding='utf-8')
        _deterministic_zip(root, output_zip)
        return summary
