from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from pathlib import PurePosixPath
from typing import Any

from app.v13.intelligence import analyze_intent, last_user_text

_DEBUG = re.compile(r"\b(?:fix|debug|bug|error|exception|traceback|crash|broken|failed|failing|issue|problem|repair|isko fix|ise fix)\b", re.I)
_TEST = re.compile(r"\b(?:test|tests|pytest|unit test|integration test|e2e|regression|coverage|validate|validation)\b", re.I)
_REFACTOR = re.compile(r"\b(?:refactor|cleanup|clean up|restructure|simplify|architecture|modularize|optimise|optimize)\b", re.I)
_BUILD = re.compile(r"\b(?:build|create|implement|add feature|develop|new endpoint|new page|new component|banao|banana)\b", re.I)
_DEPLOY = re.compile(r"\b(?:deploy|deployment|production|render|vercel|docker|build failed|ci|github actions|environment|env|config)\b", re.I)
_SECURITY = re.compile(r"\b(?:auth|authentication|authorization|permission|security|secret|token|jwt|password|api key|idor|xss|csrf|ssrf)\b", re.I)
_FILE = re.compile(
    r"(?<![\w/.-])([A-Za-z0-9_@./()-]+\.(?:py|pyi|js|jsx|mjs|cjs|ts|tsx|java|kt|kts|go|rs|php|rb|c|cc|cpp|h|hpp|cs|swift|dart|html|htm|css|scss|sql|sh|ps1|json|ya?ml|toml|ini|cfg|gradle|properties|md|txt))(?![\w/.-])",
    re.I,
)
_BACKTICK = re.compile(r"`([^`\n]{2,180})`")
_ERROR = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*(?:Error|Exception))\b")
_SYMBOL = re.compile(
    r"\b(?:function|class|method|component|hook|endpoint|route|symbol|variable|const|def)\s+[`'\"]?([A-Za-z_$][\w$]{2,80})",
    re.I,
)
_ROUTE = re.compile(r"(?<!\w)(/[A-Za-z0-9_./{}:\-]{2,180})")

_CONFIG = {
    "package.json", "requirements.txt", "pyproject.toml", "dockerfile",
    "render.yaml", "vercel.json", "next.config.ts", "next.config.js",
    "vite.config.ts", "vite.config.js", "build.gradle", "build.gradle.kts",
    "settings.gradle", "settings.gradle.kts",
}


def _clean(value: str, limit: int = 1600) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()[:limit]


def _previous_user(messages: list[dict[str, Any]]) -> str:
    seen = 0
    for item in reversed(messages):
        if item.get("role") != "user":
            continue
        seen += 1
        if seen == 2:
            return _clean(item.get("content", ""), 1800)
    return ""


def _tokens(value: str) -> set[str]:
    stop = {"this", "that", "with", "from", "file", "code", "please", "karo", "karna", "isko", "ise", "project", "error", "issue", "problem"}
    return {
        token
        for token in re.findall(r"[A-Za-z0-9_.$@/\-]{3,}", str(value or "").casefold())
        if token not in stop
    }


def _unique(values: list[str], limit: int) -> tuple[str, ...]:
    out: list[str] = []
    seen: set[str] = set()
    for raw in values:
        value = _clean(raw, 220)
        key = value.casefold()
        if value and key not in seen:
            seen.add(key)
            out.append(value)
        if len(out) >= limit:
            break
    return tuple(out)


def _file_hints(text: str) -> tuple[str, ...]:
    values = [m.group(1) for m in _FILE.finditer(text)]
    for m in _BACKTICK.finditer(text):
        value = m.group(1).strip()
        if "/" in value or "." in PurePosixPath(value).name:
            values.append(value)
    return _unique(values, 12)


def _symbol_hints(text: str) -> tuple[str, ...]:
    values = [m.group(1) for m in _SYMBOL.finditer(text)]
    values += [m.group(1) for m in _ERROR.finditer(text)]
    values += [m.group(1) for m in _ROUTE.finditer(text)]
    for m in _BACKTICK.finditer(text):
        value = m.group(1).strip()
        if re.fullmatch(r"[A-Za-z_$][\w$]{2,80}", value):
            values.append(value)
    return _unique(values, 16)


