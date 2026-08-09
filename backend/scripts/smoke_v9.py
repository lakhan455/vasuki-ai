from __future__ import annotations
import os, httpx
BASE = os.getenv("VASUKI_SMOKE_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
def main():
    paths = ["/health", "/health/extended", "/health/v8-phase5", "/health/v9-phase1"]
    ok = True
    with httpx.Client(timeout=20.0) as client:
        for p in paths:
            try:
                r = client.get(BASE+p)
                passed = r.status_code < 400
                print("PASS" if passed else "FAIL", p, r.status_code)
                ok = ok and passed
            except Exception as exc:
                print("FAIL", p, exc); ok = False
    return 0 if ok else 1
if __name__ == "__main__":
    raise SystemExit(main())
