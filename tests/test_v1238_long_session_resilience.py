from __future__ import annotations

from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / 'src'
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def test_session_logger_counts_existing_records_without_read_text(tmp_path, monkeypatch):
    from session_log import SessionLogger

    path = tmp_path / 'session.jsonl'
    path.write_text('{"seq":1}\n\n{"seq":2}\n', encoding='utf-8')

    original = Path.read_text
    def forbidden(self, *args, **kwargs):
        if self == path:
            raise AssertionError('session logger must stream long JSONL files')
        return original(self, *args, **kwargs)
    monkeypatch.setattr(Path, 'read_text', forbidden)

    logger = SessionLogger(path)
    try:
        assert logger._seq == 2
    finally:
        logger.close()


def test_session_logger_markdown_streams_source_file(tmp_path, monkeypatch):
    from session_log import SessionLogger

    path = tmp_path / 'session.jsonl'
    path.write_text('{"ts":"t","seq":1,"event":"OPEN"}\n', encoding='utf-8')
    logger = SessionLogger(path)
    original = Path.read_text
    def forbidden(self, *args, **kwargs):
        if self == path:
            raise AssertionError('markdown export must stream long JSONL files')
        return original(self, *args, **kwargs)
    monkeypatch.setattr(Path, 'read_text', forbidden)
    try:
        out = tmp_path / 'session.md'
        logger.write_markdown(out)
        assert '**OPEN**' in out.read_text(encoding='utf-8')
    finally:
        logger.close()


def test_session_log_write_failure_is_nonfatal_and_observable(tmp_path):
    from session_log import SessionLogger

    class BrokenFile:
        closed = False
        def write(self, _text):
            raise OSError('disk full')
        def flush(self):
            raise OSError('disk full')
        def close(self):
            self.closed = True

    logger = SessionLogger(tmp_path / 'session.jsonl')
    logger._fp.close()
    logger._fp = BrokenFile()
    record = logger.log('EDIT', element='a')
    assert record['event'] == 'EDIT'
    assert logger.degraded is True
    assert 'disk full' in logger.last_error


def test_render_resource_bitmap_cache_is_bounded(tmp_path):
    from PIL import Image
    from resource_cache import RenderResources

    resources = RenderResources(bitmap_limit=3)
    paths = []
    for index in range(5):
        path = tmp_path / f'{index}.png'
        Image.new('1', (2, 2), index % 2).save(path)
        paths.append(path.resolve())
        resources.bitmap(path)

    assert len(resources._bitmaps) == 3
    assert paths[0] not in resources._bitmaps
    assert paths[1] not in resources._bitmaps
    assert paths[-1] in resources._bitmaps


def test_render_resource_cache_hit_refreshes_lru_order(tmp_path):
    from PIL import Image
    from resource_cache import RenderResources

    resources = RenderResources(bitmap_limit=2)
    a = tmp_path / 'a.png'; b = tmp_path / 'b.png'; c = tmp_path / 'c.png'
    for path in (a, b, c):
        Image.new('1', (2, 2), 1).save(path)
    resources.bitmap(a); resources.bitmap(b); resources.bitmap(a); resources.bitmap(c)
    assert a.resolve() in resources._bitmaps
    assert b.resolve() not in resources._bitmaps
    assert c.resolve() in resources._bitmaps


def test_render_resource_fontpack_rejects_path_escape_before_reading_external_file(tmp_path, monkeypatch):
    import json
    from resource_cache import RenderResources

    root = tmp_path / 'font'; root.mkdir()
    outside = tmp_path / 'secret.bin'; outside.write_bytes(b'SECRET')
    (root / 'fontpack.json').write_text(json.dumps({
        'schema': 1, 'name': 'bad', 'cell': {'w': 1, 'h': 1}, 'baseline': 0, 'advance': 1,
        'glyphs': {'A': {'asset': '../secret.bin', 'advance': 1}},
    }), encoding='utf-8')

    original = Path.read_bytes
    def guarded(self, *args, **kwargs):
        if self.resolve() == outside.resolve():
            raise AssertionError('cache must not read outside font pack before validation')
        return original(self, *args, **kwargs)
    monkeypatch.setattr(Path, 'read_bytes', guarded)

    with pytest.raises(ValueError, match='inside font pack'):
        RenderResources().font_pack(root)


def test_asset_scan_skips_symlink_that_resolves_outside_project(tmp_path):
    from PIL import Image
    from asset_library import AssetLibrary

    root = tmp_path / 'project'; assets = root / 'assets'; assets.mkdir(parents=True)
    valid = assets / 'valid.png'; Image.new('1', (2, 2), 1).save(valid)
    outside = tmp_path / 'outside.png'; Image.new('1', (2, 2), 1).save(outside)
    link = assets / 'outside.png'
    try:
        link.symlink_to(outside)
    except (OSError, NotImplementedError):
        pytest.skip('symlink creation is unavailable in this environment')

    entries = AssetLibrary(root, ['assets']).scan()
    assert [entry.rel_path for entry in entries] == ['assets/valid.png']


def test_asset_scan_tolerates_file_disappearing_mid_scan(tmp_path, monkeypatch):
    from PIL import Image
    from asset_library import AssetLibrary

    root = tmp_path / 'project'; assets = root / 'assets'; assets.mkdir(parents=True)
    stable = assets / 'stable.png'; transient = assets / 'transient.png'
    Image.new('1', (2, 2), 1).save(stable); Image.new('1', (2, 2), 1).save(transient)

    original = Path.read_bytes
    def flaky(self, *args, **kwargs):
        if self.resolve() == transient.resolve():
            raise FileNotFoundError(self)
        return original(self, *args, **kwargs)
    monkeypatch.setattr(Path, 'read_bytes', flaky)

    entries = AssetLibrary(root, ['assets']).scan()
    assert [entry.rel_path for entry in entries] == ['assets/stable.png']


def test_session_logger_resumes_from_highest_existing_sequence(tmp_path):
    from session_log import SessionLogger

    path = tmp_path / 'session.jsonl'
    path.write_text(
        '{"seq":1,"event":"A"}\n'
        '{broken\n'
        '{"seq":100,"event":"B"}\n',
        encoding='utf-8',
    )
    logger = SessionLogger(path)
    try:
        record = logger.log('C')
        assert record['seq'] == 101
    finally:
        logger.close()
