# -*- coding: utf-8 -*-
"""Skill 工具 — 列出/执行技能（热加载）"""
from typing import Any

from core.skills.loader import SkillLoader
from core.tools.base import tool

_loader = SkillLoader()


@tool("列出可用技能", risk="read")
async def list_skills() -> str:
    skills = _loader.reload_if_changed()
    if not skills:
        return "暂无技能"
    return "\n".join(f"- {name}: {s.description}" for name, s in skills.items())


@tool("执行技能（params 为参数对象）", risk="exec")
async def run_skill_tool(name: str, params: dict, session: Any | None = None) -> str:
    from core.skills.executor import run_skill  # 延迟导入，避免与 core.tools 包循环
    skills = _loader.reload_if_changed()
    skill = skills.get(name)
    if not skill:
        return f"Error: 未知技能 {name}（可用 list_skills 查看）"
    # session 由 acall 注入：危险技能需要经当前会话向操作者确认
    return await run_skill(skill, params, session=session)
