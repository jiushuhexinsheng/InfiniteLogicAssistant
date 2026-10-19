# -*- coding: utf-8 -*-
"""Zipformer KWS 包装（sherpa-onnx 关键词检测，拼音 tokens）。

Zipformer KWS wrapper (sherpa-onnx keyword spotting, pinyin tokens).

关键词文件按「模型 + 关键词列表」哈希落在 ``data/generated/kws/``，**不写进模型目录**：
模型目录可能是只读的，而且同一模型会被多组关键词复用。
The keywords file is generated under ``data/generated/kws/`` keyed by model + keyword
list — never written into the model directory (which may be read-only and shared by
several keyword sets).
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from core import config
from core.logger import logger
from core.voice.local.sherpa_onnx import audio, hardware


@dataclass(frozen=True)
class KwsOptions:
    """KWS 引擎参数。KWS engine options."""

    model_dir: str
    keywords: tuple[str, ...] = ()
    provider: str = "cpu"
    device: int = 0
    num_threads: int = 2
    threshold: float = 0.25
    score: float = 1.0
    sample_rate: int = audio.SAMPLE_RATE


class KwsError(RuntimeError):
    """KWS 加载/推理失败。KWS load/inference failure."""


class KwsEngine:
    """懒加载的 KWS 引擎。Lazily loaded KWS engine."""

    def __init__(self, opts: KwsOptions) -> None:
        self.opts = opts
        self._spotter: Any | None = None
        self._loaded = False
        self._reason = ""

    # ── 模型文件 ──

    @staticmethod
    def _pick(d: Path, kind: str, *, prefer_int8: bool = True) -> Path | None:
        """按前缀挑文件（int8 优先）。Pick a model file by prefix (int8 preferred)."""
        cands = sorted(d.glob(f"{kind}-*.onnx")) or sorted(d.glob(f"{kind}*.onnx"))
        if not cands:
            return None
        if prefer_int8:
            i8 = [c for c in cands if ".int8." in c.name]
            if i8:
                return i8[0]
        return cands[0]

    def _model_dir(self) -> Path:
        d = Path(self.opts.model_dir)
        if not d.is_absolute():
            d = Path(config.ROOT_DIR) / d
        return d

    def _keywords_file(self, d: Path, tokens: Path) -> Path:
        """按模型 + 关键词生成稳定的关键词文件。Generate a stable keywords file."""
        keywords = tuple(k for k in self.opts.keywords if k and k.strip())
        if not keywords:
            raise KwsError("未配置唤醒词")
        digest = hashlib.sha1(
            ("\n".join(keywords) + "|" + str(d.resolve())).encode("utf-8")
        ).hexdigest()[:16]
        out_dir = Path(config.ROOT_DIR) / "data" / "generated" / "kws"
        out_dir.mkdir(parents=True, exist_ok=True)
        out = out_dir / f"keywords-{digest}.txt"

        from sherpa_onnx.utils import text2token  # type: ignore[import-untyped]
        encoded = text2token(list(keywords), tokens=str(tokens), tokens_type="ppinyin")
        lines = [
            " ".join(map(str, toks)) + f" @{word}"
            for toks, word in zip(encoded, keywords)
        ]
        out.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return out

    # ── 生命周期 ──

    def _load(self) -> bool:
        if self._loaded:
            return self._spotter is not None
        self._loaded = True
        try:
            import sherpa_onnx  # type: ignore[import-untyped]

            d = self._model_dir()
            tokens = d / "tokens.txt"
            if not tokens.is_file():
                self._reason = f"KWS 模型目录不存在或缺 tokens.txt：{d}"
                return False
            enc = self._pick(d, "encoder")
            dec = self._pick(d, "decoder")
            jn = self._pick(d, "joiner")
            if enc is None or dec is None or jn is None:
                self._reason = f"KWS 模型文件不全（缺 encoder/decoder/joiner）：{d}"
                return False

            kw_path = self._keywords_file(d, tokens)
            provider = hardware.resolve_provider(self.opts.provider)
            self._spotter = sherpa_onnx.KeywordSpotter(
                tokens=str(tokens),
                encoder=str(enc),
                decoder=str(dec),
                joiner=str(jn),
                keywords_file=str(kw_path),
                keywords_threshold=float(self.opts.threshold),
                keywords_score=float(self.opts.score),
                num_threads=hardware.resolve_threads(self.opts.num_threads),
                provider=provider,
                device=int(self.opts.device),
            )
            self._reason = ""
            logger.info("KWS 就绪：{}（provider={}）", d.name, provider)
            return True
        except Exception as e:  # noqa: BLE001
            self._reason = f"KWS 加载失败: {e}"
            self._spotter = None
            return False

    def available(self) -> bool:
        """是否可用（会触发加载）。Whether usable (triggers loading)."""
        return self._load()

    def status(self) -> tuple[bool, str]:
        """(可用, 人话原因)。(available, human-readable reason)."""
        if self._load():
            return True, ""
        return False, self._reason or "KWS 不可用"

    # ── 推理 ──

    def detect(self, samples: np.ndarray, sample_rate: int) -> str | None:
        """一段 PCM → 命中的关键词；未命中/不可用返回 None。

        One PCM clip → the matched keyword; None on miss or when unavailable.
        """
        if not self._load() or self._spotter is None:
            return None
        arr = audio.resample_linear(
            np.asarray(samples, dtype=np.float32), sample_rate, self.opts.sample_rate
        )
        if arr.size == 0:
            return None
        try:
            stream = self._spotter.create_stream()
            stream.accept_waveform(self.opts.sample_rate, arr.tolist())
            stream.input_finished()
            while self._spotter.is_ready(stream):
                self._spotter.decode_stream(stream)
                result = self._spotter.get_result(stream)
                if result:
                    self._spotter.reset_stream(stream)
                    return str(result)
            return None
        except Exception as e:  # noqa: BLE001
            logger.warning("KWS 推理失败（本段按未命中）: {}", e)
            return None
