# -*- coding: utf-8 -*-
"""单连接流式会话：PCM 帧 → 本地 VAD → KWS → ASR → partial/final。

Per-connection streaming session: PCM frames → local VAD → KWS → ASR → partial/final.

设计取舍：

- **分段只由本地 VAD 决定**（本项目没有云端 VAD）；VAD 模型缺失时明确报错，
  不偷偷退回旧的浏览器切段链路。
- **本地 ASR** 在说话期间增量解码并推 partial；**云端 ASR** 只在 VAD 段结束时
  上传一次，推 final（不伪造 partial）。
- **唤醒闸门（gate）**：连接上有两种模式 —— ``wake``（等待唤醒词）与 ``open``
  （通话/续聊/作答/指令窗，免唤醒）。``wake`` 模式下 KWS 在**云端上传之前**判定：
  未命中且本地文本也未命中唤醒词时，该段不上云、不出文本，final 带 ``gate="drop"``。
  ``open`` 模式跳过上传闸门，按 ASR 模式正常转写。
- **KWS** 仍是发音级判定；``kws=api`` 退化为转写后的文本拼音判定（不做上传前拦截），
  ``kws=off`` 表示不判唤醒（所有非空文本都当指令）。
- 解码/合成/KWS 都放线程池，绝不阻塞事件循环。

Design:

- **Segmentation is local VAD only** (there is no cloud VAD); a missing VAD model is a
  clear error, never a silent fallback to the legacy browser-segment pipeline.
- **Local ASR** decodes incrementally while speaking and emits partials; **cloud ASR**
  uploads once at the VAD endpoint and emits a final (no fake partials).
- **Wake gate**: a connection is in ``wake`` (waiting for the wake word) or ``open``
  (call mode / follow-up / answering / command window). In ``wake`` mode KWS judges
  **before** any cloud upload: a miss (and no local text hit) drops the segment without
  uploading, and the final carries ``gate="drop"``. ``open`` skips the upload gate.
  ``kws=api`` degrades to post-transcript text judging (no pre-upload gate) and
  ``kws=off`` means "do not judge wake" (every non-empty transcript is a command).
- Decode/synthesis/KWS run in worker threads and never block the event loop.
"""
from __future__ import annotations

import asyncio
import base64
import json
import time
from collections import deque
from typing import Any

import numpy as np

from core import config
from core.logger import audit, logger
from core.voice.local.runtime import get_runtime
from core.voice.local.sherpa_onnx import audio
from core.voice.streaming import protocol

