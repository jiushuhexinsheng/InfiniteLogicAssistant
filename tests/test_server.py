# -*- coding: utf-8 -*-
"""server.py — API 端点测试（TestClient + monkeypatch，杜绝真实网络）"""
import pytest
from fastapi.testclient import TestClient

import server as server_module
import core.config as config_mod
from core.api import state
from core.orchestrator import pipeline as pipeline_mod
from core.orchestrator.intent import IntentResult
from core.orchestrator.task import Task


class _NoAsr:
    """ASR 不可用桩，隔离真实网络。"""

    def available(self):
        return False


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
    import core.history as history_mod
    monkeypatch.setattr(history_mod, "get_history_store", lambda: history_mod.HistoryStore(tmp_path / "history.db"))
    return TestClient(server_module.app)


# ─── 安全：API token 与 host 校验 ───

def test_api_token_enforced(client, monkeypatch):
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
    server_module._validate_bind("127.0.0.1", "")  # localhost 无需 token
    server_module._validate_bind("0.0.0.0", "abc")  # 非 localhost 但有 token
    import pytest
    with pytest.raises(RuntimeError):
        server_module._validate_bind("0.0.0.0", "")  # 非 localhost 且无 token → 拒绝


# ─── 基础端点 ───

def test_ping(client):
    data = client.get("/api/ping").json()
    assert data["ok"] is True
    assert "time" in data


def test_config_shape(client):
    data = client.get("/api/config").json()
    assert {"llm_available", "llm_profile", "asr_available", "asr_profile",
            "tts_available", "tts_profile", "wake_word", "vad"} <= set(data)
    assert data["llm_available"] is False
    assert data["asr_available"] is False


def test_tools_list(client):
    data = client.get("/api/tools").json()
    assert data["ok"] is True
    names = [t["function"]["name"] for t in data["tools"]]
    assert {"get_datetime", "calculate", "web_search", "get_weather"} <= set(names)
    # schema 应含参数描述
    calc = next(t for t in data["tools"] if t["function"]["name"] == "calculate")
    assert "expression" in calc["function"]["parameters"]["properties"]


# ─── 语音转写 ───

