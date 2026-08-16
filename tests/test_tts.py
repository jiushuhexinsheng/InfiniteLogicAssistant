# -*- coding: utf-8 -*-
"""core/tts.py — 配置错误应抛 TtsConfigError（API 层映射 400）且提示可操作"""
import pytest

from core.tts import TtsConfigError, _synthesize_chat, synthesize


@pytest.mark.asyncio
async def test_synthesize_chat_voiceclone_missing_voice_ref_raises_config_error():
    """voiceclone 模型缺 voice_ref 是配置错误（不是网络错误），抛 TtsConfigError"""
    with pytest.raises(TtsConfigError, match="voice_ref"):
        await _synthesize_chat("你好", {"chat_path": "/v1/chat/completions", "model": "mimo-v2.5-tts-voiceclone"})


@pytest.mark.asyncio
async def test_synthesize_chat_preset_uses_default_voice(monkeypatch):
    """标准/预置音色模型无需 voice_ref：voice 缺省用配置音色，空则兜底 mimo_default"""
    captured = {}

    class _Resp:
        def json(self):
            return {"choices": [{"message": {"audio": {"data": ""}}}]}

    async def fake_post(profile, path, payload):
        captured["payload"] = payload
        return _Resp()

    monkeypatch.setattr("core.tts._post", fake_post)
    await _synthesize_chat("你好", {"chat_path": "/v1/chat/completions"})
    assert captured["payload"]["model"] == "mimo-v2.5-tts"
    assert captured["payload"]["audio"]["voice"] == "mimo_default"


@pytest.mark.asyncio
async def test_synthesize_disabled_raises_config_error(monkeypatch):
    """未启用 TTS 属配置错误"""
    monkeypatch.setattr("core.tts.is_tts_enabled", lambda: False)
    with pytest.raises(TtsConfigError):
        await synthesize("你好")
