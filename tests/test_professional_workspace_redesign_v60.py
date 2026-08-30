from __future__ import annotations

from pathlib import Path
import sys

SIM = Path(__file__).resolve().parents[1] / 'src'
sys.path.insert(0, str(SIM))


def _source(name: str) -> str:
    return (SIM / name).read_text(encoding='utf-8')


def test_designer_shell_uses_professional_panels_not_bento_cards():
    source = _source('gui.py')
    build_ui = source[source.index('        def _build_ui(self):'):source.index('        def _build_menu(self):')]
    assert 'ProfessionalPanel' in build_ui
    assert 'BentoCard(' not in build_ui
    assert 'self.inspector_tabs=QTabWidget()' in build_ui
    assert 'self.workspace_splitter.setChildrenCollapsible(False)' in build_ui


def test_runtime_and_canvas_settings_are_progressively_disclosed():
    source = _source('gui.py')
    assert "self.inspector_tabs.addTab(self.inspector_page" in source
    assert "self.inspector_tabs.addTab(self.state_page" in source
    # These low-frequency controls must live on the State tab rather than the
    # always-visible properties stack.
    assert 'self.state_layout.addWidget(self.canvas_config_panel)' in source
    assert 'self.state_layout.addWidget(self.runtime_panel)' in source


def _method_source(source: str, name: str) -> str:
    start = source.index(f'        def {name}')
    next_def = source.find('\n        def ', start + 1)
    return source[start:] if next_def < 0 else source[start:next_def]


def test_drag_path_uses_fast_preview_and_defers_full_refresh():
    source = _source('gui.py')
    canvas_move = _method_source(source, '_canvas_move')
    assert 'refresh_drag_preview' in canvas_move
    assert 'refresh_all' not in canvas_move
    finish = _method_source(source, '_finish_canvas_drag')
    assert 'refresh_all(keep_selection=True)' in finish


def test_performance_profiler_exposes_bounded_samples_and_summary():
    from performance_profiler import PerformanceProfiler

    p = PerformanceProfiler(max_samples=4)
    for value in (1.0, 2.0, 3.0, 4.0, 5.0):
        p.record('render', value)
    summary = p.summary('render')
    assert summary.count == 4
    assert summary.latest_ms == 5.0
    assert summary.max_ms == 5.0
    assert summary.avg_ms == 3.5


def test_professional_workspace_model_prioritizes_canvas_and_modes():
    from professional_workspace import workspace_plan, WorkspaceMode

    wide = workspace_plan(1600, 950, WorkspaceMode.DESIGN)
    assert wide.canvas_fraction >= 0.65
    assert wide.left_visible and wide.inspector_visible
    assert wide.bottom_drawer_default is False

    compact = workspace_plan(960, 680, WorkspaceMode.DESIGN)
    assert compact.canvas_fraction >= 0.60
    assert compact.compact

    pixel = workspace_plan(1400, 850, WorkspaceMode.PIXEL)
    assert pixel.tool_rail_width < pixel.inspector_width
    assert pixel.canvas_fraction >= 0.65


def test_pixel_studio_is_a_mode_specific_professional_workspace():
    source = _source('pixel_studio_qt.py')
    assert 'self.workspace_splitter = QSplitter(Qt.Horizontal)' in source
    assert "self.tool_rail.setObjectName('ToolRail')" in source
    assert 'self.inspector_scroll=QScrollArea()' in source
    assert 'self.inspector_tabs' not in source
    assert 'self.statusBar().addWidget(self.pixel_status' in source

def test_pixel_selection_can_move_as_one_undoable_operation():
    from pixel_studio import PixelDocument

    d = PixelDocument(16, 8)
    d.rectangle(2, 2, 4, 4, filled=True)
    before = [row[:] for row in d.pixels]
    d.move_region(2, 2, 3, 3, 4, 0)
    assert d.get(6, 2) == 1
    assert d.get(2, 2) == 0
    assert d.undo()
    assert d.pixels == before

def test_canvas_frame_updates_do_not_relayout_when_dimensions_are_unchanged():
    source = _source('qt_canvas.py')
    method = source[source.index('    def set_frame'):source.index('    def _origin', source.index('    def set_frame'))]
    assert 'size_changed' in method
    assert 'if size_changed:' in method

def test_interaction_benchmark_reports_render_and_validation_costs():
    from interaction_benchmark import benchmark_scene
    result = benchmark_scene('main_scene', iterations=3)
    assert result.iterations == 3
    assert result.render.avg_ms > 0
    assert result.validation.avg_ms > 0
    assert result.full_pipeline.avg_ms >= result.render.avg_ms


def test_explicit_geometry_does_not_resolve_an_unused_bitmap(monkeypatch):
    from editor_model import EditorSession
    from support import load_curing_scene

    scene = load_curing_scene()
    session = EditorSession(scene)
    monkeypatch.setattr(
        session.resources,
        'bitmap',
        lambda _path: (_ for _ in ()).throw(AssertionError('unused bitmap resolution')),
    )

    geometry = session.geometry('battery')

    assert (geometry.x, geometry.y, geometry.w, geometry.h) == (5, 2, 11, 28)
