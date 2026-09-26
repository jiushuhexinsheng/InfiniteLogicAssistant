# -*- coding: utf-8 -*-
"""SSE 事件契约（QuestionEvent 泛化 + 块协议 additive 字段）的测试。
Tests for the SSE event contract (the generalized QuestionEvent + block-protocol
additive fields).
"""
import pytest
from pydantic import ValidationError

from core.orchestrator.events import (
    AnswerEvent, BlockEvent, ContentDeltaEvent, DoneEvent, QuestionEvent,
    QuestionOption, ReasoningDeltaEvent, ToolEndEvent, ToolStartEvent, UsageEvent,
    from_llm_event,
)


def test_question_event_defaults_to_text():
    """缺省 kind 为 text，且不带选项。kind defaults to text with no options."""
    evt = QuestionEvent(question="目标位置？", session_id="s1").emit()
    assert evt == {"type": "question", "question": "目标位置？", "session_id": "s1", "kind": "text", "options": []}


def test_question_event_choice_carries_options():
    """选择类携带选项列表（value 机器可读、label 展示用）。
    A choice question carries its option list (value for machines, label for display)."""
    evt = QuestionEvent(
        question="确认执行吗？",
        session_id="s1",
        kind="choice",
        options=[QuestionOption(value="yes", label="确认"), QuestionOption(value="no", label="取消")],
    ).emit()
    assert evt["kind"] == "choice"
    assert evt["options"] == [{"value": "yes", "label": "确认"}, {"value": "no", "label": "取消"}]


def test_question_event_composite_kind():
    """综合类 kind 为 composite。A composite question uses kind=composite."""
    evt = QuestionEvent(question="选一个并补充说明", kind="composite",
                        options=[QuestionOption(value="a", label="甲")]).emit()
    assert evt["kind"] == "composite"
    assert len(evt["options"]) == 1


def test_question_event_rejects_legacy_kinds():
    """旧的 clarify / confirm 不再是合法 kind（已并入 text / choice）。
    The legacy clarify / confirm kinds are no longer valid (folded into text / choice)."""
    for legacy in ("clarify", "confirm"):
        with pytest.raises(ValidationError):
            QuestionEvent(question="q", kind=legacy)


# ─── 块协议 additive 字段：未设不下发（旧前端零感知）───
# Block-protocol additive fields: unset fields are dropped (legacy frontends see
# an unchanged shape).


def test_new_fields_are_omitted_when_unset():
    """新字段缺省 None 时不出现在事件 dict —— 旧事件形状保持不变。
    New fields default to None and are absent from the event dict — legacy
    shapes stay unchanged."""
    evt = QuestionEvent(question="q", session_id="s1").emit()
    assert "qid" not in evt
    assert "turn_id" not in evt
    start = ToolStartEvent(name="t", args={}).emit()
    assert set(start) == {"type", "name", "args"}
    end = ToolEndEvent(name="t", status="ok", output="o").emit()
    assert set(end) == {"type", "name", "status", "output"}


def test_tool_events_carry_call_id_and_agent():
    """工具事件携带 call_id（配对）与 agent（多智能体归属）。
    Tool events carry call_id (pairing) and agent (multi-agent attribution)."""
    start = ToolStartEvent(name="web_search", args={"q": "x"}, call_id="call_1",
                           agent="sub:searcher", turn_id="turn_1").emit()
    assert start["call_id"] == "call_1"
    assert start["agent"] == "sub:searcher"
    assert start["turn_id"] == "turn_1"
    end = ToolEndEvent(name="web_search", status="ok", output="r", call_id="call_1",
                       truncated=True, output_len=1832).emit()
    assert end["call_id"] == "call_1"
    assert end["truncated"] is True
    assert end["output_len"] == 1832


def test_question_event_carries_qid():
    """question 事件携带 qid（问答配对与陈旧作答拒收）。
    A question event carries qid (pairs answers, rejects stale ones)."""
    evt = QuestionEvent(question="哪个城市？", session_id="s1", qid="q_31bd").emit()
    assert evt["qid"] == "q_31bd"


def test_answer_event_shape():
    """answer 事件：qid/text/choice/source（语音作答可审计）。
    answer event: qid/text/choice/source (voice answers auditable)."""
    evt = AnswerEvent(qid="q_1", text="上海", choice=None, source="voice").emit()
    assert evt == {"type": "answer", "qid": "q_1", "text": "上海", "source": "voice"}
    # choice=None 被 exclude_none 剔除；显式 choice 下发
    evt2 = AnswerEvent(qid="q_1", text="", choice="yes", source="button").emit()
    assert evt2["choice"] == "yes"


def test_block_event_carries_block_dict():
    """block 事件直通块 dict（信封 + payload）。
    block event passes a block dict (envelope + payload) through."""
    blk = {"v": 1, "id": "blk_1", "type": "image", "ts": "t", "payload": {"src": "a.png"}}
    evt = BlockEvent(block=blk).emit()
    assert evt == {"type": "block", "block": blk}


# ─── from_llm_event：LLM 流事件 → 编排事件（统一产出口径）───
# from_llm_event: LLM stream events → orchestration events (single convention).


def test_from_llm_event_wraps_stream_events():
    """content_delta / reasoning_delta / usage 包装为类型化事件。
    content_delta / reasoning_delta / usage wrap into typed events."""
    assert from_llm_event({"type": "content_delta", "text": "hi"}) == \
        ContentDeltaEvent(text="hi").emit()
    assert from_llm_event({"type": "reasoning_delta", "text": "think"}) == \
        ReasoningDeltaEvent(text="think").emit()
    assert from_llm_event({"type": "usage", "usage": {"total_tokens": 3}}) == \
        UsageEvent(usage={"total_tokens": 3}).emit()


def test_from_llm_event_skips_execution_layer_events():
    """tool_call_delta / done 由执行层编排，适配器返回 None。
    tool_call_delta / done are orchestrated by the execution layer — the adapter
    returns None."""
    assert from_llm_event({"type": "tool_call_delta"}) is None
    assert from_llm_event({"type": "done", "message": {}}) is None
    assert from_llm_event({"type": "unknown"}) is None


def test_done_event_unchanged():
    """done 事件形状不变（旧前端零感知）。
    done event shape is unchanged (legacy frontends unaffected)."""
    assert DoneEvent().emit() == {"type": "done"}
