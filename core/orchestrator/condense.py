# -*- coding: utf-8 -*-
"""滚动压缩 — ReAct 历史超阈值时折叠中间段（docs/designs/08 批2，借鉴 OpenHands Condenser）

只动**本轮 LLM 视角**：调用方把压缩后的历史用于下一次 chat 调用，会话持久化
（session.messages / history.db）不受影响。方向 fail-open —— LLM 摘要失败就原样返回，
压缩坏了最多是「没压缩」，绝不丢任务。

Rolling condenser — fold the middle of a ReAct history once it exceeds the
threshold (docs/designs/08 batch 2, inspired by OpenHands' Condenser). Only the
**LLM's view of this turn** changes: callers feed the condensed history to the next
chat call; the persisted session (session.messages / history.db) is untouched.
Fail-open by design — an LLM summarization failure returns the input unchanged, so
a broken condenser degrades to "no condensation", never to lost work.
"""
from core.llm.client import get_llm_client
from core.logger import logger

# 头部保留条数（system + 任务描述）。Head kept (system + task description).
KEEP_HEAD = 2
# 尾部保留条数（最近的工具往返/对话）。Tail kept (the most recent tool exchanges).
KEEP_TAIL = 6
# 摘要 prompt。Summary prompt.
_CONDENSE_SYSTEM = (
    "把下面的执行历史压缩成一段中文摘要：保留已确认的关键结论、尚未完成的目标、"
    "关键参数与失败原因；省略过程性细节。只输出摘要本身，不要客套。"
)


def _transcript(messages: list[dict]) -> str:
    """把待压段落转成给摘要 LLM 的可读转写（每条限幅，防转写本身爆量）。

    Render the to-be-folded span into a readable transcript for the summarizer
    (per-message caps, so the transcript itself cannot blow up).

    Args:
        messages: 中间段消息。The middle-span messages.

    Returns:
        转写文本。Transcript text.
    """
    lines: list[str] = []
    for m in messages:
        role = m.get("role", "?")
        content = str(m.get("content") or "")[:500]
        tcs = m.get("tool_calls") or []
        for tc in tcs:
            fn = (tc.get("function") or {})
            lines.append(f"[{role}] 调用 {fn.get('name', '?')}({str(fn.get('arguments', ''))[:200]})")
        if role == "tool":
            lines.append(f"[tool] 结果: {content}")
        elif content:
            lines.append(f"[{role}] {content}")
    return "\n".join(lines)


async def maybe_condense(history: list[dict], *, threshold_chars: int
                          ) -> tuple[list[dict], int]:
    """超阈值就把中间段折叠为一条摘要；返回 (LLM 视角的新历史, 省略条数)。

    结构安全（docs/designs/08 批2 的坑）：
    - 头 = 前 2 条（system + 任务），尾 = 最近 6 条；
    - 尾部开头若是 `role="tool"`（其请求已被压掉的孤儿结果），并入被压段一并丢弃 ——
      否则 OpenAI 兼容端点会因 tool 消息无前置 tool_calls 报 400；
    - 压缩产物是一条纯文本 assistant 消息，无悬空 tool_calls。

    Fold the middle into one summary once over the threshold; returns (the LLM-view
    history, omitted count). Structural safety (the trap in docs/designs/08 batch 2):
    head = first 2 (system + task), tail = last 6; orphan ``role="tool"`` results at
    the start of the tail (their requests were folded away) join the folded span and
    are dropped — otherwise OpenAI-compatible endpoints 400 on tool messages without
    a preceding tool_calls; the product is a plain-text assistant message with no
    dangling tool_calls.

    Args:
        history: 当前 LLM 视角历史（调用方的列表，不原地修改）。Current LLM-view history (caller's list; not mutated in place).
        threshold_chars: 阈值字符数（0=禁用）。Threshold characters (0 = disabled).

    Returns:
        (新历史, 省略条数)。(new history, omitted count).
    """
    if threshold_chars <= 0 or len(history) <= KEEP_HEAD + KEEP_TAIL:
        return history, 0
    total = sum(len(str(m.get("content") or "")) for m in history)
    if total <= threshold_chars:
        return history, 0

    cut = len(history) - KEEP_TAIL
    # 尾段开头**连续的孤儿 tool 结果**划给被压段（连同它们已被压掉的请求一起丢弃）——
    # 方向是向后吃（cut 增大、middle 增长），否则孤儿会留在新尾段开头，OpenAI 兼容
    # 端点因 tool 消息无前置 tool_calls 报 400。至少保留尾段 1 条。
    # Leading orphan tool results at the tail's start join the folded span (dropped
    # along with their already-folded requests) — the direction is forward (cut grows,
    # middle grows); otherwise the orphan stays at the new tail's start and
    # OpenAI-compatible endpoints 400 on a tool message without tool_calls. At least
    # one tail message is kept.
    while cut < len(history) - 1 and history[cut].get("role") == "tool":
        cut += 1
    middle = history[KEEP_HEAD:cut]
    if not middle:
        return history, 0
    head = history[:KEEP_HEAD]
    tail = history[cut:]

    try:
        messages = [
            {"role": "system", "content": _CONDENSE_SYSTEM},
            {"role": "user", "content": _transcript(middle)},
        ]
        summary = ""
        async for evt in get_llm_client().retry_stream_chat(messages):
            if evt["type"] == "content_delta":
                summary += evt.get("text") or ""
            if evt["type"] == "done":
                summary = str(evt.get("message", {}).get("content") or summary)
                break
        summary = summary.strip()
        if not summary:
            raise ValueError("空摘要")
    except Exception as e:
        logger.warning("condense 摘要失败，保持原历史: {}", e)
        return history, 0

    folded = [{"role": "assistant", "content": f"[上下文压缩] {summary}"}]
    return head + folded + tail, len(middle)
