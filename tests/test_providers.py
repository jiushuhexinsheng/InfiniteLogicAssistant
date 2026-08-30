# -*- coding: utf-8 -*-
"""core/vendors.py — 厂商目录 / 协议分派 / 模型路径 / 预填 / 剥密钥"""
import core.config as c
from core.vendors import (
    BUILTIN_ASR,
    BUILTIN_LLM,
    BUILTIN_TTS,
    get_preset,
    get_vendor_catalog,
    models_path_for,
    preset_to_profile,
    resolve_protocol,
    to_public_dict,
)


def test_catalog_counts():
    assert len(BUILTIN_LLM) == 16
    assert len(BUILTIN_ASR) == 3
    assert len(BUILTIN_TTS) == 2
    ids = list(get_vendor_catalog())
    assert len(ids) == 21
    assert len(ids) == len(set(ids))  # 预设 ID 全目录唯一（防跨 kind 冲突）


def test_catalog_entries_pair_base_and_path():
    """endpoint 为基座（不含 /v1），chat_path 相对，避免拼出 /v1/v1/ 错误地址。"""
    for pid, p in BUILTIN_LLM.items():
        if p.provider == "openai":
            assert "/v1" not in p.endpoint.rstrip("/").split("/")[-2:], f"{pid} endpoint 不应含 /v1"
            assert p.chat_path.endswith("/chat/completions")
    # 内置预设均有展示名与至少一个模型（本地 LM Studio 可空 models）
    for pid, p in get_vendor_catalog().items():
        assert p.label, pid


def test_catalog_merge_yaml_override_and_append(monkeypatch):
    custom = c.VendorPreset(kind="llm", label="自定义", endpoint="https://x", chat_path="/v1/chat/completions")
    monkeypatch.setattr(c, "get_settings", lambda: c.Settings(vendor_presets={"custom": custom}))
    cat = get_vendor_catalog()
    assert "custom" in cat and cat["custom"].label == "自定义"
    # 同 ID 覆盖内置
    override = c.VendorPreset(kind="llm", label="覆盖版", endpoint="https://y")
    monkeypatch.setattr(c, "get_settings", lambda: c.Settings(vendor_presets={"deepseek": override}))
    assert get_vendor_catalog()["deepseek"].label == "覆盖版"


def test_resolve_protocol():
    assert resolve_protocol({"provider": "openai"}) == "openai"
    assert resolve_protocol({"provider": "anthropic"}) == "anthropic"
    assert resolve_protocol({"provider": "gemini"}) == "gemini"
    assert resolve_protocol({"vendor": "gemini"}) == "gemini"   # vendor 反查目录
    assert resolve_protocol({"vendor": "anthropic"}) == "anthropic"
    assert resolve_protocol({"provider": "xiaomi", "chat_path": "/v1/chat/completions"}) == "openai"  # 未知→openai
    assert resolve_protocol({"provider": "custom", "chat_path": "/v1/messages"}) == "anthropic"        # chat_path 推断
    assert resolve_protocol({"provider": "custom", "chat_path": "/v1beta/models/m:streamGenerateContent?alt=sse"}) == "gemini"


def test_models_path_for():
    assert models_path_for({"chat_path": "/v1/chat/completions"}) == "/v1/models"
    assert models_path_for({"chat_path": "/chat/completions"}) == "/models"
    assert models_path_for({"models_path": "/v1beta/models"}) == "/v1beta/models"
    assert models_path_for({"chat_path": "/v1beta/models/m:streamGenerateContent?alt=sse"}) == "/v1beta/models"


def test_preset_to_profile_prefill():
    p = get_preset("deepseek")
    prof = preset_to_profile("deepseek", p)
    assert prof["vendor"] == "deepseek"
    assert prof["provider"] == "openai"
    assert prof["endpoint"] == "https://api.deepseek.com"
    assert prof["chat_path"] == "/v1/chat/completions"
    assert prof["model"] == "deepseek-chat"
    assert prof["api_key_env"] == "DEEPSEEK_API_KEY"
    assert prof["models"] == ["deepseek-chat", "deepseek-reasoner"]
    # TTS 预填音色
    mimo = get_preset("xiaomi-mimo")
    tprof = preset_to_profile("xiaomi-mimo", mimo)
    assert tprof["voices"][0] == "Chloe"
    assert tprof["format"] == "wav"


def test_xiaomi_presets_compat():
    llm = get_preset("xiaomi-mimo-llm")
    assert llm.provider == "openai"
    assert llm.compat == {"max_tokens_field": "max_completion_tokens"}  # 小米用 max_completion_tokens
    assert llm.models[0] == "mimo-v2.5-pro"
    asr = get_preset("xiaomi-mimo-asr")
    assert asr.compat["auth_header"] == "api-key"
    assert asr.compat["audio_data_url"] is True
    assert asr.models == ["mimo-v2.5-asr"]


def test_to_public_dict_strips_secrets():
    out = to_public_dict({"a": 1, "api_key": "x", "api_token": "y", "nested": {"api_key": "z"}, "list": [{"api_token": "w"}]})
    assert out["a"] == 1
    assert "api_key" not in out and "api_token" not in out
    assert out["nested"] == {}
    assert out["list"] == [{}]
