# -*- coding: utf-8 -*-
"""通话模式的文本判定：L0 确定性粗筛 + L1 文本快筛 + L2 云端意图闸门。

Call-mode text judging: L0 deterministic screen + L1 text screen + L2 cloud intent gate.

音频分段、本地/云端转写已经移到流式 WebSocket 会话；这里只保留「已经有文本之后」的
判定，供 `/voice/call/judge` 使用。模块级不 import config —— 配置值由调用方注入，
便于逐条测试。唯一的外部 IO 是 L2 的 LLM 调用。

Audio segmentation and local/cloud transcription now live in the streaming WebSocket
session; this module keeps only the post-transcript judgement used by
`/voice/call/judge`. It imports no config at module level — callers inject the values so
every rule is unit testable. The only external IO is L2's LLM call.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True)
class SegmentMeta:
    """段落判定上下文（前端随段上报 + 后端会话态）。

    Segment context (reported by the frontend per segment + backend session state).
    """

    tab_focused: bool = False
    in_open_window: bool = False
    session_active: bool = True
    tts_active: bool = False
    echo_guard: bool = False


def screen_l0(meta: SegmentMeta, *, duration_s: float, rms: float,
              min_seconds: float, min_rms: float) -> str | None:
    """L0 粗筛：返回丢弃原因，`None` = 放行。检查顺序即优先级（会话 > 回声 > 形态 > 焦点）。

    L0 screen: drop reason or ``None`` to pass. Order is priority (session > echo >
    shape > focus).
    """
    if not meta.session_active:
        return "no_session"
    if meta.tts_active or meta.echo_guard:
        return "echo"
    if duration_s < min_seconds:
        return "too_short"
    if rms < min_rms:
        return "low_rms"
    if not meta.tab_focused and not meta.in_open_window:
        return "unfocused"
    return None


# 语气词/填充词白噪：命中即丢（对 AI 说不会以它们独立成句）。
# Filler words: dropped outright (nobody addresses an assistant with these alone).
_FILLERS = {"嗯", "啊", "呃", "哦", "额", "嗯嗯", "哦哦", "啊啊", "那个", "这个", "呃呃", "呵呵", "哈哈"}


def quick_screen(text: str) -> str | None:
    """L1 文本快筛：返回丢弃原因，`None` = 放行。

    刻意保守：只杀空转写/纯标点/填充词/单字符——「是不是对助手说的」语义判断归 L2，
    L1 越权会误杀正常指令（漏报比误传贵）。

    L1 text screen: drop reason or ``None``. Deliberately conservative — only
    empty/punctuation/filler/single-char. "Is this addressed to the assistant" is L2's
    job; over-reaching here drops real commands (a miss costs more than an extra call).
    """
    t = text.strip().strip("。！？!?，,、 ").strip()
    if not t:
        return "empty"
    if t in _FILLERS:
        return "filler"
    if len(t) < 2:
        return "too_short"
    return None


# ── L2 云端意图闸门（四分类）/ L2 cloud intent gate (four-way) ──
_CALL_TOOL = {
    "type": "function",
    "function": {
        "name": "judge",
        "description": "判断转写文本是否是对语音助手说的",
        "parameters": {
            "type": "object",
            "properties": {
                "verdict": {"type": "string",
                            "enum": ["command", "chitchat", "bystander", "unsure"]},
                "note": {"type": "string", "description": "一句话理由"},
            },
            "required": ["verdict", "note"],
        },
    },
}

_VALID_VERDICTS = ("command", "chitchat", "bystander", "unsure")


async def judge_call_intent(text: str, recent: str, *, relax: bool,
                            llm: Callable | None = None) -> str:
    """L2 意图闸门：四分类判定「是否对助手说」。llm 注入便于测试；失败兜底 unsure。

    L2 addressee gate (four-way). ``llm`` is injectable for tests; any failure falls
    back to "unsure" (a miss that the relax re-run can still rescue).
    """
    try:
        # 裁决 R13：惰性 import + client 构造整段在 try 内——构造路径抛出也静默兜底。
        # logger 置于首位，保证 except 分支必有绑定。
        from core.logger import logger
        from core import config
        from core.llm.client import get_llm_client
        from core.prompts import CALL_GATE_RELAX_NOTE, CALL_GATE_SYSTEM

        call = llm or get_llm_client().retry_stream_chat
        system = CALL_GATE_SYSTEM + (CALL_GATE_RELAX_NOTE if relax else "")
        user = f"转写：{text}"
        if recent:
            user += f"\n最近片段：{recent}"
        messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        async for evt in call(messages, tools=[_CALL_TOOL],
                              temperature=config.settings.agent.structured_temperature):
            if evt["type"] == "done":
                msg = evt["message"]
                tc = (msg.get("tool_calls") or [{}])[0]
                raw = tc.get("function", {}).get("arguments") or "{}"
                import json as _json
                data = _json.loads(raw) if isinstance(raw, str) else raw
                v = data.get("verdict")
                v = v if v in _VALID_VERDICTS else "unsure"
                logger.info("call-gate: {} → {}{}", text[:40], v, " (relax)" if relax else "")
                return v
        return "unsure"
    except Exception as e:
        logger.warning("call-gate 失败兜底 unsure: {}", e)
        return "unsure"
