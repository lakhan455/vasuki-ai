from __future__ import annotations

import base64
from io import BytesIO

from PIL import Image

from app.main_v9_phase3 import app
from app.services.document_intelligence_v9 import (
    deterministic_compare,
    extract_text_document,
    flatten_blocks,
    select_evidence,
)
from app.services.image_studio_v9 import (
    ASPECT_RATIOS,
    fit_data_url_to_ratio,
    normalize_aspect_ratio,
    normalize_preset,
    studio_prompt,
    upscale_image_bytes,
)


def _png(width: int = 80, height: int = 50) -> bytes:
    image = Image.new("RGB", (width, height), "white")
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def test_phase3_normalizes_presets_and_ratios():
    assert normalize_preset("photorealistic") == "photo"
    assert normalize_preset("unknown") == "none"
    assert normalize_aspect_ratio("16:9") == "landscape"
    assert normalize_aspect_ratio("unknown") == "square"


def test_phase3_studio_prompt_contains_controls():
    value = studio_prompt(
        "A premium NFC card",
        preset="product",
        aspect_ratio="4:5",
        variation_index=2,
    )
    assert "A premium NFC card" in value
    assert "portrait" in value
    assert "variation 2" in value


def test_phase3_fit_data_url_applies_exact_ratio():
    raw = _png(100, 60)
    data_url = "data:image/png;base64," + base64.b64encode(raw).decode("ascii")
    output, meta = fit_data_url_to_ratio(data_url, "landscape")
    assert output.startswith("data:image/png;base64,")
    assert (meta["width"], meta["height"]) == ASPECT_RATIOS["landscape"]
    decoded = base64.b64decode(output.split(",", 1)[1])
    with Image.open(BytesIO(decoded)) as image:
        assert image.size == ASPECT_RATIOS["landscape"]


def test_phase3_local_upscale_is_bounded():
    output, meta = upscale_image_bytes(_png(200, 100), scale=4)
    assert output
    assert meta["width"] == 800
    assert meta["height"] == 400
    assert meta["generative_super_resolution"] is False


def test_phase3_text_extraction_has_line_citations():
    document = extract_text_document(
        b"alpha beta gamma\nsecond line\nthird line",
        filename="notes.txt",
        source_id="D1",
    )
    assert document["blocks"]
    assert document["blocks"][0]["citation_id"].startswith("D1:L")


def test_phase3_evidence_selection_prefers_matching_block():
    document = extract_text_document(
        b"apples are red\n\nquantum computing uses qubits",
        filename="notes.txt",
        source_id="D1",
    )
    selected = select_evidence("What uses qubits?", flatten_blocks([document]), limit=1)
    assert "qubits" in selected[0]["text"]


def test_phase3_deterministic_compare():
    left = extract_text_document(b"same\nold value", filename="a.txt", source_id="D1")
    right = extract_text_document(b"same\nnew value", filename="b.txt", source_id="D2")
    result = deterministic_compare([left, right])
    assert result["left"] == "a.txt"
    assert result["right"] == "b.txt"
    assert 0 <= result["similarity_percent"] <= 100


def test_phase3_routes_registered():
    paths = {path for route in app.routes if (path := getattr(route, "path", None))}
    expected = {
        "/api/image/v3/options",
        "/api/image/v3/generate",
        "/api/image/v3/variations",
        "/api/image/v3/edit",
        "/api/image/v3/enhance",
        "/api/documents/v3/extract",
        "/api/documents/v3/ocr",
        "/api/documents/v3/ask",
        "/api/documents/v3/compare",
        "/health/v9-phase3",
    }
    assert expected.issubset(paths)
