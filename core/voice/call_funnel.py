# -*- coding: utf-8 -*-
"""通话模式判定漏斗 — L0 确定性粗筛（零模型、零云端）+ L2 云端意图闸门。

L0 是纯规则：会话态、回声、能量/时长、焦点/开放窗口。任一命中即给出丢弃原因
（reason 字符串，直接进 audit 行），`None` 表示放行进 L1；L1 文本快筛同为纯规则。
模块级不 import config —— 配置值与依赖由调用方注入，便于逐条测试；唯一的 IO 是
逐级决策的 audit 行（``core.logger.audit``）。
本模块有两处云端调用：run_funnel 的 ``cloud_transcribe``（云端精转写）与 L2 的
``judge_call_intent``（意图闸门）。judge 的 config/LLM 仅在函数内取，
``llm`` 可注入假件，任何失败兜底 ``"unsure"``（宁可漏一判，不可断链路）。

Stage 0 of the call-mode judgement funnel (deterministic screen, zero models, zero
cloud). Pure rules: session state, echo, energy/duration, focus/open-window. A hit
returns the drop reason (goes straight into the audit line); ``None`` means proceed
to L1; L1 text screen is pure rules too. The module level imports no config —
callers inject everything, so every rule is unit testable; the only IO is the
per-stage audit line (``core.logger.audit``). This module makes two cloud calls:
``cloud_transcribe`` in ``run_funnel`` (cloud transcription) and L2's
``judge_call_intent`` (the addressee gate). The judge takes config/LLM inside the
function, ``llm`` is injectable for tests, and any failure falls back to ``"unsure"``
(better a missed verdict than a broken pipeline).
"""
from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from core.logger import audit


@dataclass(frozen=True)
class SegmentMeta:
    """段落判定上下文（前端随段上报 + 后端会话态）。Segment context (reported by the
    frontend per segment + backend session state)."""

    tab_focused: bool = False
    in_open_window: bool = False
    session_active: bool = True
    tts_active: bool = False
    echo_guard: bool = False


@dataclass(frozen=True)
class FunnelResult:
    """漏斗判定结果。Funnel verdict.

    verdict: "dropped" | "incomplete" | "chitchat" | "command"
    hit: 仅 command/chitchat 为 True（relax 提升由 L2 层处理）。
    """

    verdict: str
    hit: bool
    stage: str
    text: str = ""
    reason: str = ""


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
    """L1 文本快筛（本地转写之后、上云之前）：返回丢弃原因，`None` = 放行。

    刻意保守：只杀空转写/纯标点/填充词/单字符——「是不是对助手说的」语义判断归 L2，
    L1 越权会误杀正常指令（漏报比误传贵）。

    L1 text screen (after local transcription, before any cloud call): drop reason or
    ``None``. Deliberately conservative — only empty/punctuation/filler/single-char.
    "Is this addressed to the assistant" is L2's job; over-eaching here drops real
    commands (a miss costs more than an extra cloud call).
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


def parse_merged_content(content: str) -> tuple[str, str | None]:
    """解析合并调用的单次输出：JSON（可带 ``` 围栏）→ (text, verdict)；非 JSON → 原文
    当转写、verdict None；verdict 越界也置 None（交回两步补判，不许瞎猜）。

    Parse a merged-call response: JSON (fences allowed) yields ``(text, verdict)``;
    non-JSON becomes the raw transcript with ``verdict=None``; an out-of-range verdict
    is also ``None`` (the two-step path re-judges rather than guess).
    """
    raw = (content or "").strip()
    if not raw:
        return "", None
    candidate = raw
    if candidate.startswith("```"):
        parts = candidate.split("```")
        if len(parts) >= 2:
            inner = parts[1]
            if inner.startswith("json"):
                inner = inner[len("json"):]
            candidate = inner.strip()
    try:
        data = json.loads(candidate)
    except Exception:
        return raw, None
    if not isinstance(data, dict):
        return raw, None
    text = str(data.get("text") or "")
    v = data.get("verdict")
    return text, (v if v in _VALID_VERDICTS else None)


# ── run_funnel：三级漏斗编排 / run_funnel: three-stage orchestration ──


