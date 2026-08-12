# -*- coding: utf-8 -*-
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


@pytest.mark.asyncio
async def test_system_probe_reads_md():
    out = await TOOLS.acall("system_probe", {})
    assert "环境感知快照" in out
