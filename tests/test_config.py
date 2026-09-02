# -*- coding: utf-8 -*-
"""core/config.py — 密钥优先级 / 新字段 / 设置快照。
Tests core/config.py — API key priority, new fields, and the settings snapshot.
"""
import pytest

import core.config as c


def _mk_profile(**kw) -> dict:
    return {"provider": "openai", "endpoint": "https://x", "model": "m", **kw}


# ─── _profile_api_key 优先级 ───

def test_profile_api_key_env_priority(monkeypatch):
    """验证 profile.api_key_env 指向的环境变量优先于段全局环境变量。Verifies the env var pointed to by profile.api_key_env takes priority over the section-level global env var."""
    monkeypatch.setenv("LLM_API_KEY", "global")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "specific")
    secrets = {"llm": {"api_key": "sec_default", "profiles": {}}}
    # profile.api_key_env 指向的 env 优先
    assert c._profile_api_key("llm", "deepseek", secrets, _mk_profile(api_key_env="DEEPSEEK_API_KEY")) == "specific"
    # 无 api_key_env → 段全局 env
    assert c._profile_api_key("llm", "deepseek", secrets, _mk_profile()) == "global"


def test_profile_api_key_secrets_fallback(monkeypatch):
    """验证无环境变量时按 secrets.profiles 再到段默认值回退。Verifies the fallback from secrets.profiles to the section default when no env var is set."""
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    secrets = {"llm": {"api_key": "sec_default", "profiles": {"deepseek": "sec_ds"}}}
    # secrets.profiles[name] > secrets 段默认
    assert c._profile_api_key("llm", "deepseek", secrets, _mk_profile()) == "sec_ds"
    assert c._profile_api_key("llm", "other", secrets, _mk_profile()) == "sec_default"


def test_inject_secrets_server_token():
    """server.api_token 从 secrets 注入（防回归：曾因插入函数悬空成死代码）。
    Verifies server.api_token is injected from secrets (regression guard: it was once dead code because an inserted function dangled).
    """
    secrets = {
        "llm": {"api_key": "", "profiles": {}}, "asr": {"api_key": "", "profiles": {}},
        "tts": {"api_key": "", "profiles": {}}, "server": {"api_token": "tok"},
    }
    data = {"server": {"host": "0.0.0.0"}}
    c._inject_secrets(data, secrets)
    assert data["server"]["api_token"] == "tok"


def test_inject_secrets_asr_tts_under_voice(monkeypatch):
    """asr/tts 密钥嵌在 voice 段下也必须注入。

    曾只找顶层 data['asr']/data['tts']，而 config.yaml 把它们放在 voice 下，
    导致 ASR/TTS 密钥永远为空（写入 secrets 也不生效 → 401）。
    Verifies ASR/TTS keys nested under the voice section are still injected; previously only top-level data['asr']/data['tts'] were checked, leaving the keys empty (401).
    """
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("MIMO_API_KEY", raising=False)
    monkeypatch.delenv("ASR_API_KEY", raising=False)
    monkeypatch.delenv("TTS_API_KEY", raising=False)
    secrets = {
        "llm": {"api_key": "", "profiles": {}},
        "asr": {"api_key": "", "profiles": {"xiaomi": "tp-key"}},
        "tts": {"api_key": "", "profiles": {"openai": "tts-key"}},
        "server": {"api_token": "tok"},
    }
    data = {
        "llm": {"active": "ds", "profiles": {"ds": {"provider": "openai"}}},
        "voice": {
            "asr": {"active": "xiaomi", "profiles": {"xiaomi": {"provider": "openai", "api_key_env": "MIMO_API_KEY"}}},
            "tts": {"enabled": False, "active": "openai", "profiles": {"openai": {"provider": "openai"}}},
        },
    }
    c._inject_secrets(data, secrets)
    # env 未设（MIMO_API_KEY）→ 落到 secrets.profiles[name]
    assert data["voice"]["asr"]["profiles"]["xiaomi"]["api_key"] == "tp-key"
    assert data["voice"]["tts"]["profiles"]["openai"]["api_key"] == "tts-key"
    # llm 顶层照常
    assert data["llm"]["profiles"]["ds"]["api_key"] == ""


def test_profile_api_key_legacy_warns(monkeypatch, capsys):
    """验证旧式 ${ENV} 写法被弃用并输出迁移提示。Verifies the legacy ${ENV} syntax is deprecated and prints a migration notice."""
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    secrets = {"llm": {"api_key": "", "profiles": {}}}
    assert c._profile_api_key("llm", "deepseek", secrets, _mk_profile(api_key="${LLM_API_KEY}")) == ""
    assert "迁移到 config.secrets.yaml" in capsys.readouterr().out


# ─── Settings 接受新字段 ───

def test_settings_accepts_vendor_presets_and_failover():
    """验证 Settings 接受 vendor_presets 与 models_failover 新字段。Verifies Settings accepts the new vendor_presets and models_failover fields."""
    s = c.Settings(
        vendor_presets={"myllm": c.VendorPreset(kind="llm", label="我的", endpoint="https://x", chat_path="/v1/chat/completions")},
        agent=c.AgentSection(models_failover=["model-b"]),
    )
    assert s.vendor_presets["myllm"].label == "我的"
    assert s.agent.models_failover == ["model-b"]


def test_profile_accepts_vendor_models_compat_api_key_env():
    """验证 LlmProfile 接受 vendor/models/compat/api_key_env 字段。Verifies LlmProfile accepts the vendor, models, compat, and api_key_env fields."""
    prof = c.LlmProfile(
        vendor="deepseek", api_key_env="DEEPSEEK_API_KEY",
        models=["deepseek-chat"], models_path="/v1/models",
        compat={"stream_options": False},
    )
    assert prof.vendor == "deepseek"
    assert prof.models == ["deepseek-chat"]
    assert prof.compat.stream_options is False


def test_compat_defaults_preserve_behavior():
    """验证 CompatConfig 默认值保持原有行为。Verifies CompatConfig defaults preserve the original behavior."""
    assert c.CompatConfig().stream_options is True
    assert c.CompatConfig().max_tokens_field == "max_tokens"


# ─── editable_snapshot：剥 api_key，留新字段 ───

def test_editable_snapshot_keeps_new_fields_strips_key(monkeypatch):
    """验证设置快照保留新字段并剥离 api_key。Verifies the editable snapshot keeps new fields and strips the api_key."""
    settings = c.Settings(llm=c.LlmSection(profiles={
        "ds": c.LlmProfile(vendor="deepseek", api_key_env="DEEPSEEK_API_KEY",
                           models=["deepseek-chat"], compat={"stream_options": False}, api_key="SECRET"),
    }))
    monkeypatch.setattr(c, "get_settings", lambda: settings)
    snap = c.editable_snapshot()
    prof = snap["llm"]["profiles"]["ds"]
    assert "api_key" not in prof
    assert prof["vendor"] == "deepseek"
    assert prof["api_key_env"] == "DEEPSEEK_API_KEY"  # 环境变量名非密钥，可透传
    assert prof["models"] == ["deepseek-chat"]
    assert prof["compat"]["stream_options"] is False  # CompatConfig 默认带 max_tokens_field
    # 密钥状态以 *_set 暴露
    assert snap["llm"]["api_key_set"]["ds"] is True
