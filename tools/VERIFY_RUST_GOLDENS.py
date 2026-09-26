"""Compare current Python production behavior with frozen Rust V2 fixtures."""
from __future__ import annotations

import argparse
from dataclasses import asdict
from hashlib import sha256
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))

from bitmap_encoding import EncodingProfile, MonoBitmap, encode_bitmap
from builtin_oled_font import builtin_glyph_rows
from font_pack import FontPack, GlyphMetrics
from framebuffer import FrameBuffer
from output_formatter import OutputItem, format_output
from output_profiles import builtin_profiles
from project_workspace import ProjectWorkspace

DEFAULT_FIXTURE = ROOT / 'test_assets' / 'rust_v2' / 'goldens.json'


def canonical_json(value) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(',', ':'), allow_nan=False).encode('utf-8')


def rows_from_strings(rows):
    return [[int(bit) for bit in row] for row in rows]


def row_strings(rows):
    return [''.join(str(bit) for bit in row) for row in rows]


def byte_result(data):
    return {'hex': data.hex(), 'byte_count': len(data),
            'sha256': sha256(data).hexdigest()}


def reference_result(case):
    spec = case['input']
    kind = case['kind']
    if kind == 'encoding':
        bitmap = MonoBitmap.from_rows(rows_from_strings(spec['rows']))
        encoded = encode_bitmap(bitmap, EncodingProfile(**spec['profile']))
        return {**byte_result(encoded.data), 'padded_size': list(encoded.padded_size)}
    if kind == 'framebuffer':
        fb = FrameBuffer(spec['width'], spec['height'])
        for x, y in spec['set_pixels']:
            fb.set_pixel(x, y)
        for mask in spec['masks']:
            fb.or_mask(rows_from_strings(mask['rows']), *mask['origin'])
        return {**byte_result(fb.to_vlsb()), 'rows': row_strings(fb.to_rows())}
    if kind == 'font':
        with TemporaryDirectory(prefix='mono-golden-font-') as temporary:
            pack = FontPack(temporary, spec['name'], cell=tuple(spec['cell']),
                            baseline=spec['baseline'], advance=spec['advance'])
            for char in spec['characters']:
                pack.set_glyph(char, builtin_glyph_rows(
                    char, pack.cell, baseline=pack.baseline),
                    GlyphMetrics(0, 0, pack.advance))
            pack.save()
            loaded = FontPack.load(temporary)
            return {
                'cell': list(loaded.cell), 'baseline': loaded.baseline,
                'advance': loaded.advance,
                'glyphs': {char: {'rows': row_strings(loaded.glyph(char).pixels),
                                 'metrics': asdict(loaded.glyph(char).metrics)}
                           for char in loaded.characters()},
                'composed_rows': row_strings(loaded.compose_text(
                    spec['text'], tracking=spec['tracking'])),
            }
    if kind == 'project':
        with TemporaryDirectory(prefix='mono-golden-project-') as temporary:
            path = Path(temporary) / 'project.oled.json'
            # Deliberately noncanonical formatting; semantics must survive save.
            path.write_bytes(json.dumps(spec['manifest'], ensure_ascii=False,
                                        indent=4).replace('\n', '\r\n').encode('utf-8'))
            before = path.read_bytes()
            project = ProjectWorkspace.load(path)
            active, profiles = project.get_output_profiles()
            read_unchanged = path.read_bytes() == before
            project.save()
            return {
                'read_preserved_bytes': read_unchanged,
                'saved_manifest': json.loads(path.read_text(encoding='utf-8')),
                'active_profile': active,
                'profile': profiles[active].to_dict(),
            }
    if kind == 'export':
        profile = builtin_profiles()[spec['profile_id']]
        encoded = encode_bitmap(
            MonoBitmap.from_rows(rows_from_strings(spec['rows'])), profile.encoding)
        formatted = format_output(
            [OutputItem(name=spec['name'], encoded=encoded)],
            profile.text, symbol=spec['symbol'])
        return {**byte_result(formatted.data), 'text': formatted.text,
                'index': [asdict(entry) for entry in formatted.index]}
    raise ValueError(f'unknown fixture kind: {kind}')


def verify(path=DEFAULT_FIXTURE):
    document = json.loads(Path(path).read_text(encoding='utf-8'))
    if document['schema_version'] != 1 or not document['cases']:
        raise ValueError('expected nonempty fixture schema 1')
    ids = [case['id'] for case in document['cases']]
    if len(ids) != len(set(ids)):
        raise ValueError('duplicate fixture ids')
    failures = []
    for case in document['cases']:
        actual = reference_result(case)
        if canonical_json(actual) != canonical_json(case['expected']):
            failures.append(case['id'])
            print(f"MISMATCH {case['id']}")
        else:
            digest = actual.get('sha256', sha256(canonical_json(actual)).hexdigest())
            print(f"OK {case['id']} sha256={digest}")
    return failures


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fixture', type=Path, default=DEFAULT_FIXTURE)
    args = parser.parse_args()
    try:
        failures = verify(args.fixture)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f'ERROR: {exc}', file=sys.stderr)
        return 1
    if failures:
        print(f'FAILED: {len(failures)} fixture(s)')
        return 1
    print('All Python reference fixtures matched (not Rust or 3-OS evidence).')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
