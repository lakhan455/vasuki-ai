from __future__ import annotations

import asyncio
import base64
import importlib.util
import ipaddress
import json
import re
import socket
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from app.services.chat_v10 import route_chat_v10

try:
    from playwright.async_api import async_playwright
except Exception:
    async_playwright = None


TERMINAL_STATES = {"succeeded", "blocked", "failed", "cancelled"}
_URL_RE = re.compile(
    r"(?P<url>https?://[^\s<>'\"]+|(?:www\.)?[a-z0-9][a-z0-9.-]+\.[a-z]{2,}(?:/[^\s<>'\"]*)?)",
    re.I,
)
_PAYMENT_OR_SECRET_RE = re.compile(
    r"\b(password|passcode|card\s*number|credit\s*card|debit\s*card|cvv|cvc|"
    r"one[-\s]*time\s*password|\botp\b|upi\s*pin|bank\s*pin|routing\s*number|"
    r"send\s*money|transfer\s*money|make\s*payment|pay\s*now|purchase|buy\s*now|"
    r"place\s*order|checkout)\b",
    re.I,
)


def normalize_start_url(goal: str, explicit_url: str | None = None) -> str:
    value = str(explicit_url or "").strip()
    if not value:
        match = _URL_RE.search(str(goal or ""))
        value = match.group("url").rstrip(".,);]") if match else ""
    if not value:
        return ""
    if not re.match(r"^https?://", value, re.I):
        value = "https://" + value.lstrip("/")
    return value


