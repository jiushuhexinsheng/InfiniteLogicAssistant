# -*- coding: utf-8 -*-
import asyncio

import pytest

from core.tools import TOOLS


def test_risk_in_meta():
    meta = {m["name"]: m for m in TOOLS.meta()}
    assert meta["write_file"]["risk"] == "write"
    assert meta["run_shell_tool"]["risk"] == "exec"
    assert meta["run_python_tool"]["risk"] == "exec"
    assert meta["system_probe"]["risk"] == "read"


def test_basic_tools_registered():
    names = {s["function"]["name"] for s in TOOLS.schemas()}
    assert {"grep_file", "find_files", "read_file", "write_file", "parse_doc",
            "list_dir", "run_shell_tool", "run_python_tool", "system_probe"} <= names


def test_schemas_do_not_contain_risk():
    # risk 不进 LLM schema（避免 provider 拒绝未知字段）
    for s in TOOLS.schemas():
        assert "risk" not in s


@pytest.mark.asyncio
async def test_read_write_file_tools(tmp_path):
    f = tmp_path / "x.txt"
    await TOOLS.acall("write_file", {"path": str(f), "content": "hi"})
    out = await TOOLS.acall("read_file", {"path": str(f)})
    assert out == "hi"


@pytest.mark.asyncio
async def test_run_shell_tool():
    out = await TOOLS.acall("run_shell_tool", {"command": "echo hi"})
    assert "hi" in out and "exit=0" in out


def test_schema_excludes_service_param_cancel():
    # cancel 是服务注入的取消令牌，不进 LLM schema
    by_name = {s["function"]["name"]: s for s in TOOLS.schemas()}
    params = by_name["run_shell_tool"]["function"]["parameters"]
    assert "cancel" not in params["properties"]
    assert "cancel" not in params.get("required", [])


@pytest.mark.asyncio
async def test_run_shell_tool_cancel_mid_run():
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
    out = await TOOLS.acall("system_probe", {})
    assert "环境感知快照" in out
