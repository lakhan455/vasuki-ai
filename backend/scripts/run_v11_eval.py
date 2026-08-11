from __future__ import annotations
import argparse, asyncio, json, os, sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))

from app.config import get_settings
from app.v11.quality import load_eval_cases, run_eval

async def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--mode",choices=["contract","live"],default="contract")
    parser.add_argument("--release",default=os.getenv("GITHUB_SHA","local")[:12] or "local")
    parser.add_argument("--limit",type=int,default=400)
    parser.add_argument("--output",default="v11-eval-report.json")
    args=parser.parse_args()
    rows=load_eval_cases()
    if len(rows)!=400:
        raise SystemExit(f"Expected 400 fixed eval cases, found {len(rows)}")
    report=await run_eval(get_settings(),release=args.release,live=args.mode=="live",limit=args.limit)
    Path(args.output).write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding="utf-8")
    print(json.dumps({"score":report["score"],"case_count":report["case_count"],"category_scores":report["category_scores"]},indent=2))
    if report["score"] < float(os.getenv("V11_MIN_EVAL_SCORE","60")):
        raise SystemExit(2)

if __name__=="__main__":
    asyncio.run(main())
