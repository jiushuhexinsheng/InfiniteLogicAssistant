# -*- coding: utf-8 -*-
"""serve 命令 — 启动 Web 服务

The serve command — start the web server."""
import argparse


def cmd_serve(args: argparse.Namespace) -> None:
    """启动 Web 服务（延迟导入 server 模块，避免加载不必要的依赖）。

    Start the web server (imports the server module lazily to avoid loading unnecessary dependencies).
    """
    from server import start_server
    start_server()
