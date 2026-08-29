from app.services.research import is_all_india_state_cm_query, needs_live_web


def test_exact_user_query_routes_to_all_india_cm_research():
    query = "haa muje ind ke saare cm ki list do 2026 ki"
    assert is_all_india_state_cm_query(query) is True
    assert needs_live_web(query) is True


def test_common_roman_hindi_variants_route_to_all_india_cm_research():
    samples = [
        "india ke sabhi cm batao",
        "bharat ke saare cm ki list do",
        "ind ke all cm 2026",
        "India CM list 2026",
        "sabhi rajya ke cm batao",
    ]
    for query in samples:
        assert is_all_india_state_cm_query(query), query


def test_single_state_cm_query_is_not_misclassified_as_all_india():
    assert is_all_india_state_cm_query("rajasthan ka cm kon hai 2026") is False
    assert needs_live_web("rajasthan ka cm kon hai 2026") is True
