# -*- coding: utf-8 -*-
"""serve 命令 — 启动 Web 服务"""
import argparse


def cmd_serve(args: argparse.Namespace) -> None:
    from server import start_server
    start_server()
