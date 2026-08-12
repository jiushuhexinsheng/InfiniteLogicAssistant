# -*- coding: utf-8 -*-
"""P1 记忆验证：跑一个「记住偏好」任务 → 检查长期记忆是否写入

用法（服务需已启动）：py -3.14 scripts/verify_memory.py
"""
import json
import sys
import time
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

BASE = "http://127.0.0.1:8520"


def main() -> None:
    text = "记住，我平时用中文交流"
    print(f"任务: {text}")
    with httpx.Client(timeout=120) as c:
        with c.stream("POST", f"{BASE}/api/voice/utter", json={"text": text}) as resp:
            for line in resp.iter_lines():
                if line.startswith("data: "):
                    evt = json.loads(line[6:])
                    t = evt["type"]
                    if t == "task_state":
                        print(f"  [状态] {evt.get('state')} {evt.get('status') or ''} {(evt.get('summary') or '')[:60]}")
                        for s in evt.get("steps") or []:
                            print(f"     🔧 {s['tool']} {s['status']} → {str(s['result'])[:60]}")
                    elif t == "question":
                        print(f"  [提问] {evt['question'][:60]}")
                        c.post(f"{BASE}/api/voice/answer",
                               json={"session_id": evt["session_id"], "text": "确认"})
                    elif t == "done":
                        break
    time.sleep(2)
    r = httpx.get(f"{BASE}/api/memory").json()
    facts = r.get("facts", [])
    print(f"\n长期记忆 facts: {len(facts)}")
    for f in facts:
        print(f"  - {f['topic']}: {f['content']} ({f['source']})")


if __name__ == "__main__":
    main()
