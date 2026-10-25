# -*- coding: utf-8 -*-
"""会话状态机与意图判断的测试。
Tests for the session state machine and intent judging.
"""
import json

import pytest

from core.orchestrator.intent import IntentResult, judge_intent
from core.orchestrator.session import Session, SessionState


def _done_with_args(args: dict) -> dict:
    return {
        "type": "done",
        "message": {
            "role": "assistant",
            "content": "",
            "tool_calls": [{
                "id": "j", "type": "function",
                "function": {"name": "judge", "arguments": json.dumps(args)},
            }],
        },
    }


class _FakeLLM:
    """模拟 LLM 客户端，按脚本回放事件。Simulates an LLM client replaying scripted events."""

    def __init__(self, script):
        self.script = script

    def retry_stream_chat(self, messages, tools=None, **kwargs):
        async def gen():
            for evt in self.script.pop(0):
                yield evt
        return gen()


# ── 会话状态机 ──

def test_session_state_transitions():
    """会话状态按合法顺序迁移。The session state transitions in the legal order."""
    s = Session()
    assert s.state == SessionState.IDLE
    s.set_state(SessionState.UNDERSTANDING)
    s.set_state(SessionState.CLARIFYING)
    s.set_state(SessionState.EXECUTING)
    s.set_state(SessionState.REPORTING)
    s.set_state(SessionState.IDLE)
    assert s.state == SessionState.IDLE


def test_session_task_mode_states_are_gone():
    """任务模式的专用状态已删除（不再区分对话/任务）。
    The task-mode-only states are gone (no more chat/task split)."""
    for name in ("CHIT_CHAT", "FORMING_TASK", "CONFIRMING"):
        assert not hasattr(SessionState, name), f"{name} 应随任务模式一起删除"


def test_session_illegal_transition_raises():
    """非法状态迁移抛出 ValueError。Illegal state transitions raise ValueError."""
    s = Session()
    with pytest.raises(ValueError):
        s.set_state(SessionState.EXECUTING)  # idle 不能直达 executing


def test_session_stop_anytime():
    """任意状态都可停止。Any state can be stopped."""
    s = Session()
    s.set_state(SessionState.UNDERSTANDING)
    s.set_state(SessionState.STOPPED)  # 任意状态可停止
    assert s.state == SessionState.STOPPED


def test_session_summary_trims():
    """summary 按上限裁剪历史。The summary trims history to the cap."""
    s = Session()
    for i in range(20):
        s.append("user", str(i))
    out = s.summary(max_messages=5)
    assert len(out) == 5
    assert out[-1]["content"] == "19"


# ── 意图判断 ──

@pytest.mark.asyncio
async def test_judge_returns_summary_with_simple_defaults(monkeypatch):
    """只回 summary 时：simple 复杂度、不反问。Summary alone means simple and unambiguous."""
    fake = _FakeLLM([[_done_with_args({"summary": "把文件复制到下载"})]])
    monkeypatch.setattr("core.orchestrator.intent.get_llm_client", lambda: fake)
    r = await judge_intent("把桌面readme.txt复制到下载")
    assert r == IntentResult(summary="把文件复制到下载", complexity="simple", ambiguous=False)


@pytest.mark.asyncio
async def test_judge_complex_intent(monkeypatch):
    """复杂意图（多步骤/多子任务）标记为 complex。Complex intents are flagged."""
    fake = _FakeLLM([[_done_with_args({"summary": "整理并分析整个项目", "complexity": "complex"})]])
    monkeypatch.setattr("core.orchestrator.intent.get_llm_client", lambda: fake)
    r = await judge_intent("把整个项目梳理一遍，写报告，再列修复清单")
    assert r.complexity == "complex"


@pytest.mark.asyncio
async def test_judge_ambiguous_carries_question_and_options(monkeypatch):
    """没把握时只返回一个问题与可选选项（供一次反问）。Ambiguity carries one question."""
    fake = _FakeLLM([[_done_with_args({
        "summary": "删除文件",
        "ambiguous": True,
        "question": "要删除哪个文件？",
        "options": [{"value": "a.txt", "label": "a.txt"}, {"value": "b.txt", "label": "b.txt"}],
    })]])
    monkeypatch.setattr("core.orchestrator.intent.get_llm_client", lambda: fake)
    r = await judge_intent("把那个文件删了")
    assert r.ambiguous is True
    assert r.question == "要删除哪个文件？"
    assert [o["value"] for o in r.options] == ["a.txt", "b.txt"]


@pytest.mark.asyncio
async def test_judge_ambiguous_without_question_downgrades(monkeypatch):
    """标了 ambiguous 却没给问题 → 不算反问（否则会卡在一个空问题前）。
    ambiguous without a question is downgraded — otherwise the turn would park on an
    empty question."""
    fake = _FakeLLM([[_done_with_args({"summary": "做事", "ambiguous": True})]])
    monkeypatch.setattr("core.orchestrator.intent.get_llm_client", lambda: fake)
    r = await judge_intent("做事")
    assert r.ambiguous is False


@pytest.mark.asyncio
async def test_judge_invalid_complexity_falls_back_to_simple(monkeypatch):
    """非法复杂度回退 simple（别把普通请求误送进多智能体）。
    An invalid complexity falls back to simple (never push an ordinary request into the
    multi-agent path)."""
    fake = _FakeLLM([[_done_with_args({"summary": "你好", "complexity": "huge"})]])
    monkeypatch.setattr("core.orchestrator.intent.get_llm_client", lambda: fake)
    r = await judge_intent("你好")
    assert r.complexity == "simple"


@pytest.mark.asyncio
async def test_judge_fallback_when_llm_fails(monkeypatch):
    """LLM 故障时兜底：用原文摘要、simple、不反问（照常执行）。
    On LLM failure: summarise the raw text, simple, no question (just proceed)."""
    class _Boom:
        def retry_stream_chat(self, messages, tools=None, **kwargs):
            raise RuntimeError("llm down")
    monkeypatch.setattr("core.orchestrator.intent.get_llm_client", lambda: _Boom())
    r = await judge_intent("打开记事本")
    assert r.summary == "打开记事本"
    assert r.complexity == "simple"
    assert r.ambiguous is False


@pytest.mark.asyncio
async def test_judge_no_tool_call_falls_back(monkeypatch):
    """模型没走工具调用 → 同样兜底而非报错。No tool call also falls back."""
    fake = _FakeLLM([[{"type": "done", "message": {"role": "assistant", "content": "嗯"}}]])
    monkeypatch.setattr("core.orchestrator.intent.get_llm_client", lambda: fake)
    r = await judge_intent("嗯")
    assert r.summary == "嗯"
    assert r.ambiguous is False
