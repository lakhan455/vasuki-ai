from __future__ import annotations

import re
import shutil
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parent
FILES = {
    "config": ROOT / "backend" / "app" / "config.py",
    "chat": ROOT / "backend" / "app" / "services" / "chat.py",
    "main": ROOT / "backend" / "app" / "main.py",
    "api": ROOT / "frontend" / "lib" / "api.ts",
}


def backup(path: Path) -> None:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_path = path.with_name(f"{path.name}.bak-speed-fix-{stamp}")
    shutil.copy2(path, backup_path)
    print(f"Backup: {backup_path}")


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if new in text:
        print(f"Already applied: {label}")
        return text
    if old not in text:
        raise RuntimeError(f"Patch point not found: {label}")
    print(f"Applied: {label}")
    return text.replace(old, new, 1)


def patch_config(path: Path) -> None:
    text = path.read_text(encoding="utf-8-sig")

    text = replace_once(
        text,
        '    groq_model: str = "openai/gpt-oss-120b"\n',
        '    groq_model: str = "openai/gpt-oss-120b"\n'
        '    # Fast model for normal questions; the large model remains for complex work.\n'
        '    groq_fast_model: str = "llama-3.1-8b-instant"\n',
        "Groq fast model",
    )

    text = replace_once(
        text,
        '    chat_timeout_seconds: int = 25\n',
        '    chat_timeout_seconds: int = 25\n'
        '    fast_provider_timeout_seconds: int = 9\n'
        '    provider_timeout_seconds: int = 18\n'
        '    provider_cooldown_seconds: int = 120\n',
        "Provider timeout and cooldown settings",
    )

    text = replace_once(
        text,
        '    max_output_tokens: int = 5000\n',
        '    max_output_tokens: int = 5000\n'
        '    max_fast_output_tokens: int = 1600\n',
        "Fast response token limit",
    )

    path.write_text(text, encoding="utf-8")


