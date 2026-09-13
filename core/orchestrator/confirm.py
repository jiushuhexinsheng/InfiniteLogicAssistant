# -*- coding: utf-8 -*-
"""高影响操作确认 — 无沙箱，但 write/exec 先复述方案请操作者确认

确认决策基于「工具实际风险」（TOOLS.risk），而非 LLM 声明的任务风险，
避免任务被误标为 read 时高风险工具无确认执行。

判定分三层，前两层是确定性的，第三层（自然语言）交 LLM：

1. **结构化选择**：前端对 kind="choice" 的提问按 options 渲染按钮（确认提问即 value 为
   yes/no 的两项，见 CONFIRM_OPTIONS），回传 choice —— 权威来源，非 "yes" 一律拒绝。
2. **自由文本精确相等**：命中同义词表 `_EXACT_YES` / `_EXACT_NO` 即出结论，不调 LLM。
3. **其余自由文本 → LLM 判定**：语音作答（P6）打开了自然语言通道，而「是的，允许本次。」
   「确认执行。」这类说法在精确匹配下会被误拒（实测：连界面按钮上的「允许本次」原样念
   出来都会被拒，因为同义词表里没有它）。第三层就是为这条通道准备的。

**为何第三层曾长期缺席、又为何现在加上**：子串/模糊匹配会把「不执行」「不太确定」误判为
批准，所以最初只做精确匹配。但语音通道开启后，「精确匹配」实际等于「拒绝一切自然表达」，
用户被卡死。折中做法是引入 LLM，但把风险压到最小 —— 见 `_resolve_confirm_llm`：只喂用户
这一句（不带对话上下文）、输出限闭集三态、除明确 approve 外一律拒绝。

**已知取舍**：这等于接受「模型可能判错」。判错的方向已被限定为「不放行」，但理论上仍存在
把真实批准判成拒绝（可用性问题）或把否定判成批准（安全问题）的可能。改动本模块时请连同
`tests/test_orchestrator_confirm.py` 里的否定/犹豫用例一起看。

High-impact operation confirmation — there is no sandbox, so write/exec operations restate the
plan and ask the operator to confirm first. The decision is based on the tools' actual risk
(TOOLS.risk), not the risk declared by the LLM, so a high-risk tool is never executed without
confirmation just because the task was mistakenly labeled as read.

Resolution has three layers, the first two deterministic and the third an LLM: a structured
choice is authoritative and never reaches the LLM; free text matching the synonym lists is
decided deterministically; everything else goes to the LLM. The third layer exists because voice
answering opened a natural-language channel, and exact matching effectively meant "reject every
natural phrasing" — in practice even speaking the UI's own button label ("允许本次") back was
rejected, since the synonym list never contained it. Fuzzy matching stayed out because it
misreads "不执行" / "不太确定" as approval; the LLM stands in for it with the risk contained —
see `_resolve_confirm_llm`. The accepted trade-off is that the model can be wrong; the failure
direction is constrained to "do not execute", but a genuine approval being read as a refusal
(usability) or a negation as approval (safety) remains possible in principle.
"""
import json

from core import config
from core.llm.client import get_llm_client
from core.logger import audit, logger
from core.orchestrator.session import Answer, Session
from core.orchestrator.task import Task
from core.prompts import CONFIRM_RESOLVE_SYSTEM
from core.tools.base import TOOLS  # 从 base 导入，避免 core.tools.__init__ 循环
from core.tools.policy import decide

# 自由文本的同义词表：只做精确相等判定（无子串匹配）。
# 非 UI 调用方（脚本 / API）可用这些字面量作答；前端一律走结构化 choice。
# Free-text synonym lists: exact equality only (no substring matching). Non-UI
# callers (scripts / API) may answer with these literals; the frontend always
# goes through the structured choice.
_EXACT_YES = {"确认", "yes", "approve"}
_EXACT_NO = {"取消", "no", "reject"}

