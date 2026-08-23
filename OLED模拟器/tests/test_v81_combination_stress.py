import itertools, random
from preferences import default_preferences
from runtime_settings import RuntimeSettings
from preference_delta import PreferenceDelta
from theme_system import THEME_NAMES, resolve_theme_name
from qt_theme import build_stylesheet
from popup_geometry import Rect, Size, place_popup
from responsive_layout import plan_layout

SCALES=('auto','90%','100%','110%','125%','150%')
MODES=('system','light','dark')
LANGS=('zh_CN','en_US')
DENSITIES=('compact','comfortable','spacious')


def runtime(theme='monooled-light',mode='system',lang='zh_CN',density='comfortable',scale='auto'):
    p=default_preferences();p['appearance'].update(color_theme=theme,theme_mode=mode,density=density,ui_scale=scale);p['language']=lang
    return RuntimeSettings.from_preferences(p)


def test_432_appearance_combinations_build_without_semantic_drift():
    count=0
    for theme,mode,lang,density,scale in itertools.product(THEME_NAMES,MODES,LANGS,DENSITIES,SCALES):
        r=runtime(theme,mode,lang,density,scale);resolved=resolve_theme_name(r.color_theme,r.theme_mode,system_dark=False);css=build_stylesheet(resolved,r.density,r.ui_scale)
        assert 'StudioSelectPopup' in css and 'font-size:' in css
        count+=1
    assert count==432


def test_10000_random_runtime_transitions_never_request_product_render():
    rng=random.Random(8100);prev=runtime()
    for _ in range(10_000):
        cur=runtime(rng.choice(THEME_NAMES),rng.choice(MODES),rng.choice(LANGS),rng.choice(DENSITIES),rng.choice(SCALES))
        d=PreferenceDelta.between(prev,cur)
        assert not d.requires_product_render
        assert d.effects <= {'language','theme','metrics','canvas','pixel','autosave','performance','shortcuts','startup'}
        prev=cur


def test_20000_popup_geometry_fuzz_never_escapes_available_screen():
    rng=random.Random(8101)
    for _ in range(20_000):
        sx=rng.randint(-3840,1920);sy=rng.randint(-1200,1200);sw=rng.randint(320,3840);sh=rng.randint(240,2160)
        screen=Rect(sx,sy,sw,sh);anchor=Rect(rng.randint(sx-500,sx+sw+500),rng.randint(sy-500,sy+sh+500),rng.randint(30,600),rng.randint(20,80));desired=Size(rng.randint(40,1200),rng.randint(40,2400))
        r=place_popup(anchor,desired,screen,margin=4)
        assert r.x>=screen.x+4 and r.y>=screen.y+4
        assert r.right<=screen.right-4 and r.bottom<=screen.bottom-4


def test_responsive_layout_extreme_matrix_remains_usable():
    sizes=((900,620),(1024,768),(1280,720),(1366,768),(1440,900),(1920,1080),(2560,1440),(3840,2160))
    for (w,h),density,scale in itertools.product(sizes,DENSITIES,(.9,1.0,1.1,1.25,1.5)):
        p=plan_layout(w,h,density,scale)
        assert p.left_width>0 and p.inspector_width>0 and p.canvas_width>=300 and p.diagnostics_height>=140
