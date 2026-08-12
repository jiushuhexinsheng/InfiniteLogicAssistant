# -*- coding: utf-8 -*-
"""语音端到端冒烟 — 说「小逻小逻」唤醒 → 说指令 → 走 /api/voice/utter 编排

用法（需先启动服务）:
    py -3.14 main.py serve            # 终端 A：启动后端
    py -3.14 scripts/voice_smoke.py   # 终端 B：对着麦克风说话

冒烟流程：
    1) 说「小逻小逻」唤醒（听到提示音）
    2) 接着说指令，如「把 C:\\test.txt 复制到下载」
    3) 若编排需要澄清/确认，脚本会提示你以文字回答
    4) Ctrl+C 退出
"""
import asyncio
import json
import sys
from pathlib import Path

import httpx

# 脚本在 scripts/ 下运行，需把项目根加入 sys.path 才能 import core
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.config import cfg
from core.voice.wake import WakeListener

BASE = "http://127.0.0.1:8520"


def check_server() -> bool:
    try:
        return httpx.get(f"{BASE}/api/ping", timeout=2).json().get("ok") is True
    except Exception:
        return False


async def run_pipeline(text: str) -> None:
    print(f"\n  🎙️ 识别指令: {text}")
    async with httpx.AsyncClient(timeout=120) as c:
        async with c.stream("POST", f"{BASE}/api/voice/utter", json={"text": text}) as r:
            async for line in r.aiter_lines():
                if not line.startswith("data: "):
                    continue
                evt = json.loads(line[6:])
                t = evt["type"]
                if t == "task_state":
                    print(f"  [状态] {evt.get('state')} {evt.get('status') or ''} {evt.get('summary') or ''}")
                    for st in evt.get("steps") or []:
                        print(f"         🔧 {st['tool']} {st['status']} → {str(st['result'])[:80]}")
                elif t == "content_delta":
                    print(f"[回复] {evt['text']}", end="", flush=True)
                elif t == "question":
                    ans = input(f"  [需要回答] {evt['question']}\n  → ")
                    await c.post(f"{BASE}/api/voice/answer",
                                 json={"session_id": evt["session_id"], "text": ans})
                elif t == "error":
                    print(f"  [错误] {evt.get('message')}")
                elif t == "done":
                    print("\n  [完成]")
                    return
            print("\n  [流结束]")


async def main() -> None:
    print("=" * 52)
    print("  语音端到端冒烟")
    print("  1) 说「小逻小逻」唤醒（听到提示音）")
    print("  2) 接着说指令，如「把 C:\\test.txt 复制到下载」")
    print("  3) 若需澄清/确认，用文字回答")
    print("  4) Ctrl+C 退出")
    print("=" * 52)
    if not check_server():
        print("\n[错误] 服务未启动。请先开一个终端运行: py -3.14 main.py serve")
        return
    model = cfg("voice.wake_word.local_model", "") or cfg("voice.wake_word.model_path", "")
    print(f"\n  模型目录: {model}")
    listener = WakeListener(model_path=model)
    if not listener.start(on_utterance=lambda t: asyncio.run(run_pipeline(t))):
        print("\n[错误] 语音监听启动失败。请检查:")
        print("  ① 系统/应用麦克风权限已开启")
        print("  ② vosk 模型目录存在（config voice.wake_word.local_model）")
        print("  ③ local_model 为 ASCII 路径（Windows 上 Kaldi/vosk 无法加载含中文的路径）")
        print("  ④ sounddevice 能访问麦克风")
        return
    print("  正在监听，说「小逻小逻」…")
    try:
        await asyncio.Event().wait()
    except (KeyboardInterrupt, asyncio.CancelledError):
        print("\n  退出")
    finally:
        listener.stop()


if __name__ == "__main__":
    asyncio.run(main())
