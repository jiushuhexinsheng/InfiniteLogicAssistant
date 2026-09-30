# -*- coding: utf-8 -*-
"""元工具 — tools_describe：按名取完整参数 schema（渐进式加载的唯一取全量入口）

渐进式加载（docs/designs/08 批4）把 `tools.lazy_groups` 组的工具降级为一行简介；
模型需要调用某工具却没参数细节时，先调本工具取 schema，再发起真实调用。
`tools_describe` 自身永远完整下发（它在 core 组）。

Meta-tool — tools_describe: fetch full parameter schemas by name (the single entry
point to full schemas under progressive loading). Progressive loading (docs/designs/08
batch 4) demotes tools in `tools.lazy_groups` to one-line stubs; when the model needs
a tool but lacks its parameter detail, it calls this tool first, then the real call.
`tools_describe` itself is always sent in full (it lives in the core group).
"""
import json

from core.tools.base import TOOLS, tool


@tool("查询指定工具的完整参数 schema（工具列表标注「需先 describe」时必先调用本工具）",
      risk="read")
async def tools_describe(names: list[str]) -> str:
    """按名称取工具的完整 OpenAI schema；未注册的名称忽略。

    Fetch full OpenAI schemas for the named tools; unknown names are ignored.

    Args:
        names: 工具名列表（1-20 个）。Tool names (1-20).

    Returns:
        JSON：{name: 完整 schema}；全部未注册时返回错误说明。JSON mapping name →
        full schema, or an error note when nothing matches.
    """
    if not names:
        return json.dumps({"error": "names 为空"}, ensure_ascii=False)
    picked = [str(n) for n in names[:20]]
    found = TOOLS.full_schemas(picked)
    if not found:
        return json.dumps({"error": f"未注册的工具: {picked}"}, ensure_ascii=False)
    return json.dumps(found, ensure_ascii=False)
