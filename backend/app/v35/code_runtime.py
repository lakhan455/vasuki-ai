from __future__ import annotations

from typing import Any

from app.v31.coding_spec import compile_coding_spec
from app.v32.impact_engine import build_impact_plan
from app.v33.patch_brain import build_patch_strategy
from app.v34.verification_engine import build_verification_plan


def build_advanced_code_context(
    prompt: str,
    existing_files: list[dict[str, str]] | None = None,
) -> tuple[str, dict[str, Any]]:
    spec = compile_coding_spec(prompt, existing_files=existing_files)
    impact = build_impact_plan(spec, existing_files)
    patch = build_patch_strategy(spec, impact)
    verify = build_verification_plan(spec, existing_files)

    lines = [
        "VASUKI V35 ADVANCED CODING CONTRACT:",
        f"Operation: {spec.operation}; regression risk: {spec.regression_risk}.",
        "Acceptance criteria: " + " | ".join(spec.acceptance_criteria),
        f"Patch mode: {patch.mode}; max intended changed files: {patch.max_changed_files}.",
        "Preserve public contracts: " + str(patch.preserve_public_contracts).lower() + ".",
        "Security review required: " + str(patch.require_security_review).lower() + ".",
        "Validation candidates: " + " | ".join((*verify.static_checks, *verify.targeted_checks)),
        (
            "Rules: inspect before editing; do not invent missing repository facts; "
            "do not add real secrets; do not claim tests/build/deploy ran without evidence; "
            "keep changes complete, runnable, and minimal."
        ),
    ]
    if spec.target_paths:
        lines.append("Explicit target hints: " + " | ".join(spec.target_paths))
    if impact.dependency_order:
        lines.append("Impact/edit order hints: " + " -> ".join(impact.dependency_order))
    if spec.constraints:
        lines.append("User constraints: " + " | ".join(spec.constraints))

    telemetry = {
        "spec": spec.to_dict(),
        "impact": impact.to_dict(),
        "patch": patch.to_dict(),
        "verification": verify.to_dict(),
    }
    return "\n".join(lines)[:10000], telemetry


def enhance_coding_request(
    prompt: str,
    existing_files: list[dict[str, str]] | None = None,
) -> tuple[str, dict[str, Any]]:
    context, telemetry = build_advanced_code_context(prompt, existing_files)
    enhanced = (
        f"ORIGINAL USER REQUEST:\n{str(prompt or '').strip()}\n\n"
        f"{context}\n\n"
        "Execute the original request while treating the V35 contract as implementation guidance, "
        "not as permission to broaden scope."
    )
    return enhanced[:30000], telemetry


def code_runtime_health() -> dict[str, Any]:
    return {
        "version": "v35",
        "name": "Advanced Coding Runtime",
        "features": [
            "spec-compiler-integration",
            "impact-aware-builder-guidance",
            "minimal-patch-guidance",
            "verification-plan-integration",
            "v16-v17-builder-transparent-upgrade",
        ],
        "extra_provider_call_required": False,
        "arbitrary_server_code_execution": False,
        "new_api_key_required": False,
    }