@dataclass(frozen=True, slots=True)
class ProjectCodingDecision:
    version: str
    action: str
    confidence: float
    active_project: bool
    project_id: str
    coding_intent: bool
    is_followup: bool
    needs_project_files: bool
    needs_dependency_impact_check: bool
    needs_test_plan: bool
    needs_security_check: bool
    explicit_files: tuple[str, ...]
    symbol_hints: tuple[str, ...]
    error_signatures: tuple[str, ...]
    reference_text: str
    reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        for key in ("explicit_files", "symbol_hints", "error_signatures", "reasons"):
            data[key] = list(data[key])
        return data


def decide_project_coding(messages: list[dict[str, Any]], *, project_id: str = "") -> ProjectCodingDecision:
    rows = [
        {"role": str(x.get("role") or ""), "content": str(x.get("content") or "")}
        for x in messages
        if str(x.get("content") or "").strip()
    ]
    current = _clean(last_user_text(rows), 10000)
    previous = _previous_user(rows)
    plan = analyze_intent(rows, require_current=False)
    text = f"{previous}\nCURRENT FOLLOW-UP: {current}" if plan.is_followup and previous else current

    debug = bool(_DEBUG.search(text))
    tests = bool(_TEST.search(text))
    refactor = bool(_REFACTOR.search(text))
    build = bool(_BUILD.search(text))
    deploy = bool(_DEPLOY.search(text))
    security = bool(_SECURITY.search(text))
    files = _file_hints(text)
    symbols = _symbol_hints(text)
    errors = _unique([m.group(1) for m in _ERROR.finditer(text)], 8)

    coding = bool(plan.task_type == "code" or debug or tests or refactor or build or files or symbols)
    if debug:
        action = "debug-repair"
    elif tests:
        action = "test-regression"
    elif refactor:
        action = "refactor"
    elif build:
        action = "implement"
    elif coding:
        action = "inspect-modify"
    else:
        action = "not-coding"

    active = bool(str(project_id or "").strip())
    needs_files = active and coding
    dependency = needs_files and action in {"debug-repair", "refactor", "implement", "inspect-modify"}
    test_plan = coding and action in {"debug-repair", "test-regression", "refactor", "implement", "inspect-modify"}

    reasons: list[str] = []
    if active:
        reasons.append("active project available")
    if plan.is_followup:
        reasons.append("follow-up inherits previous coding request")
    if debug:
        reasons.append("debug/repair intent detected")
    if files:
        reasons.append("explicit file reference detected")
    if symbols:
        reasons.append("symbol/route/error hint detected")
    if deploy:
        reasons.append("deployment/config impact may matter")
    if security:
        reasons.append("security-sensitive code path may matter")
    if needs_files:
        reasons.append("inspect relevant Project KB files")

    confidence = float(plan.confidence) + (0.06 if coding else 0) + (0.08 if files else 0) + (0.05 if symbols or errors else 0)
    if plan.is_followup and previous:
        confidence += 0.03

    return ProjectCodingDecision(
        version="v19.2",
        action=action,
        confidence=round(max(0.25, min(0.99, confidence)), 3),
        active_project=active,
        project_id=str(project_id or "").strip(),
        coding_intent=coding,
        is_followup=bool(plan.is_followup),
        needs_project_files=needs_files,
        needs_dependency_impact_check=dependency,
        needs_test_plan=test_plan,
        needs_security_check=security,
        explicit_files=files,
        symbol_hints=symbols,
        error_signatures=errors,
        reference_text=previous if plan.is_followup else "",
        reasons=tuple(reasons or ["no project coding action required"]),
    )


