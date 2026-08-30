from ui_latency import LATENCY_BUDGET_MS,UiLatencyProfiler,percentile

def test_latency_budgets_match_release_contract():
    assert LATENCY_BUDGET_MS['popup_open']==32.0
    assert LATENCY_BUDGET_MS['popup_select_close']==50.0
    assert LATENCY_BUDGET_MS['language_switch']==100.0
    assert LATENCY_BUDGET_MS['theme_switch']==120.0
    assert LATENCY_BUDGET_MS['ui_scale_switch']==150.0

def test_percentile_and_profiler_are_deterministic():
    assert percentile([1,2,3,4,5],.95)==5
    p=UiLatencyProfiler(max_samples=4)
    for v in (10,20,30,40,50):p.record('popup_open',v)
    s=p.summary('popup_open')
    assert s['count']==4 and s['max_ms']==50 and s['p95_ms']==50
    assert not p.within_budget('popup_open')
