# -*- coding: utf-8 -*-
"""本地流式转写 — sherpa-onnx streaming zipformer（通话漏斗 L1，零云端）。

模型缺失/加载失败 → available()=False、transcribe_wav 返回空串：漏斗降级为 L0+L2
（与 KWS 闸门同一「坏得静默、链路不断」契约）。wav 经 accept_waveform 直喂，采样率
不一致由 sherpa 内部重采样（1.13.8 文档确认）。

Local streaming transcription — sherpa-onnx streaming zipformer (funnel L1, zero cloud).
Missing/failed model → available()=False and transcribe_wav returns "" so the funnel
degrades to L0+L2 (same "fail silent, never break the chain" contract as the KWS gate).
wav samples go straight into accept_waveform; sherpa resamples internally on rate
mismatch (confirmed against the 1.13.8 docstring).
"""
from __future__ import annotations

import io
import wave
from typing import Any

from core import config
from core.config import add_reload_hook
from core.logger import logger

_instance: "LocalAsr | None" = None


class LocalAsr:
    """sherpa-onnx 流式识别单例（懒加载，配置热重载后重建）。Lazy-load singleton."""

    def __init__(self) -> None:
        self._recognizer: Any | None = None
        self._loaded = False

    def _load(self) -> bool:
        if self._loaded:
            return self._recognizer is not None
        self._loaded = True
        try:
            if not config.settings.voice.call.enabled:
                return False
            d = config.ROOT_DIR / config.settings.voice.call.local_asr_model
            tokens = d / "tokens.txt"
            if not tokens.is_file():
                logger.info("本地转写模型不存在（{}），L1 跳过（漏斗走 L0+L2）", d)
                return False
            enc = self._pick(d, "encoder", prefer_int8=True)
            dec = self._pick(d, "decoder")
            jn = self._pick(d, "joiner")
            if enc is None or dec is None or jn is None:
                logger.warning("本地转写模型文件不全（{}），L1 跳过", d)
                return False
            import sherpa_onnx
            self._recognizer = sherpa_onnx.OnlineRecognizer.from_transducer(
                tokens=str(tokens), encoder=str(enc), decoder=str(dec), joiner=str(jn),
                num_threads=2, sample_rate=16000, feature_dim=80,
                enable_endpoint_detection=False, decoding_method="greedy_search",
            )
            logger.info("本地转写就绪：{}", d.name)
            return True
        except Exception as e:
            logger.warning("本地转写加载失败，L1 跳过: {}", e)
            self._recognizer = None
            return False

    @staticmethod
    def _pick(d, kind: str, prefer_int8: bool = False):
        """按前缀挑模型文件（int8 优先），找不到返回 None。Pick a model file by prefix."""
        cands = sorted(d.glob(f"{kind}-*.onnx"))
        if not cands:
            return None
        if prefer_int8:
            i8 = [c for c in cands if ".int8." in c.name]
            if i8:
                return i8[0]
        return cands[0]

    def available(self) -> bool:
        return self._load()

    def transcribe_wav(self, wav_bytes: bytes) -> str:
        """整段 wav → 文本；任何失败返回 ""（调用方按无文本降级）。Never raises."""
        if not self.available():
            return ""
        rec = self._recognizer
        if rec is None:
            return ""  # 双保险 / belt and braces
        try:
            with wave.open(io.BytesIO(wav_bytes), "rb") as w:
                sr = w.getframerate()
                frames = w.readframes(w.getnframes())
            import numpy as np
            samples = (np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0)
            if samples.size == 0:
                return ""
            stream = rec.create_stream()
            stream.accept_waveform(float(sr), samples.tolist())
            stream.input_finished()
            while rec.is_ready(stream):
                rec.decode_stream(stream)
            return (rec.get_result(stream) or "").strip()
        except Exception as e:
            logger.warning("本地转写失败（按无文本降级）: {}", e)
            return ""


def get_local_asr() -> LocalAsr:
    global _instance
    if _instance is None:
        _instance = LocalAsr()
    return _instance


def _reset_local_asr() -> None:
    global _instance
    _instance = None


add_reload_hook(_reset_local_asr)
