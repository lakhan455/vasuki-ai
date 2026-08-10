from __future__ import annotations

import asyncio
import json

from app.config import get_settings
from app.services.omniroute_gateway_v10 import probe, snapshot
from app.services.omniroute_knowledge_v10 import corpus_info


async def main() -> int:
    settings = get_settings()
    result = {
        "knowledge": corpus_info(),
        "gateway": await probe(settings),
        "telemetry": snapshot(),
    }
    print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
    return 0 if result["knowledge"].get("available") else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