# 预卷时长（毫秒）：本地 VAD 的 speech_detected 比真实语音起点晚 250–500 ms
# （TEN-VAD 自身窗口约 260 ms，再叠加 vad.min_speech_ms 的判定门限）。预卷短于这个
# 滞后就会把「衍衡」这类短词的首字切掉，只剩尾字——实测 100 ms 门限约 320 ms 触发
# 滞后、300 ms 门限约 500 ms，旧的 200 ms 预卷会整字丢失。1 s 覆盖两种门限，每连接
# 只占约 64 KB。
# Pre-roll (ms): the local VAD's speech_detected trails the true onset by 250–500 ms
# (TEN-VAD's own ~260 ms window plus the vad.min_speech_ms gate). A shorter pre-roll
# clips the first syllable of short words such as 「衍衡」 — measured lag is ~320 ms at
# the 100 ms gate and ~500 ms at 300 ms; the old 200 ms pre-roll dropped the whole first
# word. 1 s covers both and costs only ~64 KB per connection.
PRE_ROLL_MS = 1000
_PRE_ROLL_FRAMES = max(1, PRE_ROLL_MS // audio.FRAME_MS)


class SessionError(RuntimeError):
    """会话无法启动（模型缺失/配置不可用）。The session cannot start."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


def _asr_mode() -> str:
    """当前 ASR 模式（local/cloud/hybrid）。Current ASR mode."""
    mode = getattr(config.settings.voice.asr, "mode", "cloud")
    return mode if mode in ("local", "cloud", "hybrid") else "cloud"


def _looks_truncated(text: str, duration_s: float) -> bool:
    """本地转写疑似被截断：短于中文语速下限的保守判定（hybrid 兜底用）。

    中文正常语速约 4–6 字/秒；阈值取 2 字/秒，只抓明显缺字（如 1.5s 只有 1–2 字），
    放过「好」「你好」这类 <0.5s 的真实短句。

    A conservative "local transcript looks truncated" test for the hybrid fallback.
    Mandarin runs ~4–6 chars/s; the 2 chars/s threshold only catches obvious truncation
    (e.g. 1.5 s → 1–2 chars) and leaves genuine short utterances (<0.5 s) alone.
    """
    return duration_s >= 0.5 and len(text.strip()) < duration_s * 2.0


class StreamingSession:
    """一个 WebSocket 连接的完整状态。Full state of one WebSocket connection."""

    def __init__(self, websocket: Any, start: dict[str, Any], *, runtime: Any = None) -> None:
        self.ws = websocket
        self.start = start
        self.runtime = runtime or get_runtime()
        self.sample_rate = int(start.get("sample_rate") or audio.SAMPLE_RATE)
        self.mode = _asr_mode()
        self.vad_mode = getattr(config.settings.voice.vad, "mode", "local")
        self.kws_mode = getattr(config.settings.voice.kws, "mode", "local")
        self.kws_enabled = bool(getattr(config.settings.voice.kws, "enabled", True))
        self.wake_enabled = bool(getattr(config.settings.voice.wake_word, "enabled", True))
        self.asr_streaming = bool(getattr(config.settings.voice.asr, "streaming", True))
        self.streaming_cfg = config.settings.voice.streaming

        self._vad_engine = self.runtime.vad()
        self._vad_stream: Any = None
        self._asr_engine: Any | None = None
        self._asr_session: Any = None
        self._kws_engine: Any | None = None

        self._active = False
        self._stopped = False
        self._muted = False
        self._segment_id = 0
        self._frames: list[np.ndarray] = []
        self._pre_roll: deque[np.ndarray] = deque(maxlen=_PRE_ROLL_FRAMES)
        # 段起点前的预卷快照：KWS 闸门与（可选）云端上传需要它覆盖 VAD 触发滞后，
        # 但 `_pre_roll` 在 `_begin()` 后即被喂给 ASR 并清空，故单独留一份。
        # Pre-roll snapshot for the segment: the KWS gate (and optional cloud upload)
        # needs it to cover the VAD trigger lag, but `_pre_roll` is fed to ASR and
        # cleared in `_begin()`, so keep a copy.
        self._preroll_snapshot: list[np.ndarray] = []
        self._last_partial = ""
        self._last_partial_at = 0.0
        self._started_at = 0.0
        self._fallback_used = False
        # 闸门模式：wake = 等待唤醒词（KWS 上传前判定）；open = 免唤醒开放聆听。
        # 只有本地 KWS 可用时才具备 wake 闸门；其余配置强制 open。
        # Gate mode: wake = waiting for the wake word (KWS gate before upload);
        # open = wake-free continuous listening. The wake gate requires a loaded local
        # KWS; every other configuration is forced open.
        self.gate_capable = False
        self._gate_mode = "open"

    # ── 启动 ──

    async def start_session(self) -> None:
        """校验模型并发送 ready；失败抛 SessionError。

        Validate models and send ready; raise SessionError on failure.
        """
        if not self.wake_enabled:
            # 关闭唤醒 = 关闭语音入口（README 的隐私承诺）；需要免唤醒持续聆听
            # 时用 kws.mode=off，而不是把 enabled 关掉。
            # Wake disabled = the voice entry point is disabled (the documented privacy
            # promise); use kws.mode=off for wake-free continuous listening instead.
            raise SessionError(
                "wake_disabled",
                "唤醒已关闭（voice.wake_word.enabled=false）：请使用文字输入；"
                "若需要免唤醒持续聆听，请恢复唤醒开关并把 kws.mode 设为 off",
            )
        if self.vad_mode == "off":
            raise SessionError("vad_disabled", "VAD 已关闭：流式链路必须启用本地 VAD")
        ok, reason = await asyncio.to_thread(self._vad_engine.status)
        if not ok:
            raise SessionError("vad_unavailable", reason)
        self._vad_stream = await asyncio.to_thread(self._vad_engine.create_stream)

        if self.mode in ("local", "hybrid"):
            self._asr_engine = self.runtime.asr()
            asr_ok, asr_reason = await asyncio.to_thread(self._asr_engine.status)
            if not asr_ok:
                if self.mode == "local":
                    raise SessionError("asr_unavailable", asr_reason)
                logger.warning("hybrid 本地 ASR 不可用（{}），本会话走云端兜底", asr_reason)
                self._asr_engine = None
        if self.mode in ("cloud", "hybrid"):
            from core.voice import get_asr
            if not get_asr().available() and self._asr_engine is None:
                raise SessionError("cloud_unavailable", "云端 ASR 未配置")

        if self.kws_mode == "local" and self.kws_enabled:
            self._kws_engine = self.runtime.kws()
            kws_ok, kws_reason = await asyncio.to_thread(self._kws_engine.status)
            if not kws_ok:
                logger.warning("本地 KWS 不可用（{}），本会话退化为文本拼音判定", kws_reason)
                self._kws_engine = None
        elif self.kws_mode == "local":
            logger.info("本地 KWS 已禁用（kws.enabled=false），本会话退化为文本拼音判定")

        # 只有「本地 KWS 可用 + 唤醒开启 + mode=local」才具备上传前闸门；
        # api/off/模型缺失一律 open（api 需要先转写才能文本判定）。
        # The pre-upload gate requires a loaded local KWS, wake enabled and mode=local;
        # api/off/missing model are open (api needs the transcript before text judging).
        self.gate_capable = (
            self.wake_enabled and self.kws_mode == "local" and self._kws_engine is not None
        )
        self._gate_mode = "wake" if self.gate_capable else "open"

        await protocol.send(self.ws, {
            "type": "ready",
            "mode": self.mode,
            "streaming": bool(self._asr_engine is not None and self.asr_streaming),
            "sample_rate": audio.SAMPLE_RATE,
            "vad": self.vad_mode,
            "kws": (
                "off" if self.kws_mode == "off"
                else "local" if self._kws_engine is not None
                else "text"
            ),
            "tts": config.settings.voice.tts.mode,
            # 前端据此校验 gate 能力：服务端不具备 wake 闸门时，客户端发 wake 会被
            # 夹回 open（通话/作答等开放聆听场景始终可用）。
            # The frontend validates gate capability: when the server cannot gate,
            # a client "wake" request is clamped to "open".
            "gate_capable": self.gate_capable,
            "gate_default": self._gate_mode,
        })

    # ── 主循环 ──

    async def run(self) -> None:
        """接收帧/控制消息直到 stop 或断开。Receive frames/control until stop/disconnect."""
        try:
            while not self._stopped:
                message = await self.ws.receive()
                if message.get("type") == "websocket.disconnect":
                    break
                text = message.get("text")
                data = message.get("bytes")
                if text is not None:
                    await self._on_control(text)
                elif data is not None:
                    await self._on_audio(data)
        finally:
            await self._close_current()
            try:
                await self.ws.close()
            except Exception:
                pass

    # ── 控制消息 ──

    async def _on_control(self, raw: str) -> None:
        try:
            msg = json.loads(raw)
        except Exception:
            await protocol.send(self.ws, {"type": "error", "code": "bad_json",
                                          "message": "控制消息必须是 JSON", "recoverable": True})
            return
        kind = msg.get("type")
        if kind == "mute":
            self._muted = True
            self._discard_audio_state()
        elif kind == "unmute":
            self._muted = False
            self._discard_audio_state()
        elif kind == "gate":
            mode = str(msg.get("mode") or "").strip().lower()
            if mode not in ("wake", "open"):
                await protocol.send(self.ws, {
                    "type": "error", "code": "bad_gate",
                    "message": "gate.mode 必须是 wake 或 open", "recoverable": True,
                })
                return
            # 服务端不具备上传闸门时，wake 请求被夹回 open（不静默假装已启用）。
            # When the server cannot gate, clamp a wake request to open.
            if mode == "wake" and not self.gate_capable:
                mode = "open"
            self._gate_mode = mode
            await protocol.send(self.ws, {"type": "gate", "mode": self._gate_mode})
        elif kind == "flush":
            await self._finish(reason="flush")
        elif kind == "cancel":
            await self._cancel()
        elif kind == "stop":
            self._stopped = True
            await protocol.send(self.ws, {"type": "done"})
        elif kind == "ping":
            await protocol.send(self.ws, {"type": "pong", "ts": int(time.time() * 1000)})
        # 未知控制消息忽略（向前兼容 / forward compatible）

    def _discard_audio_state(self) -> None:
        """丢弃预卷与当前段（mute/unmute 时调用）。

        播报期间前端停止送帧，若不清理，`_pre_roll` 里播报前的音频会被拼进
        播报后的第一段，VAD/ASR 也带着旧状态（回声护栏漏音）。这里把两者一起复位。

        Drop the pre-roll and the current segment (called on mute/unmute). While the
        assistant speaks the frontend stops sending frames; without this cleanup the
        pre-playback audio in `_pre_roll` would be prepended to the first segment after
        playback, and VAD/ASR would keep stale state (echo-guard leak).
        """
        self._pre_roll.clear()
        self._preroll_snapshot = []
        if self._vad_stream is not None:
            self._vad_stream.reset()
        if self._active:
            self._active = False
            self._frames = []
            self._asr_session = None

    # ── 音频帧 ──

    async def _on_audio(self, data: bytes) -> None:
        if self._muted or self._stopped or self._vad_stream is None:
            return
        samples = audio.pcm16le_to_float32(data)
        if samples.size == 0:
            return
        self._pre_roll.append(samples)

        # VAD 的 accept/pop 是轻量 C++ 调用，同步执行；只有 decode 走线程池。
        # VAD accept/pop are lightweight C++ calls; only decode goes to the thread pool.
        self._vad_stream.accept(samples, self.sample_rate)
        speech = self._vad_stream.speech_detected()

        if speech and not self._active:
            await self._begin()
        elif self._active:
            await self._feed(samples)

        segment = self._vad_stream.pop_segment()
        if segment is not None:
            if not self._active:
                await self._begin()
            await self._finish(vad_samples=segment, reason="vad_end")
            return

        if self._active:
            if self._elapsed_ms() >= self.streaming_cfg.max_utterance_ms:
                await self._finish(reason="max_duration")
                self._vad_stream.reset()
                return
            await self._maybe_partial()

    # ── 段生命周期 ──

    async def _begin(self) -> None:
        """开始一段：建 ASR 流、清空段缓冲、通知前端。Start a segment."""
        self._active = True
        self._segment_id += 1
        self._frames = []
        self._last_partial = ""
        self._last_partial_at = 0.0
        self._started_at = time.monotonic()
        self._asr_session = None
        if self._asr_engine is not None:
            try:
                self._asr_session = await asyncio.to_thread(self._asr_engine.create_session)
            except Exception as e:  # noqa: BLE001
                logger.warning("本地 ASR 会话创建失败（hybrid 会走云端）: {}", e)
                self._asr_session = None
        # 先留一份预卷快照：KWS 闸门与云端上传要用它覆盖 VAD 触发滞后。
        # Snapshot the pre-roll first: the KWS gate and cloud upload use it to cover
        # the VAD trigger lag.
        self._preroll_snapshot = list(self._pre_roll)
        # 把预卷（含触发帧）喂给 ASR，避免吞掉首字。
        # Feed the pre-roll (including the trigger frame) so the first phoneme survives.
        for frame in self._pre_roll:
            self._frames.append(frame)
            if self._asr_session is not None:
                try:
                    self._asr_session.accept(frame, self.sample_rate)
                except Exception:
                    self._asr_session = None
        self._pre_roll.clear()
        await protocol.send(self.ws, {
            "type": "vad", "event": "speech_start", "segment_id": self._segment_id,
        })
        await protocol.send(self.ws, {
            "type": "status", "state": "recognizing", "segment_id": self._segment_id,
        })

    async def _feed(self, samples: np.ndarray) -> None:
        """把一帧喂给当前段。Feed one frame into the active segment."""
        self._frames.append(samples)
        if self._asr_session is not None:
            try:
                self._asr_session.accept(samples, self.sample_rate)
            except Exception as e:  # noqa: BLE001
                logger.warning("本地 ASR 喂帧失败（本段转云端）: {}", e)
                self._asr_session = None

    async def _maybe_partial(self) -> None:
        """按节流间隔解码并推送 partial。Decode and push a partial at the throttle interval."""
        # voice.asr.streaming=false：关闭边说边出字（段尾仍会 finish 出 final）。
        # voice.asr.streaming=false: no incremental text; the segment still finishes
        # with a final transcript.
        if not self.asr_streaming:
            return
        if self._asr_session is None:
            return
        now = time.monotonic()
        interval = self.streaming_cfg.partial_interval_ms / 1000.0
        if now - self._last_partial_at < interval:
            return
        self._last_partial_at = now
        try:
            text = await asyncio.to_thread(self._asr_session.decode)
        except Exception as e:  # noqa: BLE001
            logger.warning("本地 ASR 解码失败: {}", e)
            return
        text = (text or "").strip()
        if not text or text == self._last_partial:
            return
        self._last_partial = text
        await protocol.send(self.ws, {
            "type": "partial", "segment_id": self._segment_id, "text": text,
        })

    async def _finish(self, *, vad_samples: np.ndarray | None = None, reason: str = "vad_end") -> None:
        """结束当前段：定稿文本、唤醒判定、发送 final。Finish the segment."""
        if not self._active:
            return
        self._active = False
        segment = self._segment_audio(vad_samples)
        # 闸门判定用的完整音频：VAD 段 + 段前预卷（补 VAD 触发滞后造成的短词首字丢失）。
        # Full audio for the gate: VAD segment plus the pre-roll snapshot (recovers a
        # short word's first syllable lost to the VAD trigger lag).
        gate_audio = self._segment_audio_with_preroll(vad_samples)
        text = ""
        engine = "local"
        fallback = False
        error = ""

        if self._asr_session is not None:
            try:
                text = (await asyncio.to_thread(self._asr_session.finish) or "").strip()
            except Exception as e:  # noqa: BLE001
                logger.warning("本地 ASR 定稿失败: {}", e)
                error = str(e)

        # 判定用时长：优先 VAD 段（不含 1s 预卷）；flush/超长段没有 VAD 段时退回计时。
        # Decision duration: prefer the VAD segment (no 1 s pre-roll); fall back to the
        # elapsed timer for flush/max-duration segments.
        if vad_samples is not None and len(vad_samples):
            decision_s = audio.duration_s(
                np.asarray(vad_samples, dtype=np.float32), audio.SAMPLE_RATE
            )
        else:
            decision_s = self._elapsed_ms() / 1000.0

        # KWS 必须先于云端上传：wake 闸门下未命中就不上云（隐私 + 成本承诺）。
        # KWS runs before any cloud upload: under the wake gate a miss never uploads.
        kws_hit: str | None = None
        detect_audio = gate_audio if self._gate_mode == "wake" else segment
        if self._kws_engine is not None and detect_audio.size:
            try:
                kws_hit = await asyncio.to_thread(
                    self._kws_engine.detect, detect_audio, audio.SAMPLE_RATE
                )
            except Exception as e:  # noqa: BLE001
                logger.warning("KWS 判定失败（按未命中）: {}", e)

        # 本地文本命中（local/hybrid 有文本；cloud 模式此时通常为空）。
        # Local text hit (local/hybrid have text; cloud mode is usually empty here).
        local_text_hit = self._text_wake_hit(text)
        drop = (
            self._gate_mode == "wake"
            and self.gate_capable
            and not kws_hit
            and not local_text_hit
        )

        if drop:
            audit(f"kws-gate skip=1 segment={self._segment_id}")
        else:
            if kws_hit and self._gate_mode == "wake":
                audit(f"kws-gate hit=1 keyword={kws_hit!r}")
            # hybrid 的兜底条件：本地为空/本地 ASR 缺失/疑似被截断（明显少于中文语速下限）。
            # Hybrid fallback conditions: empty local text / missing local ASR / obviously
            # truncated output. local mode never uploads (privacy invariant).
            suspicious = self.mode == "hybrid" and _looks_truncated(text, decision_s)
            need_cloud = self.mode == "cloud" or (
                self.mode == "hybrid" and (not text or self._asr_session is None or suspicious)
            )
            # wake 闸门下上传带预卷（保住唤醒词首字）；open 模式维持原有 VAD 段。
            # Under the wake gate, upload with the pre-roll (preserve the wake word's
            # first syllable); open mode keeps the plain VAD segment as before.
            upload_audio = (
                gate_audio
                if (self._gate_mode == "wake"
                    and bool(getattr(config.settings.voice.kws, "upload_preroll", True)))
                else segment
            )
            if need_cloud and upload_audio.size:
                try:
                    cloud_text = (await self._cloud_transcribe(upload_audio) or "").strip()
                    if cloud_text or not text:
                        text = cloud_text
                        engine = "cloud"
                        fallback = self.mode == "hybrid"
                    else:
                        # 云端没给出更好的结果：保留本地短文本，绝不用空串覆盖。
                        # Cloud produced nothing better: keep the local short text, never
                        # overwrite it with an empty string.
                        logger.info("hybrid 云端兜底为空，保留本地文本: {!r}", text)
                    error = ""
                except Exception as e:  # noqa: BLE001
                    logger.warning("云端 ASR 失败（via=stream）: {}", e)
                    error = str(e)

        if drop:
            # 闸门丢弃：不带文本、不带唤醒结论，前端按 gate="drop" 静默处理。
            # Gate drop: no text and no wake verdict; the frontend handles gate="drop"
            # as a silent no-op.
            text = ""
            engine = "kws"
            fallback = False
            error = ""

        wake = self._wake_verdict(text, kws_hit)
        duration_ms = self._elapsed_ms()
        level = audio.rms(segment) if segment.size else 0.0
        await protocol.send(self.ws, {
            "type": "vad",
            "event": "speech_end",
            "segment_id": self._segment_id,
            "duration_ms": duration_ms,
        })
        if error and not text:
            await protocol.send(self.ws, {
                "type": "error", "code": "asr_failed", "message": error, "recoverable": True,
            })
        await protocol.send(self.ws, {
            "type": "final",
            "segment_id": self._segment_id,
            "text": text,
            "engine": engine,
            "fallback": fallback,
            "reason": reason,
            "duration_ms": duration_ms,
            "rms": level,
            "wake": wake,
            # gate="drop" = 被唤醒闸门在本机丢弃（未上传、无文本）；其余为当前闸门模式。
            # gate="drop" = dropped locally by the wake gate (no upload, no text);
            # otherwise the active gate mode.
            "gate": "drop" if drop else self._gate_mode,
        })

        if drop:
            pass  # 丢弃段只记 kws-gate skip（上面已记）。The drop audit is emitted above.
        elif engine == "cloud":
            tail = " fallback=1" if fallback else ""
            audit(f"audio-upload via=stream gate={self._gate_mode} chars={len(text)} text={text[:80]!r}{tail}")
        else:
            audit(f"asr-stream local chars={len(text)} text={text[:80]!r}")
        if kws_hit:
            audit(f"kws-stream hit=1 keyword={kws_hit!r}")

        await self._close_current()
        self._frames = []
        self._pre_roll.clear()
        self._preroll_snapshot = []
        self._last_partial = ""

    async def _cancel(self) -> None:
        """丢弃当前段（前端取消）。Drop the current segment (client cancel)."""
        seg_id = self._segment_id
        await self._close_current()
        self._frames = []
        self._pre_roll.clear()
        self._preroll_snapshot = []
        self._active = False
        if self._vad_stream is not None:
            self._vad_stream.reset()
        await protocol.send(self.ws, {"type": "cancelled", "segment_id": seg_id})

    async def _close_current(self) -> None:
        """关掉当前 ASR 会话（幂等）。Close the current ASR session (idempotent)."""
        session = self._asr_session
        self._asr_session = None
        if session is not None:
            try:
                await asyncio.to_thread(session.close)
            except Exception:
                pass

    # ── 辅助 ──

    def _elapsed_ms(self) -> int:
        """当前段已持续毫秒。Current segment duration in ms."""
        if not self._started_at:
            return 0
        return int((time.monotonic() - self._started_at) * 1000)

    def _segment_audio(self, vad_samples: np.ndarray | None) -> np.ndarray:
        """取当前段的 16 kHz 单声道音频。Get the segment as 16 kHz mono audio."""
        if vad_samples is not None and len(vad_samples):
            return audio.resample_linear(
                np.asarray(vad_samples, dtype=np.float32), audio.SAMPLE_RATE, audio.SAMPLE_RATE
            )
        if not self._frames:
            return np.zeros(0, dtype=np.float32)
        merged = np.concatenate(self._frames)
        return audio.resample_linear(merged, self.sample_rate, audio.SAMPLE_RATE)

    def _segment_audio_with_preroll(self, vad_samples: np.ndarray | None) -> np.ndarray:
        """VAD 段 + 段前预卷（仅 VAD 段存在时拼；flush 的 `_frames` 已含预卷）。

        The VAD segment plus the pre-roll snapshot (only when a VAD segment exists;
        flush segments already include the pre-roll via `_frames`).
        """
        base = self._segment_audio(vad_samples)
        if vad_samples is None or not len(vad_samples) or not self._preroll_snapshot:
            return base
        pre = np.concatenate(self._preroll_snapshot)
        pre = audio.resample_linear(
            np.asarray(pre, dtype=np.float32), self.sample_rate, audio.SAMPLE_RATE
        )
        if not base.size:
            return pre
        return np.concatenate([pre, base])

    def _text_wake_hit(self, text: str) -> bool:
        """文本是否命中唤醒词（供闸门在 KWS 未命中时给本地文本一次机会）。

        Whether the text hits a wake keyword (lets local text rescue a KWS miss).
        """
        if not text:
            return False
        from core.voice.wake import detect
        keywords = list(config.settings.voice.wake_word.keywords)
        return bool(detect(text, keywords).matched)

    async def _cloud_transcribe(self, segment: np.ndarray) -> str:
        """把一段 16 kHz PCM 上传云端转写。Upload one 16 kHz PCM segment to cloud ASR."""
        from core.voice import get_asr
        asr = get_asr()
        if not asr.available():
            raise RuntimeError("云端 ASR 未配置")
        wav = audio.write_wav_bytes(segment, audio.SAMPLE_RATE)
        return await asr.transcribe_base64(base64.b64encode(wav).decode(), "wav")

    def _wake_verdict(self, text: str, kws_hit: str | None) -> dict[str, Any]:
        """文本拼音判定 + KWS 发音判定合成唤醒结论。Combine text and KWS verdicts."""
        if not self.wake_enabled:
            return {"matched": False, "command": "", "keyword": "",
                    "source": "", "text": text}
        # kws.mode=off：不判唤醒 —— 每个非空转写都当指令（免唤醒持续聆听）。
        # kws.mode=off: no wake judging — every non-empty transcript is a command
        # (wake-free continuous listening).
        if self.kws_mode == "off":
            body = (text or "").strip()
            return {"matched": bool(body), "command": body, "keyword": "",
                    "source": "off" if body else "", "text": body}
        from core.voice.wake import detect
        keywords = list(config.settings.voice.wake_word.keywords)
        result = detect(text, keywords) if text else None
        text_hit = bool(result and result.matched)
        audio_hit = bool(kws_hit) and self.kws_mode == "local"
        matched = text_hit or audio_hit
        command = result.command if result and result.matched else ""
        return {
            "matched": matched,
            "command": command,
            "keyword": kws_hit or "",
            "source": "kws" if audio_hit else ("text" if text_hit else ""),
            "text": text,
        }
