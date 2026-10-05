# -*- coding: utf-8 -*-
"""通话模式判定漏斗 — L0 确定性粗筛（本级零模型、零云端）。

L0 是纯规则：会话态、回声、能量/时长、焦点/开放窗口。任一命中即给出丢弃原因
（reason 字符串，直接进 audit 行），`None` 表示放行进 L1。本模块不 import config
也不做 IO —— 配置值与依赖全部由调用方注入，便于逐条测试。

Stage 0 of the call-mode judgement funnel (deterministic screen, zero models, zero
cloud). Pure rules: session state, echo, energy/duration, focus/open-window. A hit
returns the drop reason (goes straight into the audit line); ``None`` means proceed
to L1. No config imports, no IO — callers inject everything, so every rule is unit
testable.
"""
from __future__ import annotations

from dataclasses import dataclass


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
