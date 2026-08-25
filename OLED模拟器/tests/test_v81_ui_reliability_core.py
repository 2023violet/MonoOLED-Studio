from copy import deepcopy

import pytest

from preferences import default_preferences
from runtime_settings import RuntimeSettings
from workspace_host import EditorRegistry


def _runtime(**changes):
    data=default_preferences()
    for path,value in changes.items():
        if path.startswith('shortcuts.'):
            data['shortcuts'][path[len('shortcuts.'):]]=value
            continue
        node=data
        parts=path.split('.')
        for p in parts[:-1]: node=node[p]
        node[parts[-1]]=value
    return RuntimeSettings.from_preferences(data)


def test_preference_delta_is_effect_scoped_and_does_not_mark_renderer_for_ui_only_changes():
    from preference_delta import PreferenceDelta
    before=_runtime()
    after=_runtime(**{'language':'en_US'})
    d=PreferenceDelta.between(before,after)
    assert d.language_changed
    assert not d.theme_changed
    assert not d.canvas_changed
    assert not d.requires_product_render
    assert d.effects == frozenset({'language'})

    after2=_runtime(**{'appearance.color_theme':'monooled-dark','appearance.ui_scale':'150%'})
    d2=PreferenceDelta.between(before,after2)
    assert d2.theme_changed and d2.ui_metrics_changed
    assert d2.effects == frozenset({'theme','metrics'})
    assert not d2.requires_product_render


def test_preference_delta_isolated_canvas_pixel_autosave_and_shortcut_domains():
    from preference_delta import PreferenceDelta
    before=_runtime()
    cases={
        'canvas.grid':False,
        'pixel_studio.brush_size':3,
        'autosave.interval_minutes':5,
        'performance.asset_cache_mb':256,
        'shortcuts.project.save':'Ctrl+Alt+S',
    }
    expected={'canvas.grid':'canvas','pixel_studio.brush_size':'pixel','autosave.interval_minutes':'autosave','performance.asset_cache_mb':'performance','shortcuts.project.save':'shortcuts'}
    for key,value in cases.items():
        d=PreferenceDelta.between(before,_runtime(**{key:value}))
        assert d.effects == frozenset({expected[key]}), (key,d.effects)


def test_popup_geometry_places_below_when_possible_and_above_at_bottom():
    from popup_geometry import Rect, Size, place_popup
    screen=Rect(0,0,1920,1080)
    anchor=Rect(100,100,220,34)
    r=place_popup(anchor,Size(220,320),screen,gap=4)
    assert r.x==100 and r.y==138
    assert r.right<=screen.right and r.bottom<=screen.bottom

    bottom=Rect(100,1030,220,34)
    r2=place_popup(bottom,Size(220,320),screen,gap=4)
    assert r2.bottom <= bottom.y-4
    assert r2.y>=screen.y


def test_popup_geometry_clamps_right_and_oversized_height():
    from popup_geometry import Rect, Size, place_popup
    screen=Rect(-1920,0,1920,1040)
    anchor=Rect(-120,900,220,34)
    r=place_popup(anchor,Size(500,2000),screen,gap=4,margin=8)
    assert r.x>=screen.x+8
    assert r.right<=screen.right-8
    assert r.y>=screen.y+8
    assert r.bottom<=screen.bottom-8
    assert r.h<=screen.h-16


def test_editor_registry_broadcasts_runtime_delta_without_touching_non_consumers():
    class E:
        def __init__(self,id): self.document_id=id; self.seen=[]
        def apply_runtime_delta(self,delta): self.seen.append(delta)
    class Legacy:
        document_id='legacy'
    r=EditorRegistry(); a=E('a'); b=E('b'); legacy=Legacy()
    r.open(a);r.open(b);r.open(legacy)
    marker=object()
    count=r.apply_runtime_delta(marker)
    assert count==2
    assert a.seen==[marker] and b.seen==[marker]


def test_theme_has_semantic_status_tokens_for_all_themes():
    from theme_system import THEME_NAMES, get_theme
    keys={
      'status.neutral.background','status.neutral.foreground',
      'status.accent.background','status.accent.foreground',
      'status.success.background','status.success.foreground',
      'status.warning.background','status.warning.foreground',
      'status.error.background','status.error.foreground',
      'popover.shadow','overlay.scrim',
    }
    for name in THEME_NAMES:
        t=get_theme(name)
        assert keys <= set(t), (name, keys-set(t))


def test_ui_metrics_scale_typography_icons_and_navigation_not_only_control_height():
    from ui_metrics import build_ui_metrics
    a=build_ui_metrics('comfortable',1.0)
    b=build_ui_metrics('comfortable',1.5)
    for key in ('control','row','font_body','font_small','font_heading','icon','gap','panel_margin','nav_min','inspector_min'):
        assert b[key] > a[key], key