# 确认提问的两个固定选项（前端据此渲染按钮）；value 供后端判定，label 供展示与记录。
# label 用「允许本次 / 拒绝」而非「确认 / 取消」：本项目不做 allow-always，
# 文案需表达「这次而已」；value 保持 yes/no，故判定逻辑与既有用例不受影响。
# The two fixed options of a confirmation question (the frontend renders buttons from
# them); value is for the backend decision, label for display and records. The labels
# say "allow once / deny" rather than "confirm / cancel" because there is no
# allow-always here; value stays yes/no so the decision logic is unaffected.
CONFIRM_OPTIONS = [
    {"value": "yes", "label": "允许本次"},
    {"value": "no", "label": "拒绝"},
]


def _resolve_confirm(answer: Answer) -> bool | None:
    """确定性判定：批准的 True / 拒绝的 False / 判不了的 None（交 LLM 层）。

    本函数**只做精确相等**，不含任何模糊匹配。分三层：
    - 结构化 choice：权威来源，非 "yes" 一律拒绝，不问 LLM；
    - 自由文本命中同义词表（`_EXACT_YES` / `_EXACT_NO`）：直接给出结论，不问 LLM；
    - 其余：返回 None，由 `_resolve_confirm_llm` 判定（自然语言表达走这条）。

    Deterministic verdict: True for approval, False for rejection, None when it cannot
    tell (handed to the LLM layer). This function does **exact equality only**, never fuzzy
    matching. Three layers: a structured choice is authoritative and never reaches the LLM; free
    text matching the synonym lists is decided here; everything else returns None for
    `_resolve_confirm_llm` (where natural-language phrasings land).

    Args:
        answer: 操作者回答。The operator's answer.

    Returns:
        True / False，或无法判定时的 None。True / False, or None when undecidable.
    """
    if answer.choice is not None:
        return answer.choice == "yes"
    text = answer.text.strip()
    if text in _EXACT_NO:
        return False
    if text in _EXACT_YES:
        return True
    return None


# 判定用的工具：闭集三态。unclear 是「拿不准」，与 reject 分开是为了让提示词与审计
# 都能区分「明确拒绝」和「没听懂」—— 但两者在最终判定上都**不放行**。
# The judgment tool: a closed set of three. "unclear" is kept apart from "reject" so both the
# prompt and the audit can tell "explicitly refused" from "did not understand" — though neither
# lets the operation through.
_RESOLVE_TOOL = {
    "type": "function",
    "function": {
        "name": "resolve_confirmation",
        "description": "把操作者对「是否执行」的回答判定为批准 / 拒绝 / 拿不准",
        "parameters": {
            "type": "object",
            "properties": {
                "decision": {"type": "string", "enum": ["approve", "reject", "unclear"]},
                "reason": {"type": "string", "description": "一句话说明判定依据"},
            },
            "required": ["decision"],
        },
    },
}


async def _resolve_confirm_llm(text: str) -> bool:
    """用 LLM 把自然语言答复判定为批准 / 拒绝；**任何不确定或异常一律拒绝**。

    ⚠️ 这是本方案引入的权衡：确认闸门之后是任意命令执行（本项目无沙箱），把它交给模型
    判定，等于接受「模型可能判错」这一风险。为把风险压到最小，本函数：
    - 只把**用户这一句**喂给模型（见 `CONFIRM_RESOLVE_SYSTEM`），不带对话上下文 ——
      上下文里有工具输出/文件内容/网页正文等攻击者可控文本，一旦带入就能助推提示注入；
    - 让模型只输出闭集三态（approve / reject / unclear），不给自由文本留余地；
    - 除明确的 approve 外，其余一切（reject / unclear / 闭集外的值 / 没有工具调用 /
      抛异常 / 解析失败）都判为拒绝 —— 判不动的方向永远是「不执行」。

    ⚠️ This is the trade-off this design accepts: arbitrary command execution sits behind this
    gate and there is no sandbox, so delegating the verdict to a model means accepting that the
    model can be wrong. To keep that risk minimal this function: feeds the model **only the
    user's single utterance** (see `CONFIRM_RESOLVE_SYSTEM`) with no conversation context, which
    is where attacker-controllable text lives; constrains the output to a closed three-value set;
    and rejects everything except an explicit approve — reject, unclear, out-of-set values, a
    missing tool call, an exception, a parse failure. When it cannot tell, it does not execute.

    Args:
        text: 操作者的自由文本答复。The operator's free-text answer.

    Returns:
        是否批准。Whether the operation is approved.
    """
    messages = [
        {"role": "system", "content": CONFIRM_RESOLVE_SYSTEM},
        # 只放用户这一句，不放任何对话历史 —— 见上面关于注入面的说明。
        # Only the utterance; no conversation history (see the injection-surface note above).
        {"role": "user", "content": text},
    ]
    try:
        async for evt in get_llm_client().retry_stream_chat(
            messages, tools=[_RESOLVE_TOOL], temperature=config.settings.agent.structured_temperature,
        ):
            if evt["type"] == "done":
                msg = evt["message"] or {}
                tc = (msg.get("tool_calls") or [{}])[0]
                raw = tc.get("function", {}).get("arguments") or "{}"
                data = json.loads(raw) if isinstance(raw, str) else raw
                decision = data.get("decision")
                logger.info("confirm_llm: {!r} → {}", text, decision)
                return decision == "approve"
        logger.warning("confirm_llm 无工具调用，判为拒绝: {!r}", text)
    except Exception as e:
        logger.warning("confirm_llm 异常，判为拒绝: {!r} — {}", text, e)
    return False


