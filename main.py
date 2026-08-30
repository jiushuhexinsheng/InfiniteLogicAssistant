# -*- coding: utf-8 -*-
"""无限逻辑·语音助手 — 主入口（CLI 分派，命令实现在 cli/ 包）

用法:
    python main.py serve     启动 Web 服务（默认命令）
    python main.py check     聚合检测（环境 / 配置 / LLM·ASR·TTS 连通性）
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from core.config import ensure_dirs


def main():
    from cli import build_parser
    ensure_dirs()
    args = build_parser().parse_args()
    if not hasattr(args, "func"):  # 无子命令 → 默认 serve
        args = build_parser().parse_args(["serve"])
    args.func(args)


if __name__ == "__main__":
    main()
