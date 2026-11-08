# -*- coding: utf-8 -*-
"""shell / python 取消与进程树（docs/designs/10 5.4）。

覆盖：取消时临时脚本被清理；POSIX 子进程自建会话；Windows 用 taskkill /T；
真实取消后子进程树消失。

Shell / python cancellation and the process tree (docs/designs/10 5.4): the temp
script is removed on cancellation; POSIX children get their own session; Windows
uses taskkill /T; and a real cancellation leaves no surviving child processes.
"""
import asyncio
import os
import signal
import subprocess
import sys
import tempfile
import time
from types import SimpleNamespace

import pytest

from core.execution import python as python_mod
from core.execution import shell as shell_mod


def test_spawn_kwargs_posix(monkeypatch):
    """POSIX：子进程自成一个会话/进程组，kill_tree 的 killpg 才打得中整棵树。"""
    monkeypatch.setattr(shell_mod.os, "name", "posix")
    assert shell_mod._spawn_kwargs() == {"start_new_session": True}


def test_spawn_kwargs_windows(monkeypatch):
    """Windows：不需要额外 spawn 参数（杀树走 taskkill /T）。"""
    monkeypatch.setattr(shell_mod.os, "name", "nt")
    assert shell_mod._spawn_kwargs() == {}


def test_kill_tree_windows_uses_taskkill_tree(monkeypatch):
    """Windows 杀树必须带 /T（连带子进程），只杀根进程会留下孤儿。"""
    calls = []
    monkeypatch.setattr(shell_mod.os, "name", "nt")
    monkeypatch.setattr(shell_mod.subprocess, "run",
                        lambda argv, **kw: calls.append(argv))
    shell_mod.kill_tree(4321)
    assert calls and calls[0][:2] == ["taskkill", "/T"]
    assert "4321" in calls[0]


def test_kill_tree_posix_uses_killpg(monkeypatch):
    """POSIX 杀树走进程组 killpg。"""
    calls = []
    monkeypatch.setattr(shell_mod.os, "name", "posix")
    monkeypatch.setattr(shell_mod.os, "killpg", lambda pid, sig: calls.append((pid, sig)),
                        raising=False)
    # Windows 的 signal 模块没有 SIGKILL；补一个值只为断言 killpg 收到了它。
    # Windows' signal module lacks SIGKILL; provide a value just to assert it is passed.
    monkeypatch.setattr(shell_mod.signal, "SIGKILL", 9, raising=False)
    shell_mod.kill_tree(4321)
    assert calls == [(4321, 9)]


@pytest.mark.asyncio
async def test_run_python_removes_temp_file_on_cancel(monkeypatch):
    """取消（run_shell 抛 CancelledError）时临时 .py 必须被删除。"""
    names: list[str] = []
    real = tempfile.NamedTemporaryFile

    def capture(*args, **kwargs):
        f = real(*args, **kwargs)
        names.append(f.name)
        return f

    async def fake_shell(cmd, **kwargs):
        raise asyncio.CancelledError

    monkeypatch.setattr(python_mod.tempfile, "NamedTemporaryFile", capture)
    monkeypatch.setattr(python_mod, "run_shell", fake_shell)

    with pytest.raises(asyncio.CancelledError):
        await python_mod.run_python("print(1)")

    assert names and not os.path.exists(names[0])


def _pid_alive(pid: int) -> bool:
    """子进程是否还活着（跨平台）。Whether the child process is still alive."""
    if os.name == "nt":
        out = subprocess.run(["tasklist", "/FI", f"PID eq {pid}"],
                             capture_output=True, text=True).stdout
        return str(pid) in out.split()
    try:
        os.kill(pid, 0)
        return True
    except (ProcessLookupError, PermissionError):
        return False


@pytest.mark.asyncio
async def test_cancel_kills_process_tree(tmp_path):
    """真实取消后，子进程及其孙进程都消失（不是只杀根进程）。"""
    pid_file = tmp_path / "grandchild.pid"
    # 子进程再拉起一个长睡孙进程，把自己的 pid 写盘（取消后拿不到 stdout）。
    code = (
        "import subprocess, sys, time, pathlib\n"
        "g = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(120)'])\n"
        f"pathlib.Path({str(pid_file)!r}).write_text(str(g.pid))\n"
        "time.sleep(120)\n"
    )
    cancel = SimpleNamespace(is_cancelled=False)
    task = asyncio.ensure_future(python_mod.run_python(code, cancel=cancel, timeout=60))
    # 等孙进程起来并写盘。Wait for the grandchild to start and record its pid.
    for _ in range(100):
        if pid_file.exists() and pid_file.read_text().strip():
            break
        await asyncio.sleep(0.1)
    grandchild = int(pid_file.read_text().strip())

    cancel.is_cancelled = True
    with pytest.raises(asyncio.CancelledError):
        await task

    # taskkill /T / killpg 是异步生效的：轮询一小段时间确认进程消失。
    # Tree kills land asynchronously: poll briefly until the pid is gone.
    deadline = time.time() + 5
    while time.time() < deadline and _pid_alive(grandchild):
        await asyncio.sleep(0.1)
    assert not _pid_alive(grandchild), "取消后孙进程仍在运行（进程树没杀干净）"
