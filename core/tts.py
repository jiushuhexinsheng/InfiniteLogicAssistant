# -*- coding: utf-8 -*-
"""TTS 语音合成 — 支持两种 OpenAI 兼容协议：
- speech：POST /v1/audio/speech，body {model, input, voice}，直接返回音频字节
- chat  ：POST /v1/chat/completions，messages + audio{format, voice}，
          音频在 choices[0].message.audio.data（base64）—— 用于 MiMo TTS 系列：
          - mimo-v2.5-tts（预置音色）：voice = 内置音色名（如 Chloe / mimo_default）
          - mimo-v2.5-tts-voiceclone（音色复刻）：voice = 参考音频 base64（需 voice_ref）
          - mimo-v2.5-tts-voicedesign（音色描述）：voice 不支持，user 消息给风格描述
"""
import base64
from pathlib import Path

import httpx

from core.config import is_tts_enabled, resolve_tts_profile
from core.logger import logger

# 输出格式 → 媒体类型
_MEDIA_TYPES = {"wav": "audio/wav", "mp3": "audio/mpeg", "pcm16": "audio/pcm"}


class TtsConfigError(RuntimeError):
    """TTS 配置错误（未启用 / 缺 voice_ref 等）。API 层映射为 400，非服务端故障。"""


async def synthesize(text: str, voice: str | None = None) -> tuple[bytes, str]:
    """调用配置的 TTS 端点合成语音，返回 (音频字节, media_type)。

    按 profile.chat_path 自动选择协议：含 'chat/completions' → chat 模式，否则 speech 模式。
    配置错误抛 TtsConfigError；网络/端点错误抛 RuntimeError。
    """
    if not is_tts_enabled():
        raise TtsConfigError(
            "TTS 未启用：voice.tts.enabled=false 或未配置 endpoint。"
            "如需后端 TTS 请在 config.yaml 配置，否则保持关闭（浏览器本地语音播报）"
        )
    if not text.strip():
        raise RuntimeError("合成文本为空")

    _, profile = resolve_tts_profile()
    path = profile.get("chat_path") or "/v1/audio/speech"
    if "chat/completions" in path:
        return await _synthesize_chat(text, profile, voice)
    return await _synthesize_speech(text, voice, profile)


def _build_url(profile: dict, path: str) -> str:
    endpoint = (profile.get("endpoint") or "").rstrip("/")
    return f"{endpoint}{path if path.startswith('/') else '/' + path}"


def _build_headers(profile: dict) -> dict:
    api_key = profile.get("api_key") or ""
    return {"Authorization": f"Bearer {api_key}"} if api_key else {}


async def _post(profile: dict, path: str, payload: dict) -> httpx.Response:
    url = _build_url(profile, path)
    timeout = float(profile.get("timeout") or 30)
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            r = await client.post(url, json=payload, headers=_build_headers(profile))
    except httpx.HTTPError as e:
        logger.error("TTS 请求失败: {}", e)
        raise RuntimeError(f"TTS 请求失败: {e}") from e
    if r.status_code != 200:
        logger.error("TTS 端点返回 {}: {}", r.status_code, r.text[:300])
        raise RuntimeError(f"TTS 端点错误 {r.status_code}: {r.text[:300]}")
    return r


def _audio_data_url(p: Path) -> str:
    """参考音频 → data URL（mp3/wav，VoiceClone 必需）"""
    suffix = p.suffix.lower()
    mime = "audio/wav" if suffix == ".wav" else ("audio/mpeg" if suffix in (".mp3", ".mpeg") else "audio/wav")
    b64 = base64.b64encode(p.read_bytes()).decode()
    return f"data:{mime};base64,{b64}"


async def _synthesize_chat(text: str, profile: dict, voice: str | None = None) -> tuple[bytes, str]:
    """MiMo TTS 系列：chat completions + audio.voice。

    voiceclone 模型 → voice = 参考音频 base64（需 voice_ref）；
    标准/预置音色模型（mimo-v2.5-tts）→ voice = 内置音色名。
    优先使用前端显式传入的 voice（UI 音色切换），其次配置 voice，空则默认 mimo_default。
    """
    model = profile.get("model") or "mimo-v2.5-tts"
    fmt = profile.get("format") or "wav"
    audio_cfg: dict = {"format": fmt}
    if "voiceclone" in model:
        voice_ref = profile.get("voice_ref") or ""
        ref = Path(voice_ref)
        # 用 is_file() 而非 exists()：空路径 Path('') 会解析成 '.'（目录），exists() 恒为 True
        if not voice_ref or not ref.is_file():
            raise TtsConfigError(
                f"voiceclone 需要 voice_ref 参考音频（当前: {voice_ref!r}）。"
                "请在 config.yaml 的 voice.tts.profiles.openai.voice_ref 配置一个 mp3/wav 样本（≤10MB），"
                "或将 voice.tts.enabled 设为 false 使用浏览器本地语音播报"
            )
        audio_cfg["voice"] = _audio_data_url(ref)
    else:
        # 前端传入 > 配置 voice > 默认 mimo_default
        audio_cfg["voice"] = (voice or "").strip() or (profile.get("voice") or "").strip() or "mimo_default"
    payload = {
        "model": model,
        "messages": [{"role": "assistant", "content": text}],
        "audio": audio_cfg,
    }
    r = await _post(profile, profile.get("chat_path") or "/v1/chat/completions", payload)
    try:
        data = r.json()["choices"][0]["message"]["audio"]["data"]
    except (KeyError, IndexError, ValueError) as e:
        raise RuntimeError(f"TTS 响应解析失败: {r.text[:300]}") from e
    audio = base64.b64decode(data)
    return audio, _MEDIA_TYPES.get(fmt, "audio/wav")


async def _synthesize_speech(text: str, voice: str | None, profile: dict) -> tuple[bytes, str]:
    """OpenAI /v1/audio/speech：{model, input, voice}"""
    use_voice = voice or profile.get("voice") or "alloy"
    payload = {
        "model": profile.get("model") or "tts-1",
        "input": text,
        "voice": use_voice,
    }
    r = await _post(profile, profile.get("chat_path") or "/v1/audio/speech", payload)
    return r.content, "audio/mpeg"
