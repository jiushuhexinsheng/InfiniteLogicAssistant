# -*- coding: utf-8 -*-
"""server.py — API 端点测试（TestClient + monkeypatch，杜绝真实网络）。
API endpoint tests using TestClient + monkeypatch with no real network access.
"""
import pytest
from fastapi.testclient import TestClient

import server as server_module
import core.config as config_mod
from core.api import state
from core.orchestrator import pipeline as pipeline_mod
from core.orchestrator.intent import IntentResult
from core.orchestrator.task import MissingItem, Task


class _NoAsr:
    """ASR 不可用桩，隔离真实网络。
    A stub for an unavailable ASR, isolating real network access.
    """

    def available(self):
        return False


class _FakeLLMClient:
    """模拟 LlmClient.retry_stream_chat，隔离真实网络。
    A fake LlmClient.retry_stream_chat, isolating real network access.
    """

    def __init__(self, events):
        self.events = events

    async def retry_stream_chat(self, messages, tools=None, *, profile=None, **kwargs):
        for e in self.events:
            yield e


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


# ─── 基础端点 ───

def test_ping(client):
    """测试 /api/ping 健康检查端点。Tests the /api/ping health check endpoint."""
    data = client.get("/api/ping").json()
    assert data["ok"] is True
    assert "time" in data


def test_config_shape(client):
    """测试 /api/config 返回结构完整的配置快照。Tests /api/config returning a complete config snapshot shape."""
    data = client.get("/api/config").json()
    assert {"llm_available", "llm_profile", "asr_available", "asr_profile",
            "tts_available", "tts_profile", "wake_word", "vad"} <= set(data)
    assert data["llm_available"] is False
    assert data["asr_available"] is False


def test_tools_list(client):
    """测试 /api/tools 列出内置工具及其参数 schema。Tests /api/tools listing built-in tools and their parameter schemas."""
    data = client.get("/api/tools").json()
    assert data["ok"] is True
    names = [t["function"]["name"] for t in data["tools"]]
    assert {"get_datetime", "calculate", "web_search", "get_weather"} <= set(names)
    # schema 应含参数描述
    calc = next(t for t in data["tools"] if t["function"]["name"] == "calculate")
    assert "expression" in calc["function"]["parameters"]["properties"]


# ─── 语音转写 ───

