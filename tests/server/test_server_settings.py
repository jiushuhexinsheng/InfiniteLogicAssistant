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


def test_patch_config_tolerates_legacy_vendor_presets(isolated_settings):
    """老配置带 vendor_presets（目录退役前的键）照常启动与 PATCH —— loader 建模前静默剥除
    （extra=forbid 否则直接拒绝）。An old config carrying vendor_presets (pre-retirement key)
    still boots and PATCHes — the loader strips it before modelling (extra=forbid would
    otherwise reject it outright)."""
    from fastapi.testclient import TestClient
    import server as server_module
    isolated_settings.CONFIG_FILE.write_text(
        "vendor_presets:\n  custom:\n    kind: llm\n    label: 我的厂商\n    endpoint: https://x\n    chat_path: /v1/chat/completions\n",
        encoding="utf-8",
    )
    with TestClient(server_module.app) as tc:
        resp = tc.patch("/api/config", json={"agent": {"recursion_limit": 5}})
        assert resp.status_code == 200
        assert tc.get("/api/config").status_code == 200


def test_patch_config_strips_retired_vad_keys(isolated_settings):
    """旧配置带三个退役 VAD 键：照常启动与 PATCH，首次保存即从磁盘清理。
    An old config carrying the three retired VAD keys still boots and PATCHes; the first
    save also removes them from disk."""
    import yaml
    from fastapi.testclient import TestClient
    import server as server_module

    isolated_settings.CONFIG_FILE.write_text(
        yaml.safe_dump({
            "voice": {"vad": {
                "silence_duration_ms": 1500,
                "max_duration_ms": 10000,
                "upload_throttle_ms": 500,
                "min_speech_ms": 100,
            }},
            "rag": {"auto_index": False},
        }, allow_unicode=True),
        encoding="utf-8",
    )
    with TestClient(server_module.app) as tc:
        assert tc.get("/api/config").status_code == 200
        resp = tc.patch("/api/config", json={"agent": {"recursion_limit": 5}})
        assert resp.status_code == 200

    saved = yaml.safe_load(isolated_settings.CONFIG_FILE.read_text(encoding="utf-8"))
    vad = saved.get("voice", {}).get("vad", {})
    assert "silence_duration_ms" not in vad
    assert "max_duration_ms" not in vad
    assert "upload_throttle_ms" not in vad
    assert vad.get("min_speech_ms") == 100


# ─── ASR 三模式（voice.asr.mode）的 PATCH 往返 ───

def test_patch_config_persists_asr_mode(isolated_settings):
    """PATCH 顶层 asr.mode → 归一化到 voice.asr 并落盘、热重载 —— 设置页三模式控件的保存路径。"""
    import yaml
    from fastapi.testclient import TestClient
    import server as server_module
    with TestClient(server_module.app) as tc:
        resp = tc.patch("/api/config", json={"asr": {"mode": "hybrid"}})
    assert resp.status_code == 200
    data = yaml.safe_load(isolated_settings.CONFIG_FILE.read_text(encoding="utf-8"))
    assert data["voice"]["asr"]["mode"] == "hybrid"
    assert isolated_settings.get_settings().voice.asr.mode == "hybrid"


def test_patch_config_rejects_local_model_present(isolated_settings):
    """`local_model_present` 是**只读展示**字段（仅出现在可编辑快照里）—— 回送会被
    `extra="forbid"` 拒绝 400，钉住「前端不得把它 PATCH 回来」。"""
    from fastapi.testclient import TestClient
    import server as server_module
    with TestClient(server_module.app) as tc:
        resp = tc.patch("/api/config", json={"asr": {"local_model_present": True}})
    assert resp.status_code == 400


def test_patch_config_migrates_legacy_local_asr_model(isolated_settings):
    """PATCH 路径与启动路径**同一套迁移**：用户显式写过旧键 voice.call.local_asr_model 时，
    一次 PATCH 会把新键写出来（不做则新键永远不出现，用户改了本地模型也读不到）。"""
    import yaml
    from fastapi.testclient import TestClient
    import server as server_module
    isolated_settings.CONFIG_FILE.write_text(
        "voice:\n  call:\n    local_asr_model: models/legacy-asr\n  asr:\n    active: a\n"
        "    profiles:\n      a:\n        provider: openai\n        endpoint: x\n        model: m\n",
        encoding="utf-8",
    )
    with TestClient(server_module.app) as tc:
        resp = tc.patch("/api/config", json={"agent": {"recursion_limit": 7}})
    assert resp.status_code == 200
    data = yaml.safe_load(isolated_settings.CONFIG_FILE.read_text(encoding="utf-8"))
    assert data["voice"]["asr"]["local_model"] == "models/legacy-asr"
