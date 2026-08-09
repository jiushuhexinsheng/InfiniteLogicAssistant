# -*- coding: utf-8 -*-
"""工具装饰器与注册中心 — @tool 自动推导 OpenAI schema（参照 InfiniteLogic src/tools/base.py）

用法:
    @tool("获取当前日期时间")
    def get_datetime() -> str: ...

    TOOLS.schemas()          # → OpenAI tools 数组
    await TOOLS.acall(name, args)  # async 执行；异常转 "Error: ..." 字符串
"""
import asyncio
import inspect
from typing import Any, Callable, get_type_hints

ToolFunc = Callable[..., Any]


class _ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, dict[str, Any]] = {}

    def register(self, name: str, func: ToolFunc, schema: dict[str, Any]) -> None:
        self._tools[name] = {"func": func, "schema": schema}

    def schemas(self) -> list[dict[str, Any]]:
        return [t["schema"] for t in self._tools.values()]

    def has(self, name: str) -> bool:
        return name in self._tools

    def call(self, name: str, args: dict[str, Any]) -> str:
        if name not in self._tools:
            return f"Error: unknown tool '{name}'"
        func = self._tools[name]["func"]
        try:
            if inspect.iscoroutinefunction(func):
                return f"Error: '{name}' is async; use acall()"
            return _to_string(func(**args))
        except Exception as exc:
            return f"Error in {name}: {exc}"

    async def acall(self, name: str, args: dict[str, Any]) -> str:
        if name not in self._tools:
            return f"Error: unknown tool '{name}'"
        func = self._tools[name]["func"]
        try:
            if inspect.iscoroutinefunction(func):
                return _to_string(await func(**args))
            return _to_string(await asyncio.to_thread(lambda: func(**args)))
        except Exception as exc:
            return f"Error in {name}: {exc}"


TOOLS = _ToolRegistry()


def _to_string(value: Any) -> str:
    if isinstance(value, str):
        return value
    return str(value)


def _python_type_to_json(py_type: Any) -> dict[str, Any]:
    mapping = {
        str: {"type": "string"},
        int: {"type": "integer"},
        float: {"type": "number"},
        bool: {"type": "boolean"},
        list: {"type": "array"},
        dict: {"type": "object"},
    }
    return mapping.get(py_type, {"type": "string"})


def _build_schema(func: ToolFunc, description: str) -> dict[str, Any]:
    sig = inspect.signature(func)
    hints = get_type_hints(func)
    properties: dict[str, dict[str, Any]] = {}
    required: list[str] = []
    for name, param in sig.parameters.items():
        if name in ("self", "cls"):
            continue
        prop = _python_type_to_json(hints.get(name, str))
        if param.default is inspect.Parameter.empty:
            required.append(name)
        else:
            prop["default"] = param.default
        properties[name] = prop
    return {
        "type": "function",
        "function": {
            "name": func.__name__,
            "description": description,
            "parameters": {"type": "object", "properties": properties, "required": required},
        },
    }


def tool(description: str | None = None) -> Callable[[ToolFunc], ToolFunc]:
    def decorator(func: ToolFunc) -> ToolFunc:
        desc = description
        if desc is None:
            doc = (func.__doc__ or "").strip()
            desc = doc.splitlines()[0] if doc else func.__name__
        TOOLS.register(func.__name__, func, _build_schema(func, desc))
        return func
    return decorator
