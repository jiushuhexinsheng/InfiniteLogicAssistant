# -*- coding: utf-8 -*-
"""音频工具：WAV / PCM 转换、重采样、分帧与能量计算。

Audio helpers: WAV/PCM conversion, resampling, framing and energy.

只依赖 numpy —— 不引入 scipy/librosa，保持本地引擎包的可部署性。重采样是
线性插值，用于把非 16 kHz 的输入喂给 VAD；ASR 直接把原始采样率交给
sherpa 的 ``accept_waveform``（1.13.8 内部重采样），不需要在这里做。
"""
from __future__ import annotations

import io
import math
import wave

import numpy as np

# ASR / VAD / KWS 的训练采样率。Training sample rate for ASR/VAD/KWS.
SAMPLE_RATE = 16000

# 流式帧长（毫秒）；20 ms 是延迟与 WebSocket 频率的折中。
# Streaming frame size in milliseconds; 20 ms balances latency and WS message rate.
FRAME_MS = 20

# 20 ms @ 16 kHz = 320 个采样。Samples in one 20 ms frame at 16 kHz.
FRAME_SAMPLES = SAMPLE_RATE * FRAME_MS // 1000


def pcm16le_to_float32(data: bytes) -> np.ndarray:
    """PCM16 小端字节 → [-1, 1] 的 float32 采样。

    PCM16 little-endian bytes → float32 samples in [-1, 1].
    """
    if not data:
        return np.zeros(0, dtype=np.float32)
    return np.frombuffer(data, dtype="<i2").astype(np.float32) / 32768.0


def float32_to_pcm16le(samples: np.ndarray) -> bytes:
    """[-1, 1] 的 float32 采样 → PCM16 小端字节。

    float32 samples in [-1, 1] → PCM16 little-endian bytes.
    """
    arr = np.clip(np.asarray(samples, dtype=np.float32), -1.0, 1.0)
    return (arr * 32767.0).astype("<i2").tobytes()


def resample_linear(samples: np.ndarray, sr_in: int, sr_out: int) -> np.ndarray:
    """线性插值重采样；采样率相同则原样返回。

    Linear-interpolation resampling; returns the input unchanged when the rates match.

    VAD 只需要 16 kHz 的近似波形（它不看音质），线性插值足够；ASR 不走这条路径，
    由 sherpa 自己按训练采样率重采样。
    """
    if sr_in == sr_out or samples.size == 0:
        return np.asarray(samples, dtype=np.float32)
    if sr_in <= 0 or sr_out <= 0:
        return np.asarray(samples, dtype=np.float32)
    duration = samples.size / float(sr_in)
    n_out = max(1, int(round(duration * sr_out)))
    src = np.arange(samples.size, dtype=np.float64) / float(sr_in)
    dst = np.arange(n_out, dtype=np.float64) / float(sr_out)
    return np.interp(dst, src, samples).astype(np.float32)


def read_wav_bytes(data: bytes) -> tuple[np.ndarray, int]:
    """WAV 字节 → (单声道 float32 采样, 采样率)。

    WAV bytes → (mono float32 samples, sample rate).

    支持 8/16/24/32 位 PCM；多声道取首声道。非 PCM（float/压缩）会抛 ValueError，
    由调用方决定是否降级。
    """
    with wave.open(io.BytesIO(data), "rb") as w:
        sr = w.getframerate()
        nch = w.getnchannels()
        width = w.getsampwidth()
        raw = w.readframes(w.getnframes())

    if not raw:
        return np.zeros(0, dtype=np.float32), sr

    if width == 1:
        arr = (np.frombuffer(raw, dtype=np.uint8).astype(np.float32) - 128.0) / 128.0
    elif width == 2:
        arr = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
    elif width == 3:
        b = np.frombuffer(raw, dtype=np.uint8).reshape(-1, 3).astype(np.int32)
        iv = b[:, 0] | (b[:, 1] << 8) | (b[:, 2] << 16)
        iv = np.where(iv >= 1 << 23, iv - (1 << 24), iv)
        arr = iv.astype(np.float32) / float(1 << 23)
    elif width == 4:
        arr = np.frombuffer(raw, dtype="<i4").astype(np.float32) / 2147483648.0
    else:
        raise ValueError(f"不支持的 WAV 采样宽度: {width}")

    if nch > 1:
        arr = arr[::nch]   # 取首声道 / take the first channel
    return arr.astype(np.float32, copy=False), sr


def write_wav_bytes(samples: np.ndarray, sample_rate: int) -> bytes:
    """[-1, 1] float32 → 16-bit PCM WAV 字节。

    float32 samples in [-1, 1] → 16-bit PCM WAV bytes.
    """
    pcm = float32_to_pcm16le(samples)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(int(sample_rate))
        w.writeframes(pcm)
    return buf.getvalue()


def rms(samples: np.ndarray) -> float:
    """归一化 RMS（0..1）。Normalised RMS in [0, 1]."""
    arr = np.asarray(samples, dtype=np.float32)
    if arr.size == 0:
        return 0.0
    return float(math.sqrt(float(np.mean(np.square(arr)))))


def duration_s(samples: np.ndarray, sample_rate: int) -> float:
    """采样数 → 秒。Sample count → seconds."""
    if sample_rate <= 0:
        return 0.0
    return float(samples.size) / float(sample_rate)


def frames(samples: np.ndarray, frame_samples: int = FRAME_SAMPLES) -> list[np.ndarray]:
    """把连续采样切成定长帧（最后一帧保留余数）。Split samples into fixed frames."""
    arr = np.asarray(samples, dtype=np.float32)
    if frame_samples <= 0:
        return [arr]
    return [arr[i:i + frame_samples] for i in range(0, arr.size, frame_samples)]