def patch_chat(path: Path) -> None:
    text = path.read_text(encoding="utf-8-sig")

    text = replace_once(
        text,
        'from __future__ import annotations\n\n'
        'from datetime import datetime, timezone\n',
        'from __future__ import annotations\n\n'
        'import asyncio\n'
        'import re\n'
        'import time\n'
        'from datetime import datetime, timezone\n',
        "Async speed imports",
    )

    text = replace_once(
        text,
        '    temperature: float = 0.0,\n'
        '    token_field: str = "max_tokens",\n'
        ') -> str:\n',
        '    temperature: float = 0.0,\n'
        '    token_field: str = "max_tokens",\n'
        '    max_output_tokens: int | None = None,\n'
        ') -> str:\n',
        "Optional provider output limit",
    )

    text = replace_once(
        text,
        '    conversation = [dict(item) for item in messages]\n'
        '    complete = ""\n\n'
        '    for continuation_index in range(settings.max_continuations + 1):\n',
        '    conversation = [dict(item) for item in messages]\n'
        '    complete = ""\n'
        '    output_limit = max_output_tokens or settings.max_output_tokens\n\n'
        '    for continuation_index in range(settings.max_continuations + 1):\n',
        "Calculate output limit once",
    )

    text = replace_once(
        text,
        '            token_field: settings.max_output_tokens,\n',
        '            token_field: output_limit,\n',
        "Use selected output limit",
    )

    helpers = r'''
_PROVIDER_COOLDOWN_UNTIL: dict[str, float] = {}

_LARGE_REQUEST_HINTS = (
    "complete code",
    "full code",
    "production-ready",
    "research paper",
    "detailed report",
    "step by step",
    "all countries",
    "all states",
    "all chief ministers",
    "all presidents",
    "long answer",
    "bada jawab",
    "bade jawab",
    "poori list",
    "puri list",
    "saare",
    "sabhi",
)


def _is_large_request(messages: list[dict]) -> bool:
    query = next(
        (
            str(item.get("content") or "")
            for item in reversed(messages)
            if item.get("role") == "user"
        ),
        "",
    )
    normalized = query.casefold()

    if len(query) > 1400 or len(query.split()) > 220:
        return True

    if any(hint in normalized for hint in _LARGE_REQUEST_HINTS):
        return True

    has_large_count = bool(re.search(r"\b(?:[5-9]\d|[1-9]\d{2,})\b", normalized))
    asks_for_list = any(
        term in normalized
        for term in ("list", "names", "naam", "countries", "states", "items")
    )
    return has_large_count and asks_for_list


def _provider_is_available(name: str) -> bool:
    return time.monotonic() >= _PROVIDER_COOLDOWN_UNTIL.get(name, 0.0)


def _clear_provider_failure(name: str) -> None:
    _PROVIDER_COOLDOWN_UNTIL.pop(name, None)


def _mark_provider_failure(name: str, error: Exception, settings: Settings) -> None:
    message = str(error).casefold()
    cooldown = 20

    if isinstance(error, asyncio.TimeoutError) or "timed out" in message:
        cooldown = 45
    elif any(
        marker in message
        for marker in (
            "401",
            "402",
            "403",
            "429",
            "quota",
            "rate limit",
            "payment required",
            "not configured",
        )
    ):
        cooldown = int(settings.provider_cooldown_seconds)

    _PROVIDER_COOLDOWN_UNTIL[name] = time.monotonic() + max(5, cooldown)


'''

    marker = "\nasync def chat_groq(\n"
    if helpers.strip() not in text:
        if marker not in text:
            raise RuntimeError("Patch point not found: chat helper insertion")
        text = text.replace(marker, "\n" + helpers + "async def chat_groq(\n", 1)
        print("Applied: smart routing helpers")
    else:
        print("Already applied: smart routing helpers")

    fast_fn = r'''

async def chat_groq_fast(
    messages: list[dict],
    settings: Settings,
    web_context: str = "",
    *,
    require_current: bool = False,
    as_of: str | None = None,
    temperature: float = 0.0,
) -> str:
    if not settings.groq_api_key:
        raise RuntimeError("GROQ_API_KEY is not configured")

    return await _openai_compatible(
        "https://api.groq.com/openai/v1/chat/completions",
        settings.groq_api_key,
        settings.groq_fast_model,
        _openai_messages(
            messages,
            web_context,
            require_current=require_current,
            as_of=as_of,
        ),
        settings,
        temperature=temperature,
        token_field="max_completion_tokens",
        max_output_tokens=min(
            settings.max_fast_output_tokens,
            settings.max_output_tokens,
        ),
    )

'''

    if "async def chat_groq_fast(" not in text:
        marker = "\nasync def chat_sambanova(\n"
        if marker not in text:
            raise RuntimeError("Patch point not found: fast Groq function")
        text = text.replace(marker, fast_fn + "async def chat_sambanova(\n", 1)
        print("Applied: fast Groq provider")
    else:
        print("Already applied: fast Groq provider")

    text = replace_once(
        text,
        'PROVIDERS = {\n    "groq": chat_groq,\n',
        'PROVIDERS = {\n    "groq_fast": chat_groq_fast,\n    "groq": chat_groq,\n',
        "Register fast provider",
    )

    old_order = (
        '        for name in ("gemini", "groq", "cerebras", "sambanova", '
        '"openrouter", "mistral")\n'
    )
    new_order = (
        '        for name in ("gemini", "groq", "sambanova", "openrouter", '
        '"mistral", "cerebras")\n'
    )
    if old_order in text:
        text = text.replace(old_order, new_order, 1)
        print("Applied: safer verification fallback order")

    new_route = r'''async def route_chat(
    provider: str,
    messages: list[dict],
    settings: Settings,
    web_context: str = "",
    *,
    require_current: bool = False,
    as_of: str | None = None,
) -> tuple[str, str]:
    if provider != "auto":
        order = [provider]
    elif _is_large_request(messages):
        order = [
            "groq",
            "sambanova",
            "gemini",
            "openrouter",
            "mistral",
            "cerebras",
            "groq_fast",
        ]
    else:
        order = [
            "groq_fast",
            "groq",
            "gemini",
            "sambanova",
            "openrouter",
            "mistral",
            "cerebras",
        ]

    errors: list[str] = []
    draft = ""
    draft_provider = ""

    for name in order:
        if not _provider_is_available(name):
            errors.append(f"{name}: temporarily skipped after a recent failure")
            continue

        timeout_seconds = (
            float(settings.fast_provider_timeout_seconds)
            if name == "groq_fast"
            else float(settings.provider_timeout_seconds)
        )

        try:
            candidate = await asyncio.wait_for(
                _call_provider(
                    name,
                    messages,
                    settings,
                    web_context,
                    require_current=require_current,
                    as_of=as_of,
                    temperature=0.0 if require_current else 0.2,
                ),
                timeout=timeout_seconds,
            )

            if not candidate.strip():
                raise RuntimeError("Provider returned an empty answer")

            draft = candidate.strip()
            draft_provider = name
            _clear_provider_failure(name)
            break
        except Exception as exc:
            _mark_provider_failure(name, exc, settings)
            errors.append(f"{name}: {exc}")

    if not draft:
        raise RuntimeError("All chat providers failed. " + " | ".join(errors))

    if (
        require_current
        and is_all_india_state_cm_query(_last_user_query(messages))
    ):
        if not web_context.strip():
            raise RuntimeError(
                "Current facts require evidence, but the evidence pack is empty"
            )

        try:
            verified, verification_provider = await _verify_current_answer(
                draft,
                draft_provider,
                messages,
                settings,
                web_context,
                as_of or datetime.now(timezone.utc).date().isoformat(),
            )
            return verified, verification_provider
        except Exception:
            return draft, f"{draft_provider}+verification-fallback"

    return draft, draft_provider
'''

    route_pattern = re.compile(r"async def route_chat\([\s\S]*\Z")
    if "temporarily skipped after a recent failure" not in text:
        if not route_pattern.search(text):
            raise RuntimeError("Patch point not found: route_chat")
        text = route_pattern.sub(new_route, text, count=1)
        print("Applied: fast reliable route_chat")
    else:
        print("Already applied: fast reliable route_chat")

    path.write_text(text, encoding="utf-8")