def test_voice_transcribe_unconfigured(client):
    resp = client.post("/api/voice/transcribe", json={"audio_base64": "xxx"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is False
    assert data["error"] == "ASR 未配置"


# ─── TTS：配置错误应映射为 400（可修复），而非 500 ───

def test_tts_config_error_maps_to_400(client, monkeypatch):
    import core.tts as tts_mod
    # 启用后端 TTS，但 voiceclone 缺 voice_ref → 配置错误
    monkeypatch.setattr(config_mod, "is_tts_enabled", lambda: True)  # voice.py 前置检查
    monkeypatch.setattr(tts_mod, "is_tts_enabled", lambda: True)     # synthesize() 内检查
    monkeypatch.setattr(
        tts_mod, "resolve_tts_profile",
        lambda: ("openai", {"endpoint": "https://x.example", "api_key": "k",
                            "model": "mimo-v2.5-tts-voiceclone",
                            "chat_path": "/v1/chat/completions"}),
    )
    resp = client.post("/api/tts", json={"text": "你好"})
    assert resp.status_code == 400
    assert "voice_ref" in resp.json()["error"]


# ─── 单工具执行 ───

def test_tools_call_ok(client):
    resp = client.post("/api/tools/call", json={"name": "get_datetime", "args": {}})
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["status"] == "ok"
    assert data["output"]


def test_tools_call_calculate(client):
    resp = client.post("/api/tools/call", json={"name": "calculate", "args": {"expression": "2+3*4"}})
    assert resp.status_code == 200
    assert resp.json()["output"] == "14"


def test_tools_call_unknown_404(client):
    resp = client.post("/api/tools/call", json={"name": "no_such_tool", "args": {}})
    assert resp.status_code == 404
    assert resp.json()["ok"] is False


def test_tools_call_invalid_args(client):
    resp = client.post("/api/tools/call", json={"name": "get_datetime", "args": "not-a-dict"})
    assert resp.status_code == 400


def test_tools_call_bad_json(client):
    resp = client.post("/api/tools/call", content="not json")
    assert resp.status_code == 400


def test_tools_call_high_risk_requires_confirm(client):
    # 非 read 工具无 confirm 字段 → 返回 needs_confirm，不执行
    resp = client.post("/api/tools/call", json={"name": "write_file", "args": {"path": "C:/x.txt", "content": "hi"}})
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is False
    assert data["needs_confirm"] is True


def test_tools_call_high_risk_with_confirm_executes(client, monkeypatch):
    async def fake_acall(name, args):
        return "ok-stubbed"
    monkeypatch.setattr("core.api.tools.TOOLS.acall", fake_acall)
    resp = client.post("/api/tools/call", json={
        "name": "write_file", "args": {"path": "x", "content": "y"}, "confirm": True,
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["output"] == "ok-stubbed"


# ─── 会话持久化 ───

@pytest.mark.asyncio
async def test_persist_session_writes_task_json(tmp_path, monkeypatch):
    import json
    import core.history as history_mod
    from core.orchestrator.session import Session
    monkeypatch.setattr(config_mod, "ROOT_DIR", tmp_path)
    monkeypatch.setattr(history_mod, "get_history_store",
                        lambda: history_mod.HistoryStore(tmp_path / "history.db"))
    s = Session()
    s.append("user", "你好")
    s.append("assistant", "你好呀")
    s.task = Task("t", "算 1+1", {"a": 1}, ["x"], "read")
    await state.persist(s, created=1700000000.0)
    p = tmp_path / "data" / "tasks" / f"{s.id}.json"
    assert p.exists()
    data = json.loads(p.read_text(encoding="utf-8"))
    assert data["session_id"] == s.id
    assert data["task"]["goal"] == "算 1+1"
    assert "finished" in data
    # 完整会话历史也保存（含助手回复）
    conv = await history_mod.HistoryStore(tmp_path / "history.db").get_conversation(s.id)
    assert conv is not None
    assert [m["role"] for m in conv["messages"]] == ["user", "assistant"]
    assert conv["summary"] == "算 1+1"  # 摘要优先任务目标


# ─── 会话历史 ───

def test_history_endpoints(client, monkeypatch, tmp_path):
    import asyncio
    import core.history as history_mod
    store = history_mod.HistoryStore(tmp_path / "h.db")
    monkeypatch.setattr(history_mod, "get_history_store", lambda: store)
    asyncio.run(store.save_conversation(
        "c1", [{"role": "user", "content": "hi"}, {"role": "assistant", "content": "hello"}],
        status="done", summary="打招呼"))
    lst = client.get("/api/history").json()
    assert lst["conversations"][0]["id"] == "c1"
    assert lst["conversations"][0]["message_count"] == 2
    det = client.get("/api/history/c1").json()["conversation"]
    assert det["messages"][1]["content"] == "hello"
    assert client.delete("/api/history/c1").json()["ok"] is True
    assert client.get("/api/history/c1").status_code == 404


# ─── 静态托管 / SPA 兜底 / 路径穿越 ───

def test_static_index(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert resp.text == "<html>spa</html>"


def test_static_file_and_spa_fallback(client):
    dist = server_module.WEB_DIST_DIR
    (dist / "assets").mkdir()
    (dist / "assets" / "app.js").write_text("JS", encoding="utf-8")
    assert client.get("/assets/app.js").status_code == 200
    assert client.get("/assets/app.js").text == "JS"
    # 不存在的非 api 路径 → SPA 兜底 index.html
    resp = client.get("/some/route")
    assert resp.status_code == 200
    assert resp.text == "<html>spa</html>"


def test_unknown_api_404(client):
    resp = client.get("/api/nope")
    assert resp.status_code == 404
    assert resp.json()["ok"] is False


def test_resolve_dist_rejects_traversal(client):
    # 直接测 _resolve_dist：httpx/TestClient 会归一化 URL 里的 ../，HTTP 层测不到原始路径
    assert server_module._resolve_dist("../config.yaml") is None
    assert server_module._resolve_dist("..\\config.yaml") is None
    # 前导 / 会被剥掉按 dist 内相对路径解析，绝不会越出 dist
    p = server_module._resolve_dist("/etc/passwd")
    assert p is not None
    assert str(p).startswith(str(server_module.WEB_DIST_DIR.resolve()))
    assert server_module._resolve_dist("assets/app.js").name == "app.js"


# ─── 编排管线端点 ───

def test_voice_utter_session_cleaned_up(client, monkeypatch):
    async def fake_judge(text):
        return IntentResult(type="chit_chat", summary="打招呼")

    async def fake_stream(*args, **kwargs):
        yield {"type": "content_delta", "text": "你好"}
        yield {"type": "done", "message": {"role": "assistant", "content": "你好"}}

    monkeypatch.setattr(pipeline_mod, "judge_intent", fake_judge)
    monkeypatch.setattr(pipeline_mod, "stream_chat", fake_stream)
    resp = client.post("/api/voice/utter", json={"text": "你好"})
    assert resp.status_code == 200
    # 流结束（done）后会话与控制器应从注册表移除
    assert state.sessions == {}
    assert state.controllers == {}
    assert state.session_ts == {}


def test_voice_utter_chit_chat(client, monkeypatch):
    async def fake_judge(text):
        return IntentResult(type="chit_chat", summary="打招呼")

    async def fake_stream(*args, **kwargs):
        yield {"type": "content_delta", "text": "你好"}
        yield {"type": "done", "message": {"role": "assistant", "content": "你好"}}

    monkeypatch.setattr(pipeline_mod, "judge_intent", fake_judge)
    monkeypatch.setattr(pipeline_mod, "stream_chat", fake_stream)
    resp = client.post("/api/voice/utter", json={"text": "你好"})
    assert resp.status_code == 200
    assert "content_delta" in resp.text and "你好" in resp.text
    assert resp.text.strip().endswith('data: {"type": "done"}')


def test_voice_utter_forwards_messages(client, monkeypatch):
    captured = {}

    async def fake_run(text, session, events, controller, channel=None, messages=None):
        captured["messages"] = messages
        await events.put({"type": "done"})

    monkeypatch.setattr(pipeline_mod, "run_pipeline", fake_run)
    resp = client.post("/api/voice/utter", json={
        "text": "hi",
        "messages": [{"role": "user", "content": "a"}, {"role": "assistant", "content": "b"}],
    })
    assert resp.status_code == 200
    assert captured["messages"] == [{"role": "user", "content": "a"}, {"role": "assistant", "content": "b"}]


def test_voice_utter_task_done(client, monkeypatch):
    async def fake_judge(text):
        return IntentResult(type="task", summary="算 1+1")

    async def fake_form(intent):
        return Task("t", "算 1+1", {}, [], "read")

    async def fake_execute(task, session, cancel, events=None):
        return {"status": "done", "summary": "= 2", "steps": []}

    async def fake_extract(task, result, store):
        pass  # 避免真实 LLM 提取

    monkeypatch.setattr(pipeline_mod, "judge_intent", fake_judge)
    monkeypatch.setattr(pipeline_mod, "form_task", fake_form)
    monkeypatch.setattr(pipeline_mod, "execute_task", fake_execute)
    monkeypatch.setattr(pipeline_mod, "extract_and_store", fake_extract)
    resp = client.post("/api/voice/utter", json={"text": "算 1+1"})
    assert resp.status_code == 200
    assert "task_state" in resp.text and "= 2" in resp.text
    assert resp.text.strip().endswith('data: {"type": "done"}')


def test_env_endpoint(client):
    resp = client.get("/api/env")
    assert resp.status_code == 200
    assert "环境感知快照" in resp.json()["content"]


def test_detection_endpoint(client):
    # 未配置任何服务 → 聚合检测全部 skip，不发真实网络
    resp = client.get("/api/detection")
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    report = data["report"]
    assert set(report) == {"environment", "config", "connectivity"}
    assert len(report["connectivity"]) == 3
    assert all(c["status"] == "skip" for c in report["connectivity"])


# ─── 设置 API：PATCH /config + PUT /config/secrets（隔离到临时文件）───

@pytest.fixture
def isolated_settings(monkeypatch, tmp_path):
    """把 config.yaml / secrets 重定向到临时文件并重置单例，避免碰真实配置。"""
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


def test_patch_config_persists_and_reloads(isolated_settings):
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
    from fastapi.testclient import TestClient
    import server as server_module

    with TestClient(server_module.app) as tc:
        resp = tc.patch("/api/config", json={"server": {"port": 9000}})
    assert resp.json()["restart_required"] is True


def test_patch_config_rejects_api_key(isolated_settings):
    # 密钥不能通过 PATCH 写入 config.yaml（会被剥离）
    from fastapi.testclient import TestClient
    import server as server_module

    with TestClient(server_module.app) as tc:
        resp = tc.patch("/api/config", json={"llm": {"profiles": {"deepseek": {"api_key": "sk-leak"}}}})
    assert resp.status_code == 200
    assert "sk-leak" not in isolated_settings.CONFIG_FILE.read_text(encoding="utf-8")


def test_patch_config_invalid_value_400(isolated_settings):
    from fastapi.testclient import TestClient
    import server as server_module

    with TestClient(server_module.app) as tc:
        resp = tc.patch("/api/config", json={"agent": {"recursion_limit": "abc"}})
    assert resp.status_code == 400
    assert "配置无效" in resp.json()["error"]


def test_put_secrets_writes_file_no_echo(isolated_settings):
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


def test_memory_endpoint(client):
    resp = client.get("/api/memory")
    assert resp.status_code == 200
    assert "facts" in resp.json()


def test_schedules_endpoints(client, tmp_path, monkeypatch):
    import core.scheduler.scheduler as sched_mod
    from core.scheduler.scheduler import Scheduler
    monkeypatch.setattr(sched_mod, "get_scheduler", lambda: Scheduler(path=tmp_path / "sched.json"))
    assert client.get("/api/schedules").json()["schedules"] == []
    r = client.post("/api/schedules", json={"cron": "0 9 * * *", "prompt": "查天气"})
    assert r.status_code == 200
    sid = r.json()["schedule"]["id"]
    assert len(client.get("/api/schedules").json()["schedules"]) == 1
    assert client.delete(f"/api/schedules/{sid}").status_code == 200
    assert client.get("/api/schedules").json()["schedules"] == []


# ─── PATCH /config：voice 归一化 / 删 profile / 保留 vendor_presets ───

def test_patch_config_normalizes_asr_tts_under_voice(isolated_settings):
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


# ─── /api/providers ───

def test_providers_catalog_no_secrets(client):
    data = client.get("/api/providers").json()
    assert data["ok"] is True
    assert set(data["catalog"]) == {"llm", "asr", "tts"}
    for items in data["catalog"].values():
        for item in items:
            assert "api_key" not in item and "api_token" not in item
    ds = next(x for x in data["catalog"]["llm"] if x["id"] == "deepseek")
    assert ds["endpoint"] == "https://api.deepseek.com"


def test_fetch_models_requires_openai(client):
    resp = client.post("/api/providers/fetch-models", json={
        "section": "llm",
        "profile": {"provider": "anthropic", "endpoint": "https://api.anthropic.com",
                    "chat_path": "/v1/messages", "name": "anthropic"},
    })
    assert resp.status_code == 400


def test_fetch_models_no_key(client, monkeypatch, tmp_path):
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
    import core.api.providers as providers_mod
    seen = {}

    async def fake_fetch(endpoint, path, api_key, timeout):
        seen.update(endpoint=endpoint, path=path, api_key=api_key)
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
    assert seen["endpoint"] == "https://api.deepseek.com"
    assert seen["path"] == "/v1/models"
    assert seen["api_key"] == "sk-test"
    assert "sk-test" not in resp.text  # 密钥不回显


def test_mcp_integration_tools(monkeypatch):
    import sys
    from pathlib import Path
    from core import config as config_mod

    echo = str(Path(__file__).resolve().parent.parent / "scripts" / "mcp_echo_server.py")

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
