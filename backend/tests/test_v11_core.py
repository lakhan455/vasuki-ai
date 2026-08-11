from app.v11.coding import build_knowledge_graph, sandbox_policy, syntax_check
from app.v11.media import consistency_prompt
from app.v11.memory import conflict_score, normalize_key, resolve_conflicts
from app.v11.operations import canary_bucket, release_for_user
from app.v11.quality import citation_fact_check, judge_answer, load_eval_cases

def test_eval_dataset_has_400_cases():
    rows=load_eval_cases()
    assert len(rows)==400
    assert {row["category"] for row in rows}=={"chat","coding","reasoning","research","rag","vision","image","memory"}

def test_judge_scores_good_answer():
    result=judge_answer("What is 2+2?","The answer is 4.",expected="4",required_terms=["4"])
    assert result["overall"]>60
    assert result["hallucination_risk"]<40

def test_judge_penalizes_empty():
    result=judge_answer("Explain Python.","",expected="Python")
    assert result["overall"]<40
    assert result["hallucination_risk"]==100

def test_citation_checker_supports_matching_claim():
    result=citation_fact_check(
        "Vasuki uses six native provider families for fallback.",
        [{"title":"spec","snippet":"Vasuki native fallback uses six provider families for chat routing."}],
    )
    assert result["claim_count"]==1
    assert result["coverage"]>=60

def test_memory_key_normalization():
    assert normalize_key(" Favorite   Color! ")=="favorite color"

def test_memory_conflict_score():
    assert conflict_score("status is active","status is not active")>0.5

def test_memory_resolver_prefers_newest_active():
    rows=[
        {"key_norm":"city","value":"old","status":"active","updated_at":"2026-01-01"},
        {"key_norm":"city","value":"new","status":"active","updated_at":"2026-08-01"},
    ]
    assert resolve_conflicts(rows)[0]["value"]=="new"

def test_python_syntax_check():
    assert syntax_check("x.py","def x():\n    return 1\n")["ok"]
    assert not syntax_check("x.py","def x(:\n pass")["ok"]

def test_graph_detects_python_symbols():
    graph=build_knowledge_graph({"app.py":"from x import y\n\ndef hello():\n    return 1\n"})
    assert any(n["name"]=="hello" for n in graph.nodes)

def test_sandbox_never_executes_server_side():
    assert sandbox_policy()["server_execution"] is False

def test_consistency_prompt_contains_controls():
    value=consistency_prompt("portrait",identity="same face",pose="side profile")
    assert "same face" in value and "side profile" in value

def test_canary_bucket_stable():
    assert canary_bucket("abc")==canary_bucket("abc")
    assert 0<=canary_bucket("abc")<100

def test_owner_always_canary():
    assert release_for_user("x",owner=True)=="v11"
