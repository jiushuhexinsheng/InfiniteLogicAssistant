# -*- coding: utf-8 -*-
"""SSE 事件契约（QuestionEvent 泛化）的测试。
Tests for the SSE event contract (the generalized QuestionEvent).
"""
import pytest
from pydantic import ValidationError

from core.orchestrator.events import QuestionEvent, QuestionOption


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
