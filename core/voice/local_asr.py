# -*- coding: utf-8 -*-
"""本地流式转写 — sherpa-onnx streaming zipformer（零云端）。

用途两处：① 通话漏斗 L1 快筛（`_local_transcribe`，返回空串即降级、链路不断）；
② ASR 三模式的本地转写通路（`core/voice/asr_dispatch.py`，`voice.asr.mode` 为
`local`/`hybrid` 时按模式调用；`local` 模式缺模型时由 dispatch 明确报错，**绝不静默上云**）。

模型缺失/加载失败 → available()=False、transcribe_wav 返回空串，`status()` 给出人话原因。
wav 经 accept_waveform 直喂，采样率不一致由 sherpa 内部重采样（1.13.8 文档确认）。
模型路径取 `voice.asr.local_model`（旧键 `voice.call.local_asr_model` 由 loader 迁移）。

Local streaming transcription — sherpa-onnx streaming zipformer (zero cloud). Used in two
places: the call-funnel L1 quick screen (returns "" to degrade, never breaking the chain),
and the ASR tri-mode local path (`core/voice/asr_dispatch.py`, driven by `voice.asr.mode`;
in `local` mode the dispatcher raises on a missing model rather than silently uploading).
Missing/failed model → available()=False, transcribe_wav returns "", and status() gives a
human-readable reason. Model path comes from `voice.asr.local_model` (the legacy
`voice.call.local_asr_model` is migrated by the loader).
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
        self._reason = ""

    def _load(self) -> bool:
        if self._loaded:
            return self._recognizer is not None
        self._loaded = True
        try:
            d = config.ROOT_DIR / config.settings.voice.asr.local_model
            tokens = d / "tokens.txt"
            if not tokens.is_file():
                self._reason = (
                    f"本地 ASR 模型目录不存在或缺 tokens.txt：{d}"
                    "（运行 python scripts/fetch_local_asr_model.py 下载）"
                )
                logger.info("本地转写模型不存在（{}），L1 跳过（漏斗走 L0+L2）", d)
                return False
            enc = self._pick(d, "encoder", prefer_int8=True)
            dec = self._pick(d, "decoder")
            jn = self._pick(d, "joiner")
            if enc is None or dec is None or jn is None:
                self._reason = f"本地 ASR 模型文件不全（缺 encoder/decoder/joiner onnx）：{d}"
                logger.warning("本地转写模型文件不全（{}），L1 跳过", d)
                return False
            try:
                import sherpa_onnx
            except ImportError as e:
                self._reason = f"sherpa_onnx 未安装：{e}"
                logger.warning("sherpa_onnx 未安装，L1 跳过: {}", e)
                return False
            self._recognizer = sherpa_onnx.OnlineRecognizer.from_transducer(
                tokens=str(tokens), encoder=str(enc), decoder=str(dec), joiner=str(jn),
                num_threads=2, sample_rate=16000, feature_dim=80,
                enable_endpoint_detection=False, decoding_method="greedy_search",
            )
            self._reason = ""
            logger.info("本地转写就绪：{}", d.name)
            return True
        except Exception as e:
            self._reason = f"本地 ASR 加载失败：{e}"
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

    def status(self) -> tuple[bool, str]:
        """(可用性, 人话原因) —— 不可用时说明「为什么 + 怎么办」，可用时原因为空串。

        供 ASR 三模式在本地不可用时给出**明确提示**（`local` 模式下绝不静默上云）。
        注意本方法会真正触发模型加载（百 MB 级）；设置页展示「模型是否就位」应改用
        纯文件系统判断（`editable_snapshot` 的 `local_model_present`），不要调它。

        (available, human-readable reason): the reason is non-empty only when
        unavailable, explaining why and what to do. Used by the ASR tri-mode path to
        surface a **clear error** instead of silently uploading in `local` mode. NOTE:
        this actually triggers model loading (hundreds of MB); the settings page should
        use a filesystem-only check instead.
        """
        if self._load():
            return True, ""
        return False, self._reason or "本地 ASR 不可用"

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


def local_model_present(model_dir: str | None = None) -> bool:
    """本地 ASR 模型是否就位 —— **纯文件系统判断**，不加载模型（供设置页只读展示）。

    刻意不调 `get_local_asr().available()`：那会 import sherpa_onnx 并把 ~173MB 的 encoder
    载入内存，只为渲染一个布尔标记。判据与 `scripts/fetch_local_asr_model.py` 的
    `is_complete` 一致（tokens.txt + 三前缀各至少一个非空 onnx）。

    Whether the local ASR model is present — a **filesystem-only** check that never loads
    the model (for the settings page's read-only flag). Deliberately avoids
    `available()`, which would import sherpa_onnx and pull the ~173MB encoder into memory
    just to render a boolean.

    Args:
        model_dir: 相对 ROOT_DIR 的模型目录；缺省取 `voice.asr.local_model`。
            Model dir relative to ROOT_DIR; defaults to `voice.asr.local_model`.
    """
    rel = config.settings.voice.asr.local_model if model_dir is None else model_dir
    d = config.ROOT_DIR / rel
    if not (d / "tokens.txt").is_file():
        return False
    return all(
        any(p.stat().st_size > 0 for p in d.glob(f"{pref}*.onnx"))
        for pref in ("encoder-", "decoder-", "joiner-")
    )


def get_local_asr() -> LocalAsr:
    global _instance
    if _instance is None:
        _instance = LocalAsr()
    return _instance


def _reset_local_asr() -> None:
    global _instance
    _instance = None


add_reload_hook(_reset_local_asr)
