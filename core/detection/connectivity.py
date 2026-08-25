# -*- coding: utf-8 -*-
"""连通性检测 — LLM / ASR / TTS（从 main.py 迁入并新增 TTS）"""
import asyncio
import base64
import io
import time
import wave
from dataclasses import dataclass

from core import config
from core.logger import logger


@dataclass
class CheckResult:
    name: str
    status: str  # ok / skip / fail
    latency_ms: int | None = None
    detail: str = ""

    @property
    def ok(self) -> bool:
        return self.status == "ok"

    def as_dict(self) -> dict:
        return {"name": self.name, "status": self.status,
                "latency_ms": self.latency_ms, "detail": self.detail}


def _silence_wav_base64(seconds: float = 0.3, rate: int = 16000) -> str:
    """生成一小段静音 WAV 的 base64（ASR 连通性测试，无需真实语音）。"""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"\x00\x00" * int(rate * seconds))
    return base64.b64encode(buf.getvalue()).decode("utf-8")


async def check_llm(timeout: int = 8) -> CheckResult:
    """LLM 连通性：stream_chat 消费 done 事件。"""
    from core.llm.stream import stream_chat
    if not config.is_llm_configured():
        return CheckResult("LLM", "skip", detail="未配置（endpoint/model 缺失）")
    _, profile = config.resolve_llm_profile()
    profile = dict(profile, timeout=timeout)
    messages = [
        {"role": "system", "content": "你是一个测试助手。"},
        {"role": "user", "content": "请只回复两个字：连通"},
    ]
    start = time.monotonic()
    try:
        async for evt in stream_chat(messages, profile=profile):
            if evt["type"] == "done":
                content = (evt["message"].get("content") or "").strip()
                return CheckResult("LLM", "ok", latency_ms=int((time.monotonic() - start) * 1000),
                                   detail=content[:80] or "(空回复)")
        return CheckResult("LLM", "fail", detail="LLM 返回空消息")
    except Exception as e:
        logger.error("LLM 连通性检测失败: {}", e)
        return CheckResult("LLM", "fail", detail=f"{type(e).__name__}: {e}")


async def check_asr(timeout: int = 30) -> CheckResult:
    """ASR 连通性：静音 WAV base64 过一遍链路。"""
    if not config.is_asr_configured():
        return CheckResult("ASR", "skip", detail="未配置（endpoint/model 缺失）")
    from core.voice import get_asr
    asr = get_asr()
    start = time.monotonic()
    try:
        text = await asr.transcribe_base64(_silence_wav_base64(), "wav")
        return CheckResult("ASR", "ok", latency_ms=int((time.monotonic() - start) * 1000),
                           detail=text.strip()[:80] or "(空文本，链路已通)")
    except Exception as e:
        logger.error("ASR 连通性检测失败: {}", e)
        return CheckResult("ASR", "fail", detail=f"{type(e).__name__}: {e}")


async def check_tts(timeout: int = 30) -> CheckResult:
    """TTS 连通性：合成一小段语音。"""
    if not config.is_tts_enabled():
        return CheckResult("TTS", "skip", detail="未启用（voice.tts.enabled=false 或未配置）")
    from core.tts import synthesize
    start = time.monotonic()
    try:
        audio, _ = await synthesize("连通测试")
        return CheckResult("TTS", "ok", latency_ms=int((time.monotonic() - start) * 1000),
                           detail=f"{len(audio)} 字节")
    except Exception as e:
        logger.error("TTS 连通性检测失败: {}", e)
        return CheckResult("TTS", "fail", detail=f"{type(e).__name__}: {e}")


async def run_checks() -> list[CheckResult]:
    """并行跑三项连通性检测。"""
    llm, asr, tts = await asyncio.gather(check_llm(), check_asr(), check_tts())
    return [llm, asr, tts]
