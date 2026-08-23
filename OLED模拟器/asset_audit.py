from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path

from assets import load_bitmap

IMAGE_SUFFIXES = {'.png', '.bmp'}
SKIP_PARTS = {'.git', '.pytest_cache', '__pycache__', 'exports', 'build', 'dist', '.venv-build'}


def _skip(path: Path, root: Path) -> bool:
    try:
        rel = path.relative_to(root)
    except ValueError:
        return True
    return any(part in SKIP_PARTS for part in rel.parts)


def audit_assets(root: str | Path) -> dict:
    root = Path(root).resolve()
    assets = []
    counts = Counter()
    images = sorted(
        p for p in root.rglob('*')
        if p.is_file() and p.suffix.lower() in IMAGE_SUFFIXES and not _skip(p, root)
    )
    for path in images:
        rel = path.relative_to(root).as_posix()
        try:
            asset = load_bitmap(path)
        except Exception as exc:
            counts['non_binary_or_invalid'] += 1
            assets.append({
                'path': rel,
                'status': 'invalid',
                'error': str(exc).replace(str(root) + '/', ''),
            })
            continue
        counts[asset.source_polarity] += 1
        assets.append({
            'path': rel,
            'status': 'ok',
            'width': asset.width,
            'height': asset.height,
            'source_mode': asset.source_mode,
            'source_polarity': asset.source_polarity,
            'inverted_for_oled': asset.inverted,
            'sha256': asset.sha256,
        })
    summary = {
        'images_scanned': len(images),
        'black_on_white': counts['black_on_white'],
        'white_on_black': counts['white_on_black'],
        'transparent': counts['transparent'],
        'non_binary_or_invalid': counts['non_binary_or_invalid'],
    }
    return {
        'schema_version': 1,
        'generated_utc': datetime.now(timezone.utc).isoformat(timespec='seconds'),
        'root': '.',
        'summary': summary,
        'assets': assets,
    }


def markdown_report(report: dict) -> str:
    s = report['summary']
    lines = [
        '# OLED Asset Polarity & Binary Audit', '',
        '> Source files are never rewritten by this audit. `black_on_white` assets are inverted only in memory by the Canonical Renderer.', '',
        f"- Images scanned: **{s['images_scanned']}**",
        f"- Opaque black-on-white (auto-normalized): **{s['black_on_white']}**",
        f"- Opaque white-on-black: **{s['white_on_black']}**",
        f"- Transparent binary: **{s['transparent']}**",
        f"- Non-binary / invalid: **{s['non_binary_or_invalid']}**", '',
        '## Non-binary / Invalid', '',
    ]
    invalid = [a for a in report['assets'] if a['status'] == 'invalid']
    if not invalid:
        lines.append('PASS — none.')
    else:
        for item in invalid:
            lines.append(f"- `{item['path']}` — {item['error']}")
    lines.extend(['', '## Polarity Contract', '',
                  '- OLED production semantics are always `0 = background`, `1 = lit`.',
                  '- Fully opaque white-background / black-foreground assets are auto-inverted in memory.',
                  '- Transparent background is always off; opaque white is lit.',
                  '- Partial alpha and non-binary RGB are rejected for production bitmap loading.',
                  '- Review sheets may intentionally be non-binary; they are not production assets unless referenced by a Scene.', ''])
    return '\n'.join(lines)


def write_report(root: str | Path, output: str | Path) -> dict:
    report = audit_assets(root)
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    (output / 'asset_audit.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    (output / 'asset_audit.md').write_text(markdown_report(report), encoding='utf-8')
    return report


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description='Audit OLED bitmap polarity and strict binary compliance.')
    parser.add_argument('--root', default=str(Path(__file__).resolve().parent.parent))
    parser.add_argument('--output', default=str(Path(__file__).resolve().parent / 'reports'))
    args = parser.parse_args(argv)
    report = write_report(args.root, args.output)
    s = report['summary']
    print(
        f"PASS: scanned={s['images_scanned']} black_on_white={s['black_on_white']} "
        f"white_on_black={s['white_on_black']} transparent={s['transparent']} invalid={s['non_binary_or_invalid']}"
    )
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