@dataclass(frozen=True)
class FunnelDeps:
    """run_funnel 的全部外部依赖（测试全量注入）。All external deps of run_funnel (fully
    injectable).

    ``judge`` 契约是**位置参数** relax（裁决 R3）：``judge_call_intent`` 本体是
    ``*, relax`` 关键字位，调用方注入时须用包装函数适配，禁止直接塞入本体。
    The ``judge`` contract takes ``relax`` positionally (Ruling R3): adapt
    ``judge_call_intent`` (keyword-only ``relax``) with a wrapper at the injection
    site; never inject the raw function.

    ``merged`` 是 L2 合并调用（单次云端 chat 同时精转写+四分类），relax 同为**位置
    参数**；返回 ``(text, verdict)``，verdict 可为 ``None``（只拿到转写）。``None``
    或抛异常都回落既有两步路径 —— 合并是增量优化，不是替换。
    ``merged`` is the L2 merged call (one cloud chat does ASR + four-way judge in a
    single request), ``relax`` positional as well; returns ``(text, verdict)`` with
    ``verdict=None`` when only the transcript came back. ``None`` or an exception
    falls back to the legacy two-step path — the merge is additive, not a replacement.
    """

    cloud_transcribe: Callable[[bytes], Awaitable[str]]
    judge: Callable[[str, str, bool], Awaitable[str]]
    merged: Callable[[bytes, str, bool], Awaitable[tuple[str, str | None]]] | None = None
    local_transcribe: Callable[[bytes], str] | None = None
    smart_turn: Callable[[bytes], Awaitable[bool]] | None = None
    min_seconds: float = 0.5
    min_rms: float = 0.02
    smart_turn_enabled: bool = False


async def run_funnel(wav: bytes, meta: SegmentMeta, deps: FunnelDeps,
                     recent: str, relax: bool, rms: float, duration_s: float) -> FunnelResult:
    """三级漏斗执行：L0 规则 → L1 本地转写/快筛/轮次 → L2 云端精转 + 意图闸门。

    L1 整级可缺（local_transcribe=None）→ 直上 L2；L2 云转写失败回落本地文本
    （final_text = 云端文本 or 本地文本），judge 本身失败才兜底 ``"unsure"``。
    audit 行：每一级决策都留痕。

    Three-stage funnel. L1 may be absent entirely (local_transcribe=None) → straight to
    L2; a failed cloud transcription falls back to the local transcript
    (``final_text = cloud or local``); only a judge failure itself falls back to
    "unsure". Every stage decision is audited.
    """
    # ── L0 ──
    reason = screen_l0(meta, duration_s=duration_s, rms=rms,
                       min_seconds=deps.min_seconds, min_rms=deps.min_rms)
    if reason is not None:
        audit(f"call-funnel drop stage=l0 reason={reason}")
        return FunnelResult(verdict="dropped", hit=False, stage="l0", reason=reason)

    # ── L1：本地转写（可用才走；不可用整体跳过本级）──
    text = ""
    if deps.local_transcribe is not None:
        text = deps.local_transcribe(wav) or ""
        if text:
            q = quick_screen(text)
            if q is not None:
                audit(f"call-funnel drop stage=l1 reason={q} text={text[:40]!r}")
                return FunnelResult(verdict="dropped", hit=False, stage="l1",
                                    text=text, reason=q)
            if deps.smart_turn_enabled and deps.smart_turn is not None:
                if not await deps.smart_turn(wav):
                    audit(f"call-funnel drop stage=l1 reason=incomplete text={text[:40]!r}")
                    return FunnelResult(verdict="incomplete", hit=False, stage="l1",
                                        text=text, reason="incomplete")

    # ── L2：合并调用优先（一次云端同时转写+判定），三重降级到既有两步 ──
    # 1) merged 给了 verdict → 直接用（不再上传、不再 judge）；
    # 2) 只给了文本 → 该文本已是云端级转写，补判即可（不许二次上传音频）；
    # 3) merged 缺席/失败/空 → 完整两步 cloud_transcribe + judge（现状成本）。
    mtext, mverdict = "", None
    if deps.merged is not None:
        try:
            mtext, mverdict = await deps.merged(wav, recent, relax)  # relax 位置传（R3）
        except Exception:
            mtext, mverdict = "", None
    if mverdict is not None:
        final_text = mtext or text
        verdict = mverdict
    elif mtext:
        final_text = mtext
        verdict = await deps.judge(mtext, recent, relax)  # relax 位置传（R3 契约）
    else:
        # 两步旧路径：云端精转写（审计在注入的 cloud_transcribe 里）+ 意图闸门。
        try:
            cloud_text = await deps.cloud_transcribe(wav)
        except Exception:
            cloud_text = ""
        final_text = cloud_text or text
        verdict = await deps.judge(final_text, recent, relax)  # relax 位置传（R3 契约）
    hit = verdict in ("command", "chitchat") or (relax and verdict == "unsure")
    audit(f"call-funnel verdict={verdict} hit={int(hit)} stage=l2 relax={int(relax)} "
          f"text={final_text[:60]!r}")
    return FunnelResult(verdict=verdict, hit=hit, stage="l2", text=final_text,
                        reason=verdict)
