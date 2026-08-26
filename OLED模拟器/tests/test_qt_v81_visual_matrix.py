import itertools, os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import pytest
pytest.importorskip('PySide6');pytest.importorskip('pytestqt')

from pathlib import Path
from PySide6.QtWidgets import QApplication

from gui import OLEDDesignerWindow
from font_pack import create_font_pack
from scene import scene_root
from theme_system import THEME_NAMES
from ui_controls import PopupManager,StudioSelect

LANGS=('zh_CN','en_US')
DENSITIES=('compact','comfortable','spacious')
UI_SCALES=('auto','90%','100%','110%','125%','150%')
THEME_MODES={
    'monooled-light':'light',
    'monooled-dark':'dark',
    'one-dark-pro':'system',
    'high-contrast':'system',
}


def _open_embedded_surfaces(window,tmp_path):
    image=next(
        e for e in window.scene['elements']
        if e.get('type')=='image'
        and e.get('asset')
        and '{' not in str(e.get('asset'))
        and (scene_root(window.scene)/str(e.get('asset'))).is_file()
    )
    window._set_selection([str(image['id'])],source='matrix',primary=str(image['id']))
    window.open_pixel_studio()
    pixel=window.editor_tabs.currentWidget()
    pack=create_font_pack(tmp_path/'font','Matrix Font',cell=(5,8),baseline=6,advance=6);pack.save()
    window.open_font_lab(pack.root)
    font=window.editor_tabs.currentWidget()
    window.open_preferences();prefs=window._preferences_window
    if not window._diagnostics_open:window.toggle_diagnostics()
    return pixel,font,prefs


def test_v81_five_surface_theme_language_density_ui_scale_matrix(qtbot,tmp_path,monkeypatch):
    # Keep this release test isolated from the developer/user profile.
    monkeypatch.setenv('LOCALAPPDATA',str(tmp_path/'localappdata'));monkeypatch.setenv('XDG_CONFIG_HOME',str(tmp_path/'config'))
    w=OLEDDesignerWindow('main_scene');qtbot.addWidget(w);w.resize(1440,900);w.show();qtbot.wait(20)
    pixel,font,prefs=_open_embedded_surfaces(w,tmp_path);qtbot.addWidget(prefs);prefs.show();qtbot.wait(10)
    baseline=w.session.render().framebuffer.to_vlsb();baseline_tab=w.editor_tabs.currentIndex();baseline_ids=tuple(w.selection_model.ids);count=0
    for theme,lang,density,scale in itertools.product(THEME_NAMES,LANGS,DENSITIES,UI_SCALES):
        w.preferences.set('language',lang,save=False);w.preferences.set('appearance.color_theme',theme,save=False);w.preferences.set('appearance.theme_mode',THEME_MODES[theme],save=False);w.preferences.set('appearance.density',density,save=False);w.preferences.set('appearance.ui_scale',scale,save=False)
        w.apply_preferences();QApplication.processEvents();count+=1
        violations=w.layout_violations()
        assert violations==[],(
            theme,lang,density,scale,violations,
            {
                'splitter':w.workspace_splitter.sizes(),
                'tabs':w.inspector_tabs.width(),
                'viewport':w.inspector_page.viewport().width(),
                'content':w.inspector_inner.width(),
                'content_hint':w.inspector_inner.sizeHint().width(),
                'properties_hint':w.properties_card.sizeHint().width(),
                'alignment_hint':w.align_card.sizeHint().width(),
            },
        )
        assert pixel.layout_violations()==[],(theme,lang,density,scale,pixel.layout_violations())
        assert font.layout_violations()==[],(theme,lang,density,scale,font.layout_violations())
        assert prefs.layout_violations()==[],(theme,lang,density,scale,prefs.layout_violations())
        assert pixel.tr.language==lang and font.tr.language==lang and prefs.tr.language==lang
        assert pixel.canvas.theme_name==w._resolved_theme and font.canvas.theme_name==w._resolved_theme
        assert w.session.render().framebuffer.to_vlsb()==baseline,('UI-only preference mutated OLED truth',theme,lang,density,scale)
        assert tuple(w.selection_model.ids)==baseline_ids
        assert w.editor_tabs.currentIndex()==baseline_tab
        assert PopupManager.visible_count()<=1
    assert count==144


def test_v81_system_light_dark_mode_transitions_keep_product_truth(qtbot,tmp_path,monkeypatch):
    monkeypatch.setenv('LOCALAPPDATA',str(tmp_path/'localappdata'));monkeypatch.setenv('XDG_CONFIG_HOME',str(tmp_path/'config'))
    w=OLEDDesignerWindow('main_scene');qtbot.addWidget(w);w.show();qtbot.wait(20);baseline=w.session.render().framebuffer.to_vlsb()
    for mode,theme in (('light','monooled-light'),('dark','monooled-dark'),('system','monooled-light'),('system','monooled-dark'),('system','one-dark-pro'),('system','high-contrast')):
        w.preferences.set('appearance.theme_mode',mode,save=False);w.preferences.set('appearance.color_theme',theme,save=False);w.apply_preferences();QApplication.processEvents();assert w.session.render().framebuffer.to_vlsb()==baseline


def test_v81_popup_survives_theme_language_transition_without_leak(qtbot):
    combo=StudioSelect();qtbot.addWidget(combo);combo.addItems(['简体中文','English','High Contrast']);combo.resize(260,34);combo.show();qtbot.wait(5)
    for _ in range(50):
        combo.showPopup();QApplication.processEvents();assert PopupManager.visible_count()==1;combo.hidePopup();QApplication.processEvents();assert PopupManager.visible_count()==0
