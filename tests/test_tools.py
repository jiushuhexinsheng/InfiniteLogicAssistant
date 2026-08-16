# -*- coding: utf-8 -*-
import pytest

from core.tools import TOOLS
from core.tools.base import tool, _build_schema


@pytest.mark.asyncio
async def test_acall_writes_audit(monkeypatch):
    calls = []
    monkeypatch.setattr("core.tools.base.audit", lambda m: calls.append(m))
    r = await TOOLS.acall("calculate", {"expression": "1+1"})
    assert r == "2"
    assert any(c.startswith("tool=calculate") and "status=ok" in c for c in calls)


@pytest.mark.asyncio
async def test_acall_error_audited(monkeypatch):
    calls = []
    monkeypatch.setattr("core.tools.base.audit", lambda m: calls.append(m))
    r = await TOOLS.acall("calculate", {"expression": "bad("})
    assert r.startswith("Error")
    assert any(c.startswith("tool=calculate") and "status=error" in c for c in calls)


def test_schemas_contain_all_tools():
    names = [s["function"]["name"] for s in TOOLS.schemas()]
    assert {"get_datetime", "calculate", "web_search", "get_weather"} <= set(names)


def test_schema_infers_required_and_type():
    @tool("t")
    def f(x: int, y: str = "a") -> str:
        return f"{x}{y}"

    s = _build_schema(f, "t")
    assert s["function"]["parameters"]["required"] == ["x"]
    assert s["function"]["parameters"]["properties"]["x"]["type"] == "integer"


def test_calculate_safe():
    assert TOOLS.call("calculate", {"expression": "2+3*4"}) == "14"
    assert TOOLS.call("calculate", {"expression": "__import__('os')"}).startswith("Error")


def test_calculate_power():
    assert TOOLS.call("calculate", {"expression": "2**8"}) == "256"


@pytest.mark.asyncio
async def test_acall_async_tool():
    result = await TOOLS.acall("calculate", {"expression": "10-3"})
    assert result == "7"


@pytest.mark.asyncio
async def test_acall_unknown_tool():
    result = await TOOLS.acall("no_such_tool", {})
    assert result.startswith("Error")