def test_voice_transcribe_unconfigured(client):
    """测试 ASR 未配置时转写返回明确错误。Tests transcription returning a clear error when ASR is unconfigured."""
    resp = client.post("/api/voice/transcribe", json={"audio_base64": "xxx"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is False
    assert data["error"] == "ASR 未配置"


# ─── TTS：配置错误应映射为 400（可修复），而非 500 ───

def test_tts_config_error_maps_to_400(client, monkeypatch):
    """测试 TTS 配置错误映射为 400 而非 500。Tests TTS config errors mapping to 400 instead of 500."""
    import core.voice.tts as tts_mod
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
    """测试单工具调用成功返回输出。Tests a successful single tool call returning output."""
    resp = client.post("/api/tools/call", json={"name": "get_datetime", "args": {}})
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["status"] == "ok"
    assert data["output"]


def test_tools_call_calculate(client):
    """测试 calculate 工具计算表达式。Tests the calculate tool evaluating an expression."""
    resp = client.post("/api/tools/call", json={"name": "calculate", "args": {"expression": "2+3*4"}})
    assert resp.status_code == 200
    assert resp.json()["output"] == "14"


def test_tools_call_unknown_404(client):
    """测试调用未知工具返回 404。Tests calling an unknown tool returning 404."""
    resp = client.post("/api/tools/call", json={"name": "no_such_tool", "args": {}})
    assert resp.status_code == 404
    assert resp.json()["ok"] is False


def test_tools_call_invalid_args(client):
    """测试非法参数返回 400。Tests invalid arguments returning 400."""
    resp = client.post("/api/tools/call", json={"name": "get_datetime", "args": "not-a-dict"})
    assert resp.status_code == 400


def test_tools_call_bad_json(client):
    """测试请求体非 JSON 时返回 400。Tests a non-JSON request body returning 400."""
    resp = client.post("/api/tools/call", content="not json")
    assert resp.status_code == 400


def test_tools_call_high_risk_requires_confirm(client):
    """测试高风险工具未带 confirm 时要求确认。Tests high-risk tools requiring confirmation without a confirm flag."""
    # 非 read 工具无 confirm 字段 → 返回 needs_confirm，不执行
    resp = client.post("/api/tools/call", json={"name": "write_file", "args": {"path": "C:/x.txt", "content": "hi"}})
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is False
    assert data["needs_confirm"] is True


def test_tools_call_high_risk_with_confirm_executes(client, monkeypatch):
    """测试高风险工具带 confirm 后执行。Tests high-risk tools executing when confirm is provided."""
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
    """测试会话持久化写入任务 JSON 与对话历史。Tests session persistence writing task JSON and conversation history."""
    import json
    import core.session.history as history_mod
    from core.orchestrator.session import Session
    monkeypatch.setattr(config_mod, "ROOT_DIR", tmp_path)
    monkeypatch.setattr(history_mod, "get_history_store",
                        lambda: history_mod.HistoryStore(tmp_path / "history.db"))
    s = Session()
    s.append("user", "你好")
    s.append("assistant", "你好呀")
    s.task = Task("t", "算 1+1", {"a": 1}, [MissingItem(question="x")], "read")
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
    """测试会话历史的列表、详情与删除端点。Tests the history list, detail and delete endpoints."""
    import asyncio
    import core.session.history as history_mod
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
    """测试静态首页托管。Tests static index page hosting."""
    resp = client.get("/")
    assert resp.status_code == 200
    assert resp.text == "<html>spa</html>"


def test_static_file_and_spa_fallback(client):
    """测试静态文件托管与 SPA 兜底。Tests static file hosting and the SPA fallback."""
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
    """测试未知 API 路径返回 404。Tests unknown API paths returning 404."""
    resp = client.get("/api/nope")
    assert resp.status_code == 404
    assert resp.json()["ok"] is False


def test_resolve_dist_rejects_traversal(client):
    """测试 _resolve_dist 拒绝路径穿越。Tests _resolve_dist rejecting path traversal."""
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
    """测试语音对话结束后会话与控制器被清理。Tests sessions and controllers being cleaned up after voice utterances end."""
    async def fake_judge(text):
        return IntentResult(type="chit_chat", summary="打招呼")

    _FAKE_EVENTS = [
        {"type": "content_delta", "text": "你好"},
        {"type": "done", "message": {"role": "assistant", "content": "你好"}},
    ]
    monkeypatch.setattr(pipeline_mod, "judge_intent", fake_judge)
    monkeypatch.setattr(pipeline_mod, "get_llm_client", lambda: _FakeLLMClient(_FAKE_EVENTS))
    resp = client.post("/api/voice/utter", json={"text": "你好"})
    assert resp.status_code == 200
    # 流结束（done）后会话与控制器应从注册表移除
    assert state.sessions == {}
    assert state.controllers == {}
    assert state.session_ts == {}


def test_voice_utter_chit_chat(client, monkeypatch):
    """测试闲聊意图的流式响应。Tests the streaming response for chit-chat intents."""
    async def fake_judge(text):
        return IntentResult(type="chit_chat", summary="打招呼")

    _FAKE_EVENTS = [
        {"type": "content_delta", "text": "你好"},
        {"type": "done", "message": {"role": "assistant", "content": "你好"}},
    ]
    monkeypatch.setattr(pipeline_mod, "judge_intent", fake_judge)
    monkeypatch.setattr(pipeline_mod, "get_llm_client", lambda: _FakeLLMClient(_FAKE_EVENTS))
    resp = client.post("/api/voice/utter", json={"text": "你好"})
    assert resp.status_code == 200
    assert "content_delta" in resp.text and "你好" in resp.text
    assert resp.text.strip().endswith('data: {"type": "done"}')


def test_voice_utter_forwards_messages(client, monkeypatch):
    """测试 voice/utter 透传历史消息。Tests voice/utter forwarding the messages history."""
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
    """测试任务意图执行后发送 task_state 事件。Tests task intents emitting task_state events after execution."""
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
    """测试 /api/env 返回环境感知快照。Tests /api/env returning the environment awareness snapshot."""
    resp = client.get("/api/env")
    assert resp.status_code == 200
    assert "环境感知快照" in resp.json()["content"]


def test_detection_endpoint(client):
    """测试未配置服务时聚合检测全部跳过。Tests aggregated detection skipping everything when no services are configured."""
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


def test_memory_endpoint(client):
    """测试 /api/memory 返回记忆事实。Tests /api/memory returning memory facts."""
    resp = client.get("/api/memory")
    assert resp.status_code == 200
    assert "facts" in resp.json()


def test_schedules_endpoints(client, tmp_path, monkeypatch):
    """测试定时任务的增删查端点。Tests the scheduled task create, list and delete endpoints."""
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


# ─── /api/voice/answer：结构化确认 choice 透传 ───


def test_voice_answer_passes_structured_choice(client):
    """按钮回传的 choice 原样透传到会话通道；空 choice 视为未选择。
    The choice returned by buttons is passed through to the session channel unchanged;
    an empty choice counts as no selection.
    """
    import asyncio

    from core.api import state
    from core.orchestrator.control import StopController
    from core.orchestrator.pipeline import EventQueueChannel
    from core.orchestrator.session import Answer, Session

    session = Session(session_id="ans-choice")
    channel = EventQueueChannel(asyncio.Queue(), "ans-choice")
    session.channel = channel
    state.register(session, StopController())
    try:
        r = client.post("/api/voice/answer", json={"session_id": "ans-choice", "text": "", "choice": "yes"})
        assert r.status_code == 200
        assert channel.answers.get_nowait() == Answer(text="", choice="yes")

        # 空字符串 choice 视为未选择（不去猜用户意图）
        r2 = client.post("/api/voice/answer", json={"session_id": "ans-choice", "text": "随便吧", "choice": ""})
        assert r2.status_code == 200
        assert channel.answers.get_nowait() == Answer(text="随便吧", choice=None)
    finally:
        state.cleanup("ans-choice")


def test_voice_answer_accepts_arbitrary_choice(client):
    """choice 不限于 yes/no —— 权限策略的「允许一次 / 永久允许」等取值必须能透传。
    choice is not limited to yes/no: values such as the permission policy's
    allow-once / allow-always must pass through. 取值合法性由消费方自行校验。
    """
    import asyncio

    from core.api import state
    from core.orchestrator.control import StopController
    from core.orchestrator.pipeline import EventQueueChannel
    from core.orchestrator.session import Answer, Session

    session = Session(session_id="ans-arb")
    channel = EventQueueChannel(asyncio.Queue(), "ans-arb")
    session.channel = channel
    state.register(session, StopController())
    try:
        r = client.post("/api/voice/answer", json={"session_id": "ans-arb", "text": "", "choice": "always"})
        assert r.status_code == 200
        assert channel.answers.get_nowait() == Answer(text="", choice="always")
    finally:
        state.cleanup("ans-arb")


def test_voice_answer_unknown_session_404(client):
    """未知会话返回 404。An unknown session returns 404."""
    r = client.post("/api/voice/answer", json={"session_id": "nope", "text": "确认"})
    assert r.status_code == 404


# ─── /api/tools/call 走权限策略 ───


def _policy_returning(action, source="rule:test"):
    from core.tools.policy import Decision
    return lambda name, section=None: Decision(action, source)


def test_tool_call_denied_by_policy_returns_403(client, monkeypatch):
    """策略 deny 的工具即使带 confirm: true 也拒绝 —— confirm 不能覆盖 deny（关键安全不变式）。
    A policy-denied tool is refused even with confirm: true — confirm cannot override
    deny (the key security invariant)."""
    from core.api import tools as tools_api
    monkeypatch.setattr(tools_api, "decide", _policy_returning("deny", "rule:run_*"))
    r = client.post("/api/tools/call",
                    json={"name": "run_shell_tool", "args": {"command": "echo hi"}, "confirm": True})
    assert r.status_code == 403
    assert "禁止" in r.json()["error"]


def test_tool_call_allowed_by_policy_needs_no_confirm(client, monkeypatch):
    """策略 allow 的工具无需 confirm 标记即可执行。A policy-allowed tool runs without the confirm flag."""
    from core.api import tools as tools_api
    monkeypatch.setattr(tools_api, "decide", _policy_returning("allow", "tier:read"))
    r = client.post("/api/tools/call", json={"name": "get_datetime", "args": {}})
    assert r.status_code == 200
    assert r.json()["ok"] is True


def test_tool_call_ask_without_confirm_returns_needs_confirm(client, monkeypatch):
    """策略 ask 且未带 confirm → 返回 needs_confirm 让前端弹窗。
    A policy-ask tool without confirm returns needs_confirm so the front end can prompt."""
    from core.api import tools as tools_api
    monkeypatch.setattr(tools_api, "decide", _policy_returning("ask", "tier:exec"))
    r = client.post("/api/tools/call", json={"name": "run_shell_tool", "args": {"command": "echo hi"}})
    assert r.status_code == 200
    assert r.json().get("needs_confirm") is True


def test_tool_call_ask_with_confirm_executes(client, monkeypatch):
    """策略 ask 且带 confirm → 正常执行（前端弹窗确认后的重调路径）。
    A policy-ask tool with confirm executes normally (the front end's post-confirmation re-call)."""
    from core.api import tools as tools_api
    monkeypatch.setattr(tools_api, "decide", _policy_returning("ask", "tier:read"))
    r = client.post("/api/tools/call", json={"name": "get_datetime", "args": {}, "confirm": True})
    assert r.status_code == 200
    assert r.json()["ok"] is True


def test_tool_call_denied_by_policy_is_audited(client, monkeypatch):
    """策略拒绝必须落审计 —— 被拦下的调用到不了 TOOLS.acall（那里才记日志），
    不记则拒绝事件完全静默。A policy denial must be audited: the blocked call never
    reaches TOOLS.acall (where logging happens), so otherwise it would be silent."""
    from core.api import tools as tools_api
    recorded: list[str] = []
    monkeypatch.setattr(tools_api, "audit", lambda msg: recorded.append(msg))
    monkeypatch.setattr(tools_api, "decide", _policy_returning("deny", "rule:run_*"))
    r = client.post("/api/tools/call", json={"name": "run_shell_tool", "args": {"command": "echo hi"}})
    assert r.status_code == 403
    assert len(recorded) == 1
    assert "denied" in recorded[0] and "run_shell_tool" in recorded[0] and "rule:run_*" in recorded[0]