def rank_project_files(query: str, rows: list[dict[str, Any]], *, decision: ProjectCodingDecision | None = None, limit: int = 5) -> list[str]:
    limit = max(1, min(int(limit), 8))
    q = _tokens(query)
    explicit = {x.replace("\\", "/").casefold() for x in (decision.explicit_files if decision else ())}
    wanted_symbols = {x.casefold() for x in (decision.symbol_hints if decision else ())}
    scored: list[tuple[float, str]] = []

    for row in rows:
        path = str(row.get("path") or "").replace("\\", "/").strip()
        if not path:
            continue
        low = path.casefold()
        name = PurePosixPath(low).name
        metadata = row.get("metadata")
        signals = metadata.get("signals", {}) if isinstance(metadata, dict) else {}
        if not isinstance(signals, dict):
            signals = {}
        symbols = {str(x).casefold() for x in (signals.get("symbols") or [])}
        imports = {str(x).casefold() for x in (signals.get("imports") or [])}
        routes = {str(x).casefold() for x in (signals.get("routes") or [])}
        score = 0.0

        for hint in explicit:
            if hint == low or hint == name:
                score += 5.0
            elif hint in low or name in hint:
                score += 3.0

        score += len(q & _tokens(low)) * 0.85
        for token in q:
            if token in low:
                score += 0.65
            if token in symbols:
                score += 1.35
            if token in imports:
                score += 0.55
            if token in routes:
                score += 1.10

        for symbol in wanted_symbols:
            if symbol in symbols:
                score += 2.2
            if symbol in routes:
                score += 1.8

        if decision and _DEPLOY.search(query) and name in _CONFIG:
            score += 1.4
        if decision and decision.needs_security_check and any(x in low for x in ("auth", "security", "permission", "middleware")):
            score += 1.35

        if score > 0:
            scored.append((score, path))

    scored.sort(key=lambda item: (-item[0], item[1].casefold()))
    selected = [path for _, path in scored[:limit]]

    if not selected:
        for row in rows:
            path = str(row.get("path") or "").strip()
            if not path:
                continue
            name = PurePosixPath(path.casefold()).name
            if name in _CONFIG or name.startswith(("main.", "app.")):
                selected.append(path)
            if len(selected) >= min(3, limit):
                break
    return selected[:limit]


def build_project_coding_context(decision: ProjectCodingDecision, files: list[dict[str, Any]]) -> str:
    if not decision.needs_project_files:
        return ""

    lines = [
        "VASUKI V19 PHASE 2 PROJECT CODING CONTEXT:",
        f"Action={decision.action}; confidence={decision.confidence:.3f}; project_id={decision.project_id}.",
        "Use the active project and selected repository files as primary coding evidence.",
        "Before rename/removal/signature changes, check definitions -> imports -> callers -> routes -> tests.",
        "Prefer minimal targeted changes. Do not rewrite unrelated files or claim tests ran without evidence.",
    ]
    if decision.reference_text:
        lines.append("Inherited request: " + _clean(decision.reference_text, 700))
    if decision.explicit_files:
        lines.append("File hints: " + " | ".join(decision.explicit_files))
    if decision.symbol_hints:
        lines.append("Symbol/route hints: " + " | ".join(decision.symbol_hints))
    if decision.error_signatures:
        lines.append("Errors: " + " | ".join(decision.error_signatures))
    if decision.needs_test_plan:
        lines.append("Include the smallest useful regression-test plan for recommended changes.")
    if decision.needs_security_check:
        lines.append("Preserve authorization boundaries and never expose secrets or credentials.")

    used = 0
    for index, row in enumerate(files, 1):
        path = str(row.get("path") or "").strip()
        content = str(row.get("content_text") or "").strip()
        metadata = row.get("metadata")
        signals = metadata.get("signals", {}) if isinstance(metadata, dict) else {}
        if not isinstance(signals, dict):
            signals = {}
        budget = min(4200, max(0, 16000 - used))
        if budget <= 0:
            break
        excerpt = content[:budget]
        used += len(excerpt)
        lines.extend([
            f"[PROJECT FILE {index}] {path}",
            "Symbols: " + ", ".join(str(x) for x in (signals.get("symbols") or [])[:18]),
            "Imports: " + ", ".join(str(x) for x in (signals.get("imports") or [])[:14]),
            "Routes: " + ", ".join(str(x) for x in (signals.get("routes") or [])[:10]),
            "CONTENT:",
            excerpt,
        ])

    lines.append("If evidence is insufficient, name the exact file or symbol that still needs inspection instead of guessing.")
    return "\n".join(lines)[:22000]


def project_coding_health() -> dict[str, Any]:
    return {
        "version": "v19.2",
        "name": "Vasuki Project Context + Coding Intent Brain",
        "features": [
            "coding-action-classification",
            "short-followup-project-resolution",
            "explicit-file-and-symbol-hints",
            "project-kb-relevant-file-ranking",
            "targeted-code-context-retrieval",
            "dependency-impact-check-policy",
            "regression-test-plan-policy",
            "security-sensitive-code-policy",
            "minimal-change-interface-preservation",
        ],
        "uses_existing_project_kb": True,
        "new_db_migration_required": False,
        "new_api_key_required": False,
        "extra_provider_call_required": False,
        "arbitrary_server_code_execution": False,
        "hidden_chain_of_thought_exposed": False,
    }
