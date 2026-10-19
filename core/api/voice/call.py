# -*- coding: utf-8 -*-
"""通话模式端点 — 会话生命周期 + 段落三级漏斗入口。

⚠️ 审计(audit)在本模块命名空间 —— 测试补丁点是 `core.api.voice.call.audit`。

Call-mode endpoints — session lifecycle + the segment funnel entry. NOTE: audit is
namespaced to this module (tests patch `core.api.voice.call.audit`).
"""
import json
import time
from dataclasses import dataclass, field

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from core import config
from core.api.schemas import CallSegmentResponse, CallSessionResponse
from core.logger import audit

router = APIRouter()


@dataclass
class _CallSession:
    started_at: float
    last_segment_at: float
    recent: list[str] = field(default_factory=list)
    consecutive_misses: int = 0
    open_until: float = 0.0

_session: _CallSession | None = None


def reset_session_state() -> None:
    """测试/重载用：清会话。Test/reload helper."""
    global _session
    _session = None


def _alive() -> bool:
    return (_session is not None
            and (time.monotonic() - _session.last_segment_at) < config.settings.voice.call.session_ttl_s)


async def _judge(text: str, recent: str, relax: bool) -> str:
    from core.voice.call_funnel import judge_call_intent
    return await judge_call_intent(text, recent, relax=relax)


@router.post("/voice/call/start", response_model=CallSessionResponse)
async def call_start():
    """进入通话模式：建立会话（后续段落才有资格进漏斗）。Enter call mode."""
    global _session
    _session = _CallSession(started_at=time.monotonic(), last_segment_at=time.monotonic())
    audit("call-start")
    return CallSessionResponse(open_window_s=config.settings.voice.call.open_window_s)


@router.post("/voice/call/stop", response_model=CallSessionResponse)
async def call_stop():
    """退出通话模式。Exit call mode."""
    reset_session_state()
    audit("call-stop")
    return CallSessionResponse()


@router.post("/voice/call/judge", response_model=CallSegmentResponse)
async def call_judge(request: Request):
    """通话模式纯文本判定：流式 ASR 已给出文本，只跑 L0 规则 + L1 快筛 + L2 闸门。

    Text-only call judging: streaming ASR already produced the transcript, so this only
    runs the L0 rules, the L1 text screen and the L2 addressee gate. No audio, no ASR,
    no cloud upload — the audio path is the streaming session.

    Args:
        request: JSON body ``{text, duration_ms, rms, tab_focused, in_open_window}``.
    """
    global _session
    try:
        params = json.loads((await request.body()).decode("utf-8"))
    except Exception:
        return JSONResponse({"ok": False, "error": "无效 JSON"}, status_code=400)
    text = str(params.get("text") or "").strip()
    duration_s = float(params.get("duration_ms") or 0) / 1000.0
    rms = float(params.get("rms") if params.get("rms") is not None else 1.0)

    from core.voice.call_funnel import SegmentMeta, quick_screen, screen_l0

    meta = SegmentMeta(
        tab_focused=bool(params.get("tab_focused")),
        in_open_window=bool(params.get("in_open_window")),
        session_active=_alive(),
    )
    if _session is not None and _alive():
        _session.last_segment_at = time.monotonic()

    cfg = config.settings.voice.call
    reason = screen_l0(meta, duration_s=duration_s, rms=rms,
                       min_seconds=cfg.l0_min_seconds, min_rms=cfg.l0_min_rms)
    if reason is not None:
        audit(f"call-funnel text drop stage=l0 reason={reason}")
        return CallSegmentResponse(hit=False, text=text, stage="l0", reason=reason)
    q = quick_screen(text)
    if q is not None:
        audit(f"call-funnel text drop stage=l1 reason={q} text={text[:40]!r}")
        return CallSegmentResponse(hit=False, text=text, stage="l1", reason=q)

    relax = False
    recent = ""
    if _session is not None and _alive():
        in_open = meta.in_open_window or time.monotonic() < _session.open_until
        relax = in_open and _session.consecutive_misses >= cfg.relax_after_misses
        recent = "; ".join(_session.recent[-3:])
    verdict = await _judge(text, recent, relax)
    hit = verdict in ("command", "chitchat") or (relax and verdict == "unsure")
    if _session is not None and _alive() and meta.session_active:
        if hit:
            _session.consecutive_misses = 0
            _session.open_until = time.monotonic() + cfg.open_window_s
        else:
            _session.consecutive_misses += 1
        if hit and text:
            _session.recent.append(text)
            _session.recent = _session.recent[-5:]
    audit(f"call-funnel text verdict={verdict} hit={int(hit)} relax={int(relax)} "
          f"text={text[:60]!r}")
    return CallSegmentResponse(hit=hit, text=text if hit else "", stage="l2", reason=verdict)
