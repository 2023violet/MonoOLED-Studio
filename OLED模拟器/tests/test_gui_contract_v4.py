from pathlib import Path

SIM=Path(__file__).resolve().parents[1]
GUI=(SIM/'gui.py').read_text(encoding='utf-8')
CANVAS=(SIM/'qt_canvas.py').read_text(encoding='utf-8')


def test_v4_gui_uses_project_assets_autosave_diff_and_handoff_services():
    for token in ['ProjectWorkspace','AssetLibrary','AutoSaveManager','diff_framebuffers','build_handoff_package','align','measure']:
        assert token in GUI


def test_phase2_gui_batch_exports_use_schema_matrix_without_clinical_preset():
    assert 'build_export_states' in GUI
    assert 'clinical_states' not in GUI


def test_v4_geometry_editor_is_two_by_two_not_four_columns():
    assert 'geom_grid.addWidget(label, 0, index)' not in GUI
    assert 'index // 2' in GUI and 'index % 2' in GUI


def test_v4_layout_reacts_to_viewport_and_splitter_changes_and_has_collapsible_diagnostics():
    assert 'installEventFilter' in GUI
    assert 'splitterMoved.connect' in GUI
    assert 'toggle_diagnostics' in GUI
    assert 'setMaximumHeight(300)' not in GUI


def test_v4_canvas_supports_multiselect_pixel_hover_and_drag_finish():
    assert 'selectionChanged' in CANVAS
    assert 'pixelHovered' in CANVAS
    assert 'dragFinished' in CANVAS
