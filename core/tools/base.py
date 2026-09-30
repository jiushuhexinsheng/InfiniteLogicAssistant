# -*- coding: utf-8 -*-
"""工具装饰器与注册中心 — @tool 自动推导 OpenAI schema（参照 InfiniteLogic src/tools/base.py）。

Tool decorator and registry — @tool auto-derives the OpenAI schema (mirrors InfiniteLogic src/tools/base.py).

用法 / Usage:
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
        """初始化空工具注册表。Initialize an empty tool registry."""
        self._tools: dict[str, dict[str, Any]] = {}

    def register(self, name: str, func: ToolFunc, schema: dict[str, Any], risk: str = "read",
                 group: str = "core") -> None:
        """注册工具及其 schema、风险等级与分组。Register a tool with its schema, risk level and group.

        Args:
            name: 工具名称。Tool name.
            func: 工具函数。Tool function.
            schema: OpenAI 函数 schema。OpenAI function schema.
            risk: 风险等级（read/write/exec）。Risk level (read/write/exec).
            group: 分组（渐进式 schema 用，docs/designs/08 批4；内置=core、MCP=mcp）。
                Group (for progressive schemas, docs/designs/08 batch 4; built-in = core, MCP = mcp).
        """
        self._tools[name] = {"func": func, "schema": schema, "risk": risk, "group": group}

    def schemas(self, stub_groups: list[str] | None = None) -> list[dict[str, Any]]:
        """返回发给 LLM 的干净 schema 列表（不含 risk）。

        渐进式加载（docs/designs/08 批4）：`stub_groups` 里的组降级为一行简介
        （parameters 置空对象 + 描述标注需先调 tools_describe），其余组完整下发。
        缺省（None/空）= 全量下发，现状零变化。

        Return clean schemas for the LLM (risk omitted). Progressive loading
        (docs/designs/08 batch 4): groups in `stub_groups` degrade to one-line stubs
        (empty parameters + a note to call tools_describe first); all other groups are
        sent in full. Default (None/empty) = full schemas, today's behaviour unchanged.

        Args:
            stub_groups: 降级为简介的分组列表。Groups degraded to stubs.

        Returns:
            OpenAI 函数 schema 列表。List of OpenAI function schemas.
        """
        stub = set(stub_groups or [])
        out: list[dict[str, Any]] = []
        for name, t in self._tools.items():
            schema = t["schema"]
            fn = schema.get("function", {})
            if t.get("group", "core") in stub:
                # 一行简介：无参数细节，提示按需取（tools_describe 是唯一取全量的入口）。
                # One-line stub: no parameter detail; fetch on demand (tools_describe is
                # the only way to the full schema).
                out.append({
                    "type": "function",
                    "function": {
                        "name": name,
                        "description": f"{fn.get('description', name)}"
                                       "（参数 schema 已折叠：先调用 tools_describe 获取后再调用本工具）",
                        "parameters": {"type": "object", "properties": {}},
                    },
                })
            else:
                out.append(schema)
        return out

    def full_schemas(self, names: list[str]) -> dict[str, dict[str, Any]]:
        """按名称取**完整** schema（tools_describe 用，无视 stub 分组）。

        Fetch **full** schemas by name (for tools_describe; stub groups do not apply).

        Args:
            names: 工具名列表。Tool names.

        Returns:
            {name: schema}（未注册的忽略）。{name: schema} (unknown names ignored).
        """
        return {n: self._tools[n]["schema"] for n in names if n in self._tools}

    def meta(self) -> list[dict[str, Any]]:
        """工具元信息（含 risk），供确认层 / 控制台展示。Tool metadata (including risk) for the confirmation layer / console display.

        Returns:
            工具元信息列表（名称 / schema / risk）。List of tool metadata (name / schema / risk).
        """
        return [{"name": n, "schema": t["schema"], "risk": t["risk"]} for n, t in self._tools.items()]

    def risk(self, name: str) -> str:
        """查询工具风险等级，未知工具返回 "read"。Get a tool's risk level; "read" for unknown tools.

        Args:
            name: 工具名称。Tool name.

        Returns:
            风险等级。Risk level.
        """
        t = self._tools.get(name)
        return t["risk"] if t else "read"

    def unregister(self, name: str) -> None:
        """注销指定工具。Unregister a tool by name.

        Args:
            name: 工具名称。Tool name.
        """
        self._tools.pop(name, None)

    def unregister_prefix(self, prefix: str) -> None:
        """注销名称以指定前缀开头的所有工具。Unregister all tools whose names start with the given prefix.

        Args:
            prefix: 名称前缀。Name prefix.
        """
        for n in list(self._tools):
            if n.startswith(prefix):
                self._tools.pop(n, None)

    def has(self, name: str) -> bool:
        """判断工具是否已注册。Check whether a tool is registered.

        Args:
            name: 工具名称。Tool name.

        Returns:
            是否存在。Whether it exists.
        """
        return name in self._tools

    def _audit(self, name: str, args: dict[str, Any], status: str, detail: str = "") -> None:
        """记录一次工具调用的审计日志。Write an audit log entry for a tool call.

        Args:
            name: 工具名称。Tool name.
            args: 调用参数。Call arguments.
            status: 状态（ok/error）。Status (ok/error).
            detail: 附加详情。Extra detail.
        """
        risk = self._tools.get(name, {}).get("risk", "read")
        args_str = json.dumps(args, ensure_ascii=False, default=str)
        audit(f"tool={name} risk={risk} args={args_str} status={status}{detail}")

    @staticmethod
    def _inject_service_params(func: ToolFunc, args: dict[str, Any], **service: Any) -> dict[str, Any]:
        """把服务注入参数（cancel 取消令牌 / session 会话）传给声明了对应形参的工具。

        这些参数不进 LLM schema（_build_schema 已跳过），由调用方在 acall/call 时注入。

        Inject service parameters (cancel token / session) into the tool if it declares matching parameters.
        These parameters are excluded from the LLM schema (skipped by _build_schema) and are injected by the caller in acall/call.

        Args:
            func: 工具函数。Tool function.
            args: 原始调用参数。Original call arguments.
            **service: 服务注入参数。Service parameters to inject.

        Returns:
            合并后的参数字典。Merged argument dict.
        """
        sig = inspect.signature(func)
        merged = dict(args)
        for name, value in service.items():
            if value is not None and name in sig.parameters:
                merged[name] = value
        return merged

    def call(self, name: str, args: dict[str, Any],
             cancel: Any | None = None, session: Any | None = None) -> str:
        """同步执行工具，异常转为 "Error: ..." 字符串。Synchronously call a tool; exceptions become "Error: ..." strings.

        Args:
            name: 工具名称。Tool name.
            args: 调用参数。Call arguments.
            cancel: 取消令牌（可选）。Cancel token (optional).
            session: 会话对象（可选）。Session object (optional).

        Returns:
            工具结果字符串。Tool result string.
        """
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
        """异步执行工具，异常转为 "Error: ..." 字符串。Asynchronously call a tool; exceptions become "Error: ..." strings.

        Args:
            name: 工具名称。Tool name.
            args: 调用参数。Call arguments.
            cancel: 取消令牌（可选）。Cancel token (optional).
            session: 会话对象（可选）。Session object (optional).

        Returns:
            工具结果字符串。Tool result string.
        """
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
    """把任意值转成字符串（字符串原样返回）。Convert any value to a string (strings pass through unchanged).

    Args:
        value: 任意值。Any value.

    Returns:
        字符串表示。String representation.
    """
    if isinstance(value, str):
        return value
    return str(value)


def _python_type_to_json(py_type: Any) -> dict[str, Any]:
    """把 Python 类型映射为 JSON schema 类型，未知类型默认 string。

    Map a Python type to a JSON schema type; unknown types default to string.

    Args:
        py_type: Python 类型。Python type.

    Returns:
        JSON schema 类型定义。JSON schema type definition.
    """
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
    """根据函数签名构建 OpenAI 函数 schema。Build an OpenAI function schema from a function's signature.

    Args:
        func: 工具函数。Tool function.
        description: 工具描述。Tool description.

    Returns:
        OpenAI 函数 schema 字典。OpenAI function schema dict.
    """
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


def tool(description: str | None = None, *, risk: str = "read",
         group: str = "core") -> Callable[[ToolFunc], ToolFunc]:
    """注册工具。risk: "read"(只读) / "write"(写) / "exec"(执行任意命令)。

    risk 不进 LLM schema，通过 TOOLS.risk(name) / TOOLS.meta() 暴露给确认层。
    group 是渐进式 schema 的分组键（docs/designs/08 批4，tools.lazy_groups 按组降级）。

    Register a tool. risk: "read" (read-only) / "write" (write) / "exec" (execute arbitrary
    commands). risk is excluded from the LLM schema and exposed to the confirmation layer
    via TOOLS.risk(name) / TOOLS.meta(). group is the progressive-schema bucket key
    (docs/designs/08 batch 4; tools.lazy_groups demotes whole groups to stubs).

    Args:
        description: 工具描述；缺省时取函数 docstring 首行。Tool description; defaults to the first line of the function docstring.
        risk: 风险等级。Risk level.
        group: 分组（默认 core）。Group (defaults to core).

    Returns:
        装饰器。The decorator.
    """
    def decorator(func: ToolFunc) -> ToolFunc:
        desc = description
        if desc is None:
            doc = (func.__doc__ or "").strip()
            desc = doc.splitlines()[0] if doc else func.__name__
        TOOLS.register(func.__name__, func, _build_schema(func, desc), risk, group=group)
        return func
    return decorator
