# -*- coding: utf-8 -*-
"""本地 KWS 前置闸门 — sherpa-onnx 关键词检测（拼音 tokens，发音级）

流水线位置：VAD 分段 → **KWS（本地）** → 命中才调云端 ASR 抬取指令 → 文本拼音判定切指令。
- 未命中 → 直接丢弃：背景媒体声/闲聊不上传、不花钱（这正是审计日志里「影视剧台词
  幻觉」问题的解药）
- 命中 → KWS 管「是不是我们的词」（听音，句中提及也会命中），文本层句首规则管
  「是不是在唤醒」（防 TTS 回声循环）—— 两层各管一半
- 引擎不可用（模型缺失/加载失败）→ 闸门自动旁路，回退纯云端判定，不阻塞唤醒

关键词文件由 `voice.wake_word.keywords` 配置经 text2token（ppinyin）生成，改唤醒词
无需手工编 token。

Local KWS pre-gate — sherpa-onnx keyword spotting (pinyin tokens, pronunciation level).
Pipeline: VAD segment → **KWS (local)** → only hits call cloud ASR for command extraction
→ text pinyin matching splits the command. Misses are dropped outright: background media
and chatter never upload or cost money (the antidote to the "TV-drama hallucination"
lines in the audit log). KWS decides "is it our word" (sound-level; mid-sentence mentions
hit too); the text-layer leading rule decides "is it a wake" (anti-echo). When the engine
is unavailable the gate auto-bypasses to pure cloud judging — it never blocks wake.
"""
import struct
import wave
from pathlib import Path
from typing import Any

from core import config
from core.config import add_reload_hook
from core.logger import logger

# sherpa 重采样器输出率；KWS 模型按 16kHz 特征训练。KWS models are trained on 16kHz features.
_TARGET_SR = 16000


