from pathlib import Path
import sys
SIM=Path(__file__).resolve().parents[1] / 'src'; sys.path.insert(0,str(SIM))
from responsive_layout import plan_layout


def test_responsive_layout_preserves_inspector_and_canvas_at_supported_sizes():
    for width,height in [(960,680),(1180,720),(1440,900),(1920,1080),(2560,1440)]:
        p=plan_layout(width,height)
        assert p.left_width>=180
        assert p.inspector_width>=280
        assert p.canvas_width>=300
        assert 0<=p.diagnostics_height<=280
        assert p.left_width+p.inspector_width+p.canvas_width<=width


def test_large_windows_give_space_to_canvas_not_unbounded_sidebars():
    p=plan_layout(2560,1440)
    assert p.left_width<=300 and p.inspector_width<=380
    assert p.canvas_width>1500
