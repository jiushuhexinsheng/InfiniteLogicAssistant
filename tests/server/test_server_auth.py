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


def test_validate_bind_requires_token():
    """测试绑定非 localhost 时必须配置 token。Tests that binding non-localhost requires a token."""
    server_module._validate_bind("127.0.0.1", "")  # localhost 无需 token
    server_module._validate_bind("0.0.0.0", "abc")  # 非 localhost 但有 token
    import pytest
    with pytest.raises(RuntimeError):
        server_module._validate_bind("0.0.0.0", "")  # 非 localhost 且无 token → 拒绝
