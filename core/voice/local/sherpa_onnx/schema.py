# -*- coding: utf-8 -*-
"""四能力参数 schema（设置页 SchemaForm 的数据源）。

Parameter schemas for the four capabilities (the settings-page SchemaForm source).

字段的 ``key`` 直接对应配置对象上的字段名；``target`` 是所属 section（目前等于 kind）。
``group`` 区分通用参数（provider/线程）与模型专属参数，前端据此分区渲染。
Each field's ``key`` is the config attribute name; ``target`` is the owning section
(currently equal to kind). ``group`` separates common tuning from model-specific params.
"""
from __future__ import annotations

from typing import Any


def _bi(zh: str, en: str) -> dict[str, str]:
    return {"zh": zh, "en": en}


def _common(kind: str) -> list[dict[str, Any]]:
    """所有本地模型共用的推理参数。Common inference params for every local model."""
    return [
        {
            "key": "provider", "target": kind, "type": "select", "group": "common",
            "label": _bi("加速后端", "Acceleration"),
            "default": "cpu",
            "options": [
                {"value": "cpu", "label": "CPU"},
                {"value": "cuda", "label": "CUDA (GPU)"},
                {"value": "coreml", "label": "CoreML"},
            ],
            "hint": _bi("只显示当前构建真实支持的后端", "Only providers supported by this build"),
        },
        {
            "key": "num_threads", "target": kind, "type": "number", "group": "common",
            "label": _bi("线程数（0=自动）", "Threads (0=auto)"),
            "default": 0, "min": 0, "max": 32, "step": 1,
        },
    ]


def capability_schema(kind: str) -> list[dict[str, Any]]:
    """返回某能力的参数 schema。Return the parameter schema for one capability."""
    common = _common(kind)
    if kind == "vad":
        return common + [
            {
                "key": "vad_threshold", "target": "vad", "type": "slider", "group": "model",
                "label": _bi("语音概率阈值", "Speech probability threshold"),
                "default": 0.5, "min": 0, "max": 1, "step": 0.01,
                "hint": _bi("调低更敏感，可能增加误报", "Lower is more sensitive"),
            },
            {
                "key": "min_speech_ms", "target": "vad", "type": "number", "group": "model",
                "label": _bi("最短语音时长（ms）", "Min speech (ms)"),
                "default": 300, "min": 0, "max": 3000, "step": 50,
            },
            {
                "key": "window_size", "target": "vad", "type": "select", "group": "model",
                "label": _bi("分析窗口", "Window size"),
                "default": 0,
                "options": [
                    {"value": 0, "label": "自动 / Auto"},
                    {"value": 128, "label": "128"},
                    {"value": 256, "label": "256"},
                    {"value": 512, "label": "512"},
                ],
            },
        ]
    if kind == "kws":
        return common + [
            {
                "key": "keywords_threshold", "target": "kws", "type": "slider", "group": "model",
                "label": _bi("关键词检测阈值", "Keyword threshold"),
                "default": 0.25, "min": 0, "max": 1, "step": 0.01,
                "hint": _bi("越低越灵敏（漏报少、误报多）", "Lower is more sensitive"),
            },
            {
                "key": "keywords_score", "target": "kws", "type": "number", "group": "model",
                "label": _bi("关键词得分加成", "Keyword score"),
                "default": 1.0, "min": 0, "max": 5, "step": 0.1,
            },
        ]
    if kind == "asr":
        return common + [
            {
                "key": "streaming", "target": "asr", "type": "switch", "group": "model",
                "label": _bi("流式出字", "Streaming partials"),
                "default": True,
                "hint": _bi("边说边出字；关闭则按 VAD 段整段识别", "Partials while speaking; off = one shot per segment"),
            },
        ]
    if kind == "tts":
        return common + [
            {
                "key": "speaker", "target": "tts", "type": "number", "group": "model",
                "label": _bi("音色 ID", "Speaker ID"),
                "default": 0, "min": 0, "max": 200, "step": 1,
            },
            {
                "key": "speed", "target": "tts", "type": "slider", "group": "model",
                "label": _bi("语速", "Speed"),
                "default": 1.0, "min": 0.5, "max": 2.0, "step": 0.05,
            },
            {
                "key": "lang", "target": "tts", "type": "text", "group": "model",
                "label": _bi("语言（空=多语种）", "Language (empty=multi)"),
                "default": "",
                "hint": _bi("Kokoro 多语种建议留空", "Leave empty for multi-lang Kokoro"),
            },
        ]
    raise ValueError(f"未知能力: {kind!r}")
