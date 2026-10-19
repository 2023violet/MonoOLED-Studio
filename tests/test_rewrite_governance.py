from __future__ import annotations

from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]


def test_adr_005_records_rewrite_decision():
    text = (ROOT / '.ai' / 'DECISIONS.md').read_text(encoding='utf-8')
    section = text[text.index('## ADR-005'):]
    for phrase in ('main-only', 'v1-final', 'docs/rewrite/2026-10-19-rust-rewrite-design.md',
                   'Rust ADR-001', 'NOT_VERIFIED', 'bugfix-only'):
        assert phrase in section


def test_current_state_points_to_rewrite_spec_without_git_snapshot():
    text = (ROOT / '.ai' / 'CURRENT_STATE.md').read_text(encoding='utf-8')
    assert re.search(r'^- Current phase: Rust Rewrite G\d', text, re.MULTILINE)
    assert '- Rewrite spec: docs/rewrite/2026-10-19-rust-rewrite-design.md' in text
    assert not re.search(r'\b[0-9a-f]{40}\b', text)
