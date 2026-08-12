# -*- coding: utf-8 -*-
import json

import pytest

from core.orchestrator.intent import IntentResult, judge_intent
from core.orchestrator.session import Session, SessionState


def _done_with_tool(type_: str, summary: str) -> dict:
    return {
        "type": "done",
        "message": {
            "role": "assistant",
            "content": "",
            "tool_calls": [{
                "id": "j", "type": "function",
                "function": {"name": "judge", "arguments": json.dumps({"type": type_, "summary": summary})},
            }],
        },
    }


class _FakeLLM:
    def __init__(self, script):
        self.script = script

    def retry_stream_chat(self, messages, tools=None):
        async def gen():
            for evt in self.script.pop(0):
                yield evt
        return gen()


# ── 会话状态机 ──

def test_session_state_transitions():
    s = Session()
    assert s.state == SessionState.IDLE
    s.set_state(SessionState.UNDERSTANDING)
    s.set_state(SessionState.FORMING_TASK)
    s.set_state(SessionState.CLARIFYING)
    s.set_state(SessionState.EXECUTING)
    s.set_state(SessionState.REPORTING)
    s.set_state(SessionState.IDLE)
    assert s.state == SessionState.IDLE


def test_session_illegal_transition_raises():
    s = Session()
    with pytest.raises(ValueError):
        s.set_state(SessionState.EXECUTING)  # idle 不能直达 executing


def test_session_stop_anytime():
    s = Session()
    s.set_state(SessionState.UNDERSTANDING)
    s.set_state(SessionState.STOPPED)  # 任意状态可停止
    assert s.state == SessionState.STOPPED


def test_session_summary_trims():
    s = Session()
    for i in range(20):
        s.append("user", str(i))
    out = s.summary(max_messages=5)
    assert len(out) == 5
    assert out[-1]["content"] == "19"


# ── 意图判断 ──

@pytest.mark.asyncio
async def test_judge_intent_task(monkeypatch):
    fake = _FakeLLM([[_done_with_tool("task", "把文件复制到下载")]])
    monkeypatch.setattr("core.orchestrator.intent.get_llm_client", lambda: fake)
    r = await judge_intent("把桌面readme.txt复制到下载")
    assert r == IntentResult(type="task", summary="把文件复制到下载")


@pytest.mark.asyncio
async def test_judge_intent_chit_chat(monkeypatch):
    fake = _FakeLLM([[_done_with_tool("chit_chat", "打招呼")]])
    monkeypatch.setattr("core.orchestrator.intent.get_llm_client", lambda: fake)
    r = await judge_intent("你好呀")
    assert r.type == "chit_chat"


@pytest.mark.asyncio
async def test_judge_intent_memory_hint_is_task():
    # 记忆类陈述规则判为任务，不走 LLM
    r = await judge_intent("记住，我平时用中文交流")
    assert r.type == "task"
    assert "记住用户偏好" in r.summary


@pytest.mark.asyncio
async def test_judge_intent_fallback_to_task(monkeypatch):
    class _Boom:
        def retry_stream_chat(self, messages, tools=None):
            raise RuntimeError("llm down")
    monkeypatch.setattr("core.orchestrator.intent.get_llm_client", lambda: _Boom())
    r = await judge_intent("打开记事本")
    assert r.type == "task"
