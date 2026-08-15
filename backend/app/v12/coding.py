\
from __future__ import annotations

import hashlib
from typing import Any

from app.v11.coding import analyze_plan_patch
from app.v12.sandbox import run_sandbox


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def apply_exact_patches(
    files: dict[str, str],
    patches: list[dict[str, Any]],
) -> dict[str, Any]:
    output = dict(files)
    applied = []

    for index, patch in enumerate(patches, 1):
        path = str(patch.get("path") or "").strip()
        before = str(patch.get("before") or "")
        after = str(patch.get("after") or "")
        expected_sha = str(patch.get("sha256") or "").strip()

        if not path or path not in output:
            raise ValueError(f"Patch {index}: file does not exist: {path}")

        current = output[path]

        if expected_sha and _sha(current) != expected_sha:
            raise ValueError(f"Patch {index}: SHA mismatch for {path}")

        count = current.count(before)

        if count != 1:
            raise ValueError(
                f"Patch {index}: expected exact block once in {path}; found {count}."
            )

        output[path] = current.replace(before, after, 1)

        applied.append(
            {
                "path": path,
                "before_chars": len(before),
                "after_chars": len(after),
                "new_sha256": _sha(output[path]),
            }
        )

    return {
        "ok": True,
        "files": output,
        "applied": applied,
    }


async def test_fix_retest(
    *,
    instruction: str,
    files: dict[str, str],
    runtime: str,
    test_command: str,
    settings,
    max_attempts: int = 3,
    timeout_seconds: int = 25,
) -> dict[str, Any]:
    max_attempts = max(1, min(3, int(max_attempts)))
    current = dict(files)
    history = []

    for attempt in range(1, max_attempts + 1):
        test = await run_sandbox(
            current,
            runtime=runtime,
            command=test_command,
            timeout_seconds=timeout_seconds,
        )

        history.append(
            {
                "attempt": attempt,
                "stage": "test",
                "result": test,
            }
        )

        if test.get("ok"):
            return {
                "ok": True,
                "attempts": attempt,
                "history": history,
                "files": current,
            }

        if not test.get("available"):
            return {
                "ok": False,
                "attempts": attempt,
                "history": history,
                "files": current,
                "error": "Safe sandbox is unavailable.",
            }

        error_context = (
            str(test.get("stderr") or "")
            + "\n"
            + str(test.get("stdout") or "")
        )[-18000:]

        repair_instruction = f"""
{instruction}

The isolated test environment failed.

Test command:
{test_command}

Failure:
{error_context}

Repair only files required to fix the failure.
Return complete changed files using the required file=relative/path fences.
"""

        repair = await analyze_plan_patch(
            repair_instruction,
            current,
            settings,
        )

        changed = repair.get("files") or {}

        history.append(
            {
                "attempt": attempt,
                "stage": "repair",
                "provider": repair.get("provider"),
                "changed_files": sorted(changed),
                "checks": repair.get("checks"),
            }
        )

        if not changed:
            break

        current.update(changed)

    final_test = await run_sandbox(
        current,
        runtime=runtime,
        command=test_command,
        timeout_seconds=timeout_seconds,
    )

    history.append(
        {
            "attempt": max_attempts,
            "stage": "final-test",
            "result": final_test,
        }
    )

    return {
        "ok": bool(final_test.get("ok")),
        "attempts": max_attempts,
        "history": history,
        "files": current,
    }
