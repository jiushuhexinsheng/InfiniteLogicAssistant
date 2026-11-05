# -*- coding: utf-8 -*-
"""安全：API token 与 host 校验。Security: API token and host validation."""
import core.config as config_mod
import server as server_module


# ─── 安全：API token 与 host 校验 ───

def test_api_token_enforced(client, monkeypatch):
    """测试 API token 校验：未带 401、带正确 token 200、静态资源不校验。Tests API token enforcement: 401 without, 200 with, static assets unchecked."""
    monkeypatch.setattr(config_mod, "get_settings", lambda: config_mod.Settings(
        server=config_mod.ServerSection(api_token="secret-token"),
        rag=config_mod.RagSection(auto_index=False),
    ))
    # 未带 token → 401
    resp = client.get("/api/tools")
    assert resp.status_code == 401
    # 带正确 token → 200
    resp = client.get("/api/tools", headers={"X-API-Token": "secret-token"})
    assert resp.status_code == 200
    # 静态资源不校验
    resp = client.get("/")
    assert resp.status_code == 200


def test_untrusted_host_rejected(client):
    """无 token 时 Host 不在白名单 → 421（DNS rebinding 防线）。"""
    resp = client.get("/api/ping", headers={"Host": "evil.example"})
    assert resp.status_code == 421


def test_untrusted_origin_rejected(client):
    """跨站 Origin → 403；本机 Origin 放行。"""
    resp = client.get("/api/ping", headers={"Origin": "https://evil.example"})
    assert resp.status_code == 403
    resp = client.get("/api/ping", headers={"Origin": "http://127.0.0.1:8520"})
    assert resp.status_code == 200


def test_remote_client_without_token_rejected(monkeypatch):
    """远端 peer 且无 token → 401（绕过 start_server 直接公开绑定的兜底）。"""
    from fastapi.testclient import TestClient
    monkeypatch.setattr(config_mod, "get_settings", lambda: config_mod.Settings(
        rag=config_mod.RagSection(auto_index=False),
    ))
    remote = TestClient(server_module.app, client=("203.0.113.9", 4321))
    assert remote.get("/api/ping").status_code == 401


def test_docs_require_token_when_configured(client, monkeypatch):
    """配置 token 后 /openapi.json 也需要 X-API-Token。"""
    monkeypatch.setattr(config_mod, "get_settings", lambda: config_mod.Settings(
        server=config_mod.ServerSection(api_token="secret-token"),
        rag=config_mod.RagSection(auto_index=False),
    ))
    assert client.get("/openapi.json").status_code == 401
    assert client.get("/openapi.json",
                      headers={"X-API-Token": "secret-token"}).status_code == 200


def test_websocket_untrusted_origin_rejected(client):
    """WS 握手在 accept 前拒绝跨站 Origin。"""
    import pytest
    from starlette.websockets import WebSocketDisconnect
    with pytest.raises(WebSocketDisconnect) as e:
        with client.websocket_connect(
            "/api/voice/asr/stream", headers={"origin": "https://evil.example"},
        ):
            pass
    assert e.value.code == 4403


def test_validate_bind_requires_token():
    """测试绑定非 localhost 时必须配置 token。Tests that binding non-localhost requires a token."""
    server_module._validate_bind("127.0.0.1", "")  # localhost 无需 token
    server_module._validate_bind("0.0.0.0", "abc")  # 非 localhost 但有 token
    import pytest
    with pytest.raises(RuntimeError):
        server_module._validate_bind("0.0.0.0", "")  # 非 localhost 且无 token → 拒绝
