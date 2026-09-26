# Rust V2 Python Reference Goldens

This is the first Phase 0 batch, not a complete compatibility certification.
Decision and gate scope: [Rust Validation Plan](../../.ai/rust/VALIDATION_PLAN.md).

Run from repository root:

```powershell
python tools/VERIFY_RUST_GOLDENS.py
python -m pytest tests/test_rust_golden_baseline.py -q
```

goldens.json schema 1 stores inputs and frozen expected results together.
Rows are strings of 0/1 in top-to-bottom order; x increases left-to-right.
Hex is lowercase, two digits per byte. SHA-256 hashes decoded binary bytes.
Project results compare JSON objects semantically; ordered arrays remain ordered.
Glyph PNG encodings and host fonts are excluded; stored pixels/metrics are truth.

The verifier reads goldens and invokes Python production functions; it has no
record/update mode. It uses temporary directories for persistence roundtrips,
does not write source fixtures, and exits nonzero on mismatch.
Reference source Git blob IDs are provenance, not hashes of checkout line endings.
The verifier exercises the current checkout; provenance is the frozen source
snapshot, so source changes require a separate review even if fixtures still pass.

The eight encoding expectations are cross-checked with pre-existing literal
tests. Other expectations were captured once from the pinned Python reference,
then stored; meaningful anchors and corruption detection are tested separately.
Review expected values before treating these files as an accepted migration gate.
Do not “fix” mismatch by regenerating expected data.

Coverage gaps: invalid input matrix, undo/redo/gesture traces, visual overlays,
full scene renderer, all export profiles/indices, TrueType/system fonts, project
migrations and failure recovery, protocol frames, GUI and non-Windows execution.
Add these before porting their corresponding behavior. Protocols must first be
specified; this batch creates no invented device contract.
