"""Build a throwaway copy of the fixture project with a large scene, for the
Designer edit benchmark.

`bench.rs`'s designer phase edits the open project, and the committed fixture has
five elements — too small to show an O(n) versus O(n²) difference. This copies
`test_assets/projects/curing_lite` into a temp directory, appends N `placeholder`
elements (optionally K `digits` elements, whose glyph lookups dominate a render) to one screen's scene, makes that screen active, and prints the project
path for `RUN_DESKTOP_BENCH.py --project`.

Nothing under `test_assets/` is written; the copy is disposable.

Usage:
  python tools/BENCH_DESIGNER_PROJECT.py --elements 1000 [--digits 0] [--out DIR]
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FIXTURE = ROOT / 'test_assets' / 'projects' / 'curing_lite'


def screen_with_elements(project: dict, root: Path) -> dict:
    """The screen the bench has to open: one that already has content."""
    for screen in project.get('screens', []):
        path = root / screen['path']
        scene = json.loads(path.read_text(encoding='utf-8'))
        if scene.get('elements'):
            return screen
    screens = project.get('screens') or []
    if not screens:
        raise SystemExit('the fixture project lists no screens')
    return screens[0]


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--elements', type=int, default=1000, help='placeholder elements to add')
    parser.add_argument('--digits', type=int, default=0, help='digit elements to add (glyph-heavy renders)')
    parser.add_argument('--out', type=Path, default=None, help='target directory (default: a temp dir)')
    args = parser.parse_args(argv)
    if args.elements < 0 or args.digits < 0:
        print('element counts must not be negative', file=sys.stderr)
        return 2

    target = args.out or Path(tempfile.mkdtemp(prefix='mono-bench-scene-'))
    if target.exists() and any(target.iterdir()):
        print(f'{target} is not empty; refusing to overwrite', file=sys.stderr)
        return 2
    shutil.copytree(FIXTURE, target, dirs_exist_ok=True)

    manifest_path = target / 'project.oled.json'
    project = json.loads(manifest_path.read_text(encoding='utf-8'))
    screen = screen_with_elements(project, target)
    scene_path = target / screen['path']
    scene = json.loads(scene_path.read_text(encoding='utf-8'))
    elements = scene.setdefault('elements', [])
    taken = {element.get('id') for element in elements}

    def fresh(prefix: str, index: int) -> str:
        candidate = f'{prefix}{index:04d}'
        while candidate in taken:
            index += 1
            candidate = f'{prefix}{index:04d}'
        taken.add(candidate)
        return candidate

    template = next((e for e in elements if e.get('type') == 'digits'), None)
    for index in range(args.digits):
        if template is None:
            print('the fixture has no digits element to clone', file=sys.stderr)
            return 2
        clone = dict(template)
        clone['id'] = fresh('bench_digit_', index)
        clone['x'] = 4 + (index % 16) * 14
        clone['y'] = 40 + (index // 16) * 28
        elements.append(clone)

    for index in range(args.elements):
        elements.append({
            'id': fresh('bench_probe_', index),
            'type': 'placeholder',
            'x': (index % 60) * 4,
            'y': (index // 60) * 3,
            'w': 4,
            'h': 3,
        })

    scene_path.write_text(json.dumps(scene, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    project['active_screen'] = screen['id']
    manifest_path.write_text(json.dumps(project, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    print(json.dumps({
        'project': str(manifest_path),
        'screen': screen['id'],
        'elements': len(elements),
    }, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))
