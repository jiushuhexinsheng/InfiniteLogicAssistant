# -*- coding: utf-8 -*-
"""tests/server 共享夹具：client（隔离网络/配置的 TestClient）与 isolated_settings。
Shared fixtures for the server test package: an isolated TestClient and redirected settings files.
"""
import pytest
from fastapi.testclient import TestClient

import core.config as config_mod
import server as server_module
from _helpers import _NoAsr


@pytest.fixture
def client(monkeypatch, tmp_path):
    # 用隔离的 Settings 实例替代全局单例（不读真实 config.yaml，避免真实密钥/真实索引）
    monkeypatch.setattr(config_mod, "get_settings",
                        lambda: config_mod.Settings(rag=config_mod.RagSection(auto_index=False)))
    # LLM/ASR 一律视为未配置（config.yaml 里配了真实 key，绝不能打到外网）
    monkeypatch.setattr(config_mod, "is_llm_configured", lambda: False)
    monkeypatch.setattr(config_mod, "is_asr_configured", lambda: False)
    # ASR 客户端桩
    monkeypatch.setattr("core.voice.get_asr", lambda: _NoAsr())
    # 静态托管指向临时 dist
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<html>spa</html>", encoding="utf-8")
    monkeypatch.setattr(server_module, "WEB_DIST_DIR", dist)
    # 会话落盘（data/tasks）与 ROOT_DIR 隔离到临时目录，避免污染真实 data/
    monkeypatch.setattr(config_mod, "ROOT_DIR", tmp_path)
    # 历史存储隔离到临时目录
    import core.session.history as history_mod
    monkeypatch.setattr(history_mod, "get_history_store", lambda: history_mod.HistoryStore(tmp_path / "history.db"))
    return TestClient(server_module.app)


@pytest.fixture
def isolated_settings(monkeypatch, tmp_path):
    """把 config.yaml / secrets 重定向到临时文件并重置单例，避免碰真实配置。
    Redirects config.yaml / secrets to temp files and resets the singleton to avoid touching real config.
    """
    import core.config as config_mod
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text(
        "agent:\n  recursion_limit: 12\n  multi_agent: false\nrag:\n  auto_index: false\n",
        encoding="utf-8",
    )
    secrets_file = tmp_path / "config.secrets.yaml"
    secrets_file.write_text("llm:\n  api_key: ''\n", encoding="utf-8")
    monkeypatch.setattr(config_mod, "CONFIG_FILE", cfg_file)
    monkeypatch.setattr(config_mod, "SECRETS_FILE", secrets_file)
    monkeypatch.setattr(config_mod, "_settings", None)
    return config_mod
