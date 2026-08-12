# -*- coding: utf-8 -*-
"""Shell 进程控制 — 执行命令，支持超时 / 流式 / 可中止（kill 进程树）

`cancel` 参数是鸭子类型（duck-typed）的 CancellationToken：
只需提供 `is_cancelled` 属性（bool）。完整实现见 core/orchestrator/control.py（P0-T10）。
"""
import asyncio
import os
import signal
import subprocess
import time
from dataclasses import dataclass
from typing import Any


@dataclass
class ShellResult:
    returncode: int
    stdout: str
    stderr: str
    duration: float


def kill_tree(pid: int) -> None:
    """强杀进程树（Windows 用 taskkill /T，POSIX 用进程组 kill）。"""
    if not pid:
        return
    if os.name == "nt":
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(pid)], capture_output=True, text=True)
    else:
        try:
            os.killpg(pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass


async def _drain(stream, buf: list[str]) -> None:
    while True:
        line = await stream.readline()
        if not line:
            break
        buf.append(line.decode("utf-8", errors="replace"))


async def run_shell(
    command: str,
    *,
    cwd: str | None = None,
    timeout: float = 30,
    cancel: Any | None = None,
) -> ShellResult:
    """执行命令；超时抛 TimeoutError，取消抛 asyncio.CancelledError（均先 kill 进程树）。"""
    if cancel is not None and cancel.is_cancelled:
        raise asyncio.CancelledError
    start = time.monotonic()
    proc = await asyncio.create_subprocess_shell(
        command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=cwd,
    )
    out_chunks: list[str] = []
    err_chunks: list[str] = []
    t_out = asyncio.ensure_future(_drain(proc.stdout, out_chunks))
    t_err = asyncio.ensure_future(_drain(proc.stderr, err_chunks))
    deadline = time.monotonic() + timeout
    try:
        while True:
            if cancel is not None and cancel.is_cancelled:
                kill_tree(proc.pid)
                proc.kill()
                raise asyncio.CancelledError
            if time.monotonic() > deadline:
                kill_tree(proc.pid)
                proc.kill()
                raise TimeoutError(f"命令超时({timeout:.0f}s): {command[:120]}")
            try:
                ret = await asyncio.wait_for(proc.wait(), timeout=0.1)
                break
            except asyncio.TimeoutError:
                continue
        await t_out
        await t_err
    finally:
        t_out.cancel()
        t_err.cancel()
    return ShellResult(ret, "".join(out_chunks), "".join(err_chunks), time.monotonic() - start)
