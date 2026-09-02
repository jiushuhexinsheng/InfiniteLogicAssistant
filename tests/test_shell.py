# -*- coding: utf-8 -*-
"""测试 core.execution.shell 模块的 run_shell 函数：正常执行、超时、取消与工作目录切换。
Tests the run_shell function in core.execution.shell: normal execution, timeout, cancellation, and working directory changes.
"""
import asyncio
from types import SimpleNamespace

import pytest

from core.execution.shell import run_shell


@pytest.mark.asyncio
async def test_run_shell_echo():
    """测试 run_shell 正常执行命令并返回输出。Tests run_shell executing a command and returning its output."""
    r = await run_shell("echo hello")
    assert r.returncode == 0
    assert "hello" in r.stdout


@pytest.mark.asyncio
async def test_run_shell_timeout():
    """测试 run_shell 超时后抛出 TimeoutError。Tests run_shell raising TimeoutError on timeout."""
    with pytest.raises(TimeoutError):
        await run_shell("ping -n 10 127.0.0.1", timeout=1)


@pytest.mark.asyncio
async def test_run_shell_cancelled_before_start():
    """测试取消标记使 run_shell 在执行前抛出 CancelledError。Tests run_shell raising CancelledError when cancelled before start."""
    cancel = SimpleNamespace(is_cancelled=True)
    with pytest.raises(asyncio.CancelledError):
        await run_shell("ping -n 5 127.0.0.1", cancel=cancel, timeout=10)


@pytest.mark.asyncio
async def test_run_shell_cwd():
    """测试 run_shell 支持在指定工作目录中执行命令。Tests run_shell executing a command in a given working directory."""
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        r = await run_shell("cd", cwd=d)
        assert r.returncode == 0
