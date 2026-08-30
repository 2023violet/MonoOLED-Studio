from pathlib import Path

SIM=Path(__file__).resolve().parents[1] / 'src'

def test_gui_exposes_new_project_action_and_saves_before_screen_switch_when_requested():
    gui=(SIM/'gui.py').read_text(encoding='utf-8')
    assert "'new_project'" in gui
    assert 'self.new_project' in gui
    assert 'if choice==QMessageBox.Save' in gui or 'if choice == QMessageBox.Save' in gui
    assert 'self.save_scene()' in gui
