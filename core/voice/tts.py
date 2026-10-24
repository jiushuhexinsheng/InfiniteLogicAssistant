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
import asyncio
import atexit
import base64
import os
import threading
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict
from pathlib import Path
from typing import Any

import httpx

from core import config as config_mod
from core.config import add_reload_hook, is_tts_enabled, resolve_tts_profile
from core.logger import logger

# 本地 Kokoro 放在**子进程**里跑：Windows 上 sherpa 的 Kokoro 在非主线程生成中文会
# 只输出极短音频（espeak/词典的线程相关状态），放在 asyncio 线程池里会静默坏掉。
# 子进程的主线程生成稳定，且不阻塞事件循环；模型在子进程内常驻。
# Run local Kokoro in a **child process**: on Windows, sherpa's Kokoro produces a
# near-empty clip for Chinese when run in a worker thread (thread-local espeak/lexicon
# state); a child process's main thread is stable and keeps the event loop free.
_tts_pool: ProcessPoolExecutor | None = None
_tts_pool_lock = threading.Lock()
_worker_engine: Any | None = None
_worker_opts: dict | None = None


def _silence_native_stderr() -> None:
    """把当前进程的 stderr 指向空设备（仅用于 TTS 子进程）。

    Kokoro 的 C++ 诊断直写 stderr，sherpa-onnx 没有日志级别 API；这些行
    （重复词条 / 未知 token / 跳过音素）属于模型自带噪音，不影响合成结果。
    子进程里关掉 fd 2 即可，父进程日志与 loguru 的文件 sink 都不受影响。

    Point this process's stderr at the null device (TTS child only). Kokoro's C++
    diagnostics write straight to stderr and sherpa-onnx exposes no log-level API;
    those lines (duplicate lexicon entries / unknown tokens / skipped phonemes) are
    model-borne noise with no effect on the output. Redirecting fd 2 in the child
    leaves the parent's logs and loguru's file sink untouched.
    """
    try:
        fd = os.open(os.devnull, os.O_WRONLY)
        try:
            os.dup2(fd, 2)
        finally:
            os.close(fd)
    except OSError:
        pass


def _tts_worker(opts: dict, text: str, quiet: bool = True) -> bytes:
    """子进程入口：加载/复用引擎并合成（必须是模块级函数，Windows spawn 可导入）。

    Child-process entry: load/reuse the engine and synthesize. Must be module-level so
    Windows spawn can import it.
    """
    global _worker_engine, _worker_opts
    if quiet:
        _silence_native_stderr()
    if _worker_engine is None or opts != _worker_opts:
        from core.voice.local.sherpa_onnx import TtsEngine, TtsOptions
        engine = TtsEngine(TtsOptions(**opts))
        ok, reason = engine.status()
        if not ok:
            raise RuntimeError(reason)
        _worker_engine = engine
        _worker_opts = dict(opts)
    return _worker_engine.synthesize_wav(text)


def _get_tts_pool() -> ProcessPoolExecutor:
    """取本地 TTS 子进程池（单 worker，惰性创建）。Get the lazy single-worker TTS pool."""
    global _tts_pool
    with _tts_pool_lock:
        if _tts_pool is None:
            _tts_pool = ProcessPoolExecutor(max_workers=1)
        return _tts_pool


def _shutdown_tts_pool() -> None:
    """关闭子进程池（配置热重载 / 进程退出）。Shut down the pool on reload/exit."""
    global _tts_pool
    with _tts_pool_lock:
        pool, _tts_pool = _tts_pool, None
    if pool is not None:
        try:
            pool.shutdown(wait=False, cancel_futures=True)
        except Exception:
            pass


def _local_options() -> dict:
    """当前配置 → 子进程 TtsOptions 字典。Current config → child TtsOptions dict."""
    t = config_mod.settings.voice.tts
    return asdict(_tts_options(t))


def _tts_options(t: Any) -> Any:
    """构造 TtsOptions（延迟 import 避免顶层拉起 sherpa）。Build TtsOptions lazily."""
    from core.voice.local.sherpa_onnx import TtsOptions
    return TtsOptions(
        model_dir=t.local_model,
        provider=t.provider,
        device=t.device,
        num_threads=t.num_threads,
        speaker=t.speaker,
        speed=t.speed,
        lang=t.lang,
    )


atexit.register(_shutdown_tts_pool)
add_reload_hook(_shutdown_tts_pool, sections=("voice",))

# 输出格式 → 媒体类型
_MEDIA_TYPES = {"wav": "audio/wav", "mp3": "audio/mpeg", "pcm16": "audio/pcm"}


class TtsConfigError(RuntimeError):
    """TTS 配置错误（未启用 / 缺 voice_ref 等）。API 层映射为 400，非服务端故障。

    TTS configuration error (not enabled / missing voice_ref, etc.). Mapped to 400 at the API layer; not a server fault.
    """


async def synthesize(text: str, voice: str | None = None, mode: str | None = None) -> tuple[bytes, str]:
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
    if not text.strip():
        raise RuntimeError("合成文本为空")

    # 前端可显式指定引擎（设置页的 local/api 选择）；缺省用配置默认值。
    # The frontend may name the engine (settings-page local/api choice); default to config.
    selected = (mode or "").strip().lower()
    if selected not in ("local", "api"):
        selected = getattr(config_mod.settings.voice.tts, "mode", "api")
    if selected == "local":
        return await _synthesize_local(text)

    if not is_tts_enabled():
        raise TtsConfigError(
            "TTS 未启用：voice.tts.enabled=false 或未配置 endpoint。"
            "如需后端 TTS 请在 config.yaml 配置，否则保持关闭（浏览器本地语音播报）"
        )

    _, profile = resolve_tts_profile()
    path = profile.get("chat_path") or "/v1/audio/speech"
    if "chat/completions" in path:
        return await _synthesize_chat(text, profile, voice)
    return await _synthesize_speech(text, voice, profile)


async def _synthesize_local(text: str) -> tuple[bytes, str]:
    """本地 Kokoro 合成（子进程，主线程生成）；不可用时明确报错，不静默回落云端。

    Local Kokoro synthesis in a child process (main-thread generation); raises clearly
    when unavailable — never silently falls back to the cloud (the user chose local).
    """
    loop = asyncio.get_running_loop()
    quiet = bool(getattr(config_mod.settings.voice.tts, "quiet_native_logs", True))
    try:
        wav = await loop.run_in_executor(
            _get_tts_pool(), _tts_worker, _local_options(), text, quiet)
    except Exception as e:  # noqa: BLE001
        raise TtsConfigError(
            f"本地 TTS 合成失败：{e}。请检查 voice.tts.local_model，"
            "或将 voice.tts.mode 改为 api"
        ) from e
    return wav, "audio/wav"


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
