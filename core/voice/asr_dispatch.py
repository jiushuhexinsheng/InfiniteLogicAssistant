# -*- coding: utf-8 -*-
"""ASR 三模式统一分发：本地 / 云端 / 混合（`voice.asr.mode`）。

唯一入口 `transcribe(wav, *, via)`，供唤醒链（`/voice/wake`、`/voice/transcribe`）与通话
漏斗 L2 精转写共用。三种模式：

- ``cloud``：走 ``active`` profile 的云端 ASR（**默认，与旧行为逐字一致**）。不触碰本地
  引擎（零加载、零额外内存）。
- ``local``：本地 sherpa-onnx 转写，音频不出本机、零成本；本地不可用时**明确抛
  ``AsrUnavailableError``，绝不静默上云**。
- ``hybrid``：本地优先 —— 本地不可用 / 转写为空 / 抛错时才调云端兜底，结果带
  ``fallback=True``（调用方据此留可观测痕迹）。

**隐私不变量（本模块的核心约束）**：只有 ``hybrid`` 分支允许「本地失败 → 上云」。本模块
不得存在把 ``local`` 模式的失败转成云端上传的任何路径 —— 用户选「本地」却偷偷上云是本
功能最不能犯的错。

Unified ASR dispatch for the tri-mode setting (`voice.asr.mode`). Single entry
`transcribe(wav, *, via)` shared by the wake chain and the call-funnel L2. PRIVACY
INVARIANT: only the `hybrid` branch may fall back from a local failure to the cloud; there
must be no path that turns a `local`-mode failure into an upload — silently uploading when
the user picked "local" is the one thing this feature must never do.

审计仍留在端点：端点据 `AsrResult.engine` 决定写 `audio-upload via=`（真上传，进成本统计）
还是 `asr-local via=`（本地，不进统计）。Audit stays in the endpoints, which pick the
prefix from `AsrResult.engine`.
"""
from __future__ import annotations

import asyncio
import base64
from dataclasses import dataclass

from core import config
from core.logger import logger

_VALID_MODES = ("local", "cloud", "hybrid")


@dataclass(frozen=True)
class AsrResult:
    """一次转写的结果。空文本是**合法结果**（静音段），不是错误。

    One transcription's outcome. An empty text is a **legitimate result** (a silent
    segment), not an error.
    """

    text: str
    engine: str                 # "local" | "cloud"
    fallback: bool = False      # hybrid 下本地失败/为空 → 云端兜底（可观测痕迹）


class AsrUnavailableError(RuntimeError):
    """转写不可用。`local` 模式下本地不可用 → 明确失败，绝不静默上云。

    Transcription unavailable. In `local` mode an unavailable local engine fails
    explicitly rather than silently uploading.
    """

    def __init__(self, code: str, message: str, *, engine: str = "") -> None:
        self.code = code        # "local_unavailable" | "cloud_unavailable"
        self.engine = engine
        super().__init__(message)


def resolve_mode() -> str:
    """读 `voice.asr.mode`；缺失或非法（理论上被 schema Literal 挡住）→ `cloud` + 告警。

    Read `voice.asr.mode`; a missing/invalid value (normally blocked by the schema Literal)
    falls back to `cloud` with a warning."""
    mode = getattr(config.settings.voice.asr, "mode", "cloud")
    if mode not in _VALID_MODES:
        logger.warning("voice.asr.mode 非法值 {!r}，按 cloud 处理", mode)
        return "cloud"
    return mode


def _local():
    """惰性取本地引擎（模块级单例；import 延迟到调用点，避免无谓的 sherpa 依赖）。"""
    from core.voice.local_asr import get_local_asr
    return get_local_asr()


def _cloud():
    from core.voice import get_asr
    return get_asr()


async def _run_local(wav: bytes) -> str:
    """同步 sherpa 解码卸载到线程池 —— 绝不阻塞事件循环（全仓仅此一处本地推理）。

    Offload the synchronous sherpa decode to a worker thread — never block the event loop.
    """
    return await asyncio.to_thread(_local().transcribe_wav, wav)


async def _run_cloud(wav: bytes, via: str = "") -> str:
    asr = _cloud()
    if not asr.available():
        # 文案与旧端点的精确值一致（test_server_basic 断言 `== "ASR 未配置"`）；
        # 细节留给日志，用户可见语仍是既有那句。
        logger.warning("云端 ASR 未配置（voice.asr.profiles 缺 endpoint/model），via={}", via)
        raise AsrUnavailableError("cloud_unavailable", "ASR 未配置", engine="cloud")
    return await asr.transcribe_base64(base64.b64encode(wav).decode(), "wav")


async def transcribe(wav: bytes, *, via: str) -> AsrResult:
    """按 `voice.asr.mode` 转写一段 wav，返回 `AsrResult`；不可用则抛 `AsrUnavailableError`。

    Args:
        wav: 16kHz mono WAV 字节。16 kHz mono WAV bytes.
        via: 调用来源（`"wake"` / `"transcribe"` / `"call-segment"`），仅用于日志上下文。
            The call site, used only for log context.

    Raises:
        AsrUnavailableError: 所选通路不可用（`local` 缺模型 / 云端未配置）。
    """
    mode = resolve_mode()

    if mode == "cloud":
        return AsrResult(await _run_cloud(wav, via), engine="cloud")

    local = _local()
    if mode == "local":
        ok, reason = local.status()
        if not ok:
            raise AsrUnavailableError(
                "local_unavailable",
                f"{reason}；local 模式不会上云 —— 请下载模型或把 voice.asr.mode 改为 cloud",
                engine="local",
            )
        return AsrResult(await _run_local(wav), engine="local")

    # hybrid：本地优先，云端兜底（唯一允许「本地失败 → 上云」的分支）
    text = ""
    if local.available():
        try:
            text = (await _run_local(wav)) or ""
        except Exception as e:
            logger.warning("hybrid 本地转写失败（via={}），回落云端: {}", via, e)
    if text.strip():
        return AsrResult(text, engine="local")
    return AsrResult(await _run_cloud(wav, via), engine="cloud", fallback=True)
