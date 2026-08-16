# -*- coding: utf-8 -*-
"""core/tts.py — 配置错误应抛 TtsConfigError（API 层映射 400）且提示可操作"""
import pytest

from core.tts import TtsConfigError, _synthesize_chat, synthesize


@pytest.mark.asyncio
async def test_synthesize_chat_missing_voice_ref_raises_config_error():
    """缺 voice_ref 是配置错误（不是网络错误），抛 TtsConfigError"""
    with pytest.raises(TtsConfigError, match="voice_ref"):
        await _synthesize_chat("你好", {"chat_path": "/v1/chat/completions", "model": "x"})


@pytest.mark.asyncio
async def test_synthesize_chat_error_hints_browser_fallback():
    """提示信息应告知可关闭后端 TTS 改用浏览器本地播报"""
    with pytest.raises(TtsConfigError, match="voice.tts.enabled"):
        await _synthesize_chat("你好", {})


@pytest.mark.asyncio
async def test_synthesize_disabled_raises_config_error(monkeypatch):
    """未启用 TTS 属配置错误"""
    monkeypatch.setattr("core.tts.is_tts_enabled", lambda: False)
    with pytest.raises(TtsConfigError):
        await synthesize("你好")
