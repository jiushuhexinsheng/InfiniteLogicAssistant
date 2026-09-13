# -*- coding: utf-8 -*-
"""测试基础工具：风险标记、注册、schema、文件读写、shell 执行、取消与系统探测。
Tests basic tools: risk markers, registration, schemas, file read/write, shell execution, cancellation, and system probing.
"""
import asyncio

import pytest

from core.tools import TOOLS


def test_risk_in_meta():
    """测试工具元数据包含正确的风险标记。Tests tool metadata containing the correct risk markers."""
    meta = {m["name"]: m for m in TOOLS.meta()}
    assert meta["write_file"]["risk"] == "write"
    assert meta["run_shell_tool"]["risk"] == "exec"
    assert meta["run_python_tool"]["risk"] == "exec"
    assert meta["system_probe"]["risk"] == "read"


def test_screenshot_is_read_not_exec():
    """截屏只**读屏**、不改系统状态 —— 归 read，否则每次截屏都要确认一次（纯摩擦、无安全收益）。

    2026-09-13 修正：此前误标为 exec。这里钉住分级，避免日后又被改回去。

    Taking a screenshot only **reads** the screen and changes no system state, so it belongs in
    read; classifying it as exec meant a confirmation on every capture — friction with no safety
    benefit. Fixed on 2026-09-13 (it had been mislabelled exec); this pins the classification so it
    cannot silently drift back.
    """
    from core.tools.base import TOOLS

    assert TOOLS.risk("gui_screenshot_tool") == "read"
    # 真正改变系统状态的 GUI 操作仍归 exec
    assert TOOLS.risk("gui_click_tool") == "exec"
    assert TOOLS.risk("gui_type_tool") == "exec"


def test_basic_tools_registered():
    """测试基础工具均已注册到 schema。Tests all basic tools being registered in the schema."""
    names = {s["function"]["name"] for s in TOOLS.schemas()}
    assert {"grep_file", "find_files", "read_file", "write_file", "parse_doc",
            "list_dir", "run_shell_tool", "run_python_tool", "system_probe"} <= names


def test_schemas_do_not_contain_risk():
    """测试 LLM schema 中不含风险字段。Tests the LLM schema not containing the risk field."""
    # risk 不进 LLM schema（避免 provider 拒绝未知字段）
    for s in TOOLS.schemas():
        assert "risk" not in s


@pytest.mark.asyncio
async def test_read_write_file_tools(tmp_path):
    """测试文件读写工具往返一致。Tests the file read/write tools round-tripping consistently."""
    f = tmp_path / "x.txt"
    await TOOLS.acall("write_file", {"path": str(f), "content": "hi"})
    out = await TOOLS.acall("read_file", {"path": str(f)})
    assert out == "hi"


@pytest.mark.asyncio
async def test_run_shell_tool():
    """测试 shell 工具执行命令并返回输出。Tests the shell tool executing a command and returning its output."""
    out = await TOOLS.acall("run_shell_tool", {"command": "echo hi"})
    assert "hi" in out and "exit=0" in out


def test_schema_excludes_service_param_cancel():
    """测试 cancel 作为服务注入参数不出现在 LLM schema 中。Tests cancel, a service-injected parameter, not appearing in the LLM schema."""
    # cancel 是服务注入的取消令牌，不进 LLM schema
    by_name = {s["function"]["name"]: s for s in TOOLS.schemas()}
    params = by_name["run_shell_tool"]["function"]["parameters"]
    assert "cancel" not in params["properties"]
    assert "cancel" not in params.get("required", [])


@pytest.mark.asyncio
async def test_run_shell_tool_cancel_mid_run():
    """测试执行中的长命令被取消令牌终止并抛出 CancelledError。Tests a long-running command being killed by the cancel token, raising CancelledError."""
    # cancel token 贯穿到工具层：执行中的长命令被 kill，抛 CancelledError
    from core.orchestrator.control import CancellationToken

    token = CancellationToken()

    async def cancel_later():
        await asyncio.sleep(0.3)
        token.cancel()

    t = asyncio.ensure_future(cancel_later())
    with pytest.raises(asyncio.CancelledError):
        await TOOLS.acall("run_shell_tool", {"command": "ping -n 8 127.0.0.1"}, cancel=token)
    t.cancel()
    await asyncio.gather(t, return_exceptions=True)


@pytest.mark.asyncio
async def test_system_probe_reads_md():
    """测试系统探测工具返回环境感知快照。Tests the system probe tool returning the environment awareness snapshot."""
    out = await TOOLS.acall("system_probe", {})
    assert "环境感知快照" in out
