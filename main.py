# -*- coding: utf-8 -*-
"""无限逻辑·语音助手 — 主入口（CLI 分派，命令实现在 cli/ 包）

用法:
    python main.py serve     启动 Web 服务（默认命令）
    python main.py check     聚合检测（环境 / 配置 / LLM·ASR·TTS 连通性）

Unlimited Logic voice assistant — main entry point (CLI dispatch; commands implemented in the cli/ package)

Usage:
    python main.py serve     Start the web server (default command)
    python main.py check     Aggregated checks (environment / config / LLM·ASR·TTS connectivity)
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from core.config import ensure_dirs


def main():
    """程序入口：确保目录结构存在，解析 CLI 参数并执行对应命令（默认 serve）。

    Program entry: ensure the directory structure exists, parse CLI arguments, and run the dispatched command (default: serve).
    """
    from cli import build_parser
    ensure_dirs()
    args = build_parser().parse_args()
    if not hasattr(args, "func"):  # 无子命令 → 默认 serve
        args = build_parser().parse_args(["serve"])
    args.func(args)


if __name__ == "__main__":
    main()
