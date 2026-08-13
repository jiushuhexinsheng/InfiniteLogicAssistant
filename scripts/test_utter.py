# -*- coding: utf-8 -*-
"""诊断：直接 POST /api/voice/utter，打印 SSE 事件"""
import json
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

BASE = "http://127.0.0.1:8520"


def main() -> None:
    text = sys.argv[1] if len(sys.argv) > 1 else "查一下现在几点"
    print(f"POST: {text}")
    with httpx.Client(timeout=60) as c:
        with c.stream("POST", f"{BASE}/api/voice/utter", json={"text": text}) as resp:
            print("status:", resp.status_code)
            for line in resp.iter_lines():
                if line.startswith("data: "):
                    evt = json.loads(line[6:])
                    print("  ", evt["type"], (evt.get("text") or evt.get("summary") or evt.get("state") or "")[:50])


if __name__ == "__main__":
    main()
