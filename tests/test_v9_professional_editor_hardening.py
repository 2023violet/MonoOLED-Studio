from pathlib import Path

ROOT=Path(__file__).resolve().parents[1] / 'src'

def text(name): return (ROOT/name).read_text(encoding='utf-8')

def test_three_role_typography_contract():
    src=text('ui_metrics.py')
    for key in ('font_display','font_body','font_metadata'): assert key in src
    for legacy in ('font_small','font_heading','font_caption','font_subhead'): assert legacy not in src

def test_single_panel_language_and_canvas_l1():
    assert 'class BentoCard' not in text('qt_widgets.py')
    css=text('qt_theme.py')
    assert 'QFrame#BentoCard' not in css
    assert "QFrame#CanvasWorkspace" in css and "border: 1px solid" in css

def test_workspace_uses_segmented_control_and_command_hierarchy():
    src=text('gui.py')
    assert "self.workspace_segment=StudioSegmentedControl" in src
    assert "self.header_save.setObjectName('PrimaryButton')" in src
    assert "self.header_validate.setObjectName('SecondaryButton')" in src
    assert "self.header_handoff.setObjectName('SecondaryButton')" in src
    assert "self.header_project.setObjectName('GhostButton')" in src
    assert "setText('⚙')" not in src

def test_technical_values_have_monospace_role():
    src=text('gui.py'); css=text('qt_theme.py')
    assert "TechnicalInput" in src and "TechnicalValue" in src
    assert 'Cascadia Code' in css and 'Consolas' in css

def test_preferences_information_architecture_contract():
    src=text('preferences_qt.py')
    assert 'nav_width = 172' in src
    assert 'content_max_width = 760' in src
    assert 'setMaximumWidth(self.content_max_width)' in src
    assert "'group.appearance'" in src and "setObjectName('SettingRow')" in src
    assert "setObjectName('SearchMatch')" in src
    assert 'setDuration(120)' in src

def test_v9_visual_capture_gate_exists():
    gate=(ROOT.parent/'tools'/'CAPTURE_V9_UI_GOLDENS.py').read_text(encoding='utf-8')
    for marker in ("'1.0','1.25','1.5','1.75','2.0'","'zh_CN','en_US'","'light','dark'",'layout_violations','main.png','preferences.png'): assert marker in gate