def patch_main(path: Path) -> None:
    text = path.read_text(encoding="utf-8-sig")

    text = replace_once(
        text,
        '            timeout=3.5,\n',
        '            timeout=1.2,\n',
        "Faster shared-memory lookup timeout",
    )

    old = (
        '    auto_research = len(query) <= 500 and should_auto_research(query)\n'
        '    should_search = request.use_web or require_current or auto_research\n'
    )
    new = (
        '    # Static questions should not wait for web search. Live/current questions\n'
        '    # and the explicit Web toggle still use verified online research.\n'
        '    auto_research = False\n'
        '    should_search = request.use_web or require_current\n'
    )
    text = replace_once(text, old, new, "Disable unnecessary automatic web search")

    path.write_text(text, encoding="utf-8")


def patch_frontend_api(path: Path) -> None:
    text = path.read_text(encoding="utf-8-sig")

    old = r'''export async function sendChat(messages: ChatMessage[], useWeb: boolean) {
  return postJsonAt(
    PROXY_API_URL,
    "/api/chat",
    {
      messages,
      provider: "auto",
      use_web: useWeb,
    },
    65000,
    2,
  );
}
'''

    new = r'''export async function sendChat(messages: ChatMessage[], useWeb: boolean) {
  const body = {
    messages,
    provider: "auto",
    use_web: useWeb,
  };

  try {
    return await postJsonAt(
      DIRECT_MEDIA_API_URL,
      "/api/chat",
      body,
      65000,
      1,
    );
  } catch (error) {
    const message =
      error instanceof Error ? error.message : "AI service connection failed.";

    if (/failed to fetch|network|connection/i.test(message)) {
      return postJsonAt(
        PROXY_API_URL,
        "/api/chat",
        body,
        65000,
        1,
      );
    }

    throw error;
  }
}
'''

    text = replace_once(
        text,
        old,
        new,
        "Direct chat backend and single retry",
    )

    path.write_text(text, encoding="utf-8")


def main() -> None:
    missing = [str(path) for path in FILES.values() if not path.exists()]
    if missing:
        raise SystemExit(
            "Project files not found. Put this script inside the project root.\n"
            + "\n".join(missing)
        )

    for path in FILES.values():
        backup(path)

    patch_config(FILES["config"])
    patch_chat(FILES["chat"])
    patch_main(FILES["main"])
    patch_frontend_api(FILES["api"])

    print("\nFast chat fix applied successfully.")
    print("Next commands:")
    print("  git add backend/app/config.py backend/app/main.py backend/app/services/chat.py frontend/lib/api.ts")
    print('  git commit -m "Fix chat speed and provider timeouts"')
    print("  git push origin main")


if __name__ == "__main__":
    main()
