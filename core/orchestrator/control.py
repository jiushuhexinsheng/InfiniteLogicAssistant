# -*- coding: utf-8 -*-
"""停止/中止控制器 — CancellationToken 贯穿执行层与子进程

stop_task(整个任务)：cancel 同一 token，执行层每个工具调用与子进程（run_shell）都检查并中止。

Stop/abort controller — a CancellationToken threaded through the execution layer
and child processes. stop_task (the whole task) cancels the same token; every
tool call and child process (run_shell) in the execution layer checks it and aborts.
"""
import asyncio


class CancellationToken:
    """取消令牌：cancel() 置位取消标志，执行点检查 is_cancelled / throw_if_cancelled 中止。

    Cancellation token: cancel() sets the cancellation flag; execution points
    check is_cancelled / throw_if_cancelled to abort.
    """

    def __init__(self) -> None:
        """初始化取消令牌（初始为未取消状态）。

        Initialize the cancellation token (initially not cancelled).
        """
        self._cancelled = False

    def cancel(self) -> None:
        """请求取消（置位取消标志）。Request cancellation (set the cancellation flag)."""
        self._cancelled = True

    @property
    def is_cancelled(self) -> bool:
        """是否已请求取消。Whether cancellation has been requested."""
        return self._cancelled

    def throw_if_cancelled(self) -> None:
        """已取消时抛出 asyncio.CancelledError，供执行点协作式中止。

        Raise asyncio.CancelledError when cancelled, enabling cooperative
        cancellation at execution points.
        """
        if self._cancelled:
            raise asyncio.CancelledError


class StopController:
    """停止控制器：持有唯一 token，stop_task() 取消整个任务（含子进程）。

    Stop controller: holds the single token; stop_task() cancels the whole task,
    including child processes.
    """

    def __init__(self) -> None:
        """初始化控制器并创建取消令牌。Initialize the controller and create the cancellation token."""
        self.token = CancellationToken()

    def stop_task(self) -> None:
        """停止整个任务（含子进程，由各执行点检查 token 并 kill）。

        Stop the entire task (including child processes; each execution point
        checks the token and kills as needed).
        """
        self.token.cancel()
