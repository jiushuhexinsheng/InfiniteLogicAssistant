# -*- coding: utf-8 -*-
"""滚动压缩（docs/designs/08 批2）的测试 — maybe_condense 的触发、结构安全与 fail-open。
Tests for the rolling condenser (docs/designs/08 batch 2) — trigger, structural
safety and fail-open of maybe_condense.
"""
import copy

import pytest

from core.orchestrator.condense import KEEP_HEAD, KEEP_TAIL, maybe_condense


class _FakeLLM:
    """按脚本回放的假 LLM（content_delta + done）。Scripted fake LLM (content_delta + done)."""

    def __init__(self, text="摘要内容", exc=None):
        self.text = text
        self.exc = exc
        self.calls: list[list[dict]] = []

    def retry_stream_chat(self, messages, **kwargs):
        self.calls.append(messages)

        async def gen():
            if self.exc:
                raise self.exc
            yield {"type": "content_delta", "content_type": None, "text": self.text}
            yield {"type": "done", "message": {"content": self.text}}
        return gen()


def _hist(n_mid: int = 8, orphan_tail: bool = False) -> list[dict]:
    """构造 system + 任务 + 中间段 + 尾段（可选：尾段以孤儿 tool 结果开头）。

    Build system + task + middle + tail (optionally with an orphan tool result at the
    tail's start).
    """
    h: list[dict] = [
        {"role": "system", "content": "SYS" * 200},
        {"role": "user", "content": "任务：做一件 long 的事"},
    ]
    for i in range(n_mid):
        h.append({"role": "assistant", "content": f"中间思考{i} " + "甲" * 100})
        h.append({"role": "tool", "tool_call_id": f"c{i}", "content": f"工具结果{i} " + "乙" * 100})
    tail = [
        {"role": "assistant", "content": "尾部结论1"},
        {"role": "user", "content": "追问"},
        {"role": "assistant", "content": "尾部结论2"},
        {"role": "tool", "tool_call_id": "t1", "content": "尾工具1"},
        {"role": "assistant", "content": "尾部结论3"},
        {"role": "assistant", "content": "尾部结论4"},
    ]  # 恰好 KEEP_TAIL 条。Exactly KEEP_TAIL.
    if orphan_tail:
        # 尾段首条 = 孤儿 tool（其请求落在被压段里）。First tail entry = orphan tool.
        orphan = {"role": "tool", "tool_call_id": "orphan", "content": "孤儿工具结果 " + "丙" * 100}
        tail = [orphan] + tail[: KEEP_TAIL - 1]
    return h + tail


@pytest.mark.asyncio
async def test_disabled_returns_unchanged(monkeypatch):
    """阈值 0（禁用）→ 原样返回同一对象，不调 LLM。Threshold 0 (disabled) → the same
    object back, LLM never called."""
    import core.orchestrator.condense as cd
    fake = _FakeLLM()
    monkeypatch.setattr(cd, "get_llm_client", lambda: fake)
    h = _hist(n_mid=8)
    out, omitted = await maybe_condense(h, threshold_chars=0)
    assert out is h and omitted == 0 and fake.calls == []

    # 阈值很高（未超）→ 同样不动。A high threshold (not reached) → also untouched.
    out2, om2 = await maybe_condense(h, threshold_chars=10_000_000)
    assert out2 is h and om2 == 0 and fake.calls == []


@pytest.mark.asyncio
async def test_folds_middle_keeps_head_tail_and_input_intact(monkeypatch):
    """超阈值 → 头尾保留、中间折叠为 [上下文压缩] 摘要；入参不被原地修改。
    Over threshold → head/tail kept, middle folded into a [上下文压缩] summary; the
    input list is not mutated in place."""
    import core.orchestrator.condense as cd
    fake = _FakeLLM(text="已确认 A，待办 B")
    monkeypatch.setattr(cd, "get_llm_client", lambda: fake)
    h = _hist(n_mid=8)
    snapshot = copy.deepcopy(h)

    out, omitted = await maybe_condense(h, threshold_chars=500)
    assert h == snapshot, "入参不得被原地修改。The input must not be mutated."
    assert omitted > 0
    assert out[:KEEP_HEAD] == h[:KEEP_HEAD]                       # 头不动。Head intact.
    assert out[-KEEP_TAIL:] == h[-KEEP_TAIL:]                     # 尾不动。Tail intact.
    folded = out[KEEP_HEAD]
    assert folded["role"] == "assistant"
    assert folded["content"] == "[上下文压缩] 已确认 A，待办 B"
    assert len(out) == KEEP_HEAD + 1 + KEEP_TAIL
    # 中间摘要确实来自转写（喂了工具结果与思考）。The summarizer saw the span.
    assert fake.calls and "工具结果0" in fake.calls[0][1]["content"]


@pytest.mark.asyncio
async def test_orphan_tool_at_tail_start_is_folded_away(monkeypatch):
    """尾段开头的孤儿 tool 结果（请求已被压掉）必须一并丢弃 —— 否则 OpenAI 兼容端点
    因 tool 消息无前置 tool_calls 报 400。
    An orphan tool result at the tail's start (its request was folded) must go too —
    otherwise OpenAI-compatible endpoints 400 on a tool message without tool_calls."""
    import core.orchestrator.condense as cd
    fake = _FakeLLM()
    monkeypatch.setattr(cd, "get_llm_client", lambda: fake)
    h = _hist(n_mid=8, orphan_tail=True)
    assert h[-KEEP_TAIL]["role"] == "tool"                        # 前提：尾段以 tool 开头。Precondition.

    out, omitted = await maybe_condense(h, threshold_chars=500)
    assert omitted > 0
    assert out[KEEP_HEAD]["role"] == "assistant"                  # 折叠产物是纯文本。The product is plain text.
    assert out[KEEP_HEAD + 1]["role"] != "tool"                   # 新尾段不以 tool 开头。New tail never starts with a tool message.
    assert "孤儿" not in str(out), "孤儿 tool 结果必须被丢弃（连同其已折叠的请求）"
    assert len(out[KEEP_HEAD + 1:]) < KEEP_TAIL, "孤儿被划给被压段后尾段应变短"


@pytest.mark.asyncio
async def test_llm_failure_fail_open(monkeypatch):
    """摘要失败 → fail-open：原历史原样返回（压缩坏了最多是没压缩）。
    Summarizer failure → fail-open: input returned unchanged (a broken condenser
    degrades to no condensation, never to lost work)."""
    import core.orchestrator.condense as cd
    fake = _FakeLLM(exc=RuntimeError("LLM down"))
    monkeypatch.setattr(cd, "get_llm_client", lambda: fake)
    h = _hist(n_mid=8)
    out, omitted = await maybe_condense(h, threshold_chars=500)
    assert omitted == 0
    assert out is h
