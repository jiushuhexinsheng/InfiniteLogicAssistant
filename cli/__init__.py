# -*- coding: utf-8 -*-
"""CLI 命令 — argparse 子命令分派（serve / check）

CLI commands — argparse subcommand dispatch (serve / check)."""
import argparse

from cli.check import cmd_check
from cli.serve import cmd_serve


def build_parser() -> argparse.ArgumentParser:
    """构建 CLI 参数解析器，注册 serve / check 两个子命令。

    Build the CLI argument parser and register the serve / check subcommands.
    """
    parser = argparse.ArgumentParser(
        prog="python main.py",
        description="无限逻辑·语音全控智能体",
    )
    sub = parser.add_subparsers(dest="command", metavar="{serve,check}")
    # 注册 `serve` 子命令，用于启动 Web 服务 (前端和后端 API)
    sub.add_parser("serve", help="启动 Web 服务（前端 + 后端 API）").set_defaults(func=cmd_serve)
    # 注册 `check` 子命令，用于聚合环境、配置校验和各种连通性检测
    sub.add_parser("check", help="聚合检测：环境 + 配置校验 + LLM/ASR/TTS 连通性").set_defaults(func=cmd_check)
    return parser
