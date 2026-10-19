# -*- coding: utf-8 -*-
"""模型与能力端点：扫描 models/{vad,kws,asr,tts,llm}、硬件/引擎能力快照。

Model and capability endpoints: scan ``models/{vad,kws,asr,tts,llm}`` and report the
hardware/engine capability snapshot.

扫描只做文件系统校验，不加载模型 —— 设置页打开时不应把几百 MB 的模型读进内存。
Scanning is filesystem-only and never loads a model — opening the settings page must not
pull hundreds of MB into memory.
"""
from __future__ import annotations

from fastapi import APIRouter

from core import config
from core.voice.local.sherpa_onnx import KINDS, hardware, registry

router = APIRouter()


@router.get("/voice/models")
async def voice_models(kind: str = ""):
    """列出模型；``kind`` 为空时返回全部能力。

    List models; an empty ``kind`` returns every capability.

    Args:
        kind: ``vad`` / ``kws`` / ``asr`` / ``tts`` / ``llm``。
    """
    if kind and kind not in KINDS:
        return {"ok": False, "error": f"未知模型类型: {kind}"}
    kinds = [kind] if kind else list(KINDS)
    return {
        "ok": True,
        "models": {k: [m.to_dict() for m in registry.scan(k)] for k in kinds},
    }


@router.post("/voice/models/refresh")
async def voice_models_refresh():
    """刷新模型列表（扫描本身无缓存，此端点只为前端语义清晰）。

    Refresh the model list (scanning is uncached; this endpoint exists for UI clarity).
    """
    return {
        "ok": True,
        "models": {k: [m.to_dict() for m in registry.scan(k)] for k in KINDS},
    }


@router.get("/voice/hardware")
async def voice_hardware():
    """推理硬件快照：CPU 核数、可用 provider、sherpa 版本、默认线程数。

    Inference hardware snapshot: CPU cores, available providers, sherpa version and the
    default thread count.
    """
    return {"ok": True, "hardware": hardware.probe().to_dict()}


@router.get("/voice/capabilities")
async def voice_capabilities():
    """四能力的当前模式 + 本地模型是否就位 + API 是否配置。

    Current mode of each capability, whether its local model is present, and whether the
    cloud API is configured.
    """
    s = config.settings.voice
    hw = hardware.probe()
    return {
        "ok": True,
        "hardware": hw.to_dict(),
        "vad": {
            "mode": s.vad.mode,
            "engine": s.vad.engine,
            "model": s.vad.model,
            "present": registry.present("vad", s.vad.model),
            "provider": s.vad.provider,
            "num_threads": s.vad.num_threads,
            "api": False,   # 本项目不提供云端 VAD / no cloud VAD
        },
        "kws": {
            "mode": s.kws.mode,
            "model_dir": s.kws.model_dir,
            "present": registry.present("kws", s.kws.model_dir),
            "provider": s.kws.provider,
            "num_threads": s.kws.num_threads,
            "api": True,    # 云端 ASR 文本 + 拼音判定 / cloud ASR text + pinyin
        },
        "asr": {
            "mode": s.asr.mode,
            "local_model": s.asr.local_model,
            "present": registry.present("asr", s.asr.local_model),
            "streaming": s.asr.streaming,
            "provider": s.asr.provider,
            "num_threads": s.asr.num_threads,
            "api": config.is_asr_configured(),
        },
        "tts": {
            "mode": s.tts.mode,
            "local_model": s.tts.local_model,
            "present": registry.present("tts", s.tts.local_model),
            "provider": s.tts.provider,
            "num_threads": s.tts.num_threads,
            "api": config.is_tts_enabled(),
        },
    }