async def _ask_operator(session: Session, plan: str, risk: str, kind: str, source: str = "") -> bool:
    """向操作者提问并解析回答；无确认通道/无法识别一律拒绝。

    source 说明本次判定的依据（形如 rule:run_* / tier:exec / default），仅用于审计，
    使日志能回答「为什么这个工具被问了 / 没被问」。

    Asks the operator and parses the answer; rejects by default when there is no
    confirmation channel or the answer is unrecognizable. source records why the
    decision was made (e.g. rule:run_* / tier:exec / default) for the audit log only.
    """
    if session.channel is None:
        audit(f"confirm {kind} risk={risk} plan={plan} decision=rejected reason=no_operator source={source}")
        return False  # 无人确认（如定时无人值守）→ 默认不执行高风险
    await session.notify(f"需要确认：{plan}")
    answer = await session.ask(f"确认执行吗？{plan}", kind="choice", options=CONFIRM_OPTIONS)
    verdict = _resolve_confirm(answer)
    # 确定性层给不出结论时（自然语言答复）才调 LLM —— 精确字面量与结构化选择都不调。
    # The LLM is consulted only when the deterministic layer cannot decide (natural-language
    # answers); exact literals and structured choices never reach it.
    if verdict is None:
        verdict = await _resolve_confirm_llm(answer.text)
        by = "llm"
    else:
        by = "choice" if answer.choice is not None else "exact"
    audit(
        f"confirm {kind} risk={risk} plan={plan} "
        f"decision={'approved' if verdict else 'rejected'}"
        f" answer={answer.text!r} choice={answer.choice!r} by={by} source={source}"
    )
    return verdict


async def confirm_if_needed(task: Task, plan: str, session: Session) -> bool:
    """任务级确认：risk=read 自动放行；write/exec 需操作者明确确认。

    Task-level confirmation: risk=read passes automatically; write/exec requires
    explicit operator confirmation.
    """
    if task.risk == "read":
        return True
    return await _ask_operator(session, plan, task.risk, "task")


async def confirm_tool(session: Session, name: str, args: dict) -> bool:
    """工具级确认：由权限策略决定放行 / 询问 / 拒绝。

    策略默认值等价于改造前的行为（read 免询问、write/exec 询问），可在设置页调整。

    Tool-level confirmation: the permission policy decides allow / ask / deny. Its
    defaults match the pre-change behaviour (read auto-allowed, write/exec asked) and
    are configurable in the settings page.
    """
    decision = decide(name)
    if decision.action == "allow":
        return True
    if decision.action == "deny":
        audit(f"tools policy denied name={name} source={decision.source}")
        return False
    plan = f"调用工具 {name}，参数 {json.dumps(args, ensure_ascii=False)}"
    return await _ask_operator(session, plan, TOOLS.risk(name), "tool", source=decision.source)
