# -*- coding: utf-8 -*-
import asyncio

import pytest

from core.execution.shell import run_shell
from core.orchestrator.control import CancellationToken, StopController


def test_token_cancel():
    t = CancellationToken()
    assert not t.is_cancelled
    t.cancel()
    assert t.is_cancelled
    with pytest.raises(asyncio.CancelledError):
        t.throw_if_cancelled()


def test_stop_controller_flags():
    c = StopController()
    c.stop_task()
    assert c.token.is_cancelled

    c2 = StopController()
    c2.pause()
    assert c2.paused
    c2.resume()
    assert not c2.paused


@pytest.mark.asyncio
async def test_run_shell_mid_run_cancel():
    # 执行中 cancel → 子进程被杀，抛 CancelledError
    token = CancellationToken()

    async def cancel_later():
        await asyncio.sleep(0.3)
        token.cancel()

    t = asyncio.ensure_future(cancel_later())
    with pytest.raises(asyncio.CancelledError):
        await run_shell("ping -n 5 127.0.0.1", cancel=token, timeout=10)
    await t
