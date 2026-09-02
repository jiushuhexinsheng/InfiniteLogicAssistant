# -*- coding: utf-8 -*-
"""TTS 语音合成 — 支持两种 OpenAI 兼容协议：
- speech：POST /v1/audio/speech，body {model, input, voice}，直接返回音频字节
- chat  ：POST /v1/chat/completions，messages + audio{format, voice}，
          音频在 choices[0].message.audio.data（base64）—— 用于 MiMo TTS 系列：
          - mimo-v2.5-tts（预置音色）：voice = 内置音色名（如 Chloe / mimo_default）
          - mimo-v2.5-tts-voiceclone（音色复刻）：voice = 参考音频 base64（需 voice_ref）
          - mimo-v2.5-tts-voicedesign（音色描述）：voice 不支持，user 消息给风格描述

TTS speech synthesis — supports two OpenAI-compatible protocols:
- speech: POST /v1/audio/speech, body {model, input, voice}; returns audio bytes directly
- chat  : POST /v1/chat/completions, messages + audio{format, voice};
          audio is in choices[0].message.audio.data (base64) — used for the MiMo TTS family:
          - mimo-v2.5-tts (preset voices): voice = built-in voice name (e.g. Chloe / mimo_default)
          - mimo-v2.5-tts-voiceclone (voice cloning): voice = reference audio base64 (voice_ref required)
          - mimo-v2.5-tts-voicedesign (voice design): voice unsupported; the user message carries the style description
"""
import base64
from pathlib import Path

import httpx

from core.config import is_tts_enabled, resolve_tts_profile
from core.logger import logger

# 输出格式 → 媒体类型
_MEDIA_TYPES = {"wav": "audio/wav", "mp3": "audio/mpeg", "pcm16": "audio/pcm"}


class TtsConfigError(RuntimeError):
    """TTS 配置错误（未启用 / 缺 voice_ref 等）。API 层映射为 400，非服务端故障。

    TTS configuration error (not enabled / missing voice_ref, etc.). Mapped to 400 at the API layer; not a server fault.
    """


async def synthesize(text: str, voice: str | None = None) -> tuple[bytes, str]:
    """调用配置的 TTS 端点合成语音，返回 (音频字节, media_type)。

    Call the configured TTS endpoint to synthesize speech and return (audio bytes, media_type).

    按 profile.chat_path 自动选择协议：含 'chat/completions' → chat 模式，否则 speech 模式。
    配置错误抛 TtsConfigError；网络/端点错误抛 RuntimeError。
    The protocol is chosen automatically by profile.chat_path: contains 'chat/completions' → chat mode, otherwise speech mode.
    Configuration errors raise TtsConfigError; network/endpoint errors raise RuntimeError.

    Args:
        text: 要合成的文本。 / The text to synthesize.
        voice: 可选的音色覆盖。 / Optional voice override.

    Returns:
        (音频字节, MIME 类型) 元组。 / A tuple of (audio bytes, MIME type).

    Raises:
        TtsConfigError: TTS 未启用或配置缺失。 / TTS is not enabled or the configuration is missing.
        RuntimeError: 文本为空、网络或端点错误。 / Empty text, or network/endpoint errors.
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
    """拼接端点 URL，确保 path 以斜杠开头。

    Build the endpoint URL, ensuring the path starts with a slash.

    Args:
        profile: TTS profile 配置。 / The TTS profile configuration.
        path: 请求路径。 / The request path.

    Returns:
        完整的请求 URL。 / The full request URL.
    """
    endpoint = (profile.get("endpoint") or "").rstrip("/")
    return f"{endpoint}{path if path.startswith('/') else '/' + path}"


def _build_headers(profile: dict) -> dict:
    """构建 Bearer 认证请求头；无 api_key 时返回空字典。

    Build a Bearer auth request header; return an empty dict when no api_key is set.

    Args:
        profile: TTS profile 配置。 / The TTS profile configuration.

    Returns:
        请求头字典。 / The request header dict.
    """
    api_key = profile.get("api_key") or ""
    return {"Authorization": f"Bearer {api_key}"} if api_key else {}


async def _post(profile: dict, path: str, payload: dict) -> httpx.Response:
    """向 TTS 端点发起 POST 请求，非 200 或网络错误统一转 RuntimeError。

    POST to the TTS endpoint; convert non-200 responses and network errors into RuntimeError.

    Args:
        profile: TTS profile 配置。 / The TTS profile configuration.
        path: 请求路径。 / The request path.
        payload: 请求体。 / The request payload.

    Returns:
        httpx 响应对象。 / The httpx response object.

    Raises:
        RuntimeError: 网络错误或端点返回非 200。 / Network errors or non-200 endpoint responses.
    """
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
    """参考音频 → data URL（mp3/wav，VoiceClone 必需）。

    Convert a reference audio file into a data URL (mp3/wav; required by VoiceClone).

    Args:
        p: 参考音频文件路径。 / The reference audio file path.

    Returns:
        形如 data:{mime};base64,... 的 data URL。 / A data URL of the form data:{mime};base64,...
    """
    suffix = p.suffix.lower()
    mime = "audio/wav" if suffix == ".wav" else ("audio/mpeg" if suffix in (".mp3", ".mpeg") else "audio/wav")
    b64 = base64.b64encode(p.read_bytes()).decode()
    return f"data:{mime};base64,{b64}"


async def _synthesize_chat(text: str, profile: dict, voice: str | None = None) -> tuple[bytes, str]:
    """MiMo TTS 系列：chat completions + audio.voice。

    MiMo TTS family: chat completions + audio.voice.

    voiceclone 模型 → voice = 参考音频 base64（需 voice_ref）；
    标准/预置音色模型（mimo-v2.5-tts）→ voice = 内置音色名。
    优先使用前端显式传入的 voice（UI 音色切换），其次配置 voice，空则默认 mimo_default。
    voiceclone models → voice = reference audio base64 (voice_ref required);
    standard/preset-voice models (mimo-v2.5-tts) → voice = built-in voice name.
    Priority: explicit voice from the frontend (UI voice switching), then the configured voice, defaulting to mimo_default when empty.

    Args:
        text: 要合成的文本。 / The text to synthesize.
        profile: TTS profile 配置。 / The TTS profile configuration.
        voice: 前端传入的音色名（可空）。 / The voice name passed from the frontend (may be empty).

    Returns:
        (音频字节, MIME 类型) 元组。 / A tuple of (audio bytes, MIME type).
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
    """OpenAI /v1/audio/speech：{model, input, voice}。

    OpenAI /v1/audio/speech: {model, input, voice}.

    Args:
        text: 要合成的文本。 / The text to synthesize.
        voice: 前端传入的音色名（可空）。 / The voice name passed from the frontend (may be empty).
        profile: TTS profile 配置。 / The TTS profile configuration.

    Returns:
        (音频字节, MIME 类型) 元组。 / A tuple of (audio bytes, MIME type).
    """
    use_voice = voice or profile.get("voice") or "alloy"
    payload = {
        "model": profile.get("model") or "tts-1",
        "input": text,
        "voice": use_voice,
    }
    r = await _post(profile, profile.get("chat_path") or "/v1/audio/speech", payload)
    return r.content, "audio/mpeg"
