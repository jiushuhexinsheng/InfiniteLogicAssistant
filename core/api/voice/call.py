# -*- coding: utf-8 -*-
"""通话模式端点 — 会话生命周期 + 段落三级漏斗入口。

每个客户端用自己的 ``call_id`` 隔离会话（多标签页/多客户端互不影响）。没有
``call_id`` 的旧请求回落到空串兼容键，保持旧客户端与既有测试语义。

⚠️ 审计(audit)在本模块命名空间 —— 测试补丁点是 `core.api.voice.call.audit`。

Call-mode endpoints — session lifecycle + the segment funnel entry. Each client owns a
``call_id`` so tabs/clients never share funnel state; requests without one fall back to
the empty legacy key (old clients keep working). NOTE: audit is namespaced to this module
(tests patch `core.api.voice.call.audit`).
"""
import json
import time
import uuid
from dataclasses import dataclass, field

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from core import config
from core.api.schemas import CallSegmentResponse, CallSessionResponse
from core.logger import audit

router = APIRouter()

# 旧客户端（不带 call_id）的兼容键；空串不会与 uuid 冲突。
# Compatibility key for old clients (no call_id); the empty string never collides with a uuid.
_LEGACY_CALL_ID = ""
_MAX_CALL_ID = 128


@dataclass
class _CallSession:
    started_at: float
    last_segment_at: float
    recent: list[str] = field(default_factory=list)
    consecutive_misses: int = 0
    open_until: float = 0.0


_sessions: dict[str, _CallSession] = {}


def reset_session_state() -> None:
    """测试/重载用：清全部通话会话。Test/reload helper: clear every call session."""
    _sessions.clear()


def _ttl() -> float:
    return config.settings.voice.call.session_ttl_s


def _prune_expired() -> None:
    """丢弃超过 TTL 的会话（每次访问时顺手清扫，字典大小有界）。"""
    ttl = _ttl()
    now = time.monotonic()
    for key in [k for k, s in _sessions.items() if now - s.last_segment_at >= ttl]:
        _sessions.pop(key, None)


def _get(call_id: str) -> _CallSession | None:
    _prune_expired()
    return _sessions.get(call_id)


async def _read_params(request: Request) -> tuple[dict | None, bool]:
    """读 JSON body：返回 ``(params, has_body)``；空 body = ``({}, False)``，非法 = ``(None, True)``。

    Read the JSON body: ``(params, has_body)``; empty body = ``({}, False)``, malformed =
    ``(None, True)``.
    """
    raw = await request.body()
    if not raw:
        return {}, False
    try:
        params = json.loads(raw.decode("utf-8"))
    except Exception:
        return None, True
    if not isinstance(params, dict):
        return None, True
    return params, True


def _body_call_id(params: dict) -> str:
    """取 body 里的 call_id（非字符串/空 = 空串，即兼容键）。"""
    value = params.get("call_id")
    return value.strip()[:_MAX_CALL_ID] if isinstance(value, str) else ""


async def _judge(text: str, recent: str, relax: bool) -> str:
    from core.voice.call_funnel import judge_call_intent
    return await judge_call_intent(text, recent, relax=relax)


@router.post("/voice/call/start", response_model=CallSessionResponse)
async def call_start(request: Request):
    """进入通话模式：建立（或替换）本客户端的会话。

    无 body → 旧客户端兼容键；有 body 且带 ``call_id`` → 用该 id；有 body 未带 →
    生成一个并随响应返回（前端保存后用于 judge/stop）。

    Enter call mode: create (or replace) this client's session. No body → the legacy
    key; a body with ``call_id`` → use it; a body without one → generate an id and return
    it (the frontend stores it for judge/stop).
    """
    params, has_body = await _read_params(request)
    if params is None:
        return JSONResponse({"ok": False, "error": "无效 JSON"}, status_code=400)
    if not has_body:
        call_id = _LEGACY_CALL_ID
    else:
        call_id = _body_call_id(params) or uuid.uuid4().hex

    _prune_expired()
    now = time.monotonic()
    _sessions[call_id] = _CallSession(started_at=now, last_segment_at=now)
    audit(f"call-start id={call_id or '-'}")
    return CallSessionResponse(
        open_window_s=config.settings.voice.call.open_window_s,
        call_id=call_id,
    )


@router.post("/voice/call/stop", response_model=CallSessionResponse)
async def call_stop(request: Request):
    """退出通话模式：只关闭本客户端的会话（未知 id 也返回成功）。

    Exit call mode: close this client's session only (an unknown id is a successful no-op).
    """
    params, has_body = await _read_params(request)
    if params is None:
        return JSONResponse({"ok": False, "error": "无效 JSON"}, status_code=400)
    call_id = _body_call_id(params) if has_body else _LEGACY_CALL_ID
    _sessions.pop(call_id, None)
    _prune_expired()
    audit(f"call-stop id={call_id or '-'}")
    return CallSessionResponse(call_id=call_id)


@router.post("/voice/call/judge", response_model=CallSegmentResponse)
async def call_judge(request: Request):
    """通话模式纯文本判定：流式 ASR 已给出文本，只跑 L0 规则 + L1 快筛 + L2 闸门。

    Text-only call judging: streaming ASR already produced the transcript, so this only
    runs the L0 rules, the L1 text screen and the L2 addressee gate. No audio, no ASR,
    no cloud upload — the audio path is the streaming session.

    Args:
        request: JSON body ``{text, duration_ms, rms, tab_focused, in_open_window, call_id?}``.
    """
    try:
        params = json.loads((await request.body()).decode("utf-8"))
    except Exception:
        return JSONResponse({"ok": False, "error": "无效 JSON"}, status_code=400)
    call_id = _body_call_id(params)
    text = str(params.get("text") or "").strip()
    duration_s = float(params.get("duration_ms") or 0) / 1000.0
    rms = float(params.get("rms") if params.get("rms") is not None else 1.0)

    from core.voice.call_funnel import SegmentMeta, quick_screen, screen_l0

    session = _get(call_id)
    meta = SegmentMeta(
        tab_focused=bool(params.get("tab_focused")),
        in_open_window=bool(params.get("in_open_window")),
        session_active=session is not None,
    )
    if session is not None:
        session.last_segment_at = time.monotonic()

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
    if session is not None:
        in_open = meta.in_open_window or time.monotonic() < session.open_until
        relax = in_open and session.consecutive_misses >= cfg.relax_after_misses
        recent = "; ".join(session.recent[-3:])
    verdict = await _judge(text, recent, relax)
    hit = verdict in ("command", "chitchat") or (relax and verdict == "unsure")
    # await 期间会话可能被 stop/过期：只对仍注册着的同一对象落状态。
    # The session may have been stopped/expired during the await: mutate only if the same
    # object is still registered.
    if session is not None and _sessions.get(call_id) is session:
        if hit:
            session.consecutive_misses = 0
            session.open_until = time.monotonic() + cfg.open_window_s
        else:
            session.consecutive_misses += 1
        if hit and text:
            session.recent.append(text)
            session.recent = session.recent[-5:]
    audit(f"call-funnel text verdict={verdict} hit={int(hit)} relax={int(relax)} "
          f"text={text[:60]!r}")
    return CallSegmentResponse(hit=hit, text=text if hit else "", stage="l2", reason=verdict)
