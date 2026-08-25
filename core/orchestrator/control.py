# -*- coding: utf-8 -*-
"""停止/中止控制器 — CancellationToken 贯穿执行层与子进程

stop_task(整个任务)：cancel 同一 token，执行层每个工具调用与子进程（run_shell）都检查并中止。
"""
import asyncio


class CancellationToken:
    def __init__(self) -> None:
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    @property
    def is_cancelled(self) -> bool:
        return self._cancelled

    def throw_if_cancelled(self) -> None:
        if self._cancelled:
            raise asyncio.CancelledError


class StopController:
    def __init__(self) -> None:
        self.token = CancellationToken()

    def stop_task(self) -> None:
        """停止整个任务（含子进程，由各执行点检查 token 并 kill）。"""
        self.token.cancel()
