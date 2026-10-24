# -*- coding: utf-8 -*-
"""本地引擎运行时：按配置构造并缓存 VAD / KWS / ASR / TTS 单例。

Local engine runtime: build and cache the VAD / KWS / ASR / TTS singletons from config.

配置热重载后整体重建；模型加载仍是惰性的（第一次使用时才读入内存）。
Rebuilt wholesale on config reload; model loading stays lazy (first use only).
"""
from __future__ import annotations

from typing import Any

from core import config
from core.config import add_reload_hook
from core.voice.local.sherpa_onnx import (
    AsrOptions,
    KwsEngine,
    KwsOptions,
    StreamingAsrEngine,
    TtsEngine,
    TtsOptions,
    VadEngine,
    VadOptions,
    registry,
)

_runtime: "LocalRuntime | None" = None


class LocalRuntime:
    """四类本地引擎的懒加载容器。Lazy container for the four local engines."""

    def __init__(self) -> None:
        self._vad: VadEngine | None = None
        self._kws: KwsEngine | None = None
        self._asr: StreamingAsrEngine | None = None
        self._tts: TtsEngine | None = None

    def vad(self) -> VadEngine:
        """本地 VAD（TEN/Silero）。Local VAD (TEN/Silero)."""
        if self._vad is None:
            v = config.settings.voice.vad
            st = config.settings.voice.streaming
            self._vad = VadEngine(VadOptions(
                model=v.model,
                kind=v.engine,
                provider=v.provider,
                device=v.device,
                num_threads=v.num_threads,
                threshold=v.vad_threshold,
                # 流式链路的端点静音/最长时长优先于旧浏览器 VAD 字段。
                # The streaming endpoint silence / max length wins over the legacy browser fields.
                min_silence_s=st.endpoint_silence_ms / 1000.0,
                min_speech_s=v.min_speech_ms / 1000.0,
                max_speech_s=st.max_utterance_ms / 1000.0,
                window_size=v.window_size,
            ))
        return self._vad

    def kws(self) -> KwsEngine:
        """本地 KWS（Zipformer）。Local KWS (Zipformer)."""
        if self._kws is None:
            k = config.settings.voice.kws
            self._kws = KwsEngine(KwsOptions(
                model_dir=k.model_dir,
                keywords=tuple(config.settings.voice.wake_word.keywords),
                provider=k.provider,
                device=k.device,
                num_threads=k.num_threads,
                threshold=k.keywords_threshold,
                score=k.keywords_score,
            ))
        return self._kws

    def asr(self) -> StreamingAsrEngine:
        """本地流式 ASR。Local streaming ASR."""
        if self._asr is None:
            a = config.settings.voice.asr
            info = registry.find("asr", a.local_model)
            self._asr = StreamingAsrEngine(AsrOptions(
                model_dir=a.local_model,
                family=info.family if info else "transducer",
                provider=a.provider,
                device=a.device,
                num_threads=a.num_threads,
                enable_endpoint_detection=False,   # 分段由本地 VAD 负责
            ))
        return self._asr

    def tts(self) -> TtsEngine:
        """本地 Kokoro TTS。Local Kokoro TTS."""
        if self._tts is None:
            t = config.settings.voice.tts
            self._tts = TtsEngine(TtsOptions(
                model_dir=t.local_model,
                provider=t.provider,
                device=t.device,
                num_threads=t.num_threads,
                speaker=t.speaker,
                speed=t.speed,
                lang=t.lang,
            ))
        return self._tts

    def reset(self) -> None:
        """丢弃全部引擎（配置热重载）。Drop every engine (config reload)."""
        self._vad = None
        self._kws = None
        self._asr = None
        self._tts = None

    def snapshot(self) -> dict[str, Any]:
        """已构造的引擎状态（不触发加载）。Status of constructed engines (no loading)."""
        out: dict[str, Any] = {}
        for name, engine in (
            ("vad", self._vad), ("kws", self._kws),
            ("asr", self._asr), ("tts", self._tts),
        ):
            out[name] = None if engine is None else engine.status()
        return out


def get_runtime() -> LocalRuntime:
    """取进程内运行时单例。Get the process-wide runtime singleton."""
    global _runtime
    if _runtime is None:
        _runtime = LocalRuntime()
    return _runtime


def _reset_runtime() -> None:
    """配置热重载后丢弃运行时。Drop the runtime after a config reload."""
    global _runtime
    _runtime = None


add_reload_hook(_reset_runtime, sections=("voice",))
