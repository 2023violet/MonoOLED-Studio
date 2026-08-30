#!/usr/bin/env python3
from __future__ import annotations

import importlib.util, json, random, sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
SIM=ROOT/'src'
sys.path.insert(0,str(SIM))
sys.path.insert(0,str(ROOT/'tools'))

import VERIFY_V81_STRESS as v81
from popup_geometry import Rect, content_popup_width, place_popup, Size
from popup_state import CloseReason, PopupInteractionState, PopupStateMachine
from qt_theme import build_stylesheet
from theme_system import THEME_NAMES


def popup_state_stress(n=100_000):
    rng=random.Random(0x820)
    closes=list(CloseReason)
    sm=PopupStateMachine()
    opens=closes_count=suppressed=0
    for _ in range(n):
        op=rng.randrange(8)
        if op==0:
            action=sm.anchor_press()
            if action=='open': opens+=1; sm.opened()
            elif action=='close': closes_count+=1; sm.closed(CloseReason.ANCHOR_TOGGLE)
        elif op==1:
            if sm.state in (PopupInteractionState.OPEN,PopupInteractionState.OPENING):
                sm.begin_commit(); sm.closed(CloseReason.ITEM_COMMIT)
        elif op==2:
            sm.closed(CloseReason.OUTSIDE_CLICK,owner_anchor=bool(rng.getrandbits(1)))
        elif op==3:
            if sm.consume_anchor_click(): suppressed+=1
        elif op==4:
            sm.clear_anchor_suppression()
        elif op==5:
            sm.set_enabled(False); assert sm.state is PopupInteractionState.DISABLED
        elif op==6:
            sm.set_enabled(True)
        else:
            sm.closed(rng.choice(closes))
        assert sm.state in PopupInteractionState
    # Deterministic direct user contract at end.
    sm=PopupStateMachine(); assert sm.anchor_press()=='open'; sm.opened(); assert sm.anchor_press()=='close'; sm.closed(CloseReason.ANCHOR_TOGGLE)
    assert sm.consume_anchor_click() is True and sm.state is PopupInteractionState.CLOSED
    assert sm.consume_anchor_click() is False and sm.anchor_press()=='open'
    return {'transitions':n,'opens':opens,'closes':closes_count,'suppressed_anchor_clicks':suppressed}


def popup_sizing_stress(n=50_000):
    rng=random.Random(0x821)
    for _ in range(n):
        anchor_w=rng.randint(48,420)
        widths=[rng.randint(0,500) for __ in range(rng.randint(1,80))]
        max_w=rng.randint(max(72,anchor_w),1200)
        w=content_popup_width(anchor_w,widths,horizontal_padding=34,minimum=72,maximum=max_w)
        assert w>=min(anchor_w,max_w) and 1<=w<=max_w
        screen=Rect(rng.randint(-5000,2000),rng.randint(-2000,1000),rng.randint(320,5120),rng.randint(240,2880))
        anchor=Rect(rng.randint(screen.x-400,screen.right+400),rng.randint(screen.y-400,screen.bottom+400),anchor_w,rng.randint(20,80))
        popup=place_popup(anchor,Size(w,rng.randint(42,1800)),screen,margin=4)
        assert popup.x>=screen.x+4 and popup.y>=screen.y+4 and popup.right<=screen.right-4 and popup.bottom<=screen.bottom-4
    # Explicit regression for the user's narrow Snap control.
    assert content_popup_width(86,[24,32,32,32,32],horizontal_padding=34,minimum=72,maximum=320)<140
    return {'cases':n}


def theme_surface_matrix():
    count=0
    for theme in THEME_NAMES:
        for density in ('compact','comfortable','spacious'):
            for scale in (.9,1.0,1.1,1.25,1.5):
                css=build_stylesheet(theme,density,scale)
                for selector in ('PreferencesRoot','PreferencesPage','PreferencesViewport','StudioSelectPopup','StudioSelectList'):
                    assert selector in css
                assert 'QListWidget#StudioSelectList { background: transparent' not in css.replace('\n',' ')
                count+=1
    return {'cases':count}


def main()->int:
    report={
        'version':'8.2.0',
        'frozen':v81.verify_frozen(),
        'preferences_fuzz':v81.fuzz_preferences(),
        'appearance_matrix':v81.appearance_matrix(),
        'preference_transitions':v81.preference_transitions(),
        'popup_geometry_fuzz':v81.popup_fuzz(),
        'popup_state_stress':popup_state_stress(),
        'popup_sizing_stress':popup_sizing_stress(),
        'theme_surface_matrix':theme_surface_matrix(),
        'responsive_matrix':v81.responsive_matrix(),
        'selection_stress':v81.selection_stress(),
        'pixel_stress':v81.pixel_stress(),
        'font_determinism':v81.font_determinism(),
        'automation_stress':v81.automation_stress(),
        'renderer_stress':v81.renderer_stress(),
    }
    target=SIM/'reports/v82_stress_report.json'
    target.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False,indent=2))
    return 0

if __name__=='__main__': raise SystemExit(main())
