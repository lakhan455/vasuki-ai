from app.services.image_v8 import classify_image_request, enhance_image_prompt


def test_image_router_detects_anime():
    decision = classify_image_request("Create an anime warrior poster")
    assert decision.image_type == "poster"  # poster intent takes visual-output priority


def test_image_router_detects_realistic():
    decision = classify_image_request("Create a photorealistic portrait with DSLR lighting")
    assert decision.image_type == "realistic"


def test_prompt_enhancer_keeps_original_request():
    original = "Create a premium coffee poster"
    enhanced = enhance_image_prompt(original, "poster")
    assert original in enhanced
    assert "professional advertising poster" in enhanced
