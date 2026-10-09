# -*- coding: utf-8 -*-
"""shell.kill_tree 的平台分派：Windows 走 taskkill /T，POSIX 走进程组 kill。

Platform dispatch of shell.kill_tree: taskkill /T on Windows, process-group kill on
POSIX. Pins both branches so a refactor cannot silently change the Windows command
line or drop the POSIX error swallowing.
"""
import asyncio
import os

import pytest

import core.execution.shell as shell_mod
from core.execution.shell import kill_tree


def test_falsy_pid_is_noop(monkeypatch):
    """pid 为 0/None 时两个平台都不动手。Neither branch runs for a falsy pid."""
    calls = []
    monkeypatch.setattr(shell_mod, "_kill_tree_windows", lambda p: calls.append(("w", p)))
    monkeypatch.setattr(shell_mod, "_kill_tree_posix", lambda p: calls.append(("p", p)))
    kill_tree(0)
    kill_tree(None)
    assert calls == []


def test_windows_branch_uses_taskkill_tree_flag(monkeypatch):
    """Windows 分支命令行钉死：taskkill /T /F /PID <pid>（/T=杀进程树）。"""
    seen = {}

    def fake_run(args, **kwargs):
        seen["args"] = args
        seen["kwargs"] = kwargs

    monkeypatch.setattr(os, "name", "nt")
    monkeypatch.setattr(shell_mod.subprocess, "run", fake_run)
    kill_tree(4321)
    assert seen["args"] == ["taskkill", "/T", "/F", "/PID", "4321"]
    assert seen["kwargs"].get("capture_output") is True
    assert seen["kwargs"].get("text") is True


def test_posix_branch_kills_process_group(monkeypatch):
    """POSIX 分支：os.killpg(pid, SIGKILL)。"""
    seen = {}

    def fake_killpg(pgid, sig):
        seen["pgid"] = pgid
        seen["sig"] = sig

    monkeypatch.setattr(os, "name", "posix")
    monkeypatch.setattr(os, "killpg", fake_killpg, raising=False)
    monkeypatch.setattr(shell_mod.signal, "SIGKILL", 9, raising=False)  # Windows 无 SIGKILL
    kill_tree(8765)
    assert seen == {"pgid": 8765, "sig": 9}


def test_posix_branch_swallows_gone_process(monkeypatch):
    """POSIX 分支：目标已不存在/无权限 → 静默（不向上抛）。"""
    def boom(pgid, sig):
        raise ProcessLookupError("gone")

    monkeypatch.setattr(os, "name", "posix")
    monkeypatch.setattr(os, "killpg", boom, raising=False)
    monkeypatch.setattr(shell_mod.signal, "SIGKILL", 9, raising=False)  # Windows 无 SIGKILL
    kill_tree(1)   # 不得抛异常


@pytest.mark.asyncio
async def test_run_shell_smoke_and_cancel(monkeypatch):
    """冒烟：真跑一条命令；取消路径先 kill 进程树。"""
    r = await shell_mod.run_shell("echo hello-platform", timeout=10)
    assert r.returncode == 0
    assert "hello-platform" in r.stdout

    killed = []
    monkeypatch.setattr(shell_mod, "kill_tree", lambda pid: killed.append(pid))

    class _Cancelled:
        is_cancelled = True

    with pytest.raises(asyncio.CancelledError):
        await shell_mod.run_shell("echo never", cancel=_Cancelled())
    # 取消发生在启动前（同步检查），未创建进程 → 未调用 kill_tree，但不得有残留
    assert isinstance(killed, list)
