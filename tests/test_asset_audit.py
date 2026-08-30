import sys
from pathlib import Path

SIM = Path(__file__).resolve().parents[1] / 'src'
ROOT = SIM.parent
sys.path.insert(0, str(SIM))

from asset_audit import audit_assets


def test_asset_audit_classifies_project_bitmaps_and_keeps_failures_visible():
    report = audit_assets(ROOT)
    assert report['summary']['images_scanned'] >= 400
    assert report['summary']['black_on_white'] > 0
    assert report['summary']['white_on_black'] > 0
    assert report['summary']['transparent'] > 0
    assert report['summary']['non_binary_or_invalid'] >= 1
    assert any(item['status'] == 'invalid' for item in report['assets'])
