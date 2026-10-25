from __future__ import annotations

import json
import os
import urllib.error
import urllib.request


BASE = os.getenv(
    "VASUKI_CANARY_BASE_URL",
    "https://vasuki-ai.onrender.com",
).rstrip("/")
SECRET = os.getenv("VASUKI_V50_CRON_SECRET", "").strip()


def request(path: str, *, method: str = "GET", headers=None):
    req = urllib.request.Request(BASE + path, method=method, headers=headers or {})
    with urllib.request.urlopen(req, timeout=90) as response:
        body = response.read().decode("utf-8", errors="replace")
        return response.status, json.loads(body)


def main() -> int:
    try:
        status, health = request("/health/v50")
    except Exception as exc:
        print("V50 health failed:", type(exc).__name__, str(exc)[:500])
        return 1

    print("health_status =", status)
    print("health_ok =", bool(health.get("ok")))
    print(
        "search_ready =",
        bool((health.get("live_knowledge") or {}).get("search_ready")),
    )
    print(
        "storage_ready =",
        bool((health.get("live_knowledge") or {}).get("storage_ready")),
    )

    if status != 200 or not health.get("ok"):
        return 1

    if SECRET:
        try:
            refresh_status, refresh = request(
                "/internal/v50/live-refresh",
                method="POST",
                headers={"X-Vasuki-Cron-Secret": SECRET},
            )
            print("refresh_status =", refresh_status)
            print("refresh_ok =", bool(refresh.get("ok")))
            if refresh_status != 200:
                return 1
        except urllib.error.HTTPError as exc:
            print("refresh_http_error =", exc.code)
            return 1
        except Exception as exc:
            print("refresh_failed =", type(exc).__name__, str(exc)[:500])
            return 1
    else:
        print("refresh_skipped = VASUKI_V50_CRON_SECRET is not configured")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
