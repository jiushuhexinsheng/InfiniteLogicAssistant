# -*- coding: utf-8 -*-
"""消息块协议 — 对话内容的模块化载体（前后端契约的后端镜像）

一条消息 = 有序块列表；块是唯一事实源，纯文本只是投影（content 镜像 /
旧读路径 / LLM 回喂降级用）。前端镜像定义在 web/src/blocks/types.ts。

块信封（所有块类型公共外壳）：
    {v, id, type, ts, turn_id, agent, meta{tts, collapsed, streaming}, payload}
- turn_id：一次用户话语 → 一次编排运行 → done 为一回合
- agent：main | coordinator | sub:<type>（多智能体归属，先写入后展示）
- meta.tts：skip | summary | full | auto（播报策略，语音是一等消费者）
- 未知块/未知版本一律包装为 unknown 块保留原始 JSON，绝不丢弃

Message Block Protocol — the modular carrier of conversation content (the
backend mirror of the frontend/backend contract). One message = an ordered list
of blocks; blocks are the single source of truth, plain text is only a
projection (for the content mirror / legacy read paths / LLM feed fallback).
The frontend mirror lives in web/src/blocks/types.ts.
"""
from datetime import datetime
from typing import Any
from uuid import uuid4

from pydantic import BaseModel

# ─── 截断口径（唯一三常量，替代散落的 500/200 魔法数）───
# Truncation policy (the only three constants; replace scattered 500/200 magic numbers).

# SSE / 预览用截断长度。Truncation length for SSE / previews.
PREVIEW_LEN = 500
# 入库（tool.payload.output）截断长度；LLM 回喂保持全文。
# Truncation length for persistence (tool.payload.output); LLM feedback stays full.
HISTORY_LEN = 4000

# 块类型常量（type 字段取值；ext:<name> 为扩展块命名空间）。
# Block type constants (values of the type field; ext:<name> is the extension namespace).
BLOCK_THINKING = "thinking"
BLOCK_TOOL = "tool"
BLOCK_TEXT = "text"
BLOCK_CODE = "code"
BLOCK_IMAGE = "image"
BLOCK_FILE = "file"
BLOCK_QUESTION = "question"
BLOCK_ANSWER = "answer"
BLOCK_NOTICE = "notice"
BLOCK_SUMMARY = "summary"
BLOCK_UNKNOWN = "unknown"

# 各类型缺省 meta（生产方可覆盖）：thinking 默认折叠不播，text 默认播报。
# Per-type default meta (producers may override): thinking collapsed & silent,
# text spoken by default.
DEFAULT_META: dict[str, dict[str, Any]] = {
    BLOCK_THINKING: {"tts": "skip", "collapsed": True},
    BLOCK_TOOL: {"tts": "skip", "collapsed": True},
    BLOCK_TEXT: {"tts": "auto", "collapsed": False},
    BLOCK_CODE: {"tts": "skip", "collapsed": False},
    BLOCK_IMAGE: {"tts": "skip", "collapsed": False},
    BLOCK_FILE: {"tts": "skip", "collapsed": False},
    BLOCK_QUESTION: {"tts": "full", "collapsed": False},
    BLOCK_ANSWER: {"tts": "skip", "collapsed": False},
    BLOCK_NOTICE: {"tts": "auto", "collapsed": False},
    BLOCK_SUMMARY: {"tts": "full", "collapsed": False},
    BLOCK_UNKNOWN: {"tts": "skip", "collapsed": True},
}


class Block(BaseModel):
    """块信封（读取侧校验用；生产侧用 make_block() 直接产 dict）。

    Block envelope (for read-side validation; producers use make_block() to emit
    a dict directly).
    """

    v: int = 1
    id: str
    type: str
    ts: str
    turn_id: str = ""
    agent: str = ""
    meta: dict[str, Any] = {}
    payload: dict[str, Any] = {}


def new_block_id() -> str:
    """生成块 ID（blk_ 前缀 + 短 uuid）。Generate a block ID (blk_ prefix + short uuid)."""
    return "blk_" + uuid4().hex[:12]


def new_turn_id() -> str:
    """生成回合 ID（turn_ 前缀 + 短 uuid）。Generate a turn ID (turn_ prefix + short uuid)."""
    return "turn_" + uuid4().hex[:12]


def make_block(type: str, payload: dict[str, Any], *, turn_id: str = "",
               agent: str = "", meta: dict[str, Any] | None = None,
               block_id: str | None = None, ts: str | None = None) -> dict[str, Any]:
    """构造块 dict：合并类型缺省 meta 与调用方 meta。

    Build a block dict: merges the type's default meta with caller meta.

    Args:
        type: 块类型（见 BLOCK_* 常量；ext:<name> 为扩展块）。Block type.
        payload: 块载荷。Block payload.
        turn_id: 所属回合。Owning turn.
        agent: 归属（main / sub:<type>）。Ownership.
        meta: 覆盖用 meta。Meta overrides.
        block_id: 指定块 ID（缺省自动生成）。Explicit block ID.
        ts: 指定时间戳（缺省当前时刻 ISO8601）。Explicit timestamp.

    Returns:
        块 dict。The block dict.
    """
    merged = dict(DEFAULT_META.get(type, {"tts": "skip", "collapsed": False}))
    if meta:
        merged.update(meta)
    return {
        "v": 1,
        "id": block_id or new_block_id(),
        "type": type,
        "ts": ts or datetime.now().isoformat(),
        "turn_id": turn_id,
        "agent": agent,
        "meta": merged,
        "payload": payload,
    }


def text_projection(blocks: list[dict[str, Any]]) -> str:
    """块列表 → 纯文本投影（content 列 / LLM 回喂降级与摘要取用）。

    遵循：text/code 取正文，tool 行 "name: output[:200]"，question "❓ …"，
    answer/notice 取原文；thinking/summary 不进投影（防上下文膨胀）。

    Project blocks to plain text (for the content column / LLM feed fallback and
    summaries). text/code contribute their body; tool becomes a
    "name: output[:200]" line; question becomes "❓ …"; answer/notice contribute
    their text; thinking/summary are excluded (to keep the context compact).
    """
    lines: list[str] = []
    for b in blocks:
        if not isinstance(b, dict):
            continue
        t = b.get("type")
        p = b.get("payload") or {}
        if t == BLOCK_TEXT:
            md = p.get("md") or ""
            if md:
                lines.append(md)
        elif t == BLOCK_CODE:
            code = p.get("code") or ""
            if code:
                lines.append(code)
        elif t == BLOCK_TOOL:
            name = p.get("name") or ""
            out = str(p.get("output") or "")
            lines.append(f"{name}: {out[:200]}")
        elif t == BLOCK_QUESTION:
            q = p.get("question") or ""
            if q:
                lines.append(f"❓ {q}")
        elif t == BLOCK_ANSWER:
            text = p.get("text") or ""
            if text:
                lines.append(text)
        elif t == BLOCK_NOTICE:
            text = p.get("text") or ""
            if text:
                lines.append(text)
        # thinking / summary / image / file / unknown / ext:* 不进镜像
    return "\n".join(lines)
