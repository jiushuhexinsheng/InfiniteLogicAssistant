# -*- coding: utf-8 -*-
"""Skill 执行器 — 把 args_template（{{param}} 占位）填参后逐步骤调工具"""
import json
from typing import Any

from core.logger import logger
from core.orchestrator.confirm import confirm_if_needed
from core.orchestrator.session import Session
from core.orchestrator.task import Task
from core.skills.loader import Skill
from core.tools.base import TOOLS  # 从 base 导入，避免 core.tools.__init__ 循环


def fill_template(template: dict, params: dict) -> dict:
    """把 args_template 里 {{key}} 替换为 params[key]。"""
    s = json.dumps(template, ensure_ascii=False)
    for k, v in (params or {}).items():
        s = s.replace("{{" + k + "}}", str(v))
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        return template


async def run_skill(skill: Skill, params: dict, session: Session | None = None, cancel: Any | None = None) -> str:
    """执行技能：dangerous 先确认；逐步骤填参调工具。"""
    if skill.dangerous:
        if session is None:
            return f"Error: 技能 {skill.name} 危险且无确认通道"
        ok = await confirm_if_needed(Task("skill", skill.name, risk="exec"),
                                     f"执行技能 {skill.name}：{skill.description}", session)
        if not ok:
            return f"Error: 操作者拒绝执行技能 {skill.name}"
    out: list[str] = []
    for step in skill.steps:
        if cancel is not None and cancel.is_cancelled:
            return "已停止"
        args = fill_template(step.args_template, params)
        result = await TOOLS.acall(step.tool, args)
        out.append(f"[{step.tool}] {result[:500]}")
    return "\n".join(out) or "（技能无步骤）"
