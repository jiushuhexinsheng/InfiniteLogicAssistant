# -*- coding: utf-8 -*-
"""TEN VAD / Silero VAD 包装（sherpa-onnx）。

TEN VAD / Silero VAD wrapper (sherpa-onnx).

VAD 只做本地推理：本项目不再提供「云端 VAD」选项，分段完全在本机完成。
VAD is local-only: there is no cloud-VAD option; segmentation happens entirely on-device.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from core.voice.local.sherpa_onnx import audio, hardware


@dataclass(frozen=True)
class VadOptions:
    """VAD 引擎参数。VAD engine options."""

    model: str
    kind: str = "ten-vad"            # ten-vad | silero
    provider: str = "cpu"
    device: int = 0
    num_threads: int = 1
    threshold: float = 0.5
    min_silence_s: float = 0.5
    min_speech_s: float = 0.25
    max_speech_s: float = 20.0
    window_size: int = 0             # 0 = 按 VAD 类型取默认（TEN 256 / Silero 512）
    sample_rate: int = audio.SAMPLE_RATE


class VadError(RuntimeError):
    """VAD 加载/推理失败。VAD load/inference failure."""


class VadEngine:
    """懒加载的 VAD 引擎（线程内共享，每个流独立）。

    Lazily loaded VAD engine (shared, one stream per session).
    """

    def __init__(self, opts: VadOptions) -> None:
        self.opts = opts
        self._config: Any | None = None
        self._loaded = False
        self._reason = ""

    def _load(self) -> bool:
        if self._loaded:
            return self._config is not None
        self._loaded = True
        try:
            import sherpa_onnx  # type: ignore[import-untyped]

            model = Path(self.opts.model)
            if not model.is_absolute():
                from core import config
                model = Path(config.ROOT_DIR) / model
            if not model.is_file():
                self._reason = f"VAD 模型不存在: {model}"
                return False

            kind = (self.opts.kind or "ten-vad").strip().lower()
            provider = hardware.resolve_provider(self.opts.provider)
            if kind == "silero":
                window = self.opts.window_size or 512
                vad_cfg = sherpa_onnx.VadModelConfig(
                    silero_vad=sherpa_onnx.SileroVadModelConfig(
                        model=str(model),
                        threshold=self.opts.threshold,
                        min_silence_duration=self.opts.min_silence_s,
                        min_speech_duration=self.opts.min_speech_s,
                        max_speech_duration=self.opts.max_speech_s,
                        window_size=int(window),
                    ),
                    sample_rate=int(self.opts.sample_rate),
                    num_threads=hardware.resolve_threads(self.opts.num_threads),
                    provider=provider,
                )
            else:
                # TEN VAD 的窗口默认 256（16 ms @ 16 kHz）。TEN VAD defaults to 256.
                window = self.opts.window_size or 256
                vad_cfg = sherpa_onnx.VadModelConfig(
                    ten_vad=sherpa_onnx.TenVadModelConfig(
                        model=str(model),
                        threshold=self.opts.threshold,
                        min_silence_duration=self.opts.min_silence_s,
                        min_speech_duration=self.opts.min_speech_s,
                        max_speech_duration=self.opts.max_speech_s,
                        window_size=int(window),
                    ),
                    sample_rate=int(self.opts.sample_rate),
                    num_threads=hardware.resolve_threads(self.opts.num_threads),
                    provider=provider,
                )
            # 只保存配置；detector 是**有状态**的，每个会话各建一个（见 VadStream）。
            # Keep the config only; the detector is **stateful**, so each session gets its own.
            self._config = vad_cfg
            self._reason = ""
            return True
        except Exception as e:  # noqa: BLE001 - 详细原因回给设置页/日志
            self._reason = f"VAD 加载失败: {e}"
            self._config = None
            return False

    def available(self) -> bool:
        """是否可用（会触发一次加载）。Whether usable (triggers loading)."""
        return self._load()

    def status(self) -> tuple[bool, str]:
        """(可用, 人话原因)。(available, human-readable reason)."""
        if self._load():
            return True, ""
        return False, self._reason or "VAD 不可用"

    def create_stream(self) -> "VadStream":
        """创建一个连接/会话级的 VAD 流。Create a per-session VAD stream."""
        if not self._load():
            raise VadError(self._reason or "VAD 不可用")
        return VadStream(self)

    def segments(self, samples: np.ndarray, sample_rate: int) -> list[np.ndarray]:
        """整段 PCM → 若干个语音段（最后 flush）。Whole PCM → speech segments (flushed)."""
        stream = self.create_stream()
        stream.accept(samples, sample_rate)
        stream.flush()
        out: list[np.ndarray] = []
        while True:
            seg = stream.pop_segment()
            if seg is None:
                break
            out.append(seg)
        return out


class VadStream:
    """一个会话独立的 VAD 流。One VAD stream per session."""

    def __init__(self, engine: VadEngine) -> None:
        self.engine = engine
        self._sr = int(engine.opts.sample_rate)
        try:
            import sherpa_onnx  # type: ignore[import-untyped]
            self._detector = sherpa_onnx.VoiceActivityDetector(
                engine._config, buffer_size_in_seconds=60)
        except Exception as e:  # noqa: BLE001
            raise VadError(f"VAD 会话创建失败: {e}") from e

    def accept(self, samples: np.ndarray, sample_rate: int) -> None:
        """喂入 PCM（自动重采样到 VAD 训练采样率）。Feed PCM (resampled to 16 kHz)."""
        if self._detector is None:
            raise VadError("VAD 未加载")
        arr = audio.resample_linear(np.asarray(samples, dtype=np.float32), sample_rate, self._sr)
        if arr.size:
            self._detector.accept_waveform(arr)

    def speech_detected(self) -> bool:
        """当前是否处于语音中。Whether speech is currently detected."""
        return bool(self._detector is not None and self._detector.is_speech_detected())

    def pop_segment(self) -> np.ndarray | None:
        """取出一段已结束的语音；没有返回 None。Pop a finished speech segment, or None."""
        if self._detector is None or self._detector.empty():
            return None
        seg = self._detector.front
        samples = np.asarray(seg.samples, dtype=np.float32)
        self._detector.pop()
        return samples

    def flush(self) -> None:
        """冲刷缓冲，迫使未结束的段产出。Flush so an open segment is emitted."""
        if self._detector is not None:
            self._detector.flush()

    def reset(self) -> None:
        """清空内部状态。Reset internal state."""
        if self._detector is not None:
            self._detector.reset()
