# -*- coding: utf-8 -*-
"""语音模块 — ASR / TTS（OpenAI 兼容多提供方，async httpx）

Voice module — ASR / TTS (OpenAI-compatible multi-provider, async httpx).

- ASR:  POST {endpoint}{chat_path} + messages[0].content input_audio（OpenAI 兼容）
- TTS:  POST {endpoint}{chat_path} + {"model","input","voice"}，响应为二进制音频

- ASR:  POST {endpoint}{chat_path} + messages[0].content input_audio (OpenAI compatible)
- TTS:  POST {endpoint}{chat_path} + {"model","input","voice"}; the response is binary audio
"""
import os
import tempfile

import httpx

from core.config import add_reload_hook, is_asr_configured, is_tts_enabled, resolve_asr_profile, resolve_tts_profile
from core.logger import logger


class ASRClient:
    """ASR 语音识别客户端（OpenAI 兼容，async）

    ASR speech recognition client (OpenAI-compatible, async).

    profile.compat 兼容开关（来自厂商预设，默认不影响既有行为）：
    - auth_header: "api-key"  用 api-key 头认证（小米 MiMo ASR 要求；默认 Bearer）
    - audio_data_url: true    input_audio.data 加 "data:{mime};base64," 前缀
    - send_language: true     请求体带 asr_options.language（提升指定语种准确率）

    Compatibility switches in profile.compat (from vendor presets; defaults keep existing behavior):
    - auth_header: "api-key"  authenticate with the api-key header (required by Xiaomi MiMo ASR; default is Bearer)
    - audio_data_url: true    prefix input_audio.data with "data:{mime};base64,"
    - send_language: true     include asr_options.language in the request body (boosts accuracy for the given language)
    """

    def __init__(self):
        """初始化 ASR 客户端，从当前 profile 读取配置。

        Initialize the ASR client, reading configuration from the current profile.
        """
        self.profile_name, p = resolve_asr_profile()
        self.provider = p.get("provider", "openai")
        self.endpoint = p.get("endpoint", "")
        self.api_key = p.get("api_key", "")
        self.model = p.get("model", "")
        self.language = p.get("language", "zh")
        self.timeout = p.get("timeout", 60)
        self.chat_path = p.get("chat_path") or "/v1/chat/completions"  # 空串也回退默认
        self.compat = p.get("compat") or {}

        if self.profile_name:
            logger.info("ASR profile '{}'（provider={}, model={}）",
                        self.profile_name, self.provider, self.model)

    @property
    def _headers(self) -> dict:
        """构建请求头：默认 Bearer 认证，兼容开关可改用 api-key。

        Build request headers: Bearer auth by default, or the api-key header when the compat switch is set.
        """
        h = {"Content-Type": "application/json"}
        if self.api_key:
            if self.compat.get("auth_header") == "api-key":
                h["api-key"] = self.api_key
            else:
                h["Authorization"] = f"Bearer {self.api_key}"
        return h

    def available(self) -> bool:
        """ASR 是否已配置可用。

        Whether the ASR service is configured and available.
        """
        return is_asr_configured()

    async def transcribe_base64(self, audio_base64: str, audio_format: str = "wav") -> str:
        """调用 OpenAI 兼容 ASR（chat completions + input_audio）。

        Call the OpenAI-compatible ASR endpoint (chat completions + input_audio).

        Args:
            audio_base64: 音频数据的 base64 编码。 / The base64-encoded audio data.
            audio_format: 音频格式，如 "wav"、"mp3"。 / Audio format, e.g. "wav" or "mp3".

        Returns:
            识别出的文本。 / The recognized text.
        """
        url = f"{self.endpoint.rstrip('/')}{self.chat_path}"
        audio = audio_base64
        if self.compat.get("audio_data_url"):
            mime = "audio/mpeg" if audio_format in ("mp3", "mpeg") else "audio/wav"
            audio = f"data:{mime};base64,{audio_base64}"
        body = {
            "model": self.model,
            "messages": [{
                "role": "user",
                "content": [
                    {"type": "input_audio", "input_audio": {"data": audio, "format": audio_format}}
                ]
            }],
            "max_tokens": 1024,
        }
        if self.compat.get("send_language") and self.language:
            body["asr_options"] = {"language": self.language}
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(url, json=body, headers=self._headers)
            resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"].strip()


class TTSClient:
    """TTS 语音合成（OpenAI 兼容，async）。

    TTS speech synthesis (OpenAI-compatible, async).
    """

    def __init__(self):
        """初始化 TTS 客户端，从当前 profile 读取配置。

        Initialize the TTS client, reading configuration from the current profile.
        """
        self.profile_name, p = resolve_tts_profile()
        self.provider = p.get("provider", "openai")
        self.endpoint = p.get("endpoint", "").rstrip("/")
        self.api_key = p.get("api_key", "")
        self.model = p.get("model", "tts-1")
        self.voice = p.get("voice", "alloy")
        self.timeout = p.get("timeout", 30)
        self.chat_path = p.get("chat_path") or "/v1/audio/speech"  # 空串也回退默认

    def available(self) -> bool:
        """TTS 是否已启用。

        Whether TTS is enabled.
        """
        return is_tts_enabled()

    async def speak(self, text: str) -> bool:
        """合成并播放语音；失败时记录警告并返回 False。

        Synthesize and play speech; log a warning and return False on failure.

        Args:
            text: 要合成的文本。 / The text to synthesize.

        Returns:
            是否播放成功。 / True if playback succeeded.
        """
        if not self.available():
            return False
        try:
            return await self._speak(text)
        except Exception as e:
            logger.warning("TTS 失败: {}", e)
            return False

    async def _speak(self, text: str) -> bool:
        """调用 OpenAI 兼容 TTS 端点并播放返回的音频。

        Call the OpenAI-compatible TTS endpoint and play the returned audio.

        Args:
            text: 要合成的文本（最多取前 500 字符）。 / The text to synthesize (capped at the first 500 characters).

        Returns:
            是否播放成功。 / True if playback succeeded.
        """
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
    """把 TTS 音频写入临时文件并打开播放（Windows）。

    Write TTS audio to a temporary file and open it for playback (Windows).

    Args:
        data: TTS 返回的音频字节。 / The audio bytes returned by TTS.

    Returns:
        恒为 True。 / Always True.
    """
    import subprocess
    tmp = os.path.join(tempfile.gettempdir(), "tts_out.mp3")
    with open(tmp, "wb") as f:
        f.write(data)
    subprocess.Popen(["start", tmp], shell=True)
    return True


def get_asr() -> ASRClient:
    """返回容器持有的全局 ASR 客户端（测试可 monkeypatch 本函数）。

    Return the global ASR client held by the container (tests may monkeypatch this function).
    """
    from core.container import AppContext
    return AppContext.get().asr()


def get_tts() -> TTSClient:
    """返回容器持有的全局 TTS 客户端（测试可 monkeypatch 本函数）。

    Return the global TTS client held by the container (tests may monkeypatch this function).
    """
    from core.container import AppContext
    return AppContext.get().tts()


def _reset_clients() -> None:
    """配置热重载后清空语音客户端，下次访问用新 profile 重建。

    Clear voice clients after a config hot-reload so the next access rebuilds them with the new profile.
    """
    from core.container import AppContext
    AppContext.get().reset_voice()


add_reload_hook(_reset_clients)
