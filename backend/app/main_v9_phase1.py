from __future__ import annotations
from typing import Any
from fastapi import Depends
from pydantic import BaseModel, Field
import app.main as legacy
import app.main_v8_phase5 as phase5
from app.auth import AuthUser, get_current_user
from app.services import personal_memory as personal_memory_service
from app.services.feature_flags_v9 import flags_for_user
from app.services.memory_policy_v9 import create_user_memory_v9, policy_summary
from app.services.quality_v9 import operational_eval_score, quality_snapshot
from app.services.research_v9 import build_research_bundle, verify_citations

app = phase5.app
settings = phase5.settings
_original_web_context = legacy._web_context

async def _web_context_v9(*, query: str, current_date: str, request):
    if not bool(getattr(request, "research_mode", False)):
        return await _original_web_context(query=query, current_date=current_date, request=request)
    bundle = await build_research_bundle(query, settings, as_of=current_date, max_sources=14)
    return True, bundle.sources, bundle.context

legacy._web_context = _web_context_v9
legacy.create_user_memory = create_user_memory_v9
personal_memory_service.create_user_memory = create_user_memory_v9

class CitationVerifyRequest(BaseModel):
    answer: str = Field(..., min_length=1, max_length=50000)
    sources: list[dict[str, Any]] = Field(default_factory=list, max_length=30)

@app.get("/api/features/v9")
async def feature_flags(current_user: AuthUser = Depends(get_current_user)):
    return {"flags": flags_for_user(current_user.id)}

@app.get("/api/quality/providers/v9")
async def provider_quality(current_user: AuthUser = Depends(get_current_user)):
    return {"ok": True, "quality": quality_snapshot(), "user_id_suffix": current_user.id[-6:]}

@app.get("/api/evals/v9/score")
async def eval_score(current_user: AuthUser = Depends(get_current_user)):
    return {"ok": True, "score": operational_eval_score(), "user_id_suffix": current_user.id[-6:]}

@app.post("/api/research/v2/verify")
async def citation_verify(payload: CitationVerifyRequest, _current_user: AuthUser = Depends(get_current_user)):
    return {"ok": True, **verify_citations(payload.answer, payload.sources)}

@app.get("/api/memory/policy/v9")
async def memory_policy(_current_user: AuthUser = Depends(get_current_user)):
    return {"ok": True, **policy_summary()}

@app.get("/health/v9-phase1")
async def health_v9_phase1():
    return {
        "ok": True,
        "version": "v9-phase1",
        "quality_benchmark_suite": True,
        "automatic_provider_quality_scoring": True,
        "research_mode_v2": True,
        "citation_verification_foundation": True,
        "memory_conflict_resolver": True,
        "memory_categories_and_lifetimes": True,
        "feature_flags": True,
        "feedback_quality_learning": True,
        "release_health_checks": True,
        "ci_cd_tests": True,
        "vasuki_eval_score_foundation": True,
        "supabase_migration_required_for_memory_supersede": True,
    }
