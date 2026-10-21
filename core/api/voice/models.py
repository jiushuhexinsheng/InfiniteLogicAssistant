# -*- coding: utf-8 -*-
"""模型与能力端点：扫描 models/{vad,kws,asr,tts,llm}、硬件/引擎能力快照。

Model and capability endpoints: scan ``models/{vad,kws,asr,tts,llm}`` and report the
hardware/engine capability snapshot.

扫描只做文件系统校验，不加载模型 —— 设置页打开时不应把几百 MB 的模型读进内存。
Scanning is filesystem-only and never loads a model — opening the settings page must not
pull hundreds of MB into memory.
"""
from __future__ import annotations

import asyncio
import time
from typing import Any

from fastapi import APIRouter

from core import config
from core.voice.local.sherpa_onnx import KINDS, hardware, registry, schema as schema_mod

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


@router.get("/voice/schema")
async def voice_schema(kind: str = "vad"):
    """某能力的参数 schema（设置页 SchemaForm 数据源）。

    Parameter schema for one capability (the settings-page SchemaForm feed).
    """
    if kind not in ("vad", "kws", "asr", "tts"):
        return {"ok": False, "error": f"未知能力: {kind}"}
    try:
        return {"ok": True, "kind": kind, "params": schema_mod.capability_schema(kind)}
    except ValueError as e:
        return {"ok": False, "error": str(e)}


@router.post("/voice/engines/{kind}/test")
async def voice_engine_test(kind: str):
    """加载并实际跑一次本地引擎，返回耗时与结果（设置页「测试」按钮）。

    Load and actually exercise one local engine, returning latency and a detail string
    (the settings-page "Test" button). This deliberately tests the **local** engine
    regardless of the configured mode.
    """
    if kind not in ("vad", "kws", "asr", "tts"):
        return {"ok": False, "ready": False, "error": f"未知能力: {kind}"}
    started = time.perf_counter()
    try:
        from core.voice.local.runtime import get_runtime
        runtime = get_runtime()
        if kind == "vad":
            engine: Any = runtime.vad()
            ok, reason = await asyncio.to_thread(engine.status)
            if not ok:
                return {"ok": False, "ready": False, "error": reason}
            import numpy as np
            segs = await asyncio.to_thread(engine.segments, np.zeros(16000, dtype=np.float32), 16000)
            detail = f"1s 静音 → {len(segs)} 段"
        elif kind == "kws":
            engine = runtime.kws()
            ok, reason = await asyncio.to_thread(engine.status)
            if not ok:
                return {"ok": False, "ready": False, "error": reason}
            from core.voice.local.sherpa_onnx import audio as audio_mod
            test_wav = config.ROOT_DIR / "models" / "kws" / \
                "sherpa-onnx-kws-zipformer-wenetspeech-3.3M-2024-01-01" / "test_wavs" / "3.wav"
            if test_wav.is_file():
                samples, sr = audio_mod.read_wav_bytes(test_wav.read_bytes())
                hit = await asyncio.to_thread(engine.detect, samples, sr)
                detail = f"测试音频命中：{hit}" if hit else "测试音频未命中（正常）"
            else:
                detail = "模型已加载（无测试音频）"
        elif kind == "asr":
            engine = runtime.asr()
            ok, reason = await asyncio.to_thread(engine.status)
            if not ok:
                return {"ok": False, "ready": False, "error": reason}
            from core.voice.local.sherpa_onnx import audio as audio_mod
            test_wav = config.ROOT_DIR / "models" / "kws" / \
                "sherpa-onnx-kws-zipformer-wenetspeech-3.3M-2024-01-01" / "test_wavs" / "3.wav"
            if not test_wav.is_file():
                return {"ok": True, "ready": True, "detail": "模型已加载（无测试音频）",
                        "latency_ms": int((time.perf_counter() - started) * 1000)}
            samples, sr = audio_mod.read_wav_bytes(test_wav.read_bytes())
            text = await asyncio.to_thread(engine.transcribe, samples, sr)
            detail = f"转写：{(text or '')[:60] or '（空）'}"
        else:  # tts
            from core.voice.tts import _synthesize_local
            wav, _media = await _synthesize_local("你好，我是衍衡")
            import io
            import wave
            with wave.open(io.BytesIO(wav), "rb") as w:
                duration = w.getnframes() / w.getframerate()
            detail = f"合成 {duration:.2f}s / {len(wav)} bytes"
        return {
            "ok": True,
            "ready": True,
            "kind": kind,
            "latency_ms": int((time.perf_counter() - started) * 1000),
            "detail": detail,
        }
    except Exception as e:  # noqa: BLE001
        return {
            "ok": False,
            "ready": False,
            "kind": kind,
            "latency_ms": int((time.perf_counter() - started) * 1000),
            "error": str(e),
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
    vad_present = registry.present("vad", s.vad.model)
    kws_present = registry.present("kws", s.kws.model_dir)
    asr_present = registry.present("asr", s.asr.local_model)
    tts_present = registry.present("tts", s.tts.local_model)
    asr_api = config.is_asr_configured()
    tts_api = config.is_tts_enabled()

    def mark(d: dict, ready: bool, reason: str) -> dict:
        d["ready"] = ready
        d["reason"] = reason
        return d

    return {
        "ok": True,
        "hardware": hw.to_dict(),
        "vad": mark({
            "mode": s.vad.mode,
            "engine": s.vad.engine,
            "model": s.vad.model,
            "present": vad_present,
            "provider": s.vad.provider,
            "num_threads": s.vad.num_threads,
            "api": False,   # 本项目不提供云端 VAD / no cloud VAD
        }, s.vad.mode != "off" and vad_present,
           "VAD 已关闭" if s.vad.mode == "off" else ("VAD 模型缺失" if not vad_present else "")),
        "kws": mark({
            "mode": s.kws.mode,
            "model_dir": s.kws.model_dir,
            "present": kws_present,
            "provider": s.kws.provider,
            "num_threads": s.kws.num_threads,
            "api": True,    # 云端 ASR 文本 + 拼音判定 / cloud ASR text + pinyin
        }, s.kws.mode != "off" and (kws_present or s.kws.mode == "api"),
           "KWS 已关闭" if s.kws.mode == "off" else ("KWS 模型缺失" if s.kws.mode == "local" and not kws_present else "")),
        "asr": mark({
            "mode": s.asr.mode,
            "local_model": s.asr.local_model,
            "present": asr_present,
            "streaming": s.asr.streaming,
            "provider": s.asr.provider,
            "num_threads": s.asr.num_threads,
            "api": asr_api,
        }, (s.asr.mode == "cloud" and asr_api) or (s.asr.mode == "local" and asr_present)
           or (s.asr.mode == "hybrid" and (asr_present or asr_api)),
           "" if ((s.asr.mode == "cloud" and asr_api) or (s.asr.mode == "local" and asr_present)
                  or (s.asr.mode == "hybrid" and (asr_present or asr_api)))
           else ("ASR API 未配置" if s.asr.mode == "cloud" else "ASR 本地模型缺失")),
        "tts": mark({
            "mode": s.tts.mode,
            "local_model": s.tts.local_model,
            "present": tts_present,
            "provider": s.tts.provider,
            "num_threads": s.tts.num_threads,
            "api": tts_api,
        }, (s.tts.mode == "local" and tts_present) or (s.tts.mode == "api" and tts_api),
           "" if ((s.tts.mode == "local" and tts_present) or (s.tts.mode == "api" and tts_api))
           else ("TTS API 未配置" if s.tts.mode == "api" else "TTS 本地模型缺失")),
    }
