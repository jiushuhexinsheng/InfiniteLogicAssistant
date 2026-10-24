# -*- coding: utf-8 -*-
"""分组模型清单与全局模型切换端点。Grouped model catalogue and global model switching."""

import yaml

from core import config as config_mod


def _settings(active: str = ""):
    """两个 LLM profile 的隔离配置。Isolated settings with two LLM profiles."""
    return config_mod.Settings(
        llm=config_mod.LlmSection(active=active, profiles={
            "p1": config_mod.LlmProfile(model="m1", models=["m1", "m-only"]),
            "p2": config_mod.LlmProfile(model="m2"),
        }),
        rag=config_mod.RagSection(auto_index=False),
    )


def test_llm_models_groups_union_and_active(client, monkeypatch):
    """models 与当前 model 去重合并；active 为空串时解析到第一个 profile。
    models and the current model merge without duplicates; an empty active resolves
    to the first profile."""
    monkeypatch.setattr(config_mod, "get_settings", lambda: _settings(active=""))

    r = client.get("/api/llm/models")

    assert r.status_code == 200
    body = r.json()
    assert body["active"] == {"provider": "p1", "model": "m1"}
    assert [g["provider"] for g in body["groups"]] == ["p1", "p2"]
    assert body["groups"][0]["models"] == ["m1", "m-only"]
    assert body["groups"][1]["models"] == ["m2"]
    assert body["groups"][0]["current_model"] == "m1"
    assert "api_key" not in r.text


def test_config_exposes_llm_model(client, monkeypatch):
    """顶栏需要模型名（同一供应商内切换模型时 llm_profile 不变）。
    The header needs the model name (llm_profile does not change when switching models
    inside one provider)."""
    monkeypatch.setattr(config_mod, "get_settings", lambda: _settings(active="p2"))

    data = client.get("/api/config").json()

    assert data["llm_profile"] == "p2"
    assert data["llm_model"] == "m2"


def test_set_active_model_persists_and_keeps_other_profiles(client, isolated_settings):
    """写入 active/profile.model 并保留其他 profile 与字段（不整段替换）。
    Writes active/profile.model while keeping the other profiles and fields intact."""
    isolated_settings.CONFIG_FILE.write_text(
        yaml.safe_dump({
            "llm": {
                "active": "p1",
                "profiles": {
                    "p1": {"provider": "openai", "endpoint": "https://a", "model": "m1",
                           "models": ["m1", "m2"], "temperature": 0.3},
                    "p2": {"provider": "openai", "endpoint": "https://b", "model": "m9"},
                },
            },
            "rag": {"auto_index": False},
        }, allow_unicode=True),
        encoding="utf-8",
    )

    r = client.post("/api/llm/active-model", json={"provider": "p2", "model": "m9"})

    assert r.status_code == 200
    assert r.json()["active"] == {"provider": "p2", "model": "m9"}
    saved = yaml.safe_load(isolated_settings.CONFIG_FILE.read_text(encoding="utf-8"))
    assert saved["llm"]["active"] == "p2"
    assert saved["llm"]["profiles"]["p2"]["model"] == "m9"
    assert saved["llm"]["profiles"]["p1"]["temperature"] == 0.3
    assert set(saved["llm"]["profiles"]) == {"p1", "p2"}


def test_set_active_model_rejects_unknown_provider_or_model(client, isolated_settings):
    """未知供应商 / 不在该供应商模型集合中的模型 → 400。
    Unknown provider, or a model outside that provider's set → 400."""
    isolated_settings.CONFIG_FILE.write_text(
        yaml.safe_dump({
            "llm": {"active": "p1", "profiles": {
                "p1": {"provider": "openai", "endpoint": "https://a", "model": "m1",
                       "models": ["m1"]},
            }},
            "rag": {"auto_index": False},
        }, allow_unicode=True),
        encoding="utf-8",
    )

    assert client.post("/api/llm/active-model",
                       json={"provider": "nope", "model": "m1"}).status_code == 400
    assert client.post("/api/llm/active-model",
                       json={"provider": "p1", "model": "not-listed"}).status_code == 400


def test_set_active_model_migrates_legacy_keys_and_strips_secrets(client, isolated_settings):
    """旧配置（vendor_presets / 遗留 api_key）也能切换模型：与 PATCH 走同一套迁移与剥密钥。
    Legacy configs (vendor_presets / leftover api_key) can switch models too: same
    migrations and secret stripping as PATCH."""
    isolated_settings.CONFIG_FILE.write_text(
        yaml.safe_dump({
            "llm": {
                "active": "p1",
                "profiles": {
                    "p1": {"provider": "openai", "endpoint": "https://a", "model": "m1",
                           "models": ["m1", "m2"], "api_key": "sk-left-in-config"},
                },
            },
            "vendor_presets": {"old": {"endpoint": "https://old"}},
            "rag": {"auto_index": False},
        }, allow_unicode=True),
        encoding="utf-8",
    )

    r = client.post("/api/llm/active-model", json={"provider": "p1", "model": "m2"})

    assert r.status_code == 200
    saved = yaml.safe_load(isolated_settings.CONFIG_FILE.read_text(encoding="utf-8"))
    assert "vendor_presets" not in saved
    assert "api_key" not in saved["llm"]["profiles"]["p1"]
    assert saved["llm"]["profiles"]["p1"]["model"] == "m2"
