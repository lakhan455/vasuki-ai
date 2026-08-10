from __future__ import annotations
import os
import httpx

BASE = os.getenv("VASUKI_SMOKE_BASE_URL", "http://127.0.0.1:8000").rstrip("/")

def main():
    paths = [
        "/health",
        "/health/extended",
        "/health/v8-phase5",
        "/health/v9-phase1",
        "/health/v9-phase2",
        "/health/v9-phase3",
        "/health/v9-phase4",
        "/health/v9-phase5",
        "/health/v9-phase6",
    ]
    ok = True
    with httpx.Client(timeout=20.0) as client:
        for path in paths:
            try:
                response = client.get(BASE + path)
                passed = response.status_code < 400
                print("PASS" if passed else "FAIL", path, response.status_code)
                ok = ok and passed
            except Exception as exc:
                print("FAIL", path, exc)
                ok = False
    return 0 if ok else 1

if __name__ == "__main__":
    raise SystemExit(main())
