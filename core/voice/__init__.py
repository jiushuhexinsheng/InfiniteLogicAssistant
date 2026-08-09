# -*- coding: utf-8 -*-
"""语音模块 — ASR / TTS（OpenAI 兼容多提供方，async httpx）

- ASR:  POST {endpoint}{chat_path} + messages[0].content input_audio（OpenAI 兼容）
- TTS:  POST {endpoint}{chat_path} + {"model","input","voice"}，响应为二进制音频
"""
import os
import tempfile

import httpx

from core.config import is_asr_configured, is_tts_enabled, resolve_asr_profile, resolve_tts_profile
from core.logger import logger


class ASRClient:
    """ASR 语音识别客户端（OpenAI 兼容，async）"""

    def __init__(self):
        self.profile_name, p = resolve_asr_profile()
        self.provider = p.get("provider", "openai")
        self.endpoint = p.get("endpoint", "")
        self.api_key = p.get("api_key", "")
        self.model = p.get("model", "")
        self.language = p.get("language", "zh")
        self.timeout = p.get("timeout", 60)
        self.chat_path = p.get("chat_path", "/v1/chat/completions")

        if self.profile_name:
            logger.info("ASR profile '{}'（provider={}, model={}）",
                        self.profile_name, self.provider, self.model)

    @property
    def _headers(self) -> dict:
        h = {"Content-Type": "application/json"}
        if self.api_key:
            h["Authorization"] = f"Bearer {self.api_key}"
        return h

    def available(self) -> bool:
        return is_asr_configured()

    async def transcribe_base64(self, audio_base64: str, audio_format: str = "wav") -> str:
        """调用 OpenAI 兼容 ASR（chat completions + input_audio）"""
        url = f"{self.endpoint.rstrip('/')}{self.chat_path}"
        body = {
            "model": self.model,
            "messages": [{
                "role": "user",
                "content": [
                    {"type": "input_audio", "input_audio": {"data": audio_base64, "format": audio_format}}
                ]
            }],
            "max_tokens": 1024,
        }
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(url, json=body, headers=self._headers)
            resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"].strip()


class TTSClient:
    """TTS 语音合成（OpenAI 兼容，async）"""

    def __init__(self):
        self.profile_name, p = resolve_tts_profile()
        self.provider = p.get("provider", "openai")
        self.endpoint = p.get("endpoint", "").rstrip("/")
        self.api_key = p.get("api_key", "")
        self.model = p.get("model", "tts-1")
        self.voice = p.get("voice", "alloy")
        self.timeout = p.get("timeout", 30)
        self.chat_path = p.get("chat_path", "/v1/audio/speech")

    def available(self) -> bool:
        return is_tts_enabled()

    async def speak(self, text: str) -> bool:
        if not self.available():
            return False
        try:
            return await self._speak(text)
        except Exception as e:
            logger.warning("TTS 失败: {}", e)
            return False

    async def _speak(self, text: str) -> bool:
        url = f"{self.endpoint}{self.chat_path}"
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        body = {"model": self.model, "input": text[:500], "voice": self.voice}
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(url, json=body, headers=headers)
            resp.raise_for_status()
        return _play_audio(resp.content)


def _play_audio(data: bytes) -> bool:
    """把 TTS 音频写入临时文件并打开播放（Windows）"""
    import subprocess
    tmp = os.path.join(tempfile.gettempdir(), "tts_out.mp3")
    with open(tmp, "wb") as f:
        f.write(data)
    subprocess.Popen(["start", tmp], shell=True)
    return True


# 全局单例
_asr: ASRClient | None = None
_tts: TTSClient | None = None


def get_asr() -> ASRClient:
    global _asr
    if _asr is None:
        _asr = ASRClient()
    return _asr


def get_tts() -> TTSClient:
    global _tts
    if _tts is None:
        _tts = TTSClient()
    return _tts
