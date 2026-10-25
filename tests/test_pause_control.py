# -*- coding: utf-8 -*-
"""暂停控制器：三档语义（safe wait / safe stop / force）。Pause controller modes."""
import asyncio

import pytest

from core.orchestrator.control import PauseController, PauseMode


@pytest.mark.asyncio
async def test_safe_wait_does_not_abort_llm_or_tools():
    """safe wait：只置暂停，不中断 LLM/工具。Safe wait only blocks at boundaries."""
    p = PauseController()
    p.pause(PauseMode.SAFE_WAIT)
    assert p.paused is True
    assert p.abort_llm is False
    assert p.abort_tools is False


@pytest.mark.asyncio
async def test_safe_stop_aborts_llm_but_not_tools():
    """safe stop：中断 LLM，等工具。Safe stop aborts LLM but lets tools finish."""
    p = PauseController()
    p.pause(PauseMode.SAFE_STOP)
    assert p.abort_llm is True
    assert p.abort_tools is False


@pytest.mark.asyncio
async def test_force_aborts_both():
    """force：LLM 与在途工具都中断。Force aborts both."""
    p = PauseController()
    p.pause(PauseMode.FORCE)
    assert p.abort_llm is True
    assert p.abort_tools is True


@pytest.mark.asyncio
async def test_wait_if_paused_blocks_until_resume():
    """暂停时 wait_if_paused 阻塞，resume 后放行。Blocks until resumed."""
    p = PauseController()
    p.pause(PauseMode.SAFE_WAIT)
    task = asyncio.ensure_future(p.wait_if_paused())
    await asyncio.sleep(0.01)
    assert not task.done()
    p.resume()
    await asyncio.wait_for(task, 1.0)
    assert p.paused is False


@pytest.mark.asyncio
async def test_interrupted_tools_are_recorded():
    """force 中断的工具记录在案（恢复时重跑/跳过）。Interrupted tools are recorded."""
    p = PauseController()
    p.pause(PauseMode.FORCE)
    p.record_interrupted("write_file", {"path": "C:/x"}, "write")
    assert p.interrupted_tools == [
        {"tool": "write_file", "args": {"path": "C:/x"}, "risk": "write"},
    ]
    p.resume()
    p.clear_interrupted()
    assert p.interrupted_tools == []
