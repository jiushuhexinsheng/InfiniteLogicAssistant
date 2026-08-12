# -*- coding: utf-8 -*-
"""server.py — API 端点测试（TestClient + monkeypatch，杜绝真实网络）"""
import pytest
from fastapi.testclient import TestClient

import server as server_module
from core import agent as agent_module
from core.orchestrator import pipeline as pipeline_mod
from core.orchestrator.intent import IntentResult
from core.orchestrator.task import Task


class _NoAsr:
    """ASR 不可用桩，隔离真实网络。"""

    def available(self):
        return False


@pytest.fixture
def client(monkeypatch, tmp_path):
    # LLM 一律视为未配置（config.yaml 里配了真实 key，绝不能打到外网）
    monkeypatch.setattr(server_module, "is_llm_configured", lambda: False)
    monkeypatch.setattr(server_module, "is_asr_configured", lambda: False)
    # ASR 客户端桩
    monkeypatch.setattr("core.voice.get_asr", lambda: _NoAsr())
    # 静态托管指向临时 dist
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<html>spa</html>", encoding="utf-8")
    monkeypatch.setattr(server_module, "WEB_DIST_DIR", dist)
    return TestClient(server_module.app)


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


# ─── SSE 聊天 ───

def test_ai_chat_unconfigured(client):
    resp = client.post("/api/ai/chat", json={"messages": [{"role": "user", "content": "hi"}]})
    assert resp.status_code == 200
    assert resp.json()["ok"] is False
    assert resp.json()["error"] == "LLM 未配置"


def test_ai_chat_sse_stream(client, monkeypatch):
    monkeypatch.setattr(server_module, "is_llm_configured", lambda: True)

    async def fake_run_agent(messages):
        yield {"type": "content_delta", "text": "你好"}
        yield {"type": "tool_start", "name": "get_datetime", "args": {}}
        yield {"type": "usage", "usage": {"total_tokens": 12}}
        yield {"type": "done"}

    monkeypatch.setattr(agent_module, "run_agent", fake_run_agent)

    resp = client.post("/api/ai/chat", json={"messages": [{"role": "user", "content": "hi"}]})
    assert resp.status_code == 200
    assert "text/event-stream" in resp.headers["content-type"]
    assert "content_delta" in resp.text
    assert "tool_start" in resp.text
    assert "usage" in resp.text
    assert "你好" in resp.text
    assert resp.text.strip().endswith('data: {"type": "done"}')


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


def test_voice_utter_task_done(client, monkeypatch):
    async def fake_judge(text):
        return IntentResult(type="task", summary="算 1+1")

    async def fake_form(intent):
        return Task("t", "算 1+1", {}, [], "read")

    async def fake_execute(task, session, cancel):
        return {"status": "done", "summary": "= 2", "steps": []}

    monkeypatch.setattr(pipeline_mod, "judge_intent", fake_judge)
    monkeypatch.setattr(pipeline_mod, "form_task", fake_form)
    monkeypatch.setattr(pipeline_mod, "execute_task", fake_execute)
    resp = client.post("/api/voice/utter", json={"text": "算 1+1"})
    assert resp.status_code == 200
    assert "task_state" in resp.text and "= 2" in resp.text
    assert resp.text.strip().endswith('data: {"type": "done"}')


def test_env_endpoint(client):
    resp = client.get("/api/env")
    assert resp.status_code == 200
    assert "环境感知快照" in resp.json()["content"]


def test_memory_endpoint(client):
    resp = client.get("/api/memory")
    assert resp.status_code == 200
    assert "facts" in resp.json()
