from __future__ import annotations
import json, os, time
from collections import defaultdict
from pathlib import Path
import httpx

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "evals" / "vasuki_eval_v9.json"
OUT = ROOT / "evals" / "latest_score.json"

def score(answer, row):
    low = answer.casefold()
    req = [str(x).casefold() for x in row.get("expected_contains", [])]
    bad = [str(x).casefold() for x in row.get("must_not_contain", [])]
    if any(x in low for x in bad): return 0.0
    if not req: return 1.0 if len(answer.strip()) >= row.get("min_chars",20) else 0.0
    return sum(x in low for x in req) / len(req)

def main():
    base = os.getenv("VASUKI_EVAL_BASE_URL","http://127.0.0.1:8000").rstrip("/")
    token = os.getenv("VASUKI_EVAL_TOKEN","").strip()
    if not token:
        print("Set VASUKI_EVAL_TOKEN first."); return 2
    rows = json.loads(DATA.read_text(encoding="utf-8"))
    groups, lats = defaultdict(list), []
    with httpx.Client(timeout=75.0) as client:
        for i,row in enumerate(rows,1):
            payload = {
                "provider":"auto",
                "messages":[{"role":"user","content":row["prompt"]}],
                "use_web":row["category"]=="research",
                "use_memory":row["category"]=="memory",
                "use_documents":False,
                "research_mode":row["category"]=="research",
            }
            t=time.perf_counter()
            try:
                r=client.post(base+"/api/chat",headers={"Authorization":f"Bearer {token}"},json=payload)
                r.raise_for_status()
                value=score(str(r.json().get("answer") or ""),row)
            except Exception:
                value=0.0
            lats.append((time.perf_counter()-t)*1000); groups[row["category"]].append(value)
            print(f"[{i}/{len(rows)}] {row['id']} {value:.2f}")
    scores={k:round(100*sum(v)/max(1,len(v))) for k,v in groups.items()}
    result={"version":"v9-phase1","questions":len(rows),"scores":scores,"overall":round(sum(scores.values())/max(1,len(scores))),"average_latency_ms":round(sum(lats)/max(1,len(lats)))}
    OUT.write_text(json.dumps(result,indent=2),encoding="utf-8")
    print(json.dumps(result,indent=2)); return 0
if __name__ == "__main__":
    raise SystemExit(main())
