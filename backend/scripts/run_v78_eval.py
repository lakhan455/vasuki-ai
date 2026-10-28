from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.config import get_settings
from app.v78.self_eval import (
    DEFAULT_MIN_CATEGORY_SCORE,
    DEFAULT_MIN_SCORE,
    FIXED_EVAL_CASES,
    run_release_eval,
)


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["contract", "live"], default="contract")
    parser.add_argument(
        "--release",
        default=os.getenv("GITHUB_SHA", "local")[:12] or "local",
    )
    parser.add_argument("--limit", type=int, default=FIXED_EVAL_CASES)
    parser.add_argument("--min-score", type=float, default=DEFAULT_MIN_SCORE)
    parser.add_argument(
        "--min-category-score",
        type=float,
        default=DEFAULT_MIN_CATEGORY_SCORE,
    )
    parser.add_argument("--output", default="v78-eval-report.json")
    args = parser.parse_args()

    result = await run_release_eval(
        get_settings(),
        release=args.release,
        live=args.mode == "live",
        limit=args.limit,
        min_score=args.min_score,
        min_category_score=args.min_category_score,
    )
    Path(args.output).write_text(
        json.dumps(result, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(json.dumps(result["summary"], indent=2, ensure_ascii=False))
    if not result["release_gate"]["passed"]:
        raise SystemExit(2)


if __name__ == "__main__":
    asyncio.run(main())
