# -*- coding: utf-8 -*-
"""CLI 命令 — argparse 子命令分派（serve / check）"""
import argparse

from cli.check import cmd_check
from cli.serve import cmd_serve


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python main.py",
        description="无限逻辑·语音全控智能体",
    )
    sub = parser.add_subparsers(dest="command", metavar="{serve,check}")
    sub.add_parser("serve", help="启动 Web 服务（前端 + 后端 API）").set_defaults(func=cmd_serve)
    sub.add_parser("check", help="聚合检测：环境 + 配置校验 + LLM/ASR/TTS 连通性").set_defaults(func=cmd_check)
    return parser
