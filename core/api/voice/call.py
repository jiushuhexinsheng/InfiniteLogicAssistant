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


# ── 可注入的执行件（测试 monkeypatch 这四个名字）──
def _local_transcribe(wav: bytes) -> str:
    from core.voice.local_asr import get_local_asr
    return get_local_asr().transcribe_wav(wav)


async def _cloud_transcribe(wav: bytes) -> str:
    """L2 精转写：按 `voice.asr.mode` 走本地/云端（与 /voice/transcribe 同一分发）。

    漏斗契约要求「链路不断」—— 任何不可用/失败返回空串（`call_funnel.py` 的
    `final_text = cloud_text or text` 自动回落 L1 文本），与旧实现的「云端不可用返回空串」
    一致。审计按 engine 分档：云端上传用 `audio-upload via=`，本地用 `asr-local via=`。

    L2 fine transcription through the shared tri-mode dispatch. The funnel contract is
    "never break the chain": any unavailability/failure returns "" so the funnel falls
    back to the L1 text (same as the old cloud-unavailable behaviour).
    """
    from core.voice import asr_dispatch
    try:
        res = await asr_dispatch.transcribe(wav, via="call-segment")
    except asr_dispatch.AsrUnavailableError as e:
        # 转写通路不可用（local 缺模型 / 云端未配置）：记一笔（**不是**上传），回落 L1 文本。
        logger.warning("call L2 转写不可用（{}），回落 L1 文本", e.code)
        audit(f"asr-local unavailable=1 via=call-segment reason={e.code}")
        return ""
    except Exception as e:
        logger.warning("call L2 转写失败，回落 L1 文本: {}", e)
        return ""
    if res.engine == "local":
        audit(f"asr-local via=call-segment chars={len(res.text)} text={res.text[:80]!r}")
    else:
        tail = " fallback=1" if res.fallback else ""
        audit(f"audio-upload via=call-segment chars={len(res.text)} text={res.text[:80]!r}{tail}")
    return res.text


async def _smart_turn(wav: bytes) -> bool:
    from core.voice.smart_turn import get_smart_turn
    import io as _io
    import wave as _wave
    try:
        with _wave.open(_io.BytesIO(wav), "rb") as w:
            sr, frames = w.getframerate(), w.readframes(w.getnframes())
        return await get_smart_turn().is_complete(frames, sr)
    except Exception:
        return True


async def _judge(text: str, recent: str, relax: bool) -> str:
    from core.voice.call_funnel import judge_call_intent
    return await judge_call_intent(text, recent, relax=relax)


async def _merged(wav: bytes, recent: str, relax: bool) -> tuple[str, str | None]:
    """L2 合并调用：单次 chat_audio 同时云端精转写+四分类。

    任何失败（ASR 不可用/无 chat_audio/网络/解析）返回 ("", None) → 漏斗自动回落
    两步旧路径，链路不断。成功上传恰好打一条 audio-upload 审计（与 _cloud_transcribe
    同口径，绝不双计）。
    """
    import base64 as _b64
    from core.prompts import CALL_GATE_MERGED_JSON, CALL_GATE_RELAX_NOTE, CALL_GATE_SYSTEM
    from core.voice import get_asr
    from core.voice.call_funnel import parse_merged_content
    try:
        asr = get_asr()
        if not asr.available():
            return "", None
        # 网关能力闸门：拒绝 text 部件的网关（小米 ASR：「text prompt is injected by the
        # gateway」，2026-10-11 实测 400）上合并形状先天不可用 —— 不发注定失败的请求，
        # 直接回空让漏斗走两步。
        # Gateway capability gate: gateways that reject text parts (Xiaomi ASR, measured
        # 400 on 2026-10-11) cannot take the merged shape at all — don't send a doomed
        # request; return empty and let the funnel run the two-step path.
        if (getattr(asr, "compat", None) or {}).get("no_text_parts"):
            return "", None
        system = CALL_GATE_SYSTEM + CALL_GATE_MERGED_JSON + (CALL_GATE_RELAX_NOTE if relax else "")
        user = "请处理附带音频。"
        if recent:
            user += f"\n最近片段：{recent}"
        content = await asr.chat_audio(system, user, _b64.b64encode(wav).decode(), "wav")
    except Exception as e:
        # 带上响应体：4xx 的服务端原因（如网关拒 text 部件）只看 status 是猜不出来的。
        # Include the response body: the server-side reason for a 4xx (e.g. the gateway
        # rejecting text parts) is unguessable from the status alone.
        resp = getattr(e, "response", None)
        body = f" | resp: {resp.text[:300]}" if resp is not None else ""
        logger.warning("call merged 调用失败，回落两步: {}{}", e, body)
        return "", None
    text, verdict = parse_merged_content(content)
    if text:
        audit(f"audio-upload via=call-segment chars={len(text)} text={text[:80]!r}")
    return text, verdict


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
        relax = in_open and _session.consecutive_misses >= cfg.relax_after_misses
    recent = "; ".join(_session.recent[-3:]) if _session else ""

    # L2 合并调用是**云端专有**优化（单次 chat 同时精转写+四分类）：local/hybrid 下「本地优先」
    # 与之冲突，一律不接线 → 漏斗自然走两步（本地/云端 L2 都支持），且本地模式下绝不因合并上云。
    # The merged L2 call is a **cloud-only** optimisation; under local/hybrid it conflicts
    # with "local first", so it is never wired up and the funnel runs the two-step path.
    from core.voice.asr_dispatch import resolve_mode
    merged_on = cfg.merge_l2 and resolve_mode() == "cloud"

    deps = FunnelDeps(
        cloud_transcribe=_cloud_transcribe,
        judge=_judge,
        merged=_merged if merged_on else None,
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
