from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / 'src'
sys.path.insert(0, str(SRC))

from c_export import write_c_header
from component_templates import TemplateLibrary
from exporter import export_scene
from font_generator import generate_glyphs
from framebuffer import FrameBuffer
from handoff import build_handoff_package


def _scene(tmp_path: Path, width: int = 16, height: int = 8) -> dict:
    return {
        '_path': str(tmp_path / 'scene.json'),
        '_root': str(tmp_path),
        'schema_version': 1,
        'product': 'artifact-integrity-test',
        'canvas': {'w': width, 'h': height},
        'storage': {'layout': 'VLSB', 'polarity': '1 = lit', 'bytes_per_frame': width * (height // 8)},
        'states': {},
        'elements': [],
        'timeline': [],
    }


def _tree_bytes(root: Path) -> dict[str, bytes]:
    return {
        p.relative_to(root).as_posix(): p.read_bytes()
        for p in sorted(root.rglob('*'))
        if p.is_file()
    }


def test_export_rejects_unsafe_frame_names_before_writing_outside_output(tmp_path):
    out = tmp_path / 'export'
    outside = tmp_path / 'escape.bin'
    with pytest.raises(ValueError, match='frame name'):
        export_scene(_scene(tmp_path), out, {'../../escape': {}})
    assert not outside.exists()
    assert not (out / 'golden').exists() or not any((out / 'golden').iterdir())


def test_export_prunes_stale_managed_frames_after_successful_reexport(tmp_path):
    out = tmp_path / 'export'
    scene = _scene(tmp_path)
    export_scene(scene, out, {'old': {}, 'keep': {}})
    assert (out / 'golden' / 'old.bin').exists()
    assert (out / 'reference' / 'old.png').exists()

    export_scene(scene, out, {'keep': {}})

    assert not (out / 'golden' / 'old.bin').exists()
    assert not (out / 'reference' / 'old.png').exists()
    assert (out / 'golden' / 'keep.bin').exists()
    assert (out / 'reference' / 'keep.png').exists()


def test_export_golden_write_failure_preserves_existing_file(tmp_path, monkeypatch):
    import atomic_io

    out = tmp_path / 'export'
    target = out / 'golden' / 'frame.bin'
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(b'OLD-GOLDEN')
    real_replace = atomic_io.os.replace

    def fail_frame_replace(src, dst):
        if Path(dst) == target:
            raise OSError('simulated replace failure')
        return real_replace(src, dst)

    monkeypatch.setattr(atomic_io.os, 'replace', fail_frame_replace)
    with pytest.raises(OSError, match='simulated replace failure'):
        export_scene(_scene(tmp_path), out, {'frame': {}})
    assert target.read_bytes() == b'OLD-GOLDEN'
    assert not target.with_name(target.name + '.tmp').exists()


def test_handoff_packaging_failure_preserves_existing_zip(tmp_path, monkeypatch):
    import handoff

    target = tmp_path / 'handoff.zip'
    target.write_bytes(b'OLD-HANDOFF')
    real_writestr = handoff.zipfile.ZipFile.writestr
    calls = {'n': 0}

    def fail_first_write(self, *args, **kwargs):
        calls['n'] += 1
        if calls['n'] == 1:
            raise OSError('simulated zip failure')
        return real_writestr(self, *args, **kwargs)

    monkeypatch.setattr(handoff.zipfile.ZipFile, 'writestr', fail_first_write)
    with pytest.raises(OSError, match='simulated zip failure'):
        build_handoff_package(_scene(tmp_path), target, states={'main': {}})
    assert target.read_bytes() == b'OLD-HANDOFF'
    assert not target.with_name(target.name + '.tmp').exists()


def test_template_save_failure_rolls_back_in_memory_state(tmp_path, monkeypatch):
    lib = TemplateLibrary(tmp_path / 'templates.json')
    lib.save_template('existing', [{'id': 'a', 'type': 'text', 'text': 'A', 'x': 0, 'y': 0}])

    def fail_save():
        raise OSError('disk full')

    monkeypatch.setattr(lib, 'save', fail_save)
    with pytest.raises(OSError, match='disk full'):
        lib.save_template('new', [{'id': 'b', 'type': 'text', 'text': 'B', 'x': 1, 'y': 1}])
    assert lib.names() == ['existing']


def test_template_programming_failure_is_not_treated_as_persistence_failure(tmp_path, monkeypatch):
    lib = TemplateLibrary(tmp_path / 'templates.json')

    def fail_save():
        raise RuntimeError('programming failure')

    monkeypatch.setattr(lib, 'save', fail_save)
    with pytest.raises(RuntimeError, match='programming failure'):
        lib.save_template('new', [{'id': 'b', 'type': 'text', 'text': 'B', 'x': 1, 'y': 1}])
    assert lib.names() == ['new']


def test_font_generator_removes_stale_managed_glyphs_on_success(tmp_path):
    out = tmp_path / 'glyphs'
    generate_glyphs('AB', output_dir=out, cell=(12, 16))
    stale = out / 'U+0042.png'
    assert stale.exists()

    generate_glyphs('A', output_dir=out, cell=(12, 16))

    assert (out / 'U+0041.png').exists()
    assert not stale.exists()


def test_font_generation_failure_leaves_previous_output_unchanged(tmp_path, monkeypatch):
    out = tmp_path / 'glyphs'
    generate_glyphs('Z', output_dir=out, cell=(12, 16))
    before = _tree_bytes(out)
    real_save = Image.Image.save
    calls = {'n': 0}

    def fail_second_save(self, fp, *args, **kwargs):
        calls['n'] += 1
        if calls['n'] == 2:
            raise OSError('simulated glyph render failure')
        return real_save(self, fp, *args, **kwargs)

    monkeypatch.setattr(Image.Image, 'save', fail_second_save)
    with pytest.raises(OSError, match='simulated glyph render failure'):
        generate_glyphs('AB', output_dir=out, cell=(12, 16))
    assert _tree_bytes(out) == before


def test_c_header_replace_failure_preserves_existing_file(tmp_path, monkeypatch):
    import atomic_io

    target = tmp_path / 'frame.h'
    target.write_text('OLD-HEADER\n', encoding='utf-8')
    real_replace = atomic_io.os.replace

    def fail_target_replace(src, dst):
        if Path(dst) == target:
            raise OSError('simulated header replace failure')
        return real_replace(src, dst)

    monkeypatch.setattr(atomic_io.os, 'replace', fail_target_replace)
    fb = FrameBuffer(16, 8)
    with pytest.raises(OSError, match='simulated header replace failure'):
        write_c_header(fb, target, name='frame')
    assert target.read_text(encoding='utf-8') == 'OLD-HEADER\n'
    assert not target.with_name(target.name + '.tmp').exists()


def test_export_rejects_case_insensitive_frame_name_collisions_for_windows(tmp_path):
    with pytest.raises(ValueError, match='collision'):
        export_scene(_scene(tmp_path), tmp_path / 'export', {'HOME': {}, 'home': {}})


def test_export_prunes_legacy_nested_managed_frames(tmp_path):
    out = tmp_path / 'export'
    legacy_bin = out / 'golden' / 'legacy' / 'old.bin'
    legacy_png = out / 'reference' / 'legacy' / 'old.png'
    legacy_bin.parent.mkdir(parents=True, exist_ok=True); legacy_bin.write_bytes(b'old')
    legacy_png.parent.mkdir(parents=True, exist_ok=True); legacy_png.write_bytes(b'old')

    export_scene(_scene(tmp_path), out, {'current': {}})

    assert not legacy_bin.exists()
    assert not legacy_png.exists()
    assert not (out / 'golden' / 'legacy').exists()
    assert not (out / 'reference' / 'legacy').exists()


def test_font_generator_preserves_unmanaged_codepoint_named_png(tmp_path):
    out = tmp_path / 'glyphs'
    out.mkdir()
    unmanaged = out / 'U+9999.png'
    unmanaged.write_bytes(b'USER-OWNED')

    generate_glyphs('A', output_dir=out, cell=(12, 16))

    assert unmanaged.read_bytes() == b'USER-OWNED'


def test_corrupt_template_library_is_quarantined_and_does_not_block_project_open(tmp_path):
    path = tmp_path / '.oled' / 'templates.json'
    path.parent.mkdir(parents=True)
    original = b'{not-json'
    path.write_bytes(original)

    lib = TemplateLibrary(path)

    assert lib.names() == []
    quarantine = path.parent / 'quarantine'
    copies = list(quarantine.glob('templates.corrupt.*.json'))
    assert len(copies) == 1
    assert copies[0].read_bytes() == original


def test_semantically_invalid_template_library_is_quarantined(tmp_path):
    path = tmp_path / '.oled' / 'templates.json'
    path.parent.mkdir(parents=True)
    path.write_text('{"schema_version":1,"templates":[]}', encoding='utf-8')

    lib = TemplateLibrary(path)

    assert lib.names() == []
    copies = list((path.parent / 'quarantine').glob('templates.corrupt.*.json'))
    assert len(copies) == 1


def test_autosave_retention_delete_failure_does_not_make_snapshot_fail(tmp_path, monkeypatch):
    from autosave import AutoSaveManager

    scene = _scene(tmp_path)
    scene['_path'] = str(tmp_path / 'scene.json')
    (tmp_path / 'scene.json').write_text('{}', encoding='utf-8')
    mgr = AutoSaveManager(scene, keep=1)
    first = mgr.snapshot(reason='first')
    real_unlink = Path.unlink

    def fail_old_unlink(self, *args, **kwargs):
        if self == first:
            raise OSError('file busy')
        return real_unlink(self, *args, **kwargs)

    monkeypatch.setattr(Path, 'unlink', fail_old_unlink)
    second = mgr.snapshot(reason='second')

    assert second.exists()
    assert first.exists()  # Retention cleanup is best-effort; the fresh snapshot remains valid.


def test_set_keep_tolerates_busy_old_snapshot(tmp_path, monkeypatch):
    from autosave import AutoSaveManager

    scene = _scene(tmp_path)
    scene['_path'] = str(tmp_path / 'scene.json')
    mgr = AutoSaveManager(scene, keep=3)
    first = mgr.snapshot(reason='first')
    mgr.snapshot(reason='second')
    real_unlink = Path.unlink

    def fail_old_unlink(self, *args, **kwargs):
        if self == first:
            raise OSError('file busy')
        return real_unlink(self, *args, **kwargs)

    monkeypatch.setattr(Path, 'unlink', fail_old_unlink)
    mgr.set_keep(1)
    assert mgr.keep == 1


def test_recovery_candidate_stat_race_does_not_escape_to_ui(tmp_path, monkeypatch):
    from autosave import AutoSaveManager

    scene_path = tmp_path / 'scene.json'
    scene_path.write_text('{}', encoding='utf-8')
    scene = _scene(tmp_path); scene['_path'] = str(scene_path)
    mgr = AutoSaveManager(scene, keep=2)
    snap = mgr.snapshot(reason='timer')
    real_stat = Path.stat

    def flaky_stat(self, *args, **kwargs):
        if self == scene_path:
            raise OSError('sharing violation')
        return real_stat(self, *args, **kwargs)

    monkeypatch.setattr(Path, 'stat', flaky_stat)
    assert mgr.recovery_candidate() == snap


def test_session_log_ui_callback_failure_does_not_break_primary_logging(tmp_path):
    from session_log import SessionLogger

    def broken_callback(_record):
        raise RuntimeError('UI mirror failed')

    path = tmp_path / 'session.jsonl'
    logger = SessionLogger(path, callback=broken_callback)
    try:
        record = logger.log('EDIT', element='hero')
    finally:
        logger.close()
    assert record['event'] == 'EDIT'
    assert '"event": "EDIT"' in path.read_text(encoding='utf-8')


def test_session_markdown_replace_failure_preserves_existing_report(tmp_path, monkeypatch):
    import atomic_io
    from session_log import SessionLogger

    log = tmp_path / 'session.jsonl'
    logger = SessionLogger(log); logger.log('EDIT'); logger.close()
    target = tmp_path / 'session.md'; target.write_text('OLD-SESSION\n', encoding='utf-8')
    real_replace = atomic_io.os.replace

    def fail_target(src, dst):
        if Path(dst) == target:
            raise OSError('session report replace failed')
        return real_replace(src, dst)

    monkeypatch.setattr(atomic_io.os, 'replace', fail_target)
    with pytest.raises(OSError, match='session report replace failed'):
        logger.write_markdown(target)
    assert target.read_text(encoding='utf-8') == 'OLD-SESSION\n'


def test_batch_validation_report_replace_failure_preserves_existing_report(tmp_path, monkeypatch):
    import atomic_io
    from batch_validate import MatrixValidationSummary, write_matrix_report

    target = tmp_path / 'matrix.md'; target.write_text('OLD-MATRIX\n', encoding='utf-8')
    summary = MatrixValidationSummary(1, 0, 0, (('case_0000', tuple()),))
    real_replace = atomic_io.os.replace

    def fail_target(src, dst):
        if Path(dst) == target:
            raise OSError('matrix replace failed')
        return real_replace(src, dst)

    monkeypatch.setattr(atomic_io.os, 'replace', fail_target)
    with pytest.raises(OSError, match='matrix replace failed'):
        write_matrix_report(summary, target)
    assert target.read_text(encoding='utf-8') == 'OLD-MATRIX\n'


def test_asset_audit_report_replace_failure_preserves_existing_json(tmp_path, monkeypatch):
    import atomic_io
    from asset_audit import write_report

    source = tmp_path / 'source'; source.mkdir()
    output = tmp_path / 'audit'; output.mkdir()
    target = output / 'asset_audit.json'; target.write_text('OLD-AUDIT\n', encoding='utf-8')
    real_replace = atomic_io.os.replace

    def fail_target(src, dst):
        if Path(dst) == target:
            raise OSError('audit replace failed')
        return real_replace(src, dst)

    monkeypatch.setattr(atomic_io.os, 'replace', fail_target)
    with pytest.raises(OSError, match='audit replace failed'):
        write_report(source, output)
    assert target.read_text(encoding='utf-8') == 'OLD-AUDIT\n'
