# -*- coding: utf-8 -*-
"""Zipformer / sherpa-onnx 流式 ASR 包装。

Zipformer / sherpa-onnx streaming ASR wrapper.

只负责「模型 → 文本」：VAD、KWS、会话协议都在上层。一个引擎实例可服务多个
WebSocket 会话（每个会话一个 ``OnlineStream``）；解码用一把锁串行化，避免并发
调用同一个 recognizer。
Only model → text; VAD/KWS/session protocol live above. One engine can serve several
WebSocket sessions (one ``OnlineStream`` each); decoding is serialised with a lock so
concurrent sessions never enter the same recognizer at once.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from core import config
from core.logger import logger
from core.voice.local.sherpa_onnx import audio, hardware


@dataclass(frozen=True)
class AsrOptions:
    """ASR 引擎参数。ASR engine options."""

    model_dir: str
    family: str = "transducer"
    provider: str = "cpu"
    device: int = 0
    num_threads: int = 2
    sample_rate: int = audio.SAMPLE_RATE
    feature_dim: int = 80
    decoding_method: str = "greedy_search"
    enable_endpoint_detection: bool = True
    rule1_min_trailing_silence: float = 2.4
    rule2_min_trailing_silence: float = 1.2
    rule3_min_utterance_length: float = 20.0
    hotwords_file: str = ""
    hotwords_score: float = 1.5


class AsrError(RuntimeError):
    """ASR 加载/推理失败。ASR load/inference failure."""


def _pick(d: Path, kind: str, *, prefer_int8: bool = True) -> Path | None:
    """按前缀挑模型文件（int8 优先）。Pick a model file by prefix (int8 preferred)."""
    cands = sorted(d.glob(f"{kind}-*.onnx")) or sorted(d.glob(f"{kind}*.onnx"))
    if not cands:
        return None
    if prefer_int8:
        i8 = [c for c in cands if ".int8." in c.name]
        if i8:
            return i8[0]
    return cands[0]


class StreamingAsrEngine:
    """懒加载的流式识别器。Lazily loaded streaming recognizer."""

    def __init__(self, opts: AsrOptions) -> None:
        self.opts = opts
        self._recognizer: Any | None = None
        self._loaded = False
        self._reason = ""
        self._lock = threading.Lock()

    def _model_dir(self) -> Path:
        d = Path(self.opts.model_dir)
        if not d.is_absolute():
            d = Path(config.ROOT_DIR) / d
        return d

    def _load(self) -> bool:
        if self._loaded:
            return self._recognizer is not None
        self._loaded = True
        try:
            import sherpa_onnx  # type: ignore[import-untyped]

            d = self._model_dir()
            tokens = d / "tokens.txt"
            if not tokens.is_file():
                self._reason = (
                    f"ASR 模型目录不存在或缺 tokens.txt：{d}"
                    "（运行 python scripts/fetch_local_asr_model.py 下载）"
                )
                return False

            provider = hardware.resolve_provider(self.opts.provider)
            common: dict[str, Any] = {
                "tokens": str(tokens),
                "num_threads": hardware.resolve_threads(self.opts.num_threads),
                "sample_rate": int(self.opts.sample_rate),
                "feature_dim": int(self.opts.feature_dim),
                "enable_endpoint_detection": bool(self.opts.enable_endpoint_detection),
                "rule1_min_trailing_silence": float(self.opts.rule1_min_trailing_silence),
                "rule2_min_trailing_silence": float(self.opts.rule2_min_trailing_silence),
                "rule3_min_utterance_length": float(self.opts.rule3_min_utterance_length),
                "decoding_method": self.opts.decoding_method,
                "provider": provider,
                "device": int(self.opts.device),
            }
            if self.opts.hotwords_file:
                common["hotwords_file"] = self.opts.hotwords_file
                common["hotwords_score"] = float(self.opts.hotwords_score)

            family = (self.opts.family or "transducer").lower()
            if family == "transducer":
                enc, dec, jn = _pick(d, "encoder"), _pick(d, "decoder"), _pick(d, "joiner")
                if not (enc and dec and jn):
                    self._reason = f"ASR transducer 模型文件不全：{d}"
                    return False
                self._recognizer = sherpa_onnx.OnlineRecognizer.from_transducer(
                    encoder=str(enc), decoder=str(dec), joiner=str(jn), **common)
            elif family == "paraformer":
                enc, dec = _pick(d, "encoder"), _pick(d, "decoder")
                if not (enc and dec):
                    self._reason = f"ASR paraformer 模型文件不全：{d}"
                    return False
                self._recognizer = sherpa_onnx.OnlineRecognizer.from_paraformer(
                    encoder=str(enc), decoder=str(dec), **common)
            elif family in ("zipformer-ctc", "ctc"):
                model = _pick(d, "model")
                if model is None:
                    self._reason = f"ASR CTC 模型缺 model*.onnx：{d}"
                    return False
                self._recognizer = sherpa_onnx.OnlineRecognizer.from_zipformer2_ctc(
                    model=str(model), **common)
            elif family == "wenet":
                model = _pick(d, "model")
                if model is None:
                    self._reason = f"ASR WeNet 模型缺 model*.onnx：{d}"
                    return False
                self._recognizer = sherpa_onnx.OnlineRecognizer.from_wenet_ctc(
                    model=str(model), **common)
            elif family == "nemo":
                model = _pick(d, "model")
                if model is None:
                    self._reason = f"ASR NeMo 模型缺 model*.onnx：{d}"
                    return False
                self._recognizer = sherpa_onnx.OnlineRecognizer.from_nemo_ctc(
                    model=str(model), **common)
            elif family == "t-one":
                model = _pick(d, "model")
                if model is None:
                    self._reason = f"ASR T-One 模型缺 model*.onnx：{d}"
                    return False
                self._recognizer = sherpa_onnx.OnlineRecognizer.from_t_one_ctc(
                    model=str(model), **common)
            else:
                self._reason = (
                    f"暂不支持该 sherpa-onnx ASR 家族：{family}（{d.name}）。"
                    "当前支持 transducer / paraformer / zipformer-ctc / wenet / nemo / t-one。"
                )
                return False

            self._reason = ""
            logger.info("本地 ASR 就绪：{}（family={}, provider={}）",
                        d.name, family, provider)
            return True
        except Exception as e:  # noqa: BLE001
            self._reason = f"ASR 加载失败: {e}"
            self._recognizer = None
            return False

    def available(self) -> bool:
        """是否可用（会触发加载）。Whether usable (triggers loading)."""
        return self._load()

    def status(self) -> tuple[bool, str]:
        """(可用, 人话原因)。(available, human-readable reason)."""
        if self._load():
            return True, ""
        return False, self._reason or "本地 ASR 不可用"

    def create_session(self) -> "AsrSession":
        """创建一个连接级识别流。Create a per-connection recognizer stream."""
        if not self._load() or self._recognizer is None:
            raise AsrError(self._reason or "本地 ASR 不可用")
        stream = self._recognizer.create_stream()
        return AsrSession(self, stream)

    def transcribe(self, samples: np.ndarray, sample_rate: int) -> str:
        """整段 PCM → 文本（阻塞；调用方放线程池）。Whole PCM → text (blocking)."""
        session = self.create_session()
        try:
            session.accept(samples, sample_rate)
            return session.finish()
        finally:
            session.close()


class AsrSession:
    """一个 WebSocket/调用的独立解码流。One independent decode stream."""

    def __init__(self, engine: StreamingAsrEngine, stream: Any) -> None:
        self.engine = engine
        self._stream = stream
        self._finished = False

    def accept(self, samples: np.ndarray, sample_rate: int) -> None:
        """喂入 PCM；采样率由 sherpa 内部重采样。Feed PCM; sherpa resamples internally."""
        if self._finished:
            return
        arr = np.asarray(samples, dtype=np.float32)
        if arr.size:
            self._stream.accept_waveform(int(sample_rate), arr.tolist())

    def decode(self) -> str:
        """解码当前可用的块并返回最新文本。Decode ready chunks and return the latest text."""
        engine = self.engine
        rec = engine._recognizer
        if rec is None:
            return ""
        with engine._lock:
            while rec.is_ready(self._stream):
                rec.decode_stream(self._stream)
            return str(rec.get_result(self._stream) or "")

    def text(self) -> str:
        """当前文本（不解码）。Current text without decoding."""
        rec = self.engine._recognizer
        if rec is None:
            return ""
        return str(rec.get_result(self._stream) or "")

    def is_endpoint(self) -> bool:
        """是否到达端点。Whether an endpoint was reached."""
        rec = self.engine._recognizer
        return bool(rec is not None and rec.is_endpoint(self._stream))

    def reset(self) -> None:
        """端点后复位，准备下一句。Reset after an endpoint, ready for the next sentence."""
        rec = self.engine._recognizer
        if rec is not None:
            rec.reset(self._stream)

    def finish(self) -> str:
        """结束输入并取最终文本（只可调用一次）。Finish input and take the final text."""
        if self._finished:
            return self.text()
        self._finished = True
        self._stream.input_finished()
        return self.decode()

    def close(self) -> None:
        """标记结束（底层流随会话回收）。Mark finished (the underlying stream is GC'd)."""
        self._finished = True