def host_intrinsically_blocked(host: str) -> bool:
    value = str(host or "").strip().strip("[]").casefold()
    if not value:
        return True
    if value in {"localhost", "localhost.localdomain"} or value.endswith(".local"):
        return True
    try:
        ip = ipaddress.ip_address(value)
    except ValueError:
        return False
    return bool(
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


async def _public_host(host: str, cache: dict[str, bool]) -> bool:
    key = str(host or "").strip().casefold()
    if key in cache:
        return cache[key]
    if host_intrinsically_blocked(key):
        cache[key] = False
        return False

    def resolve() -> list[str]:
        addresses: list[str] = []
        for item in socket.getaddrinfo(key, None, proto=socket.IPPROTO_TCP):
            address = item[4][0]
            if address not in addresses:
                addresses.append(address)
        return addresses

    try:
        addresses = await asyncio.to_thread(resolve)
    except Exception:
        cache[key] = False
        return False

    if not addresses:
        cache[key] = False
        return False

    for address in addresses:
        if host_intrinsically_blocked(address):
            cache[key] = False
            return False

    cache[key] = True
    return True


async def public_http_url(url: str, cache: dict[str, bool] | None = None) -> bool:
    value = str(url or "").strip()
    try:
        parsed = urlparse(value)
    except Exception:
        return False
    if parsed.scheme.casefold() not in {"http", "https"}:
        return False
    if parsed.username or parsed.password:
        return False
    if not parsed.hostname:
        return False
    return await _public_host(parsed.hostname, cache if cache is not None else {})


def interaction_policy(action: dict[str, Any], element: dict[str, Any] | None) -> dict[str, Any]:
    kind = str(action.get("action") or "").casefold()
    target = element if isinstance(element, dict) else {}
    input_type = str(target.get("type") or "").casefold()
    combined = " ".join(
        str(value or "")
        for value in (
            target.get("text"),
            target.get("aria_label"),
            target.get("placeholder"),
            target.get("name"),
            target.get("href"),
            action.get("reason"),
        )
    )

    if input_type in {"password", "file"}:
        return {
            "allowed": False,
            "approval_required": False,
            "reason": f"V70 blocks {input_type} input for safety.",
        }

    if bool(target.get("download")):
        return {
            "allowed": False,
            "approval_required": False,
            "reason": "V70 blocks browser downloads in this version.",
        }

    if _PAYMENT_OR_SECRET_RE.search(combined):
        return {
            "allowed": False,
            "approval_required": False,
            "reason": "V70 blocks credential/payment/high-impact financial interactions.",
        }

    if kind in {"click", "fill", "press"}:
        return {
            "allowed": True,
            "approval_required": True,
            "reason": "Interactive browser action requires explicit approval.",
        }

    return {
        "allowed": True,
        "approval_required": False,
        "reason": "Read-only browser action.",
    }


async def browser_runtime_snapshot(settings: Any) -> dict[str, Any]:
    enabled = bool(getattr(settings, "v70_browser_enabled", True))
    package_installed = importlib.util.find_spec("playwright") is not None
    executable_path = ""
    browser_installed = False
    error = ""

    if enabled and package_installed and async_playwright is not None:
        try:
            manager = await async_playwright().start()
            try:
                executable_path = str(manager.chromium.executable_path or "")
                browser_installed = bool(
                    executable_path and Path(executable_path).exists()
                )
            finally:
                await manager.stop()
        except Exception as exc:
            error = f"{type(exc).__name__}: {str(exc)[:500]}"

    ready = bool(enabled and package_installed and browser_installed)
    return {
        "ok": True,
        "version": "v70",
        "name": "Vasuki Real Browser Agent",
        "enabled": enabled,
        "ready": ready,
        "playwright_package_installed": package_installed,
        "chromium_installed": browser_installed,
        "chromium_executable_present": browser_installed,
        "runtime_error": error or None,
        "features": {
            "navigate_public_web": ready,
            "page_text_extraction": ready,
            "screenshot": ready,
            "link_navigation": ready,
            "click_with_approval": ready,
            "fill_with_approval": ready,
            "keypress_with_approval": ready,
            "isolated_context_per_job": True,
            "downloads": False,
            "file_upload": False,
            "password_entry": False,
            "payment_actions": False,
            "private_network_access": False,
        },
        "safety": {
            "interactive_actions_require_approval": True,
            "credentials_and_payment_blocked": True,
            "private_and_loopback_networks_blocked": True,
            "browser_context_persisted": False,
            "fake_ready_state_allowed": False,
        },
        "new_database_migration_required": False,
    }


@dataclass
class BrowserJob:
    id: str
    user_id: str
    goal: str
    start_url: str
    max_steps: int
    status: str = "queued"
    stage: str = "queued"
    progress: int = 0
    message: str = "Browser work queued"
    error: str = ""
    events: list[dict[str, Any]] = field(default_factory=list)
    pending_action: dict[str, Any] | None = None
    result: dict[str, Any] | None = None
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    task: asyncio.Task | None = None
    approval_event: asyncio.Event = field(default_factory=asyncio.Event)
    approval_decision: str = ""

    def snapshot(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "ok": self.status != "failed",
            "job_id": self.id,
            "status": self.status,
            "stage": self.stage,
            "progress": self.progress,
            "message": self.message,
            "error": self.error or None,
            "goal": self.goal,
            "start_url": self.start_url,
            "max_steps": self.max_steps,
            "events": list(self.events[-40:]),
            "pending_action": self.pending_action,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }
        if self.status in TERMINAL_STATES and self.result is not None:
            payload["result"] = self.result
        return payload


_JOBS: dict[str, BrowserJob] = {}
_LOCK = asyncio.Lock()


def _event(
    job: BrowserJob,
    *,
    stage: str,
    state: str,
    detail: str,
    evidence: dict[str, Any] | None = None,
) -> None:
    job.events.append(
        {
            "at": time.time(),
            "stage": stage,
            "state": state,
            "detail": str(detail or "")[:1200],
            "evidence": evidence or {},
        }
    )
    if len(job.events) > 80:
        del job.events[:-80]


async def _set_progress(
    job: BrowserJob,
    *,
    stage: str,
    progress: int,
    message: str,
) -> None:
    async with _LOCK:
        current = _JOBS.get(job.id)
        if not current:
            return
        current.stage = stage[:80]
        current.progress = max(0, min(100, int(progress)))
        current.message = str(message or "")[:500]
        current.updated_at = time.time()


async def _page_snapshot(page: Any) -> dict[str, Any]:
    script = r"""
() => {
  const visible = (el) => {
    const style = window.getComputedStyle(el);
    const rect = el.getBoundingClientRect();
    return style.visibility !== "hidden" &&
      style.display !== "none" &&
      rect.width > 0 &&
      rect.height > 0;
  };

  const nodes = Array.from(
    document.querySelectorAll(
      "a,button,input,textarea,select,[role='button'],[role='link'],[contenteditable='true'],summary"
    )
  ).filter(visible).slice(0, 100);

  const elements = nodes.map((el, index) => {
    const id = `v70-${index}`;
    el.setAttribute("data-vasuki-agent-id", id);
    const text = (
      el.innerText ||
      el.value ||
      el.getAttribute("aria-label") ||
      el.getAttribute("title") ||
      ""
    ).trim().replace(/\s+/g, " ").slice(0, 220);

    return {
      id,
      tag: el.tagName.toLowerCase(),
      role: el.getAttribute("role") || "",
      type: el.getAttribute("type") || "",
      text,
      aria_label: el.getAttribute("aria-label") || "",
      placeholder: el.getAttribute("placeholder") || "",
      name: el.getAttribute("name") || "",
      href: el.href || "",
      download: Boolean(el.hasAttribute("download")),
      disabled: Boolean(el.disabled),
    };
  });

  return {
    title: document.title || "",
    text: (document.body?.innerText || "")
      .replace(/\n{3,}/g, "\n\n")
      .slice(0, 14000),
    elements,
  };
}
"""
    data = await page.evaluate(script)
    if not isinstance(data, dict):
        data = {}
    data["url"] = str(page.url or "")
    return data


def _json_from_text(value: str) -> dict[str, Any] | None:
    text = str(value or "").strip()
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", text, re.I)
    if fence:
        text = fence.group(1).strip()
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        parsed = json.loads(text[start : end + 1])
    except Exception:
        return None
    return parsed if isinstance(parsed, dict) else None


async def _agent_decision(
    goal: str,
    snapshot: dict[str, Any],
    settings: Any,
    *,
    step: int,
    max_steps: int,
) -> dict[str, Any]:
    elements = snapshot.get("elements")
    elements = elements if isinstance(elements, list) else []
    compact = [
        {
            "id": item.get("id"),
            "tag": item.get("tag"),
            "role": item.get("role"),
            "type": item.get("type"),
            "text": item.get("text"),
            "aria_label": item.get("aria_label"),
            "placeholder": item.get("placeholder"),
            "href": item.get("href"),
            "disabled": item.get("disabled"),
        }
        for item in elements[:80]
        if isinstance(item, dict)
    ]

    prompt = f"""You are Vasuki Browser Agent V70.

GOAL:
{goal}

CURRENT PAGE:
URL: {snapshot.get("url") or ""}
TITLE: {snapshot.get("title") or ""}

VISIBLE PAGE TEXT:
{str(snapshot.get("text") or "")[:12000]}

INTERACTIVE ELEMENTS:
{json.dumps(compact, ensure_ascii=False)}

STEP: {step}/{max_steps}

Return strict JSON only. Choose exactly one action:
1) {{"action":"done","final_answer":"...","reason":"..."}}
2) {{"action":"goto","url":"https://...","reason":"..."}}
3) {{"action":"click","target_id":"v70-#","reason":"..."}}
4) {{"action":"fill","target_id":"v70-#","value":"...","reason":"..."}}
5) {{"action":"press","target_id":"v70-#","key":"Enter","reason":"..."}}
6) {{"action":"scroll","direction":"down|up","reason":"..."}}

Rules:
- Use only the page evidence above.
- Prefer goto using a visible link href instead of clicking a link.
- Do not request passwords, OTPs, payment/card/bank data, file uploads, purchases, or downloads.
- Never claim an action happened until the next page snapshot proves it.
- If the goal is already answered, choose done.
- If blocked by login/credentials/payment or the site lacks needed information, choose done and explain the limitation.
"""
    answer, provider = await route_chat_v10(
        "auto",
        [{"role": "user", "content": prompt}],
        settings,
        "",
        require_current=False,
    )
    decision = _json_from_text(answer) or {
        "action": "done",
        "final_answer": (
            "Browser Agent could not derive a safe structured next action from the current page."
        ),
        "reason": "unstructured-agent-output",
    }
    decision["provider"] = provider
    return decision


def _element_by_id(
    snapshot: dict[str, Any],
    target_id: str,
) -> dict[str, Any] | None:
    items = snapshot.get("elements")
    if not isinstance(items, list):
        return None
    for item in items:
        if isinstance(item, dict) and str(item.get("id") or "") == target_id:
            return item
    return None


async def _screenshot_data_url(page: Any) -> str:
    try:
        raw = await page.screenshot(
            type="jpeg",
            quality=58,
            full_page=False,
        )
        if not raw:
            return ""
        return "data:image/jpeg;base64," + base64.b64encode(raw).decode("ascii")
    except Exception:
        return ""


async def _execute(job: BrowserJob, settings: Any) -> None:
    browser = None
    manager = None
    context = None
    host_cache: dict[str, bool] = {}

    try:
        runtime = await browser_runtime_snapshot(settings)
        if not runtime.get("ready"):
            job.status = "blocked"
            job.stage = "browser-runtime-unavailable"
            job.progress = 100
            job.message = "Playwright Chromium is not installed on this runtime"
            job.result = {
                "answer": (
                    "Browser Agent is implemented but this server does not currently have "
                    "the required Chromium runtime installed. No browser action was faked."
                ),
                "sources": [],
                "execution_proof": {
                    "browser_launched": False,
                    "runtime_ready": False,
                    "runtime": runtime,
                },
            }
            return

        if not await public_http_url(job.start_url, host_cache):
            job.status = "blocked"
            job.stage = "blocked-url"
            job.progress = 100
            job.message = "The requested URL is not an allowed public web address"
            job.result = {
                "answer": (
                    "Browser Agent blocked the start URL because it is not a "
                    "public HTTP(S) destination."
                ),
                "sources": [],
                "execution_proof": {
                    "browser_launched": False,
                    "blocked_url": job.start_url,
                },
            }
            return

        await _set_progress(
            job,
            stage="launching-browser",
            progress=5,
            message="Launching isolated Chromium",
        )
        manager = await async_playwright().start()
        browser = await manager.chromium.launch(
            channel="chromium",
            headless=bool(getattr(settings, "v70_browser_headless", True)),
            args=["--disable-dev-shm-usage"],
        )
        context = await browser.new_context(
            accept_downloads=False,
            ignore_https_errors=False,
            java_script_enabled=True,
            viewport={"width": 1365, "height": 820},
            user_agent="VasukiAI-BrowserAgent/70",
        )
        page = await context.new_page()

        async def route_guard(route: Any) -> None:
            url = str(route.request.url or "")
            if url.startswith(("data:", "blob:", "about:")):
                await route.continue_()
                return
            if await public_http_url(url, host_cache):
                await route.continue_()
            else:
                await route.abort()

        await page.route("**/*", route_guard)

        timeout_ms = int(
            max(
                5.0,
                min(
                    60.0,
                    float(
                        getattr(
                            settings,
                            "v70_browser_timeout_seconds",
                            25.0,
                        )
                    ),
                ),
            )
            * 1000
        )

        await _set_progress(
            job,
            stage="navigating",
            progress=12,
            message="Opening the requested public page",
        )
        await page.goto(
            job.start_url,
            wait_until="domcontentloaded",
            timeout=timeout_ms,
        )

        if not await public_http_url(str(page.url or ""), host_cache):
            raise RuntimeError(
                "Navigation redirected to a blocked or private destination."
            )

        _event(
            job,
            stage="navigate",
            state="completed",
            detail=f"Opened {page.url}",
            evidence={"url": page.url, "title": await page.title()},
        )

        final_answer = ""
        steps_executed = 0

        for step in range(1, job.max_steps + 1):
            await _set_progress(
                job,
                stage="reading-page",
                progress=min(
                    86,
                    15 + int(65 * step / max(1, job.max_steps)),
                ),
                message=f"Inspecting browser page · step {step}/{job.max_steps}",
            )

            snapshot = await _page_snapshot(page)
            decision = await _agent_decision(
                job.goal,
                snapshot,
                settings,
                step=step,
                max_steps=job.max_steps,
            )
            action = str(
                decision.get("action") or "done"
            ).casefold()
            reason = str(
                decision.get("reason") or ""
            )[:700]
            steps_executed = step

            _event(
                job,
                stage="agent-decision",
                state="planned",
                detail=f"Step {step}: {action}. {reason}",
                evidence={
                    "url": snapshot.get("url"),
                    "title": snapshot.get("title"),
                    "action": action,
                },
            )

            if action == "done":
                final_answer = str(
                    decision.get("final_answer") or ""
                ).strip()
                if not final_answer:
                    final_answer = (
                        "Browser Agent finished because no further "
                        "safe browser action was required."
                    )
                break

            if action == "scroll":
                direction = str(
                    decision.get("direction") or "down"
                ).casefold()
                amount = -620 if direction == "up" else 620
                await page.mouse.wheel(0, amount)
                await page.wait_for_timeout(350)
                _event(
                    job,
                    stage="scroll",
                    state="completed",
                    detail=f"Scrolled {direction}.",
                )
                continue

            if action == "goto":
                target_url = str(
                    decision.get("url") or ""
                ).strip()
                if not await public_http_url(
                    target_url,
                    host_cache,
                ):
                    final_answer = (
                        "Browser Agent stopped because the planned navigation "
                        "target was not an allowed public HTTP(S) URL."
                    )
                    _event(
                        job,
                        stage="goto",
                        state="blocked",
                        detail="Blocked non-public navigation target.",
                        evidence={"url": target_url},
                    )
                    break

                await page.goto(
                    target_url,
                    wait_until="domcontentloaded",
                    timeout=timeout_ms,
                )
                if not await public_http_url(
                    str(page.url or ""),
                    host_cache,
                ):
                    raise RuntimeError(
                        "Navigation redirected to a blocked/private destination."
                    )
                _event(
                    job,
                    stage="goto",
                    state="completed",
                    detail=f"Navigated to {page.url}",
                    evidence={"url": page.url},
                )
                continue

            if action not in {"click", "fill", "press"}:
                final_answer = (
                    "Browser Agent stopped on unsupported planned action: "
                    f"{action}."
                )
                break

            target_id = str(
                decision.get("target_id") or ""
            )
            element = _element_by_id(
                snapshot,
                target_id,
            )
            if element is None:
                _event(
                    job,
                    stage="interaction",
                    state="blocked",
                    detail="Planned target was no longer present on the page.",
                    evidence={"target_id": target_id},
                )
                continue

            policy = interaction_policy(
                decision,
                element,
            )
            if not policy["allowed"]:
                final_answer = str(
                    policy["reason"]
                )
                _event(
                    job,
                    stage="interaction",
                    state="blocked",
                    detail=final_answer,
                    evidence={
                        "action": action,
                        "target": element,
                    },
                )
                break

            if policy["approval_required"]:
                async with _LOCK:
                    current = _JOBS.get(job.id)
                    if not current:
                        return
                    current.status = "awaiting_approval"
                    current.stage = "approval"
                    current.message = (
                        "Approval required before interactive browser action"
                    )
                    current.pending_action = {
                        "type": f"browser.{action}",
                        "action": action,
                        "target_id": target_id,
                        "target_text": str(
                            element.get("text")
                            or element.get("aria_label")
                            or element.get("placeholder")
                            or ""
                        )[:300],
                        "target_tag": element.get("tag"),
                        "input_type": element.get("type"),
                        "value_preview": (
                            str(
                                decision.get("value")
                                or ""
                            )[:300]
                            if action == "fill"
                            else ""
                        ),
                        "key": (
                            str(
                                decision.get("key")
                                or ""
                            )[:80]
                            if action == "press"
                            else ""
                        ),
                        "reason": reason,
                        "url": snapshot.get("url"),
                    }
                    current.updated_at = time.time()

                _event(
                    job,
                    stage="approval",
                    state="waiting",
                    detail=(
                        f"Waiting for approval: {action} on {target_id}."
                    ),
                    evidence={
                        "target": element,
                        "reason": reason,
                    },
                )

                job.approval_decision = ""
                job.approval_event.clear()

                try:
                    await asyncio.wait_for(
                        job.approval_event.wait(),
                        timeout=600.0,
                    )
                except asyncio.TimeoutError:
                    job.status = "cancelled"
                    job.stage = "approval-expired"
                    job.progress = 100
                    job.message = "Browser approval expired"
                    job.pending_action = None
                    job.result = {
                        "answer": (
                            "Approval expired. The interactive browser "
                            "action was not executed."
                        ),
                        "sources": [],
                        "execution_proof": {
                            "browser_launched": True,
                            "interactive_action_executed": False,
                        },
                    }
                    return

                if job.approval_decision != "approve":
                    job.status = "cancelled"
                    job.stage = "cancelled"
                    job.progress = 100
                    job.message = "Browser action was not approved"
                    job.pending_action = None
                    job.result = {
                        "answer": (
                            "Browser work stopped before the interactive "
                            "action because approval was not granted."
                        ),
                        "sources": [],
                        "execution_proof": {
                            "browser_launched": True,
                            "interactive_action_executed": False,
                        },
                    }
                    return

                job.status = "running"
                job.pending_action = None

            locator = page.locator(
                f'[data-vasuki-agent-id="{target_id}"]'
            )

            if action == "click":
                await locator.click(
                    timeout=timeout_ms,
                )
            elif action == "fill":
                await locator.fill(
                    str(
                        decision.get("value")
                        or ""
                    )[:4000],
                    timeout=timeout_ms,
                )
            elif action == "press":
                key = str(
                    decision.get("key")
                    or "Enter"
                )[:80]
                await locator.press(
                    key,
                    timeout=timeout_ms,
                )

            await page.wait_for_timeout(500)

            if str(page.url or "").startswith(
                ("http://", "https://")
            ):
                if not await public_http_url(
                    str(page.url or ""),
                    host_cache,
                ):
                    raise RuntimeError(
                        "Interactive action navigated to a "
                        "blocked/private destination."
                    )

            _event(
                job,
                stage="interaction",
                state="completed",
                detail=f"Approved browser {action} executed.",
                evidence={
                    "target_id": target_id,
                    "url": page.url,
                },
            )

        final_snapshot = await _page_snapshot(page)

        if not final_answer:
            final_answer = (
                f"Browser Agent reached its {job.max_steps}-step safety limit. "
                "The final page is shown in the execution proof."
            )

        screenshot = await _screenshot_data_url(page)
        final_url = str(
            final_snapshot.get("url")
            or page.url
            or ""
        )
        final_title = str(
            final_snapshot.get("title")
            or ""
        )

        source = {
            "title": (
                final_title
                or final_url
                or "Browser page"
            ),
            "url": final_url,
            "domain": (
                urlparse(final_url).netloc
                if final_url
                else ""
            ),
            "source_type": "browser",
        }

        job.status = "succeeded"
        job.stage = "ready"
        job.progress = 100
        job.message = "Browser work completed"
        job.result = {
            "answer": final_answer,
            "sources": (
                [source]
                if final_url
                else []
            ),
            "screenshot_data_url": screenshot,
            "final_url": final_url,
            "final_title": final_title,
            "final_page_text": str(
                final_snapshot.get("text")
                or ""
            )[:10000],
            "execution_proof": {
                "browser_launched": True,
                "engine": "playwright-chromium",
                "steps_executed": steps_executed,
                "isolated_context": True,
                "downloads_allowed": False,
                "private_network_access_allowed": False,
                "interactive_actions_require_approval": True,
                "credentials_and_payment_blocked": True,
            },
        }

    except asyncio.CancelledError:
        job.status = "cancelled"
        job.stage = "cancelled"
        job.progress = 100
        job.message = "Browser work cancelled"
        if job.result is None:
            job.result = {
                "answer": (
                    "Browser work was cancelled before completion."
                ),
                "sources": [],
                "execution_proof": {
                    "cancelled": True,
                },
            }
        raise

    except Exception as exc:
        job.status = "failed"
        job.stage = "failed"
        job.progress = 100
        job.error = (
            f"{type(exc).__name__}: {str(exc)[:1800]}"
        )
        job.message = (
            f"Browser work failed: {str(exc)[:500]}"
        )
        job.result = {
            "answer": (
                "Browser Agent failed before completion. "
                "No browser action was reported as completed without evidence."
            ),
            "sources": [],
            "execution_proof": {
                "failed": True,
                "error_type": type(exc).__name__,
                "no_fake_completion": True,
            },
        }
        _event(
            job,
            stage="runtime",
            state="failed",
            detail=str(exc)[:1000],
        )

    finally:
        job.updated_at = time.time()

        if context is not None:
            try:
                await context.close()
            except Exception:
                pass

        if browser is not None:
            try:
                await browser.close()
            except Exception:
                pass

        if manager is not None:
            try:
                await manager.stop()
            except Exception:
                pass


async def _cleanup(ttl_seconds: int = 3600) -> None:
    cutoff = time.time() - max(
        300,
        int(ttl_seconds),
    )
    async with _LOCK:
        stale = [
            job_id
            for job_id, job in _JOBS.items()
            if (
                job.updated_at < cutoff
                and job.status in TERMINAL_STATES
            )
        ]
        for job_id in stale:
            _JOBS.pop(
                job_id,
                None,
            )


async def create_browser_job(
    settings: Any,
    *,
    user_id: str,
    goal: str,
    start_url: str | None = None,
    max_steps: int = 6,
    ttl_seconds: int = 3600,
) -> dict[str, Any]:
    await _cleanup(
        ttl_seconds
    )

    value = str(
        goal or ""
    ).strip()

    if len(value) < 3:
        raise ValueError(
            "Browser work goal is too short."
        )

    url = normalize_start_url(
        value,
        start_url,
    )

    if not url:
        raise ValueError(
            "Browser Work needs a public website URL in the request."
        )

    job = BrowserJob(
        id=uuid.uuid4().hex,
        user_id=user_id,
        goal=value[:12000],
        start_url=url[:3000],
        max_steps=max(
            1,
            min(
                10,
                int(max_steps),
            ),
        ),
    )

    async with _LOCK:
        active = sum(
            1
            for item in _JOBS.values()
            if (
                item.user_id == user_id
                and item.status in {
                    "queued",
                    "running",
                    "awaiting_approval",
                }
            )
        )

        if active >= 1:
            raise RuntimeError(
                "You already have an active Browser Agent job."
            )

        _JOBS[job.id] = job

    job.task = asyncio.create_task(
        _execute(
            job,
            settings,
        ),
        name=f"vasuki-browser-{job.id[:8]}",
    )

    return job.snapshot()


async def get_browser_job(
    *,
    user_id: str,
    job_id: str,
    ttl_seconds: int = 3600,
) -> dict[str, Any] | None:
    await _cleanup(
        ttl_seconds
    )

    async with _LOCK:
        job = _JOBS.get(
            job_id
        )

        if (
            not job
            or job.user_id != user_id
        ):
            return None

        return job.snapshot()


async def approve_browser_job(
    *,
    user_id: str,
    job_id: str,
    approve: bool,
) -> dict[str, Any] | None:
    async with _LOCK:
        job = _JOBS.get(
            job_id
        )

        if (
            not job
            or job.user_id != user_id
        ):
            return None

        if job.status != "awaiting_approval":
            return job.snapshot()

        job.approval_decision = (
            "approve"
            if approve
            else "reject"
        )
        job.updated_at = time.time()
        job.approval_event.set()

        return job.snapshot()


async def cancel_browser_job(
    *,
    user_id: str,
    job_id: str,
) -> dict[str, Any] | None:
    async with _LOCK:
        job = _JOBS.get(
            job_id
        )

        if (
            not job
            or job.user_id != user_id
        ):
            return None

        if job.status in TERMINAL_STATES:
            return job.snapshot()

        job.approval_decision = "reject"
        job.approval_event.set()
        task = job.task

    if (
        task
        and not task.done()
    ):
        task.cancel()

    async with _LOCK:
        current = _JOBS.get(
            job_id
        )
        return (
            current.snapshot()
            if current
            else None
        )


async def shutdown_browser_jobs() -> None:
    async with _LOCK:
        tasks = [
            job.task
            for job in _JOBS.values()
            if (
                job.task
                and not job.task.done()
            )
        ]

    for task in tasks:
        task.cancel()
