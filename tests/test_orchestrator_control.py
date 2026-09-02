# -*- coding: utf-8 -*-
"""取消令牌、停止控制器与 shell 中途取消的测试。
Tests for the cancellation token, stop controller, and mid-run shell cancellation.
"""
import asyncio

import pytest

from core.execution.shell import run_shell
from core.orchestrator.control import CancellationToken, StopController


def test_token_cancel():
    """取消令牌置位后抛 CancelledError。The cancelled token raises CancelledError."""
    t = CancellationToken()
    assert not t.is_cancelled
    t.cancel()
    assert t.is_cancelled
    with pytest.raises(asyncio.CancelledError):
        t.throw_if_cancelled()


def test_stop_controller_flags():
    """停止控制器会取消其令牌。The stop controller cancels its token."""
    c = StopController()
    c.stop_task()
    assert c.token.is_cancelled


@pytest.mark.asyncio
async def test_run_shell_mid_run_cancel():
    """shell 执行中取消会杀死子进程并抛 CancelledError。Cancelling mid-run kills the child process and raises CancelledError."""
    # 执行中 cancel → 子进程被杀，抛 CancelledError
    token = CancellationToken()

    async def cancel_later():
        await asyncio.sleep(0.3)
        token.cancel()

    t = asyncio.ensure_future(cancel_later())
    with pytest.raises(asyncio.CancelledError):
        await run_shell("ping -n 5 127.0.0.1", cancel=token, timeout=10)
    await t
