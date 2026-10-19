# -*- coding: utf-8 -*-
"""本框架专用的 sherpa-onnx 本地语音后端。

The sherpa-onnx local speech backend built for this project.

四个能力各自独立：

- :class:`VadEngine` — TEN VAD / Silero VAD，本地分段（无云端 VAD）
- :class:`KwsEngine` — Zipformer 关键词检测
- :class:`StreamingAsrEngine` — Zipformer / 其它在线 sherpa ASR
- :class:`TtsEngine` — Kokoro（以及同结构的 sherpa TTS）

模型发现走 :mod:`registry`（扫描 ``models/{vad,kws,asr,tts,llm}``），硬件加速走
:mod:`hardware`（每个模型可独立选 cpu/cuda/coreml）。
"""
from __future__ import annotations

from .asr import AsrError, AsrOptions, AsrSession, StreamingAsrEngine
from .audio import (
    FRAME_MS,
    FRAME_SAMPLES,
    SAMPLE_RATE,
    duration_s,
    float32_to_pcm16le,
    pcm16le_to_float32,
    read_wav_bytes,
    resample_linear,
    rms,
    write_wav_bytes,
)
from .hardware import (
    VALID_PROVIDERS,
    HardwareInfo,
    ProviderUnavailableError,
    available_providers,
    default_num_threads,
    probe,
    resolve_provider,
    resolve_threads,
)
from .kws import KwsEngine, KwsError, KwsOptions
from .registry import KINDS, ModelInfo, find, inspect, models_root, present, scan
from .tts import TtsEngine, TtsError, TtsOptions
from .vad import VadEngine, VadError, VadOptions, VadStream

__all__ = [
    "AsrError", "AsrOptions", "AsrSession", "StreamingAsrEngine",
    "KwsEngine", "KwsError", "KwsOptions",
    "TtsEngine", "TtsError", "TtsOptions",
    "VadEngine", "VadError", "VadOptions", "VadStream",
    "FRAME_MS", "FRAME_SAMPLES", "SAMPLE_RATE",
    "duration_s", "float32_to_pcm16le", "pcm16le_to_float32",
    "read_wav_bytes", "resample_linear", "rms", "write_wav_bytes",
    "VALID_PROVIDERS", "HardwareInfo", "ProviderUnavailableError",
    "available_providers", "default_num_threads", "probe",
    "resolve_provider", "resolve_threads",
    "KINDS", "ModelInfo", "find", "inspect", "models_root", "present", "scan",
]
