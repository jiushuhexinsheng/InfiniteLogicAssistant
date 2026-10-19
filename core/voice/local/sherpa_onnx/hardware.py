# -*- coding: utf-8 -*-
"""推理硬件：CPU/GPU provider、线程数与可用性探测。

Inference hardware: CPU/GPU provider selection, thread counts and availability probing.

每个模型（VAD/KWS/ASR/TTS）都可以单独选 ``cpu`` / ``cuda`` / ``coreml``。选 GPU 但
运行时不可用时**不静默回退** —— 引擎加载会抛出 :class:`ProviderUnavailableError`，
设置页据此显示真实原因（静默回退会让人以为 GPU 已生效）。

Every model (VAD/KWS/ASR/TTS) may pick ``cpu`` / ``cuda`` / ``coreml`` independently.
When a GPU provider is requested but unavailable at runtime the engine raises
:class:`ProviderUnavailableError` rather than silently falling back — a silent
fallback would make the settings page claim GPU while inference runs on CPU.
"""
from __future__ import annotations

import os
from dataclasses import asdict, dataclass

# sherpa-onnx 接受的 provider 名。Provider names accepted by sherpa-onnx.
VALID_PROVIDERS = ("cpu", "cuda", "coreml")


class ProviderUnavailableError(RuntimeError):
    """请求的加速 provider 在当前环境不可用。Requested provider is unavailable here."""

    def __init__(self, requested: str, available: tuple[str, ...]) -> None:
        self.requested = requested
        self.available = available
        super().__init__(
            f"推理加速不可用：请求 {requested!r}，当前环境只提供 "
            f"{', '.join(available) or '未知'}。请改选 cpu，或安装带 CUDA 的 "
            "onnxruntime-gpu / sherpa-onnx GPU 构建。"
        )


@dataclass(frozen=True)
class HardwareInfo:
    """一次硬件探测的只读快照。Read-only hardware snapshot."""

    cpu_count: int
    providers: tuple[str, ...]
    sherpa_version: str
    default_threads: int

    def to_dict(self) -> dict:
        """转为可 JSON 序列化的字典。JSON-serialisable dict."""
        d = asdict(self)
        d["providers"] = list(self.providers)
        return d


def default_num_threads(cap: int = 4) -> int:
    """默认线程数：CPU 核数的一半，上限 ``cap``，至少 1。

    Default thread count: half the cores, capped, at least 1.
    """
    cores = os.cpu_count() or 1
    return max(1, min(cap, cores // 2 or 1))


def available_providers() -> tuple[str, ...]:
    """当前 onnxruntime 可用的执行 provider（归一成 sherpa 的命名）。

    Execution providers available in this onnxruntime, normalised to sherpa's naming.
    """
    found: list[str] = []
    try:
        import onnxruntime as ort  # type: ignore[import-untyped]
        raw = set(ort.get_available_providers())
    except Exception:
        raw = set()
    if "CPUExecutionProvider" in raw or not raw:
        found.append("cpu")
    if "CUDAExecutionProvider" in raw:
        found.append("cuda")
    if "CoreMLExecutionProvider" in raw:
        found.append("coreml")
    # TensorRT 最终仍通过 CUDA provider 暴露；不单独列为可选。
    # TensorRT surfaces through the CUDA provider; not offered as a separate choice.
    return tuple(dict.fromkeys(found))


def sherpa_version() -> str:
    """已安装的 sherpa-onnx 版本；未安装返回空串。Installed sherpa-onnx version, or ''."""
    try:
        import sherpa_onnx  # type: ignore[import-untyped]
        return str(getattr(sherpa_onnx, "__version__", "") or "")
    except Exception:
        return ""


def probe() -> HardwareInfo:
    """探测 CPU / provider / sherpa 版本。Probe CPU, providers and sherpa version."""
    return HardwareInfo(
        cpu_count=os.cpu_count() or 1,
        providers=available_providers(),
        sherpa_version=sherpa_version(),
        default_threads=default_num_threads(),
    )


def resolve_provider(requested: str, *, allow_fallback: bool = False) -> str:
    """校验 provider；不可用时抛错或显式回退。

    Validate a provider; raise when unavailable, or fall back explicitly.

    Args:
        requested: ``cpu`` / ``cuda`` / ``coreml``。
        allow_fallback: True 时不可用则回退 ``cpu``（调用方需把回退事实记入状态），
            False（默认）时抛 :class:`ProviderUnavailableError`。

    Raises:
        ProviderUnavailableError: ``allow_fallback=False`` 且 provider 不可用。
        ValueError: provider 名非法。
    """
    name = (requested or "cpu").strip().lower()
    if name not in VALID_PROVIDERS:
        raise ValueError(f"未知推理 provider: {requested!r}（可选 {', '.join(VALID_PROVIDERS)}）")
    available = available_providers()
    if name in available:
        return name
    if allow_fallback:
        return "cpu"
    raise ProviderUnavailableError(name, available)


def resolve_threads(requested: int) -> int:
    """线程数：0 或负数 → 自动。Thread count: 0/negative → automatic."""
    n = int(requested or 0)
    if n <= 0:
        return default_num_threads()
    return max(1, n)
