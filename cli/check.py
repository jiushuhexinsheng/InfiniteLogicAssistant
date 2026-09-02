# -*- coding: utf-8 -*-
"""check 命令 — 聚合检测：环境 + 配置校验 + LLM/ASR/TTS 连通性（core.detection.run_all）

The check command — aggregated checks: environment + config validation + LLM/ASR/TTS connectivity (core.detection.run_all)."""
import argparse
import asyncio
import sys

from core.detection import run_all

_LEVEL_LABEL = {"ok": "[OK]  ", "skip": "[跳过]", "fail": "[失败]"}
_ISSUE_LABEL = {"error": "[错误]", "warning": "[警告]", "info": "[信息]"}

_ENV_KEYS = ("os", "hostname", "arch", "cpu", "memory_gb", "python", "net_ok")


def _print_env(env: dict) -> None:
    """按固定顺序打印环境信息键值对。

    Print environment info key-value pairs in a fixed order.
    """
    for k in _ENV_KEYS:
        if k in env:
            print(f"  {k:10} {env[k]}")


async def _run_check() -> bool:
    """跑聚合检测，打印结果，返回是否有失败。

    Run the aggregated checks, print the results, and return whether any check failed.
    """
    report = await run_all()
    env = report.get("environment") or {}
    cfg = report.get("config") or {}
    conns = report.get("connectivity") or []

    print("=" * 56)
    print("  聚合检测 — 环境 / 配置 / LLM·ASR·TTS 连通性")
    print("=" * 56)

    print("环境")
    _print_env(env)

    print("\n配置校验")
    issues = cfg.get("issues") or []
    for issue in issues:
        label = _ISSUE_LABEL.get(issue.get("level"), "[?]")
        print(f"  {label} {issue.get('key')}: {issue.get('message')}")
    if not issues:
        print("  通过（无问题）")

    print("\n连通性")
    failed = not cfg.get("ok", True)
    for c in conns:
        label = _LEVEL_LABEL.get(c.get("status"), "[?]")
        detail = c.get("detail") or ""
        if c.get("latency_ms") is not None:
            detail = f"{detail}（{c['latency_ms']}ms）"
        print(f"  {str(c.get('name', '')):6} {label} {detail}")
        if c.get("status") == "fail":
            failed = True

    print(f"\n{'=' * 56}")
    if failed:
        print("  结果: 存在失败项，请查看 data/agent.log")
    else:
        print("  结果: 全部正常（未配置项已跳过）")
    print(f"{'=' * 56}\n")
    return failed


def cmd_check(args: argparse.Namespace) -> None:
    """聚合检测命令；存在失败项时以退出码 1 结束（供脚本 / start.bat 判断）。

    The aggregated-check command; exits with code 1 when any check failed (for scripts / start.bat).
    """
    failed = asyncio.run(_run_check())
    if failed:
        sys.exit(1)
