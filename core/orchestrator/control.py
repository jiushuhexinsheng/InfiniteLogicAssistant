# -*- coding: utf-8 -*-
"""停止/中止控制器 — CancellationToken 贯穿执行层与子进程

层级：stop_task(整个任务)/ stop_step(当前步骤) / pause(挂起)。
执行层每个工具调用与子进程（run_shell）都接受同一 token。
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
        self._paused = False

    def stop_task(self) -> None:
        """停止整个任务（含子进程，由各执行点检查 token 并 kill）。"""
        self.token.cancel()

    def stop_step(self) -> None:
        """停止当前步骤（基础实现与全停同效，后续可细化到单步）。"""
        self.token.cancel()

    def pause(self) -> None:
        self._paused = True

    def resume(self) -> None:
        self._paused = False

    @property
    def paused(self) -> bool:
        return self._paused
