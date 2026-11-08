# -*- coding: utf-8 -*-
"""Shell 进程控制 — 执行命令，支持超时 / 流式 / 可中止（kill 进程树）。Shell process control — run commands with timeout / streaming / cancellation (kills the process tree).

`cancel` 参数是鸭子类型（duck-typed）的 CancellationToken：
The `cancel` argument is a duck-typed CancellationToken:
只需提供 `is_cancelled` 属性（bool）。完整实现见 core/orchestrator/control.py（P0-T10）。
it only needs an `is_cancelled` attribute (bool). Full implementation in core/orchestrator/control.py (P0-T10).
"""
import asyncio
import locale
import os
import signal
import subprocess
import time
from dataclasses import dataclass
from typing import Any

from core import config
from core.execution.env import subprocess_env


@dataclass
class ShellResult:
    """一次命令执行的完整结果。The complete result of a single command execution."""

    returncode: int
    stdout: str
    stderr: str
    duration: float


def _spawn_kwargs() -> dict[str, Any]:
    """平台相关的子进程 spawn 参数。

    POSIX 上让子进程自成一个会话/进程组，kill_tree 的 os.killpg 才真正有效；
    Windows 不需要额外参数（杀树走 taskkill /T）。

    Platform-specific spawn arguments: on POSIX the child gets its own session /
    process group so kill_tree's os.killpg hits the whole tree; Windows needs
    nothing extra (the tree is killed via taskkill /T).
    """
    return {"start_new_session": True} if os.name != "nt" else {}


def _kill_tree_windows(pid: int) -> None:
    """Windows：taskkill /T 杀整棵进程树。Windows: taskkill /T kills the whole tree."""
    subprocess.run(["taskkill", "/T", "/F", "/PID", str(pid)], capture_output=True, text=True)


def _kill_tree_posix(pid: int) -> None:
    """POSIX：进程组 kill（进程不存在/无权限静默 —— 目标已死即达成）。

    POSIX: process-group kill (silently ignore gone/no-permission — a dead target is
    the goal anyway).
    """
    try:
        os.killpg(pid, signal.SIGKILL)  # type: ignore[attr-defined]  # POSIX only
    except (ProcessLookupError, PermissionError):
        pass


def kill_tree(pid: int) -> None:
    """强杀进程树（平台分派：Windows taskkill /T，POSIX 进程组 kill）。

    Force-kill the process tree, dispatched per platform (taskkill /T on Windows,
    process-group kill on POSIX).
    """
    if not pid:
        return
    if os.name == "nt":
        _kill_tree_windows(pid)
    else:
        _kill_tree_posix(pid)


async def _drain(stream, buf: list[bytes], limit: int) -> bool:
    """逐行读取子进程输出到字节缓冲，超过 limit 后继续排空但不再累积。

    Drain a subprocess stream line by line into a byte buffer; after `limit` is
    reached keep draining (so the child never blocks) but stop accumulating.

    Returns:
        是否发生截断。Whether truncation happened.
    """
    total = 0
    truncated = False
    while True:
        line = await stream.readline()
        if not line:
            break
        if total >= limit:
            truncated = True
            continue
        chunk = line[: limit - total]
        buf.append(chunk)
        total += len(chunk)
        if len(chunk) < len(line):
            truncated = True
    return truncated


def _decode_output(raw: bytes) -> str:
    """按 UTF-8 解码，失败回退系统编码（中文 Windows 的 cmd 输出是 cp936）。

    Decode as UTF-8, falling back to the system encoding (cmd.exe output on Chinese
    Windows is cp936)."""
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode(locale.getpreferredencoding(False) or "utf-8", errors="replace")


async def run_shell(
    command: str,
    *,
    cwd: str | None = None,
    timeout: float = 30,
    cancel: Any | None = None,
) -> ShellResult:
    """执行命令；超时抛 TimeoutError，取消抛 asyncio.CancelledError（均先 kill 进程树）。Run a command; raises TimeoutError on timeout and asyncio.CancelledError on cancellation (both kill the process tree first)."""
    if cancel is not None and cancel.is_cancelled:
        raise asyncio.CancelledError
    start = time.monotonic()
    proc = await asyncio.create_subprocess_shell(
        command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=cwd,
        env=subprocess_env(),
        **_spawn_kwargs(),
    )
    out_chunks: list[bytes] = []
    err_chunks: list[bytes] = []
    limit = max(0, int(config.settings.tools.shell_max_output_bytes))
    t_out = asyncio.ensure_future(_drain(proc.stdout, out_chunks, limit))
    t_err = asyncio.ensure_future(_drain(proc.stderr, err_chunks, limit))
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
        out_trunc = await t_out
        err_trunc = await t_err
    except asyncio.CancelledError:
        # 外部取消（runner 收尾 / FORCE 暂停）不会走上面的轮询分支：这里补杀进程树。
        # External cancellation (runner teardown / FORCE pause) never reaches the poll
        # branch, so kill the process tree here before propagating.
        kill_tree(proc.pid)
        try:
            proc.kill()
        except ProcessLookupError:
            pass
        raise
    finally:
        t_out.cancel()
        t_err.cancel()
    stdout = _decode_output(b"".join(out_chunks))
    stderr = _decode_output(b"".join(err_chunks))
    if out_trunc:
        stdout += f"\n[输出已截断，上限 {limit} 字节]"
    if err_trunc:
        stderr += f"\n[输出已截断，上限 {limit} 字节]"
    return ShellResult(ret, stdout, stderr, time.monotonic() - start)
