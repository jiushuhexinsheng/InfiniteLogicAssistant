# -*- coding: utf-8 -*-
"""单连接流式会话：PCM 帧 → 本地 VAD → KWS → ASR → partial/final。

Per-connection streaming session: PCM frames → local VAD → KWS → ASR → partial/final.

设计取舍：

- **分段只由本地 VAD 决定**（本项目没有云端 VAD）；VAD 模型缺失时明确报错，
  不偷偷退回旧的浏览器切段链路。
- **本地 ASR** 在说话期间增量解码并推 partial；**云端 ASR** 只在 VAD 段结束时
  上传一次，推 final（不伪造 partial）。
- **KWS** 在段尾对同一段音频做发音级判定；KWS=api 时退化为文本拼音判定。
- 解码/合成/KWS 都放线程池，绝不阻塞事件循环。

Design:

- **Segmentation is local VAD only** (there is no cloud VAD); a missing VAD model is a
  clear error, never a silent fallback to the legacy browser-segment pipeline.
- **Local ASR** decodes incrementally while speaking and emits partials; **cloud ASR**
  uploads once at the VAD endpoint and emits a final (no fake partials).
- **KWS** judges the same segment at its end (pronunciation level); ``kws=api`` degrades
  to text/pinyin judging.
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
        self._pre_roll: deque[np.ndarray] = deque(maxlen=10)   # ~200 ms
        self._last_partial = ""
        self._last_partial_at = 0.0
        self._started_at = 0.0
        self._fallback_used = False

    # ── 启动 ──

    async def start_session(self) -> None:
        """校验模型并发送 ready；失败抛 SessionError。

        Validate models and send ready; raise SessionError on failure.
        """
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

        if self.kws_mode == "local":
            self._kws_engine = self.runtime.kws()
            kws_ok, kws_reason = await asyncio.to_thread(self._kws_engine.status)
            if not kws_ok:
                logger.warning("本地 KWS 不可用（{}），本会话退化为文本拼音判定", kws_reason)
                self._kws_engine = None

        await protocol.send(self.ws, {
            "type": "ready",
            "mode": self.mode,
            "streaming": bool(self._asr_engine is not None and config.settings.voice.asr.streaming),
            "sample_rate": audio.SAMPLE_RATE,
            "vad": self.vad_mode,
            "kws": self.kws_mode if self._kws_engine is not None else "text",
            "tts": config.settings.voice.tts.mode,
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
        elif kind == "unmute":
            self._muted = False
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

        need_cloud = self.mode == "cloud" or (
            self.mode == "hybrid" and (not text or self._asr_session is None)
        )
        if need_cloud and segment.size:
            try:
                text = (await self._cloud_transcribe(segment) or "").strip()
                engine = "cloud"
                fallback = self.mode == "hybrid"
                error = ""
            except Exception as e:  # noqa: BLE001
                logger.warning("云端 ASR 失败（via=stream）: {}", e)
                error = str(e)

        kws_hit: str | None = None
        if self._kws_engine is not None and segment.size:
            try:
                kws_hit = await asyncio.to_thread(self._kws_engine.detect, segment, audio.SAMPLE_RATE)
            except Exception as e:  # noqa: BLE001
                logger.warning("KWS 判定失败（按未命中）: {}", e)

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
        })

        if engine == "cloud":
            tail = " fallback=1" if fallback else ""
            audit(f"audio-upload via=stream chars={len(text)} text={text[:80]!r}{tail}")
        else:
            audit(f"asr-stream local chars={len(text)} text={text[:80]!r}")
        if kws_hit:
            audit(f"kws-stream hit=1 keyword={kws_hit!r}")

        await self._close_current()
        self._frames = []
        self._pre_roll.clear()
        self._last_partial = ""

    async def _cancel(self) -> None:
        """丢弃当前段（前端取消）。Drop the current segment (client cancel)."""
        seg_id = self._segment_id
        await self._close_current()
        self._frames = []
        self._pre_roll.clear()
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
