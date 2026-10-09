# -*- coding: utf-8 -*-
"""提供商目录 / fetch-models 与 MCP 工具注册。Provider catalog, fetch-models and MCP tool registration."""
import pytest
from fastapi.testclient import TestClient

import core.config as config_mod
import server as server_module


# ─── /api/providers ───

def test_providers_catalog_no_secrets(client):
    """测试提供商目录不含密钥信息。Tests the providers catalog containing no secret fields."""
    data = client.get("/api/providers").json()
    assert data["ok"] is True
    assert set(data["catalog"]) == {"llm", "asr", "tts"}
    for items in data["catalog"].values():
        for item in items:
            assert "api_key" not in item and "api_token" not in item
    ds = next(x for x in data["catalog"]["llm"] if x["id"] == "deepseek")
    assert ds["endpoint"] == "https://api.deepseek.com"


def test_fetch_models_accepts_anthropic(client, monkeypatch):
    """测试 fetch-models 接受 anthropic 原生协议。Tests fetch-models accepting the anthropic native protocol."""
    import core.api.providers as providers_mod
    captured = {}

    async def fake_fetch(profile, api_key):
        captured.update(profile=profile, api_key=api_key)
        return ["claude-3-5-haiku-latest"]

    monkeypatch.setenv("LLM_API_KEY", "sk-test")
    monkeypatch.setattr(providers_mod, "_fetch_models", fake_fetch)
    resp = client.post("/api/providers/fetch-models", json={
        "section": "llm",
        "profile": {"provider": "anthropic", "endpoint": "https://api.anthropic.com",
                    "chat_path": "/v1/messages", "name": "anthropic"},
    })
    assert resp.status_code == 200
    assert resp.json()["models"] == ["claude-3-5-haiku-latest"]
    assert captured["profile"]["provider"] == "anthropic"  # 原生协议也已放行


def test_fetch_models_no_key(client, monkeypatch, tmp_path):
    """测试缺少 API Key 时 fetch-models 返回 400。Tests fetch-models returning 400 when no API key is available."""
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("ASR_API_KEY", raising=False)
    monkeypatch.delenv("TTS_API_KEY", raising=False)
    sfile = tmp_path / "secrets-empty.yaml"
    sfile.write_text("llm:\n  api_key: ''\n", encoding="utf-8")
    monkeypatch.setattr(config_mod, "SECRETS_FILE", sfile)
    resp = client.post("/api/providers/fetch-models", json={
        "section": "llm",
        "profile": {"provider": "openai", "endpoint": "https://api.deepseek.com",
                    "chat_path": "/v1/chat/completions", "name": "ds"},
    })
    assert resp.status_code == 400
    assert "API Key" in resp.json()["error"]


def test_fetch_models_success(client, monkeypatch):
    """测试 fetch-models 成功拉取模型且不回显密钥。Tests fetch-models fetching models successfully without echoing the key."""
    import core.api.providers as providers_mod
    seen = {}

    async def fake_fetch(profile, api_key):
        seen.update(profile=profile, api_key=api_key)
        return ["model-a", "model-b"]

    monkeypatch.setenv("LLM_API_KEY", "sk-test")
    monkeypatch.setattr(providers_mod, "_fetch_models", fake_fetch)
    resp = client.post("/api/providers/fetch-models", json={
        "section": "llm",
        "profile": {"provider": "openai", "endpoint": "https://api.deepseek.com",
                    "chat_path": "/v1/chat/completions", "name": "ds"},
    })
    assert resp.status_code == 200
    assert resp.json()["models"] == ["model-a", "model-b"]
    assert seen["profile"]["endpoint"] == "https://api.deepseek.com"
    assert seen["api_key"] == "sk-test"
    assert "sk-test" not in resp.text  # 密钥不回显


@pytest.mark.asyncio
async def test_fetch_models_dispatch_protocols():
    """测试各厂商协议（anthropic/gemini/openai）的模型解析。Tests model parsing for anthropic, gemini and openai protocols."""
    import httpx
    import core.api.providers as providers_mod

    async def _run(profile, handler):
        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        try:
            return await providers_mod._fetch_models(profile, "k", client=client)
        finally:
            await client.aclose()

    # anthropic：x-api-key 头 + data[].id
    def anth_handler(request):
        assert request.headers["x-api-key"] == "k"
        assert request.headers["anthropic-version"] == "2023-06-01"
        return httpx.Response(200, json={"data": [{"id": "claude-3-5-haiku-latest"}]})

    anth = await _run(
        {"provider": "anthropic", "endpoint": "https://api.anthropic.com"},
        anth_handler,
    )
    assert anth == ["claude-3-5-haiku-latest"]

    # gemini：剥 models/ 前缀 + 只留 generateContent 方法
    gem = await _run(
        {"provider": "gemini", "endpoint": "https://generativelanguage.googleapis.com"},
        lambda r: httpx.Response(200, json={"models": [
            {"name": "models/gemini-2.5-flash", "supportedGenerationMethods": ["generateContent"]},
            {"name": "models/text-embedding-004", "supportedGenerationMethods": ["embedContent"]},
        ]}),
    )
    assert gem == ["gemini-2.5-flash"]

    # openai：models_path 从 chat_path 推导
    oai = await _run(
        {"provider": "openai", "endpoint": "https://api.deepseek.com", "chat_path": "/v1/chat/completions"},
        lambda r: httpx.Response(200, json={"data": [{"id": "deepseek-chat"}]}),
    )
    assert oai == ["deepseek-chat"]


def test_mcp_integration_tools(monkeypatch):
    """测试 MCP 服务器启动后注册工具。Tests MCP servers registering tools after startup."""
    import sys
    from pathlib import Path
    from core import config as config_mod

    # 仓库根/scripts：本文件在 tests/server/ 下，需上溯三层。
    echo = str(Path(__file__).resolve().parent.parent.parent / "scripts" / "mcp_echo_server.py")

    monkeypatch.setattr(config_mod, "get_settings", lambda: config_mod.Settings(
        mcp=config_mod.McpSection(servers=[
            config_mod.McpServer(name="echo", command=sys.executable, args=[echo]),
        ]),
        rag=config_mod.RagSection(auto_index=False),
    ))
    # with 触发 lifespan：启动 MCP → 注册工具；退出时关闭
    with TestClient(server_module.app) as client:
        data = client.get("/api/tools").json()
        names = {t["function"]["name"] for t in data["tools"]}
        assert "mcp_echo_echo" in names
        assert "mcp_echo_add" in names
