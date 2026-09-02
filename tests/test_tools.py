# -*- coding: utf-8 -*-
"""测试工具注册表：调用、审计、schema 推断与计算工具。
Tests the tool registry: invocation, auditing, schema inference, and the calculate tool.
"""
import pytest

from core.tools import TOOLS
from core.tools.base import tool, _build_schema


@pytest.mark.asyncio
async def test_acall_writes_audit(monkeypatch):
    """测试工具成功调用时写入审计日志。Tests an audit log being written on a successful tool call."""
    calls = []
    monkeypatch.setattr("core.tools.base.audit", lambda m: calls.append(m))
    r = await TOOLS.acall("calculate", {"expression": "1+1"})
    assert r == "2"
    assert any(c.startswith("tool=calculate") and "status=ok" in c for c in calls)


@pytest.mark.asyncio
async def test_acall_error_audited(monkeypatch):
    """测试工具调用出错时写入错误审计日志。Tests an error audit log being written when a tool call fails."""
    calls = []
    monkeypatch.setattr("core.tools.base.audit", lambda m: calls.append(m))
    r = await TOOLS.acall("calculate", {"expression": "bad("})
    assert r.startswith("Error")
    assert any(c.startswith("tool=calculate") and "status=error" in c for c in calls)


def test_schemas_contain_all_tools():
    """测试 schema 列表包含全部注册工具。Tests the schema list containing all registered tools."""
    names = [s["function"]["name"] for s in TOOLS.schemas()]
    assert {"get_datetime", "calculate", "web_search", "get_weather"} <= set(names)


def test_schema_infers_required_and_type():
    """测试 schema 从类型注解推断必填参数与参数类型。Tests the schema inferring required parameters and types from annotations."""
    @tool("t")
    def f(x: int, y: str = "a") -> str:
        return f"{x}{y}"

    s = _build_schema(f, "t")
    assert s["function"]["parameters"]["required"] == ["x"]
    assert s["function"]["parameters"]["properties"]["x"]["type"] == "integer"


def test_calculate_safe():
    """测试计算工具支持安全表达式并拒绝危险代码。Tests the calculate tool supporting safe expressions and rejecting dangerous code."""
    assert TOOLS.call("calculate", {"expression": "2+3*4"}) == "14"
    assert TOOLS.call("calculate", {"expression": "__import__('os')"}).startswith("Error")


def test_calculate_power():
    """测试计算工具支持幂运算。Tests the calculate tool supporting power operations."""
    assert TOOLS.call("calculate", {"expression": "2**8"}) == "256"


@pytest.mark.asyncio
async def test_acall_async_tool():
    """测试异步调用工具返回正确结果。Tests an async tool call returning the correct result."""
    result = await TOOLS.acall("calculate", {"expression": "10-3"})
    assert result == "7"


@pytest.mark.asyncio
async def test_acall_unknown_tool():
    """测试调用未知工具返回错误。Tests calling an unknown tool returning an error."""
    result = await TOOLS.acall("no_such_tool", {})
    assert result.startswith("Error")
