from pathlib import Path

from app.v31.coding_spec import compile_coding_spec
from app.v32.impact_engine import build_impact_plan
from app.v33.patch_brain import build_patch_strategy
from app.v34.verification_engine import build_verification_plan
from app.v35.code_runtime import enhance_coding_request
from app.v36.image_director import direct_image_prompt
from app.v37.image_fidelity import build_fidelity_prompt
from app.v38.image_runtime import build_image_generation_plan
from app.v39.creator_critic import review_code_plan, review_image_plan
from app.v40.creator_runtime import build_creator_context, creator_inspect, creator_runtime_health

FILES = [
    {"path": "backend/app/auth.py", "content": "def login(user):\n    return user\n"},
    {"path": "backend/tests/test_auth.py", "content": "def test_login():\n    pass\n"},
    {"path": "requirements.txt", "content": "fastapi\n"},
]


def test_v31_compiles_debug_spec():
    spec = compile_coding_spec(
        "Fix backend/app/auth.py login TypeError without migration",
        existing_files=FILES,
    )
    assert spec.operation == "debug-repair"
    assert "backend/app/auth.py" in spec.target_paths
    assert spec.regression_risk in {"medium", "high"}


def test_v32_impact_resolves_test_and_config():
    spec = compile_coding_spec(
        "Fix backend/app/auth.py login TypeError",
        existing_files=FILES,
    )
    impact = build_impact_plan(spec, FILES)
    assert "backend/app/auth.py" in impact.primary_files
    assert "backend/tests/test_auth.py" in impact.test_files
    assert "requirements.txt" in impact.config_files


def test_v33_patch_is_bounded():
    spec = compile_coding_spec("Fix backend/app/auth.py login TypeError", existing_files=FILES)
    impact = build_impact_plan(spec, FILES)
    patch = build_patch_strategy(spec, impact)
    assert 3 <= patch.max_changed_files <= 16
    assert patch.preserve_public_contracts is True
    assert "evidence" in patch.completion_policy


def test_v34_python_validation_plan():
    spec = compile_coding_spec("Fix backend/app/auth.py", existing_files=FILES)
    verify = build_verification_plan(spec, FILES)
    assert "python -m compileall <changed-python-paths>" in verify.static_checks
    assert any("pytest" in cmd for cmd in verify.targeted_checks)
    assert verify.commands_are_candidates_only is True


def test_v35_enhanced_request_preserves_original():
    enhanced, telemetry = enhance_coding_request("Fix login bug", FILES)
    assert "ORIGINAL USER REQUEST:\nFix login bug" in enhanced
    assert "VASUKI V35 ADVANCED CODING CONTRACT" in enhanced
    assert telemetry["spec"]["operation"] == "debug-repair"


def test_v36_image_direction():
    direction = direct_image_prompt(
        "Create a photorealistic BMW photo, 16:9, low angle, golden hour, 4K"
    )
    assert direction.aspect_hint == "16:9 landscape"
    assert direction.camera == "low-angle perspective"
    assert direction.requested_resolution_signal == "4k-signal"


def test_v37_fidelity_reuses_identity_lock():
    prompt = 'Create a black BMW M5 Competition photo with text "VASUKI"'
    direction = direct_image_prompt(prompt)
    fidelity = build_fidelity_prompt(prompt, direction)
    assert "VEHICLE MODEL LOCK" in fidelity.prompt
    assert "COLOR LOCK" in fidelity.prompt
    assert fidelity.exact_text_lock is True
    assert len(fidelity.prompt) <= 2048


def test_v38_explicit_provider_preserved():
    plan = build_image_generation_plan(
        "Create a realistic product poster",
        provider="huggingface",
    )
    assert plan.routing_policy == "preserve-explicit-provider"
    assert plan.requested_provider == "huggingface"


def test_v38_auto_provider_keeps_existing_fallback():
    plan = build_image_generation_plan(
        "Create a cinematic city image",
        provider="auto",
    )
    assert "omniroute" in plan.routing_policy
    assert "fallback" in plan.routing_policy


def test_v39_code_review_ready():
    _enhanced, telemetry = enhance_coding_request("Fix login bug", FILES)
    review = review_code_plan(telemetry)
    assert review.ready is True
    assert review.score == 100


def test_v39_image_review_ready():
    plan = build_image_generation_plan(
        "Create a cinematic city image"
    ).to_dict()
    review = review_image_plan(plan)
    assert review.ready is True


def test_v40_creator_detects_both_tracks():
    result = creator_inspect(
        "Build a React landing page and generate a premium hero image",
        existing_files=[],
    )
    assert result["mode"] == "code+image"
    assert "coding" in result
    assert "image" in result


def test_v40_context_only_for_creator_tasks():
    assert build_creator_context(
        [{"role": "user", "content": "hello"}]
    ) == ""
    context = build_creator_context(
        [{"role": "user", "content": "fix my FastAPI bug"}]
    )
    assert "CODING:" in context


def test_v40_health_contract():
    health = creator_runtime_health()
    assert health["db_migration_required"] is False
    assert health["new_api_key_required"] is False
    assert health["extra_provider_call_required"] is False
    assert health["arbitrary_server_code_execution"] is False
    assert health["automatic_deploy_without_confirmation"] is False
    assert health["native_image_resolution_guarantee"] is False


def test_main_v11_v40_integration_present():
    backend = Path(__file__).resolve().parents[1]
    source = (backend / "app" / "main_v11.py").read_text(encoding="utf-8")
    assert "VASUKI_V40_ADVANCED_CREATOR_RUNTIME_INTEGRATION" in source
    assert "build_autonomous_project = _v40_build_autonomous_project" in source
    assert "v10.legacy.route_image = _v40_route_image" in source
    assert "v10.legacy._private_context = _v40_private_context" in source
    assert '@app.get("/health/v40")' in source


def test_frontend_v40_label_and_header_cleanup():
    repo = Path(__file__).resolve().parents[2]
    source = (repo / "frontend" / "components" / "ChatApp.tsx").read_text(
        encoding="utf-8"
    )
    assert "Vasuki Core · V40 Advanced Creator Runtime · online" in source
    assert '<div className="pv-header-right">' not in source
    assert "pv-living-mind-badge" not in source
