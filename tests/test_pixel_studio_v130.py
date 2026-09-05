from __future__ import annotations

import sys
from pathlib import Path

SIM = Path(__file__).resolve().parents[1] / 'src'
sys.path.insert(0, str(SIM))

import pixel_studio
from pixel_studio import PixelDocument


def test_pack_unpack_round_trip_preserves_pixels():
    rows = [[0, 1, 0, 1, 1, 0, 0, 1, 1], [1, 0, 0, 0, 0, 0, 0, 0, 0]]
    packed = PixelDocument._pack_pixels(rows)
    assert PixelDocument._unpack_pixels(packed, 9, 2) == rows
    # 18 pixels pack into 3 bytes
    assert len(packed) == 3


def test_undo_redo_state_survives_bit_packing():
    document = PixelDocument(4, 3)
    before = [row[:] for row in document.pixels]
    document.pencil(2, 1, 1)
    document.brush(0, 0, 1, size=2)
    assert document.get(2, 1) == 1 and document.get(0, 0) == 1
    # one undo reverts the brush only; the second reverts the pencil
    assert document.undo() and document.get(0, 0) == 0 and document.get(2, 1) == 1
    assert document.undo() and document.pixels == before
    assert document.redo() and document.get(2, 1) == 1


def test_gesture_coalescing_keeps_single_undo_entry():
    document = PixelDocument(8, 8)
    document.begin_gesture()
    for x in range(8):
        document.stroke_segment(x, 0, x, 7, value=1)
    document.end_gesture()
    assert len(document._undo) == 1
    entries_before = len(document._undo)
    document.begin_gesture()
    document.stroke_segment(0, 0, 7, 7, value=0)
    document.end_gesture()
    assert len(document._undo) == entries_before + 1


def test_undo_budget_prunes_by_packed_size(monkeypatch):
    monkeypatch.setattr(pixel_studio, 'MAX_UNDO_BYTES', 24 * 1024)
    document = PixelDocument(256, 256, max_undo=200)  # packed snapshot = 8 KiB -> cap = 3
    assert document._effective_limit() == 3
    for step in range(6):
        document.pencil(step, 0, 1)
    assert len(document._undo) == 3
    # The three most recent snapshots are retained: undoing three steps restores
    # the canvas right after step 2.
    for _ in range(3):
        assert document.undo()
    assert document.get(2, 0) == 1 and document.get(3, 0) == 0
    assert document.undo() is False


def test_large_canvas_undo_depth_is_bounded_by_budget():
    document = PixelDocument(512, 512, max_undo=200)  # packed snapshot = 32 KiB -> cap = 2048
    assert document._effective_limit() == 200
    huge = PixelDocument(4096, 4096, max_undo=200)  # packed snapshot = 2 MiB -> cap = 32
    assert huge._effective_limit() == 32


def test_clear_region_is_single_undoable_edit():
    document = PixelDocument(8, 8)
    document.rectangle(0, 0, 7, 7, filled=True)
    assert document.get(3, 3) == 1
    document.clear_region(2, 2, 3, 3)
    assert document.get(3, 3) == 0
    assert document.get(0, 0) == 1 and document.get(7, 7) == 1
    assert len(document._undo) == 2  # rectangle + clear_region
    assert document.undo() and document.get(3, 3) == 1
