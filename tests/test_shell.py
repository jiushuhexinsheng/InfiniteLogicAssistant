# -*- coding: utf-8 -*-
import asyncio
from types import SimpleNamespace

import pytest

from core.execution.shell import run_shell


@pytest.mark.asyncio
async def test_run_shell_echo():
    r = await run_shell("echo hello")
    assert r.returncode == 0
    assert "hello" in r.stdout


@pytest.mark.asyncio
async def test_run_shell_timeout():
    with pytest.raises(TimeoutError):
        await run_shell("ping -n 10 127.0.0.1", timeout=1)


@pytest.mark.asyncio
async def test_run_shell_cancelled_before_start():
    cancel = SimpleNamespace(is_cancelled=True)
    with pytest.raises(asyncio.CancelledError):
        await run_shell("ping -n 5 127.0.0.1", cancel=cancel, timeout=10)


@pytest.mark.asyncio
async def test_run_shell_cwd():
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        r = await run_shell("cd", cwd=d)
        assert r.returncode == 0
