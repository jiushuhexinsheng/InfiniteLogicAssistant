# -*- coding: utf-8 -*-
"""Skill 工具 — 列出/执行技能（热加载）

Skill tools — list/run skills (hot-reloaded)
"""
from typing import Any

from core.skills.loader import SkillLoader
from core.tools.base import tool

_loader = SkillLoader()


@tool("列出可用技能", risk="read")
async def list_skills() -> str:
    """列出可用技能。List available skills.

    Returns:
        技能列表字符串；无技能时返回 "暂无技能"。Skill list; "暂无技能" when empty.
    """
    skills = _loader.reload_if_changed()
    if not skills:
        return "暂无技能"
    return "\n".join(f"- {name}: {s.description}" for name, s in skills.items())


@tool("执行技能（params 为参数对象）", risk="exec")
async def run_skill_tool(name: str, params: dict, session: Any | None = None) -> str:
    """执行技能（params 为参数对象）。Run a skill (params is the parameter object).

    Args:
        name: 技能名称。Skill name.
        params: 技能参数。Skill parameters.
        session: 会话对象（由 acall 注入，用于危险技能确认）。Session object (injected by acall, used to confirm dangerous skills).

    Returns:
        技能执行结果。Skill execution result.
    """
    from core.skills.executor import run_skill  # 延迟导入，避免与 core.tools 包循环
    skills = _loader.reload_if_changed()
    skill = skills.get(name)
    if not skill:
        return f"Error: 未知技能 {name}（可用 list_skills 查看）"
    # session 由 acall 注入：危险技能需要经当前会话向操作者确认
    return await run_skill(skill, params, session=session)