class KwsGate:
    """sherpa-onnx 关键词检测闸门（懒加载单例，配置热重载后重建）。

    Keyword-spotting gate (lazy singleton, rebuilt on config reload).
    """

    def __init__(self) -> None:
        """惰性状态：spotter 未加载前 is_available() 为 False。Lazy state: unavailable until loaded."""
        self._spotter: Any | None = None  # sherpa_onnx.KeywordSpotter（延迟导入）
        self._loaded = False
        self._keywords: list[str] = []

    def _load(self) -> bool:
        """加载模型与关键词文件；任何失败都记日志并保持不可用（闸门旁路）。

        Load the model and keywords file; any failure logs and stays unavailable
        (the gate bypasses).
        """
        if self._loaded:
            return self._spotter is not None
        self._loaded = True
        try:
            cfg = config.settings.voice.kws
            if not cfg.enabled:
                logger.info("KWS 闸门已禁用（voice.kws.enabled=false）")
                return False
            d = Path(cfg.model_dir)
            if not d.is_absolute():
                d = config.ROOT_DIR / d
            tokens = d / "tokens.txt"
            if not tokens.is_file():
                logger.info("KWS 模型不存在（{}），闸门旁路（纯云端判定）", d)
                return False

            # 关键词文件：配置的唤醒词 → ppinyin tokens（随配置重建，改词即时生效）
            # Keywords file: configured wake words → ppinyin tokens (rebuilt per config).
            from sherpa_onnx.utils import text2token

            keywords = config.settings.voice.wake_word.keywords
            encoded = text2token(keywords, tokens=str(tokens), tokens_type="ppinyin")
            kw_lines = [" ".join(map(str, toks)) + f" @{word}"
                        for toks, word in zip(encoded, keywords)]
            kw_path = d / "keywords.generated.txt"
            kw_path.write_text("\n".join(kw_lines) + "\n", encoding="utf-8")

            import sherpa_onnx

            enc = self._pick(d, "encoder-epoch-12-avg-2-chunk-16-left-64.int8.onnx")
            dec = self._pick(d, "decoder-epoch-12-avg-2-chunk-16-left-64.onnx")
            jn = self._pick(d, "joiner-epoch-12-avg-2-chunk-16-left-64.int8.onnx")
            self._spotter = sherpa_onnx.KeywordSpotter(
                tokens=str(tokens), encoder=str(enc), decoder=str(dec), joiner=str(jn),
                keywords_file=str(kw_path),
                keywords_threshold=cfg.keywords_threshold,
                keywords_score=cfg.keywords_score,
                num_threads=2,
            )
            self._keywords = list(keywords)
            logger.info("KWS 闸门就绪：关键词 {}（阈值 {}）", self._keywords, cfg.keywords_threshold)
            return True
        except Exception as e:
            logger.warning("KWS 加载失败，闸门旁路: {}", e)
            self._spotter = None
            return False

    @staticmethod
    def _pick(d: Path, name: str) -> Path:
        """取模型文件（int8 优先由调用方文件名决定；不存在时报错）。
        Take a model file (the caller decides int8; raise when missing)."""
        p = d / name
        if not p.is_file():
            raise FileNotFoundError(f"KWS 模型文件缺失: {p}")
        return p

    def is_available(self) -> bool:
        """闸门是否可用（模型已加载）。Whether the gate is available (model loaded)."""
        return self._load()

    def detect_wav_bytes(self, wav: bytes) -> bool | None:
        """判定一段 WAV 音频里有没有唤醒词（发音级）—— 三态。

        True  命中（音频里听到了唤醒词，发音级）
        False 未命中（音频里没有，直接丢弃、不上云）
        None  旁路（引擎不可用/音频解析失败/检测异常）—— 放行交云端判定，但
              **不构成音频判定**（调用方不得据此触发「音频优先」规则）

        兼容任意采样率/声道（sherpa 自带重采样器）。

        Decide whether a WAV clip contains a wake word (pronunciation level) —
        three-valued. True = hit (the wake word was heard); False = miss (drop the
        clip, no cloud call); None = bypass (engine unavailable / parse failure /
        detection error) — the clip proceeds to cloud judging but is **not** an
        audio verdict (callers must not trigger the "audio-first" rule on it).
        """
        if not self._load():
            return None  # 闸门不可用 → 旁路 / gate unavailable → bypass
        try:
            sr, samples = _wav_to_mono_float(wav)
        except Exception as e:
            logger.warning("KWS 音频解析失败，本段旁路交云端判定: {}", e)
            return None
        if not samples:
            return False  # 空音频：合理丢弃 / empty audio: drop
        sp = self._spotter
        if sp is None:
            return None  # 双保险 / belt and braces
        try:
            stream = sp.create_stream()
            stream.accept_waveform(sr, samples)
            stream.input_finished()
            while sp.is_ready(stream):
                sp.decode_stream(stream)
                r = sp.get_result(stream)
                if r:
                    sp.reset_stream(stream)
                    return True
            return False
        except Exception as e:
            logger.warning("KWS 检测异常，本段旁路交云端判定: {}", e)
            return None


def _wav_to_mono_float(data: bytes) -> tuple[float, list[float]]:
    """WAV bytes → (sample_rate, 单声道 float32 采样)。WAV bytes → (sample_rate, mono float32 samples)."""
    import io

    with wave.open(io.BytesIO(data), "rb") as w:
        sr = w.getframerate()
        nch, sw = w.getnchannels(), w.getsampwidth()
        raw = w.readframes(w.getnframes())
    if sw == 2:
        samples = struct.unpack(f"<{len(raw)//2}h", raw)
        floats = [s / 32768.0 for s in samples]
    elif sw == 1:
        floats = [(b - 128) / 128.0 for b in raw]
    elif sw == 4:
        samples = struct.unpack(f"<{len(raw)//4}i", raw)
        floats = [s / 2147483648.0 for s in samples]
    else:
        raise ValueError(f"不支持的 WAV 采样宽度: {sw}")
    if nch > 1:
        floats = floats[::nch]  # 取首声道 / take the first channel
    return float(sr), floats


_gate: KwsGate | None = None


def get_kws() -> KwsGate:
    """取全局闸门单例（配置热重载后重建）。Get the global gate singleton (rebuilt on reload)."""
    global _gate
    if _gate is None:
        _gate = KwsGate()
    return _gate


def _reset_kws() -> None:
    """配置热重载时丢弃闸门，下次访问重建。Drop the gate on config reload; rebuilt on next access."""
    global _gate
    _gate = None


add_reload_hook(_reset_kws)
