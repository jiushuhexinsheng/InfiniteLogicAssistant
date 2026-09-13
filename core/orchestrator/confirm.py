# -*- coding: utf-8 -*-
"""高影响操作确认 — 无沙箱，但 write/exec 先复述方案请操作者确认

确认决策基于「工具实际风险」（TOOLS.risk），而非 LLM 声明的任务风险，
避免任务被误标为 read 时高风险工具无确认执行。

判定以**结构化选择**为准：前端对 kind="confirm" 的提问渲染「确认 / 取消」按钮，
回传 choice="yes"/"no"。自由文本只接受与同义词表的**精确相等**，绝不做子串匹配
—— 子串匹配会把「不执行」「不太确定」这类否定/犹豫表达误判为批准，而这道确认
是任意命令执行前的唯一闸门，必须 fail closed。

High-impact operation confirmation — there is no sandbox, so write/exec
operations restate the plan and ask the operator to confirm first. The decision
is based on the tools' actual risk (TOOLS.risk), not the risk declared by the
LLM, so a high-risk tool is never executed without confirmation just because the
task was mistakenly labeled as read.

The decision rests on a **structured choice**: for kind="confirm" questions the
frontend renders confirm/cancel buttons and returns choice="yes"/"no". Free text
is accepted only on **exact equality** with a synonym list, never by substring
matching — substring matching misreads negations and hedges such as "不执行" or
"不太确定" as approval, and this confirmation is the only gate before arbitrary
command execution, so it must fail closed.
"""
import json

from core.logger import audit
from core.orchestrator.session import Answer, Session
from core.orchestrator.task import Task
from core.tools.base import TOOLS  # 从 base 导入，避免 core.tools.__init__ 循环

# 自由文本的同义词表：只做精确相等判定（无子串匹配）。
# 非 UI 调用方（脚本 / API）可用这些字面量作答；前端一律走结构化 choice。
# Free-text synonym lists: exact equality only (no substring matching). Non-UI
# callers (scripts / API) may answer with these literals; the frontend always
# goes through the structured choice.
_EXACT_YES = {"确认", "yes", "approve"}
_EXACT_NO = {"取消", "no", "reject"}

# 确认提问的两个固定选项（前端据此渲染按钮）；value 供后端判定，label 供展示与记录。
# The two fixed options of a confirmation question (the frontend renders buttons from
# them); value is for the backend decision, label for display and records.
CONFIRM_OPTIONS = [
    {"value": "yes", "label": "确认"},
    {"value": "no", "label": "取消"},
]


def _resolve_confirm(answer: Answer) -> bool:
    """把操作者回答解析为「批准 / 拒绝」。

    结构化 choice 优先；无 choice 时只认精确匹配的自由文本；其余一律拒绝。

    Resolve the operator's answer into approved / rejected. The structured choice
    wins; without one, only an exact free-text match is accepted; everything else
    is rejected.

    Args:
        answer: 操作者回答。The operator's answer.

    Returns:
        是否批准。Whether the operation is approved.
    """
    if answer.choice is not None:
        return answer.choice == "yes"
    text = answer.text.strip()
    if text in _EXACT_NO:
        return False
    return text in _EXACT_YES


async def _ask_operator(session: Session, plan: str, risk: str, kind: str) -> bool:
    """向操作者提问并解析回答；无确认通道/无法识别一律拒绝。

    Asks the operator and parses the answer; rejects by default when there is no
    confirmation channel or the answer is unrecognizable.
    """
    if session.channel is None:
        audit(f"confirm {kind} risk={risk} plan={plan} decision=rejected reason=no_operator")
        return False  # 无人确认（如定时无人值守）→ 默认不执行高风险
    await session.notify(f"需要确认：{plan}")
    answer = await session.ask(f"确认执行吗？{plan}", kind="choice", options=CONFIRM_OPTIONS)
    approved = _resolve_confirm(answer)
    reason = "" if approved else (" choice" if answer.choice else " text")
    audit(
        f"confirm {kind} risk={risk} plan={plan} "
        f"decision={'approved' if approved else 'rejected'}"
        f" answer={answer.text!r} choice={answer.choice!r}{reason}"
    )
    return approved


async def confirm_if_needed(task: Task, plan: str, session: Session) -> bool:
    """任务级确认：risk=read 自动放行；write/exec 需操作者明确确认。

    Task-level confirmation: risk=read passes automatically; write/exec requires
    explicit operator confirmation.
    """
    if task.risk == "read":
        return True
    return await _ask_operator(session, plan, task.risk, "task")


async def confirm_tool(session: Session, name: str, args: dict) -> bool:
    """工具级确认：基于工具实际风险（TOOLS.risk）；read 放行，write/exec 需操作者确认。

    Tool-level confirmation based on the tool's actual risk (TOOLS.risk); read
    passes through, write/exec requires operator confirmation.
    """
    risk = TOOLS.risk(name)
    if risk == "read":
        return True
    plan = f"调用工具 {name}，参数 {json.dumps(args, ensure_ascii=False)}"
    return await _ask_operator(session, plan, risk, "tool")
