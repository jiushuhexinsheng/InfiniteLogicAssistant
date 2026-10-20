# -*- coding: utf-8 -*-
"""Kokoro TTS 包装（sherpa-onnx OfflineTts）。

Kokoro TTS wrapper (sherpa-onnx OfflineTts).

合成是同步阻塞的，调用方必须放线程池；同一实例的 ``generate`` 用锁串行化。
Synthesis is synchronous and blocking — callers must use a worker thread; ``generate``
is serialised per instance with a lock.
"""
from __future__ import annotations

import os
import shutil
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from core import config
from core.logger import logger
from core.voice.local.sherpa_onnx import audio, hardware


def _ascii_espeak_dir(data_dir: Path) -> Path:
    """把 espeak-ng-data 复制到 ASCII 路径（Windows 上 espeak-ng 不认中文路径）。

    Copy espeak-ng-data to an ASCII path: espeak-ng on Windows cannot open
    non-ASCII paths and silently falls back to /usr/share/espeak-ng-data, which
    makes Kokoro fail at load time. ``C:\\Users\\Public`` is ASCII and writable.
    """
    if os.name != "nt" or str(data_dir).isascii():
        return data_dir
    base = Path(os.environ.get("PUBLIC", r"C:\Users\Public")) / "InfiniteLogicAssistant"
    dest = base / "espeak-ng-data"
    try:
        src_phontab = data_dir / "phontab"
        if not (dest / "phontab").is_file() or (
            src_phontab.is_file()
            and src_phontab.stat().st_mtime > (dest / "phontab").stat().st_mtime
        ):
            base.mkdir(parents=True, exist_ok=True)
            if dest.exists():
                shutil.rmtree(dest)
            shutil.copytree(data_dir, dest)
        return dest
    except Exception as e:  # noqa: BLE001
        logger.warning("espeak-ng 数据目录复制失败（回退原路径）: {}", e)
        return data_dir


@dataclass(frozen=True)
class TtsOptions:
    """TTS 引擎参数。TTS engine options."""

    model_dir: str
    family: str = "kokoro"
    provider: str = "cpu"
    device: int = 0
    num_threads: int = 2
    speaker: int = 0
    speed: float = 1.0
    lang: str = ""
    length_scale: float = 1.0


class TtsError(RuntimeError):
    """TTS 加载/合成失败。TTS load/synthesis failure."""


def _pick_file(d: Path, stem: str, *, prefer_int8: bool = False) -> Path | None:
    """按 stem 挑 onnx（可优先 int8）。Pick an ONNX file by stem (int8 optionally preferred)."""
    cands = sorted(d.glob(f"{stem}*.onnx"))
    if not cands:
        return None
    if prefer_int8:
        i8 = [c for c in cands if ".int8." in c.name]
        if i8:
            return i8[0]
    return cands[0]


class TtsEngine:
    """懒加载的 Kokoro TTS 引擎。Lazily loaded Kokoro TTS engine."""

    def __init__(self, opts: TtsOptions) -> None:
        self.opts = opts
        self._tts: Any | None = None
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
            return self._tts is not None
        self._loaded = True
        try:
            import sherpa_onnx  # type: ignore[import-untyped]

            d = self._model_dir()
            model = _pick_file(d, "model")
            tokens = d / "tokens.txt"
            voices = d / "voices.bin"
            if not voices.is_file():
                alt = d / "voices.txt"
                voices = alt if alt.is_file() else voices
            data_dir = _ascii_espeak_dir(d / "espeak-ng-data")
            dict_dir = d / "dict"
            lexicon = ",".join(str(p) for p in sorted(d.glob("lexicon*.txt")))

            if model is None or not tokens.is_file():
                self._reason = f"TTS 模型目录不存在或缺 model/tokens：{d}"
                return False

            provider = hardware.resolve_provider(self.opts.provider)
            kokoro = sherpa_onnx.OfflineTtsKokoroModelConfig(
                model=str(model),
                voices=str(voices) if voices.is_file() else "",
                tokens=str(tokens),
                lexicon=lexicon,
                data_dir=str(data_dir) if data_dir.is_dir() else "",
                dict_dir=str(dict_dir) if dict_dir.is_dir() else "",
                length_scale=float(self.opts.length_scale),
                # 多语种 Kokoro 的 lang 留空，交给 lexicon/拼音处理；传 'multi'
                # 会被 espeak 当成不存在的 voice 而失败。
                # Keep lang empty for multi-lang Kokoro; 'multi' is not an espeak voice.
                lang=self.opts.lang,
            )
            model_cfg = sherpa_onnx.OfflineTtsModelConfig(
                kokoro=kokoro,
                num_threads=hardware.resolve_threads(self.opts.num_threads),
                provider=provider,
                debug=False,
            )
            tts_cfg = sherpa_onnx.OfflineTtsConfig(
                model=model_cfg,
                max_num_sentences=1,
                silence_scale=0.2,
            )
            self._tts = sherpa_onnx.OfflineTts(tts_cfg)
            self._reason = ""
            logger.info("本地 TTS 就绪：{}（provider={}）", d.name, provider)
            return True
        except Exception as e:  # noqa: BLE001
            self._reason = f"TTS 加载失败: {e}"
            self._tts = None
            return False

    def available(self) -> bool:
        """是否可用（会触发加载）。Whether usable (triggers loading)."""
        return self._load()

    def status(self) -> tuple[bool, str]:
        """(可用, 人话原因)。(available, human-readable reason)."""
        if self._load():
            return True, ""
        return False, self._reason or "本地 TTS 不可用"

    def synthesize(self, text: str) -> tuple[np.ndarray, int]:
        """文本 → (float32 采样, 采样率)。Text → (float32 samples, sample rate)."""
        if not text.strip():
            raise TtsError("合成文本为空")
        if not self._load() or self._tts is None:
            raise TtsError(self._reason or "本地 TTS 不可用")
        with self._lock:
            generated = self._tts.generate(
                text, sid=int(self.opts.speaker), speed=float(self.opts.speed)
            )
        samples = np.asarray(generated.samples, dtype=np.float32)
        return samples, int(generated.sample_rate)

    def synthesize_wav(self, text: str) -> bytes:
        """文本 → 16-bit PCM WAV 字节。Text → 16-bit PCM WAV bytes."""
        samples, sr = self.synthesize(text)
        return audio.write_wav_bytes(samples, sr)
