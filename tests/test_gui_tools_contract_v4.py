from pathlib import Path
SIM=Path(__file__).resolve().parents[1] / 'src'

def test_gui_exposes_v4_template_conversion_header_and_overview_tools():
    gui=(SIM/'gui.py').read_text(encoding='utf-8')
    for token in ['TemplateLibrary','save_template','insert_template','convert_asset','export_c_header','export_thumbnail_wall','check_design_rules','diff_scenes']:
        assert token in gui
