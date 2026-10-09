# -*- coding: utf-8 -*-
"""编排管线端点、env/detection 快照与 /voice/utter 的 mode 透传。
Orchestration pipeline endpoints, env/detection snapshots and /voice/utter mode pass-through.
"""
from core.api import state
from core.orchestrator import pipeline as pipeline_mod
from core.orchestrator.intent import IntentResult
from core.orchestrator.task import Task

from _helpers import _FakeLLMClient


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
    # 末帧必须是 done（seq 由 SSE 层追加，docs/designs/06 —— 不再断言精确 JSON 全文）。
    # The last frame must be done (seq is appended by the SSE layer, docs/designs/06 —
    # no longer asserting the exact JSON verbatim).
    assert resp.text.strip().split("\n\n")[-1].startswith('data: {"type": "done"')


def test_voice_utter_forwards_messages(client, monkeypatch):
    """测试 voice/utter 透传历史消息。Tests voice/utter forwarding the messages history."""
    captured = {}

    async def fake_run(text, session, events, controller, channel=None, messages=None, mode="chat"):
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

    async def fake_extract(task, result, store, session=None):
        pass  # 避免真实 LLM 提取

    monkeypatch.setattr(pipeline_mod, "judge_intent", fake_judge)
    monkeypatch.setattr(pipeline_mod, "form_task", fake_form)
    monkeypatch.setattr(pipeline_mod, "execute_task", fake_execute)
    monkeypatch.setattr(pipeline_mod, "extract_and_store", fake_extract)
    resp = client.post("/api/voice/utter", json={"text": "算 1+1"})
    assert resp.status_code == 200
    assert "task_state" in resp.text and "= 2" in resp.text
    # 末帧必须是 done（seq 由 SSE 层追加，docs/designs/06 —— 不再断言精确 JSON 全文）。
    # The last frame must be done (seq is appended by the SSE layer, docs/designs/06 —
    # no longer asserting the exact JSON verbatim).
    assert resp.text.strip().split("\n\n")[-1].startswith('data: {"type": "done"')


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


# ─── /voice/utter 的 mode 透传 ───

def test_voice_utter_passes_mode_to_pipeline(client, monkeypatch):
    """mode 从请求体传到 pipeline；非法/缺失一律按 chat（向后兼容）。"""
    from core.orchestrator import pipeline as pl

    captured: dict = {}

    async def fake_run_pipeline(text, session, events, controller, channel=None,
                                messages=None, mode="chat"):
        captured["mode"] = mode

    # voice.py 在函数内 `from core.orchestrator.pipeline import run_pipeline`，
    # 即调用时才读模块属性 → patch 源模块即可生效。
    # voice.py imports run_pipeline lazily inside the handler, so patching the source
    # module attribute takes effect.
    monkeypatch.setattr(pl, "run_pipeline", fake_run_pipeline)

    for payload, expected in (
        ({"text": "做事", "mode": "task"}, "task"),
        ({"text": "做事", "mode": "胡说"}, "chat"),   # 非法值回退
        ({"text": "做事"}, "chat"),                   # 缺省（老前端）
    ):
        with client.stream("POST", "/api/voice/utter", json=payload) as r:
            assert r.status_code == 200
            list(r.iter_lines())
        assert captured["mode"] == expected, f"{payload} → 期望 {expected}"
