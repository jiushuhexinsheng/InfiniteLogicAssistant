# -*- coding: utf-8 -*-
"""基础端点、语音转写与 TTS 错误映射。Basic endpoints, transcription and TTS error mapping."""
import core.config as config_mod


# ─── 基础端点 ───

def test_ping(client):
    """测试 /api/ping 健康检查端点。Tests the /api/ping health check endpoint."""
    data = client.get("/api/ping").json()
    assert data["ok"] is True
    assert "time" in data


def test_config_shape(client):
    """测试 /api/config 返回结构完整的配置快照。Tests /api/config returning a complete config snapshot shape."""
    data = client.get("/api/config").json()
    assert {"llm_available", "llm_profile", "asr_available", "asr_profile",
            "tts_available", "tts_profile", "wake_word", "vad"} <= set(data)
    assert data["llm_available"] is False
    assert data["asr_available"] is False


def test_tools_list(client):
    """测试 /api/tools 列出内置工具及其参数 schema。Tests /api/tools listing built-in tools and their parameter schemas."""
    data = client.get("/api/tools").json()
    assert data["ok"] is True
    names = [t["function"]["name"] for t in data["tools"]]
    assert {"get_datetime", "calculate", "web_search", "get_weather"} <= set(names)
    # schema 应含参数描述
    calc = next(t for t in data["tools"] if t["function"]["name"] == "calculate")
    assert "expression" in calc["function"]["parameters"]["properties"]


# ─── 语音转写 ───

def test_voice_transcribe_unconfigured(client):
    """测试 ASR 未配置时转写返回明确错误。Tests transcription returning a clear error when ASR is unconfigured."""
    resp = client.post("/api/voice/transcribe", json={"audio_base64": "xxx"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is False
    assert data["error"] == "ASR 未配置"


# ─── TTS：配置错误应映射为 400（可修复），而非 500 ───

def test_tts_config_error_maps_to_400(client, monkeypatch):
    """测试 TTS 配置错误映射为 400 而非 500。Tests TTS config errors mapping to 400 instead of 500."""
    import core.voice.tts as tts_mod
    # 启用后端 TTS，但 voiceclone 缺 voice_ref → 配置错误
    monkeypatch.setattr(config_mod, "is_tts_enabled", lambda: True)  # voice.py 前置检查
    monkeypatch.setattr(tts_mod, "is_tts_enabled", lambda: True)     # synthesize() 内检查
    monkeypatch.setattr(
        tts_mod,
        "resolve_tts_profile",
        lambda: ("openai", {"endpoint": "https://x.example", "api_key": "k",
                            "model": "mimo-v2.5-tts-voiceclone",
                            "chat_path": "/v1/chat/completions"}),
    )
    resp = client.post("/api/tts", json={"text": "你好"})
    assert resp.status_code == 400
    assert "voice_ref" in resp.json()["error"]
