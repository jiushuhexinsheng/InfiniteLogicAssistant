# -*- coding: utf-8 -*-
"""高影响操作确认 — 无沙箱，但 write/exec 先复述方案请操作者确认"""
from core.orchestrator.session import Session
from core.orchestrator.task import Task

_CONFIRM_YES = ("确认", "执行", "可以", "是", "同意", "确定", "好")
_CONFIRM_NO = ("取消", "不要", "否", "停下", "不执行", "拒绝")


async def confirm_if_needed(task: Task, plan: str, session: Session) -> bool:
    """risk=read 自动放行；write/exec 需操作者明确确认；无可确认对象时拒绝。"""
    if task.risk == "read":
        return True
    if session.channel is None:
        return False  # 无人确认（如定时无人值守）→ 默认不执行高风险
    await session.notify(f"需要确认：{plan}")
    ans = (await session.ask(f"确认执行吗？{plan}")).strip()
    if any(w in ans for w in _CONFIRM_YES):
        return True
    if any(w in ans for w in _CONFIRM_NO):
        return False
    return False  # 模糊回答默认不执行
