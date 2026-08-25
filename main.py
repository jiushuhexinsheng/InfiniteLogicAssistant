# -*- coding: utf-8 -*-
"""无限逻辑·语音助手 — 主入口

用法:
    python main.py serve             启动 Web 服务
    python main.py test              测试 LLM / ASR / TTS 连通性
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from core.config import ensure_dirs


def cmd_serve():
    from server import start_server
    start_server()


async def _cmd_test() -> bool:
    """连通性测试：跑三项检测，返回是否有失败。"""
    from core.detection.connectivity import run_checks

    print("=" * 56)
    print("  连通性测试 — LLM / ASR / TTS")
    print("=" * 56)

    results = await run_checks()
    failed = False
    for r in results:
        label = {"ok": "[OK]  ", "skip": "[跳过]", "fail": "[失败]"}[r.status]
        detail = r.detail or ""
        if r.latency_ms is not None:
            detail = f"{detail}（{r.latency_ms}ms）"
        print(f"{r.name:6} {label} {detail}")
        if r.status == "fail":
            failed = True

    print(f"\n{'=' * 56}")
    if failed:
        print("  结果: 存在连通性失败，请查看 data/agent.log")
    else:
        print("  结果: 全部正常（未配置项已跳过）")
    print(f"{'=' * 56}\n")
    return failed


def cmd_test():
    failed = asyncio.run(_cmd_test())
    if failed:
        sys.exit(1)


def main():
    ensure_dirs()
    cmd = sys.argv[1] if len(sys.argv) > 1 else "serve"
    if cmd == "serve":
        cmd_serve()
    elif cmd == "test":
        cmd_test()
    else:
        print(f"用法: python main.py {{serve|test}}")
        sys.exit(1)


if __name__ == "__main__":
    main()
