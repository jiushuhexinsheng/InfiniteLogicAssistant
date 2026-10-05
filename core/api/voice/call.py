# -*- coding: utf-8 -*-
"""通话模式端点 — 会话生命周期 + 段落三级漏斗入口。

⚠️ 审计(audit)在本模块命名空间 —— 测试补丁点是 `core.api.voice.call.audit`。

Call-mode endpoints — session lifecycle + the segment funnel entry. NOTE: audit is
namespaced to this module (tests patch `core.api.voice.call.audit`).
"""
import base64
import io
import json
import time
import wave
from dataclasses import dataclass, field

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from core import config
from core.api.schemas import CallSegmentResponse, CallSessionResponse
from core.logger import audit, logger
from core.voice.call_funnel import FunnelDeps, SegmentMeta, run_funnel

router = APIRouter()

_SESSION_TTL_S = 300.0      # 无段落自动过期（防会话泄漏）
_RELAX_AFTER = 2            # 开放窗口内连续 miss 数，达到后复判放宽


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
    return _session is not None and (time.monotonic() - _session.last_segment_at) < _SESSION_TTL_S


# ── 可注入的执行件（测试 monkeypatch 这四个名字）──
def _local_transcribe(wav: bytes) -> str:
    from core.voice.local_asr import get_local_asr
    return get_local_asr().transcribe_wav(wav)


async def _cloud_transcribe(wav: bytes) -> str:
    """云端精转写：与 /voice/transcribe 同通道，逐条记 audio-upload 审计。"""
    from core.voice import get_asr
    import base64 as _b64
    asr = get_asr()
    if not asr.available():
        return ""
    text = await asr.transcribe_base64(_b64.b64encode(wav).decode(), "wav")
    audit(f"audio-upload via=call-segment chars={len(text)} text={text[:80]!r}")
    return text


async def _smart_turn(wav: bytes) -> bool:
    from core.voice.smart_turn import get_smart_turn
    import io as _io, wave as _wave
    try:
        with _wave.open(_io.BytesIO(wav), "rb") as w:
            sr, frames = w.getframerate(), w.readframes(w.getnframes())
        return await get_smart_turn().is_complete(frames, sr)
    except Exception:
        return True


async def _judge(text: str, recent: str, relax: bool) -> str:
    from core.voice.call_funnel import judge_call_intent
    return await judge_call_intent(text, recent, relax=relax)


def _duration_rms(wav: bytes) -> tuple[float, float]:
    """从 wav 算 (时长秒, 归一化 RMS)。客户端不可信，能量在服务端算。"""
    with wave.open(io.BytesIO(wav), "rb") as w:
        sr, n = w.getframerate(), w.getnframes()
        frames = w.readframes(n)
    import struct
    if not frames:
        return 0.0, 0.0
    samples = struct.unpack(f"<{len(frames) // 2}h", frames)
    rms = (sum(s * s for s in samples) / len(samples)) ** 0.5 / 32768.0
    return (n / sr) if sr else 0.0, rms


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


@router.post("/voice/call/segment", response_model=CallSegmentResponse)
async def call_segment(request: Request):
    """段落进漏斗：L0 规则 → L1 本地 → L2 云端精判；hit 才由前端送编排。

    Segment into the funnel; only a hit is sent to the orchestrator by the frontend.
    """
    global _session
    try:
        params = json.loads((await request.body()).decode("utf-8"))
    except Exception:
        return JSONResponse({"ok": False, "error": "无效 JSON"}, status_code=400)
    b64 = params.get("audio_base64") or ""
    if not b64:
        return JSONResponse({"ok": False, "error": "缺少 audio_base64"}, status_code=400)
    try:
        wav = base64.b64decode(b64)
        duration_s, rms = _duration_rms(wav)
    except Exception:
        return JSONResponse({"ok": False, "error": "无效音频"}, status_code=400)

    meta = SegmentMeta(
        tab_focused=bool(params.get("tab_focused")),
        in_open_window=bool(params.get("in_open_window")),
        session_active=_alive(),
    )
    if _session is not None and _alive():
        _session.last_segment_at = time.monotonic()

    cfg = config.settings.voice.call
    relax = False
    if _session is not None and _alive():
        # 开放窗口两处来源取或：前端刚播报完（meta.in_open_window，本段上报）或
        # 后端自记的窗口（命中后开的 open_until）。任一成立即算在窗口内，允许 relax 复判放宽。
        in_open = meta.in_open_window or time.monotonic() < _session.open_until
        relax = in_open and _session.consecutive_misses >= _RELAX_AFTER
    recent = "; ".join(_session.recent[-3:]) if _session else ""

    deps = FunnelDeps(
        cloud_transcribe=_cloud_transcribe,
        judge=_judge,
        local_transcribe=_local_transcribe,
        smart_turn=_smart_turn if cfg.smart_turn_enabled else None,
        min_seconds=cfg.l0_min_seconds,
        min_rms=cfg.l0_min_rms,
        smart_turn_enabled=cfg.smart_turn_enabled,
    )
    try:
        result = await run_funnel(wav, meta, deps, recent, relax, rms, duration_s)
    except Exception as e:
        logger.error("call_segment 漏斗异常: {}", e)
        audit("call-funnel error")
        return CallSegmentResponse(hit=False, reason="error")

    # 会话记账：命中清零 miss 并开窗；miss 计数（供 relax 复判）。
    if _session is not None and _alive() and meta.session_active:
        if result.hit:
            _session.consecutive_misses = 0
            _session.open_until = time.monotonic() + cfg.open_window_s
        else:
            _session.consecutive_misses += 1
        if result.text:
            _session.recent.append(result.text)
            _session.recent = _session.recent[-5:]
    return CallSegmentResponse(hit=result.hit, text=result.text,
                               stage=result.stage, reason=result.reason)
