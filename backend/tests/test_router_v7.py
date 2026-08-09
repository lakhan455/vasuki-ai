from app.services.router_v7 import classify_route
def test_short_code_is_strong():
    d=classify_route([{"role":"user","content":"Fix this TypeError"}])
    assert d.task_type=="code" and d.tier=="strong"
def test_logic_is_strong():
    d=classify_route([{"role":"user","content":"Prove sqrt(2) is irrational"}])
    assert d.task_type=="reasoning" and d.tier=="strong"
def test_hello_is_fast():
    d=classify_route([{"role":"user","content":"hello"}])
    assert d.task_type=="simple" and d.tier=="fast"
def test_latest_is_research():
    d=classify_route([{"role":"user","content":"latest RBI repo rate"}],require_current=True)
    assert d.task_type=="research" and d.tier=="strong" and d.needs_web
