# -*- coding: utf-8 -*-
"""渐进式工具 schema（docs/designs/08 批4）的测试 — 分组降级、tools_describe 与默认行为。
Tests for progressive tool schemas (docs/designs/08 batch 4) — group stubbing,
tools_describe and the default behaviour.
"""
import json

import pytest

from core.tools import TOOLS


def test_default_schemas_full_and_include_new_tools():
    """默认（stub_groups 缺省）= 全量下发，行为与现状一致；tools_describe 已注册。
    Default (stub_groups omitted) = full schemas, today's behaviour; tools_describe
    is registered."""
    schemas = TOOLS.schemas()
    names = {s["function"]["name"] for s in schemas}
    assert "tools_describe" in names and "memory_put" in names
    # 全量：每个 schema 都带 parameters 细节。Full: every schema carries parameters.
    assert all(s["function"].get("parameters", {}).get("properties") is not None for s in schemas)


def test_stub_groups_degrade_only_those_groups():
    """stub_groups 只降级命中组：简介无参数细节 + 标注 describe；core 组不受影响。
    stub_groups degrades only matching groups: no parameter detail + a describe note;
    the core group is untouched."""
    # 造一个 mcp 组的假工具（不走网络）。A fake mcp-group tool (no network).
    from core.tools.base import tool
    import core.tools.base as base_mod

    @tool("假 MCP 工具", risk="exec", group="mcp")
    async def _fake_mcp_tool(query: str) -> str:
        return query

    try:
        full = {s["function"]["name"]: s for s in TOOLS.schemas()}
        assert full["_fake_mcp_tool"]["function"]["parameters"]["properties"]  # 全量有细节。

        stubbed = {s["function"]["name"]: s for s in TOOLS.schemas(stub_groups=["mcp"])}
        m = stubbed["_fake_mcp_tool"]["function"]
        assert m["parameters"] == {"type": "object", "properties": {}}
        assert "tools_describe" in m["description"]
        # core 组仍完整。Core stays full.
        assert stubbed["tools_describe"]["function"]["parameters"]["properties"]
    finally:
        base_mod.TOOLS.unregister("_fake_mcp_tool")


def test_tools_describe_returns_full_schema():
    """tools_describe 按名返回完整 schema（无视 stub 分组）；未注册名容错。
    tools_describe returns full schemas by name (stub groups notwithstanding);
    unknown names are tolerated."""
    from core.tools.describe import tools_describe
    import asyncio

    out = json.loads(asyncio.run(tools_describe(["memory_put", "不存在的工具"])))
    assert "memory_put" in out
    assert out["memory_put"]["function"]["parameters"]["properties"]
    assert "不存在的工具" not in out

    err = json.loads(asyncio.run(tools_describe([])))
    assert "error" in err
