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
import json
from typing import Any, Callable, get_type_hints

from core.logger import audit

ToolFunc = Callable[..., Any]


class _ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, dict[str, Any]] = {}

    def register(self, name: str, func: ToolFunc, schema: dict[str, Any], risk: str = "read") -> None:
        self._tools[name] = {"func": func, "schema": schema, "risk": risk}

    def schemas(self) -> list[dict[str, Any]]:
        # 发给 LLM 的干净 schema（不含 risk，避免部分 provider 拒绝未知字段）
        return [t["schema"] for t in self._tools.values()]

    def meta(self) -> list[dict[str, Any]]:
        """工具元信息（含 risk），供确认层 / 控制台展示。"""
        return [{"name": n, "schema": t["schema"], "risk": t["risk"]} for n, t in self._tools.items()]

    def risk(self, name: str) -> str:
        t = self._tools.get(name)
        return t["risk"] if t else "read"

    def unregister(self, name: str) -> None:
        self._tools.pop(name, None)

    def unregister_prefix(self, prefix: str) -> None:
        for n in list(self._tools):
            if n.startswith(prefix):
                self._tools.pop(n, None)

    def has(self, name: str) -> bool:
        return name in self._tools

    def _audit(self, name: str, args: dict[str, Any], status: str, detail: str = "") -> None:
        risk = self._tools.get(name, {}).get("risk", "read")
        args_str = json.dumps(args, ensure_ascii=False, default=str)
        audit(f"tool={name} risk={risk} args={args_str} status={status}{detail}")

    @staticmethod
    def _inject_service_params(func: ToolFunc, args: dict[str, Any], **service: Any) -> dict[str, Any]:
        """把服务注入参数（cancel 取消令牌 / session 会话）传给声明了对应形参的工具。

        这些参数不进 LLM schema（_build_schema 已跳过），由调用方在 acall/call 时注入。
        """
        sig = inspect.signature(func)
        merged = dict(args)
        for name, value in service.items():
            if value is not None and name in sig.parameters:
                merged[name] = value
        return merged

    def call(self, name: str, args: dict[str, Any],
             cancel: Any | None = None, session: Any | None = None) -> str:
        if name not in self._tools:
            return f"Error: unknown tool '{name}'"
        func = self._tools[name]["func"]
        call_args = self._inject_service_params(func, args, cancel=cancel, session=session)
        try:
            if inspect.iscoroutinefunction(func):
                return f"Error: '{name}' is async; use acall()"
            result = _to_string(func(**call_args))
            self._audit(name, args, "error" if result.startswith("Error") else "ok")
            return result
        except Exception as exc:
            self._audit(name, args, "error", f" error={exc}")
            return f"Error in {name}: {exc}"

    async def acall(self, name: str, args: dict[str, Any],
                    cancel: Any | None = None, session: Any | None = None) -> str:
        if name not in self._tools:
            return f"Error: unknown tool '{name}'"
        func = self._tools[name]["func"]
        call_args = self._inject_service_params(func, args, cancel=cancel, session=session)
        try:
            if inspect.iscoroutinefunction(func):
                result = _to_string(await func(**call_args))
            else:
                result = _to_string(await asyncio.to_thread(lambda: func(**call_args)))
            self._audit(name, args, "error" if result.startswith("Error") else "ok")
            return result
        except Exception as exc:
            self._audit(name, args, "error", f" error={exc}")
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
        # self/cls 是方法绑定；cancel/session 是服务注入参数，都不进 LLM schema
        if name in ("self", "cls", "cancel", "session"):
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


def tool(description: str | None = None, *, risk: str = "read") -> Callable[[ToolFunc], ToolFunc]:
    """注册工具。risk: "read"(只读) / "write"(写) / "exec"(执行任意命令)。

    risk 不进 LLM schema，通过 TOOLS.risk(name) / TOOLS.meta() 暴露给确认层。
    """
    def decorator(func: ToolFunc) -> ToolFunc:
        desc = description
        if desc is None:
            doc = (func.__doc__ or "").strip()
            desc = doc.splitlines()[0] if doc else func.__name__
        TOOLS.register(func.__name__, func, _build_schema(func, desc), risk)
        return func
    return decorator
