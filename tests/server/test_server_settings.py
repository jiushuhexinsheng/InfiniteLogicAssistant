# -*- coding: utf-8 -*-
"""设置 API：PATCH /config、PUT /config/secrets 及 voice 归一化等落盘行为。
Settings API: PATCH /config, PUT /config/secrets and their on-disk normalization behavior.
"""


# ─── 设置 API：PATCH /config + PUT /config/secrets（隔离到临时文件）───

def test_patch_config_persists_and_reloads(isolated_settings):
    """测试 PATCH /api/config 持久化并热重载。Tests PATCH /api/config persisting changes and hot-reloading."""
    from fastapi.testclient import TestClient
    import server as server_module

    with TestClient(server_module.app) as tc:
        resp = tc.patch("/api/config", json={"agent": {"recursion_limit": 3}})
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["restart_required"] is False
    # 热重载后单例反映新值
    assert isolated_settings.get_settings().agent.recursion_limit == 3
    # 落盘
    assert "recursion_limit: 3" in isolated_settings.CONFIG_FILE.read_text(encoding="utf-8")


def test_patch_config_restart_required_for_server(isolated_settings):
    """测试修改 server 配置标记需要重启。Tests server config changes being flagged as restart-required."""
    from fastapi.testclient import TestClient
    import server as server_module

    with TestClient(server_module.app) as tc:
        resp = tc.patch("/api/config", json={"server": {"port": 9000}})
    assert resp.json()["restart_required"] is True


def test_patch_config_rejects_api_key(isolated_settings):
    """测试 PATCH 配置时剥离 api_key 密钥。Tests api_key secrets being stripped from PATCH config."""
    # 密钥不能通过 PATCH 写入 config.yaml（会被剥离）
    from fastapi.testclient import TestClient
    import server as server_module

    with TestClient(server_module.app) as tc:
        resp = tc.patch("/api/config", json={"llm": {"profiles": {"deepseek": {"api_key": "sk-leak"}}}})
    assert resp.status_code == 200
    assert "sk-leak" not in isolated_settings.CONFIG_FILE.read_text(encoding="utf-8")


def test_patch_config_invalid_value_400(isolated_settings):
    """测试非法配置值返回 400。Tests invalid config values returning 400."""
    from fastapi.testclient import TestClient
    import server as server_module

    with TestClient(server_module.app) as tc:
        resp = tc.patch("/api/config", json={"agent": {"recursion_limit": "abc"}})
    assert resp.status_code == 400
    assert "配置无效" in resp.json()["error"]


def test_put_secrets_writes_file_no_echo(isolated_settings):
    """测试 PUT secrets 写入文件且不回显密钥。Tests PUT secrets writing to file without echoing the key."""
    import yaml
    from fastapi.testclient import TestClient
    import server as server_module

    with TestClient(server_module.app) as tc:
        resp = tc.put("/api/config/secrets", json={"path": "llm.api_key", "value": "sk-test"})
    assert resp.status_code == 200
    assert resp.json()["set"] is True
    # 写入了 secrets 文件
    data = yaml.safe_load(isolated_settings.SECRETS_FILE.read_text(encoding="utf-8"))
    assert data["llm"]["api_key"] == "sk-test"
    # 响应不回显密钥
    assert "sk-test" not in resp.text


def test_put_secrets_per_profile(isolated_settings):
    """测试按 profile 写入与清除密钥。Tests writing and clearing secrets per profile."""
    import yaml
    from fastapi.testclient import TestClient
    import server as server_module

    with TestClient(server_module.app) as tc:
        resp = tc.put("/api/config/secrets", json={"path": "llm.profiles.deepseek", "value": "sk-ds"})
    assert resp.status_code == 200
    data = yaml.safe_load(isolated_settings.SECRETS_FILE.read_text(encoding="utf-8"))
    assert data["llm"]["profiles"]["deepseek"] == "sk-ds"
    # 清除
    with TestClient(server_module.app) as tc2:
        resp2 = tc2.put("/api/config/secrets", json={"path": "llm.profiles.deepseek", "value": ""})
    assert resp2.json()["set"] is False
    data = yaml.safe_load(isolated_settings.SECRETS_FILE.read_text(encoding="utf-8"))
    assert "profiles" not in data.get("llm", {}) or "deepseek" not in data["llm"].get("profiles", {})


# ─── PATCH /config：voice 归一化 / 删 profile / 保留 vendor_presets ───

def test_patch_config_normalizes_asr_tts_under_voice(isolated_settings):
    """测试顶层 asr/tts 配置归一化到 voice 段。Tests top-level asr/tts config being normalized into the voice section."""
    # 前端快照把 asr/tts 放顶层，PATCH 应归一化到 voice 段（Settings extra=forbid 拒绝顶层）
    import yaml
    from fastapi.testclient import TestClient
    import server as server_module
    with TestClient(server_module.app) as tc:
        resp = tc.patch("/api/config", json={
            "tts": {"enabled": True, "active": "openai", "profiles": {"openai": {"provider": "openai"}}},
        })
    assert resp.status_code == 200
    data = yaml.safe_load(isolated_settings.CONFIG_FILE.read_text(encoding="utf-8"))
    assert data["voice"]["tts"]["enabled"] is True
    assert "tts" not in data


def test_patch_config_deletes_profile(isolated_settings):
    """测试 PATCH 配置时删除缺失的 profile。Tests PATCH config deleting profiles that are no longer present."""
    import yaml
    from fastapi.testclient import TestClient
    import server as server_module
    isolated_settings.CONFIG_FILE.write_text(
        "llm:\n  active: a\n  profiles:\n"
        "    a:\n      provider: openai\n      endpoint: x\n      model: m\n      chat_path: /v1/chat/completions\n"
        "    b:\n      provider: openai\n      endpoint: y\n      model: n\n",
        encoding="utf-8",
    )
    with TestClient(server_module.app) as tc:
        resp = tc.patch("/api/config", json={
            "llm": {"active": "a", "profiles": {
                "a": {"provider": "openai", "endpoint": "x", "model": "m", "chat_path": "/v1/chat/completions"},
            }},
        })
    assert resp.status_code == 200
    data = yaml.safe_load(isolated_settings.CONFIG_FILE.read_text(encoding="utf-8"))
    assert set(data["llm"]["profiles"]) == {"a"}  # 被删的 b 不残留


def test_patch_config_preserves_vendor_presets(isolated_settings):
    """测试 PATCH 配置保留 vendor_presets。Tests PATCH config preserving vendor presets."""
    import yaml
    from fastapi.testclient import TestClient
    import server as server_module
    isolated_settings.CONFIG_FILE.write_text(
        "vendor_presets:\n  custom:\n    kind: llm\n    label: 我的厂商\n    endpoint: https://x\n    chat_path: /v1/chat/completions\n",
        encoding="utf-8",
    )
    with TestClient(server_module.app) as tc:
        resp = tc.patch("/api/config", json={"agent": {"recursion_limit": 5}})
    assert resp.status_code == 200
    data = yaml.safe_load(isolated_settings.CONFIG_FILE.read_text(encoding="utf-8"))
    assert data["vendor_presets"]["custom"]["label"] == "我的厂商"
