"""Export or check the frozen V1 golden corpus used by the Rust rewrite.

Usage:
    python tools/EXPORT_GOLDEN_CORPUS.py [--output DIR]
    python tools/EXPORT_GOLDEN_CORPUS.py --check [--output DIR]
"""
from __future__ import annotations

import argparse
import json
from hashlib import sha256
import os
from pathlib import Path
import platform
import subprocess
import sys
import tempfile

TOOLS = Path(__file__).resolve().parent
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import golden_corpus  # noqa: E402
from golden_corpus.common import ROOT, canonical_json  # noqa: E402

DEFAULT_OUTPUT = ROOT / 'fixtures' / 'golden'


def _blob(relative: str) -> str:
    result = subprocess.run(['git', 'hash-object', '--no-filters', relative], cwd=ROOT,
                            capture_output=True, text=True, check=False)
    if result.returncode:
        raise RuntimeError(f'git hash-object failed for {relative}: {result.stderr.strip()}')
    return result.stdout.strip()


def _reference(categories) -> dict:
    sources = sorted({source for category in categories for source in category.sources})
    try:
        import PIL
        pillow = PIL.__version__
    except ImportError:  # pragma: no cover - Pillow is a V1 runtime dependency
        pillow = 'missing'
    return {
        'python_version': platform.python_version(),
        'pillow_version': pillow,
        'source_blobs': {source: _blob(source) for source in sources},
    }


def _build_cases(category) -> list[dict]:
    with tempfile.TemporaryDirectory(prefix='mono-golden-') as work:
        cases = category.build(Path(work))
    ids = [item['id'] for item in cases]
    duplicates = sorted({item for item in ids if ids.count(item) > 1})
    if duplicates:
        raise ValueError(f'{category.name}: duplicate case ids {duplicates}')
    return sorted(cases, key=lambda item: item['id'])


def _write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f'.{path.name}.tmp')
    temporary.write_bytes(data)
    os.replace(temporary, path)


def generate(out_dir: Path) -> dict:
    out_dir = Path(out_dir)
    categories = list(golden_corpus.CATEGORIES)
    manifest = {'schema_version': 1, 'reference': _reference(categories), 'categories': {}}
    for category in categories:
        cases = _build_cases(category)
        payload = canonical_json({'category': category.name, 'cases': cases})
        _write(out_dir / f'{category.name}.json', payload)
        levels = {'strict': 0, 'semantic': 0}
        for item in cases:
            levels[item['level']] += 1
        manifest['categories'][category.name] = {
            'file': f'{category.name}.json',
            'sha256': sha256(payload).hexdigest(),
            'case_count': len(cases),
            'levels': levels,
        }
    _write(out_dir / 'manifest.json', canonical_json(manifest))
    return manifest


def _load_cases(path: Path) -> dict[str, dict]:
    if not path.is_file():
        return {}
    return {item['id']: item for item in json.loads(path.read_text(encoding='utf-8'))['cases']}


def check(committed: Path) -> list[str]:
    """Regenerate into a temporary directory and list changed `<category>:<case id>` entries."""
    committed = Path(committed)
    changes: list[str] = []
    with tempfile.TemporaryDirectory(prefix='mono-golden-check-') as temp:
        fresh_dir = Path(temp)
        fresh = generate(fresh_dir)
        old_manifest_path = committed / 'manifest.json'
        old = json.loads(old_manifest_path.read_text(encoding='utf-8')) if old_manifest_path.is_file() else {'categories': {}, 'reference': {}}
        names = sorted(set(fresh['categories']) | set(old.get('categories', {})))
        for name in names:
            if name not in fresh['categories'] or name not in old.get('categories', {}):
                changes.append(f'{name}:*')
                continue
            new_cases = _load_cases(fresh_dir / f'{name}.json')
            old_cases = _load_cases(committed / f'{name}.json')
            for case_id in sorted(set(new_cases) | set(old_cases)):
                if new_cases.get(case_id) != old_cases.get(case_id):
                    changes.append(f'{name}:{case_id}')
        if fresh.get('reference') != old.get('reference'):
            for key in sorted(set(fresh['reference']) | set(old.get('reference', {}))):
                if fresh['reference'].get(key) != old.get('reference', {}).get(key):
                    changes.append(f'reference:{key}')
        if not changes and (fresh_dir / 'manifest.json').read_bytes() != old_manifest_path.read_bytes():
            changes.append('manifest:*')
    return changes


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='Export or check the V1 golden corpus')
    parser.add_argument('--output', default=str(DEFAULT_OUTPUT), help='corpus directory')
    parser.add_argument('--check', action='store_true', help='fail if regeneration differs from the committed corpus')
    args = parser.parse_args(argv)
    target = Path(args.output)
    if args.check:
        changes = check(target)
        for change in changes:
            print(f'changed: {change}')
        print('golden corpus: OK' if not changes else f'golden corpus: {len(changes)} change(s)')
        return 1 if changes else 0
    manifest = generate(target)
    for name, entry in manifest['categories'].items():
        print(f"{name}: {entry['case_count']} cases (strict {entry['levels']['strict']}, semantic {entry['levels']['semantic']})")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
