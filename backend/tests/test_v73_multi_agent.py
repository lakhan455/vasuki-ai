from __future__ import annotations

import asyncio
from pathlib import Path

from app.v73 import multi_agent


class Settings:
    v73_max_agents = 3
    v73_max_parallel_agents = 3
    v73_agent_timeout_seconds = 8.0


def test_v73_health_is_truthful_and_bounded():
    health = multi_agent.health_snapshot(Settings())
    assert health["version"] == "v73"
    assert health["cost_controls"]["max_specialist_agents"] == 3
    assert health["cost_controls"]["max_parallel_agents"] == 3
    assert health["safety"]["external_writes"] is False
    assert health["persistence"]["survives_restart"] is False
    assert health["new_database_migration_required"] is False


def test_v73_multi_agent_job_runs_real_parallel_model_calls(monkeypatch):
    calls: list[str] = []

    async def fake_chat(provider, messages, settings, web_context="", **kwargs):
        user = str(messages[-1].get("content") or "")
        if "synthesizer for Vasuki Multi-Agent Brain" in user:
            calls.append("synthesizer")
            return "Final combined answer with constraints preserved.", "fake-synth"
        if "Repair this multi-agent answer." in user:
            calls.append("repair")
            return "Repaired final answer with constraints preserved.", "fake-repair"
        calls.append("specialist")
        return "Specialist finding with concrete recommendation and risk.", "fake-agent"

    monkeypatch.setattr(multi_agent, "route_chat_v10", fake_chat)

    async def scenario():
        started = await multi_agent.create_multi_agent_job(
            Settings(),
            user_id="user-1",
            goal="Design a practical launch plan for a small product and identify risks.",
        )
        for _ in range(100):
            state = await multi_agent.get_multi_agent_job(
                user_id="user-1", job_id=started["job_id"],
            )
            assert state is not None
            if state["status"] in multi_agent.TERMINAL_STATES:
                return state
            await asyncio.sleep(0.01)
        raise AssertionError("V73 test job did not finish.")

    state = asyncio.run(scenario())
    assert state["status"] == "succeeded"
    result = state["result"]
    assert result["execution_proof"]["specialist_agents_requested"] == 3
    assert result["execution_proof"]["specialist_agents_completed"] == 3
    assert result["execution_proof"]["external_writes"] == 0
    assert len(calls) >= 4


def test_v73_research_mode_uses_live_research(monkeypatch):
    class FakePlan:
        def to_dict(self):
            return {"mode": "research", "steps": [], "orchestration": {}}

    monkeypatch.setattr(
        multi_agent, "build_execution_plan", lambda *args, **kwargs: FakePlan(),
    )

    async def fake_chat(provider, messages, settings, web_context="", **kwargs):
        return "Evidence-grounded synthesis.", "fake-provider"

    async def fake_research(query, settings):
        return {
            "answer": "Verified research evidence.",
            "sources": [{"title": "Source", "url": "https://example.com"}],
        }

    monkeypatch.setattr(multi_agent, "route_chat_v10", fake_chat)
    monkeypatch.setattr(multi_agent, "run_research", fake_research)

    async def scenario():
        started = await multi_agent.create_multi_agent_job(
            Settings(), user_id="user-research",
            goal="Research current market conditions.",
        )
        for _ in range(100):
            state = await multi_agent.get_multi_agent_job(
                user_id="user-research", job_id=started["job_id"],
            )
            if state and state["status"] in multi_agent.TERMINAL_STATES:
                return state
            await asyncio.sleep(0.01)
        raise AssertionError("Research job did not finish.")

    state = asyncio.run(scenario())
    assert state["status"] == "succeeded"
    proof = state["result"]["execution_proof"]
    assert proof["live_research_used"] is True
    assert proof["live_research_source_count"] == 1


def test_v73_production_wiring_present():
    repo = Path(__file__).resolve().parents[2]
    main = (repo / "backend/app/main_v11.py").read_text(encoding="utf-8")
    config = (repo / "backend/app/config.py").read_text(encoding="utf-8")
    api = (repo / "frontend/lib/api.ts").read_text(encoding="utf-8")
    chat = (repo / "frontend/components/ChatApp.tsx").read_text(encoding="utf-8")

    assert '"/health/v73"' in main
    assert '"/api/v73/agents/jobs"' in main
    assert "v73_max_parallel_agents" in config
    assert "startMultiAgentV73" in api
    assert "startMultiAgentV73" in chat
    assert 'mode: "agents"' in chat
    assert "cancelMultiAgentV73" in chat
