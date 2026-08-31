# -*- coding: utf-8 -*-
"""高影响操作确认 — 无沙箱，但 write/exec 先复述方案请操作者确认

确认决策基于「工具实际风险」（TOOLS.risk），而非 LLM 声明的任务风险，
避免任务被误标为 read 时高风险工具无确认执行。
"""
import json

from core.logger import audit
from core.orchestrator.session import Session
from core.orchestrator.task import Task
from core.tools.base import TOOLS  # 从 base 导入，避免 core.tools.__init__ 循环

_CONFIRM_YES = ("确认", "执行", "可以", "是", "同意", "确定", "好")
_CONFIRM_NO = ("取消", "不要", "否", "停下", "拒绝", "算了", "不行")
# 紧跟在确认词前、用于把该词翻转为否定的字（"不是/不执行/不可以/别执行"）
_NEGATIONS = ("不", "别", "没", "无")


def _classify_answer(ans: str) -> bool | None:
    """解析操作者回答 → True=同意 / False=拒绝 / None=模糊。

    否定感知：确认词被紧邻否定字抵消时判为拒绝，避免子串匹配把
    「不是 / 不执行 / 不可以 / 不同意」误判成同意。
    """
    ans = ans.strip()
    if not ans:
        return None
    # 1. 显式否定短语 → 拒绝（优先于确认词，如「不执行」同时含「执行」）
    if any(w in ans for w in _CONFIRM_NO):
        return False
    # 2. 确认词若被紧邻否定字抵消 → 拒绝
    for w in _CONFIRM_YES:
        idx = ans.find(w)
        while idx != -1:
            if idx > 0 and ans[idx - 1] in _NEGATIONS:
                return False
            idx = ans.find(w, idx + 1)
    # 3. 未被抵消的确认词 → 同意
    if any(w in ans for w in _CONFIRM_YES):
        return True
    return None  # 模糊 → 调用方默认拒绝


async def _ask_operator(session: Session, plan: str, risk: str, kind: str) -> bool:
    """向操作者提问并解析回答；无确认通道/模糊回答一律拒绝。"""
    if session.channel is None:
        audit(f"confirm {kind} risk={risk} plan={plan} decision=rejected reason=no_operator")
        return False  # 无人确认（如定时无人值守）→ 默认不执行高风险
    await session.notify(f"需要确认：{plan}")
    ans = (await session.ask(f"确认执行吗？{plan}")).strip()
    decision = _classify_answer(ans)
    if decision is True:
        audit(f"confirm {kind} risk={risk} plan={plan} decision=approved answer={ans!r}")
        return True
    if decision is False:
        audit(f"confirm {kind} risk={risk} plan={plan} decision=rejected answer={ans!r}")
        return False
    audit(f"confirm {kind} risk={risk} plan={plan} decision=rejected answer={ans!r} reason=ambiguous")
    return False  # 模糊回答默认不执行


async def confirm_if_needed(task: Task, plan: str, session: Session) -> bool:
    """任务级确认：risk=read 自动放行；write/exec 需操作者明确确认。"""
    if task.risk == "read":
        return True
    return await _ask_operator(session, plan, task.risk, "task")


async def confirm_tool(session: Session, name: str, args: dict) -> bool:
    """工具级确认：基于工具实际风险（TOOLS.risk）；read 放行，write/exec 需操作者确认。"""
    risk = TOOLS.risk(name)
    if risk == "read":
        return True
    plan = f"调用工具 {name}，参数 {json.dumps(args, ensure_ascii=False)}"
    return await _ask_operator(session, plan, risk, "tool")
