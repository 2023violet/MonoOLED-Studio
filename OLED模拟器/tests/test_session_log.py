import json
import sys
from pathlib import Path

SIM = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SIM))

from session_log import SessionLogger


def test_jsonl_is_flushed_with_sequence_and_callback_and_markdown(tmp_path):
    events = []
    path = tmp_path / 'session.jsonl'
    logger = SessionLogger(path, callback=events.append)
    first = logger.log('EDIT', element='mode_icon', field='x', before=94, after=95)
    second = logger.log('STATE', name='phase', before='standby', after='running')

    lines = path.read_text(encoding='utf-8').splitlines()
    assert len(lines) == 2
    decoded = [json.loads(line) for line in lines]
    assert decoded[0]['seq'] == 1
    assert decoded[1]['seq'] == 2
    assert decoded[0]['event'] == 'EDIT'
    assert decoded[0]['element'] == 'mode_icon'
    assert first == events[0]
    assert second == events[1]

    md = tmp_path / 'session.md'
    logger.write_markdown(md)
    text = md.read_text(encoding='utf-8')
    assert '# OLED UI Session Log' in text
    assert 'EDIT' in text
    assert 'mode_icon' in text
    logger.close()
