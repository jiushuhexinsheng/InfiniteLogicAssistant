# -*- coding: utf-8 -*-
"""本地语音引擎预热：启动后台加载 VAD/KWS/ASR/TTS，缩短首次开麦等待。

Warm up the local voice engines in a background thread at startup so the first
session does not pay the cold model-load cost.

只预热配置里启用的本地引擎；云端 ASR/TTS 不在这里（它们无模型可加载）。单个引擎
失败只记 warning，绝不把异常抛回启动流程。``IL_NO_VOICE_WARMUP=1`` 可整体关闭
（测试用 TestClient 启动 lifespan 时靠它避免加载真实模型/拉起 TTS 子进程）。

Only engines configured as local are warmed; cloud ASR/TTS are skipped (nothing to load).
One engine failing logs a warning and never escapes into startup. ``IL_NO_VOICE_WARMUP=1``
disables warmup entirely (tests booting the lifespan rely on it to avoid loading real
models or spawning the TTS child process).
"""
from __future__ import annotations

import os
import threading
from typing import Any, Callable

from core.logger import logger

_DISABLE_ENV = "IL_NO_VOICE_WARMUP"
_TRUTHY = ("1", "true", "yes", "on")


def warmup_disabled() -> bool:
    """是否关闭预热（环境变量）。Whether warmup is disabled by the environment."""
    return os.environ.get(_DISABLE_ENV, "").strip().lower() in _TRUTHY


def _warm_local_tts(tts_warm: Callable[[], Any] | None = None) -> None:
    """预 spawn 本地 TTS 子进程并加载 Kokoro。

    Windows 上 Kokoro 必须在子进程主线程生成（见 core/voice/tts.py 顶部说明），
    这里复用同一个 ProcessPoolExecutor，首次真实合成即可命中已加载的 worker。
    Pre-spawn the local TTS child process and load Kokoro. On Windows Kokoro must run
    on a child process's main thread (see core/voice/tts.py); the first real synthesis
    then reuses the already-loaded worker.
    """
    if tts_warm is not None:
        tts_warm()
        return
    from core import config
    from core.voice import tts as tts_mod

    opts = tts_mod._local_options()
    quiet = bool(getattr(config.settings.voice.tts, "quiet_native_logs", True))
    tts_mod._get_tts_pool().submit(tts_mod._tts_worker, opts, "你好", quiet).result(timeout=120)


def warm_local_voice(runtime: Any = None, *, tts_warm: Callable[[], Any] | None = None) -> dict[str, str]:
    """按配置预热本地引擎，返回 {引擎: ok|error: ...}。

    单个引擎失败不影响其他引擎，也不抛异常 —— 启动路径只看日志。
    Warm the configured local engines and return {engine: ok|error: ...}. One engine
    failing never stops the others and never raises — startup only logs the report.

    Args:
        runtime: 本地运行时（默认取进程单例；测试可注入）。Local runtime (defaults to
            the process singleton; injectable for tests).
        tts_warm: 可注入的 TTS 预热函数（测试用）。Injectable TTS warm hook (tests).
    """
    from core import config
    from core.voice.local.runtime import get_runtime

    rt = runtime if runtime is not None else get_runtime()
    report: dict[str, str] = {}
    voice = config.settings.voice

    def _run(name: str, fn: Callable[[], Any]) -> None:
        try:
            fn()
            report[name] = "ok"
        except Exception as e:  # noqa: BLE001 - 预热失败只降级，不影响启动
            report[name] = f"error: {e}"
            logger.warning("语音预热失败（{}）: {}", name, e)

    if getattr(voice.vad, "mode", "local") == "local":
        def _warm_vad() -> None:
            rt.vad().status()
            # VAD 的 detector 是每会话创建的，预建一次把 C++ 侧初始化也热起来。
            # The detector is per-session; build one now so its C++ init is warm too.
            rt.vad().create_stream()

        _run("vad", _warm_vad)

    kws = voice.kws
    if getattr(kws, "enabled", False) and getattr(kws, "mode", "local") == "local":
        _run("kws", lambda: rt.kws().status())

    if getattr(voice.asr, "mode", "cloud") in ("local", "hybrid"):
        _run("asr", lambda: rt.asr().status())

    if getattr(voice.tts, "mode", "api") == "local":
        _run("tts", lambda: _warm_local_tts(tts_warm))

    return report


def start_voice_warmup() -> threading.Thread | None:
    """后台启动预热（daemon 线程）；关闭环境变量时返回 None。

    Start warmup on a daemon thread; returns None when disabled. Any failure is logged.
    """
    if warmup_disabled():
        return None

    def _run() -> None:
        try:
            report = warm_local_voice()
            logger.info("语音引擎预热完成: {}", report)
        except Exception as e:  # noqa: BLE001 - 预热绝不能影响服务启动
            logger.warning("语音引擎预热失败: {}", e)

    thread = threading.Thread(target=_run, name="voice-warmup", daemon=True)
    thread.start()
    return thread
