# -*- coding: utf-8 -*-
"""执行器（execute_task）各路径的测试。
Tests for the executor (execute_task) covering its main paths.
"""
import json

import pytest

from core.orchestrator.control import CancellationToken
from core.orchestrator.executor import execute_task
from core.orchestrator.session import Answer, Session
from core.orchestrator.task import Task


def _done(content=None, tool=None, args="{}"):
    msg = {"role": "assistant", "content": content or ""}
    if tool:
        msg["tool_calls"] = [{"id": "c", "type": "function", "function": {"name": tool, "arguments": args}}]
    return {"type": "done", "message": msg}


class _FakeLLM:
    """模拟 LLM 客户端，按脚本逐轮回放事件。Simulates an LLM client that replays scripted events turn by turn."""

    def __init__(self, script):
        self.script = script

    def retry_stream_chat(self, messages, tools=None):
        async def gen():
            for evt in self.script.pop(0):
                yield evt
        return gen()


class _Channel:
    """模拟会话通道，返回预设答案。Simulates a session channel returning preset answers."""

    def __init__(self, answers):
        self.answers = list(answers)

    async def ask(self, q, *, kind="text", options=None):
        a = self.answers.pop(0)
        return a if isinstance(a, Answer) else Answer(text=a)

    async def notify(self, text):
        pass


@pytest.mark.asyncio
async def test_execute_converges(monkeypatch):
    """工具调用后收敛到 done。Converges to done after a tool call."""
    fake = _FakeLLM([
        [_done(tool="calculate", args=json.dumps({"expression": "1+1"}))],
        [_done(content="结果是 2")],
    ])
    monkeypatch.setattr("core.orchestrator.executor.get_llm_client", lambda: fake)
    s = Session()
    s.channel = _Channel([])
    r = await execute_task(Task("t", "算 1+1", risk="read"), s, CancellationToken())
    assert r["status"] == "done"
    assert "2" in r["summary"]
    assert any(st["tool"] == "calculate" and st["status"] == "ok" for st in r["steps"])


@pytest.mark.asyncio
async def test_execute_step_limit(monkeypatch):
    """达到步数上限后失败。Fails after hitting the step limit."""
    class _Fake:
        def retry_stream_chat(self, messages, tools=None):
            async def gen():
                yield _done(tool="calculate", args=json.dumps({"expression": "1"}))
            return gen()
    monkeypatch.setattr("core.orchestrator.executor.get_llm_client", lambda: _Fake())
    s = Session()
    s.channel = _Channel([])
    r = await execute_task(Task("t", "无限循环", risk="read"), s, CancellationToken())
    assert r["status"] == "failed"
    assert "上限" in r["summary"]


@pytest.mark.asyncio
async def test_execute_cancelled_before(monkeypatch):
    """执行前已取消则返回 stopped。Returns stopped when cancelled before execution."""
    token = CancellationToken()
    token.cancel()
    s = Session()
    s.channel = _Channel([])
    r = await execute_task(Task("t", "x", risk="read"), s, token)
    assert r["status"] == "stopped"


@pytest.mark.asyncio
async def test_execute_uses_coordinator_for_complex(monkeypatch):
    """复杂任务交给多智能体协调器。Complex tasks are delegated to the multi-agent coordinator."""
    from core import config as config_mod

    async def fake_coordinator(task, session, cancel, events=None):
        return {"status": "done", "summary": "多智能体结果", "subtasks": [
            {"goal": "a", "agent_type": "doer", "status": "done", "output": "ok", "tools": []}]}

    monkeypatch.setattr("core.orchestrator.executor.run_coordinator", fake_coordinator)
    monkeypatch.setattr(config_mod, "get_settings",
                        lambda: config_mod.Settings(agent=config_mod.AgentSection(multi_agent=True)))
    s = Session()
    s.channel = _Channel([])
    r = await execute_task(
        Task("t", "这是一个很长的复杂任务目标需要拆分成多个子任务来处理",
             params={"a": 1, "b": 2}, risk="read"),
        s, CancellationToken(),
    )
    assert r["status"] == "done"
    assert "多智能体结果" in r["summary"]
    assert any(st["tool"] == "agent:doer" for st in r["steps"])


@pytest.mark.asyncio
async def test_execute_injects_context(monkeypatch):
    """上下文注入到首条用户消息。Context is injected into the first user message."""
    async def fake_build_context(query):
        # 主执行路径走 with_sources（docs/designs/05）：返回 (文本, 命中)。
        # The main execution path uses with_sources (docs/designs/05): (text, hits).
        return "【相关文档/环境】\nPython 3.14", []

    monkeypatch.setattr("core.orchestrator.executor.build_context_with_sources", fake_build_context)

    class _Fake:
        def __init__(self):
            self.msgs = None

        def retry_stream_chat(self, messages, tools=None):
            self.msgs = messages

            async def gen():
                yield _done(content="完成")
            return gen()

    fake = _Fake()
    monkeypatch.setattr("core.orchestrator.executor.get_llm_client", lambda: fake)
    s = Session()
    s.channel = _Channel([])
    r = await execute_task(Task("t", "查 python 版本", risk="read"), s, CancellationToken())
    assert r["status"] == "done"
    assert "Python 3.14" in fake.msgs[0]["content"]


@pytest.mark.asyncio
async def test_execute_multi_agent_streams_summary_and_records(monkeypatch):
    """多智能体摘要流式输出并记录到会话。The multi-agent summary streams out and is recorded in the session."""
    import asyncio
    from core import config as config_mod

    async def fake_coordinator(task, session, cancel, events=None):
        return {"status": "done", "summary": "多智能体最终结论：已全部完成", "subtasks": [
            {"goal": "a", "agent_type": "doer", "status": "done", "output": "ok", "tools": []}]}

    monkeypatch.setattr("core.orchestrator.executor.run_coordinator", fake_coordinator)
    monkeypatch.setattr(config_mod, "get_settings",
                        lambda: config_mod.Settings(agent=config_mod.AgentSection(multi_agent=True)))
    s = Session()
    s.channel = _Channel([])
    events: asyncio.Queue = asyncio.Queue()
    r = await execute_task(
        Task("t", "这是一个很长的复杂任务目标需要拆分成多个子任务来处理",
             params={"a": 1, "b": 2}, risk="read"),
        s, CancellationToken(), events,
    )
    assert r["status"] == "done"
    deltas = "".join(e.get("text", "") for e in _drain(events) if e["type"] == "content_delta")
    assert deltas == "多智能体最终结论：已全部完成"
    assert any(m.get("role") == "assistant" and "多智能体最终结论" in m.get("content", "") for m in s.messages)


@pytest.mark.asyncio
async def test_execute_records_assistant_reply(monkeypatch):
    """助手回复记录进会话历史。The assistant reply is recorded in the session history."""
    fake = _FakeLLM([
        [_done(content="结果是 2")],
    ])
    monkeypatch.setattr("core.orchestrator.executor.get_llm_client", lambda: fake)
    s = Session()
    s.channel = _Channel([])
    r = await execute_task(Task("t", "算 1+1", risk="read"), s, CancellationToken())
    assert r["status"] == "done"
    assert any(m.get("role") == "assistant" and "结果是 2" in m.get("content", "") for m in s.messages)


def _drain(q):
    out = []
    while not q.empty():
        out.append(q.get_nowait())
    return out


@pytest.mark.asyncio
async def test_execute_read_tools_run_concurrently(monkeypatch):
    """read 级工具并发执行且按序回喂。Read-level tools run concurrently and feed back in order."""
    msg = {
        "role": "assistant", "content": "",
        "tool_calls": [
            {"id": "c1", "type": "function", "function": {"name": "calculate", "arguments": json.dumps({"expression": "1+1"})}},
            {"id": "c2", "type": "function", "function": {"name": "get_datetime", "arguments": "{}"}},
        ],
    }
    fake = _FakeLLM([
        [{"type": "done", "message": msg}],
        [_done(content="完成")],
    ])
    monkeypatch.setattr("core.orchestrator.executor.get_llm_client", lambda: fake)
    s = Session()
    s.channel = _Channel([])
    r = await execute_task(Task("t", "多工具", risk="read"), s, CancellationToken())
    assert r["status"] == "done"
    # read 级工具并发执行，结果按原顺序回喂
    tools = [st["tool"] for st in r["steps"]]
    assert tools == ["calculate", "get_datetime"]
    assert all(st["status"] == "ok" for st in r["steps"])


@pytest.mark.asyncio
async def test_execute_high_risk_confirm_rejected(monkeypatch, asking_policy):
    """高风险工具经操作者取消后记为错误。A high-risk tool cancelled by the operator is recorded as an error."""
    fake = _FakeLLM([
        [_done(tool="write_file", args=json.dumps({"path": "C:/x.txt", "content": "hi"}))],
        [_done(content="已跳过")],
    ])
    monkeypatch.setattr("core.orchestrator.executor.get_llm_client", lambda: fake)
    s = Session()
    s.channel = _Channel(["取消"])
    r = await execute_task(Task("t", "写文件", risk="write"), s, CancellationToken())
    assert r["status"] == "done"
    assert r["steps"][0]["status"] == "error"


@pytest.mark.asyncio
async def test_execute_high_risk_tool_confirm_ignores_task_risk_read(monkeypatch, asking_policy):
    """任务误标 read 时仍按工具实际风险确认。Tool risk still gates confirmation even when the task is mislabeled as read."""
    # 堵洞：任务被 LLM 误标为 read，但调用了 write_file → 仍必须经操作者确认（答「取消」被拒）
    fake = _FakeLLM([
        [_done(tool="write_file", args=json.dumps({"path": "C:/x.txt", "content": "hi"}))],
        [_done(content="已跳过")],
    ])
    monkeypatch.setattr("core.orchestrator.executor.get_llm_client", lambda: fake)
    s = Session()
    s.channel = _Channel(["取消"])
    r = await execute_task(Task("t", "写文件", risk="read"), s, CancellationToken())
    assert r["status"] == "done"
    assert r["steps"][0]["status"] == "error"


@pytest.mark.asyncio
async def test_execute_emits_streaming_events(monkeypatch):
    """执行过程发出流式事件。Execution emits streaming events."""
    import asyncio
    fake = _FakeLLM([
        [_done(tool="calculate", args=json.dumps({"expression": "1+1"})),
         {"type": "usage", "usage": {"total_tokens": 5}}],
        [{"type": "content_delta", "text": "结果是 "},
         {"type": "content_delta", "text": "2"},
         _done(content="结果是 2")],
    ])
    monkeypatch.setattr("core.orchestrator.executor.get_llm_client", lambda: fake)
    s = Session()
    s.channel = _Channel([])
    events: asyncio.Queue = asyncio.Queue()
    r = await execute_task(Task("t", "算 1+1", risk="read"), s, CancellationToken(), events)
    assert r["status"] == "done"
    evts = []
    while not events.empty():
        evts.append(events.get_nowait())
    types = [e["type"] for e in evts]
    assert "tool_start" in types and "tool_end" in types
    assert "usage" in types
    content = "".join(e.get("text", "") for e in evts if e["type"] == "content_delta")
    assert "结果是 2" in content


@pytest.mark.asyncio
async def test_execute_forwards_reasoning_delta(monkeypatch):
    """reasoning_delta 不再被丢弃 —— 思考流断链修复的回归。
    reasoning_delta is no longer dropped — regression for the broken thinking stream."""
    import asyncio
    fake = _FakeLLM([
        [{"type": "reasoning_delta", "text": "先想想"},
         {"type": "reasoning_delta", "text": "再算算"},
         _done(content="结果是 2")],
    ])
    monkeypatch.setattr("core.orchestrator.executor.get_llm_client", lambda: fake)
    s = Session()
    s.channel = _Channel([])
    events: asyncio.Queue = asyncio.Queue()
    r = await execute_task(Task("t", "算 1+1", risk="read"), s, CancellationToken(), events)
    assert r["status"] == "done"
    reasoning = []
    while not events.empty():
        e = events.get_nowait()
        if e["type"] == "reasoning_delta":
            reasoning.append(e["text"])
    assert "".join(reasoning) == "先想想再算算"


@pytest.mark.asyncio
async def test_execute_tool_events_carry_call_id_and_truncation(monkeypatch):
    """工具事件带 call_id 配对与显式截断标注（truncated / output_len）。
    Tool events carry call_id pairing and explicit truncation marks."""
    import asyncio
    big_output = "x" * 600
    fake = _FakeLLM([
        [_done(tool="calculate", args=json.dumps({"expression": "1+1"}))],
        [_done(content="好")],
    ])
    monkeypatch.setattr("core.orchestrator.executor.get_llm_client", lambda: fake)

    import core.tools as tools_pkg
    async def fake_acall(name, args, cancel=None, session=None):
        return big_output
    monkeypatch.setattr(tools_pkg.TOOLS, "acall", fake_acall)
    s = Session()
    s.channel = _Channel([])
    events: asyncio.Queue = asyncio.Queue()
    r = await execute_task(Task("t", "跑命令", risk="read"), s, CancellationToken(), events)
    assert r["status"] == "done"
    evts = []
    while not events.empty():
        evts.append(events.get_nowait())
    start = next(e for e in evts if e["type"] == "tool_start")
    end = next(e for e in evts if e["type"] == "tool_end")
    assert start["call_id"] == end["call_id"] == "c"  # _done 的 tool id
    assert end["truncated"] is True
    assert end["output_len"] == 600
    assert len(end["output"]) == 500


@pytest.mark.asyncio
async def test_auto_allowed_tools_run_concurrently(monkeypatch):
    """被策略 allow 的工具（含 write 级）并发执行，不再逐个确认。

    用在飞计数判定并发，而非墙钟耗时 —— 耗时阈值在负载下会 flaky。
    Policy-allowed tools (including write-level ones) run concurrently without prompting.
    Concurrency is detected via an in-flight counter rather than wall-clock time, since a
    timing threshold is flaky under load.
    """
    import asyncio

    import core.orchestrator.confirm as confirm_mod
    import core.orchestrator.executor as ex
    from core.tools.policy import Decision

    # 必须同时 patch 两处：executor 用 decide 做并发分流，confirm_tool 用 decide
    # 决定要不要问。只 patch 一处会让 write 级工具仍走真实策略（tier=ask）而触发询问。
    # Both must be patched: executor uses decide for the concurrency split, while
    # confirm_tool uses it to decide whether to ask. Patching only one leaves a
    # write-level tool on the real policy (tier=ask) and it prompts.
    _allow = lambda name, section=None: Decision("allow", "rule:test")  # noqa: E731
    monkeypatch.setattr(ex, "decide", _allow)
    monkeypatch.setattr(confirm_mod, "decide", _allow)

    started: list[str] = []
    inflight = 0
    max_inflight = 0

    async def fake_acall(name, args, cancel=None, session=None):
        nonlocal inflight, max_inflight
        started.append(name)
        inflight += 1
        max_inflight = max(max_inflight, inflight)
        await asyncio.sleep(0.05)
        inflight -= 1
        return "ok"

    monkeypatch.setattr(ex.TOOLS, "acall", fake_acall)

    msg = {
        "role": "assistant", "content": "",
        "tool_calls": [
            {"id": "c1", "type": "function",
             "function": {"name": "write_file", "arguments": json.dumps({"path": "a", "content": "1"})}},
            {"id": "c2", "type": "function",
             "function": {"name": "write_file", "arguments": json.dumps({"path": "b", "content": "2"})}},
        ],
    }
    fake = _FakeLLM([[{"type": "done", "message": msg}], [_done(content="完成")]])
    monkeypatch.setattr("core.orchestrator.executor.get_llm_client", lambda: fake)

    s = Session()
    s.channel = _Channel([])  # 一旦询问就会 IndexError
    r = await execute_task(Task("t", "写两个文件", risk="write"), s, CancellationToken())
    assert r["status"] == "done"
    assert len(started) == 2
    assert max_inflight == 2, "两个工具应同时在飞（并发），而非串行"


@pytest.mark.asyncio
async def test_sources_block_and_cite_note_emitted(monkeypatch):
    """RAG 命中 → sources 块直通事件流，system 提示带 [n] 引用标注尾注
    （docs/designs/05 §3.1/§3.2）。"""
    import asyncio

    # 记录 system 提示（断言引用尾注真的进了首条 history）。
    # Records the system prompt (asserts the citation note actually reaches history).

    class _Rec:
        def __init__(self, script):
            self.script = script
            self.hist: list[list[dict]] = []

        def retry_stream_chat(self, history, tools=None):
            self.hist.append(history)

            async def gen():
                for evt in self.script.pop(0):
                    yield evt
            return gen()

    fake = _Rec([[_done(content="完成")]])
    monkeypatch.setattr("core.orchestrator.executor.get_llm_client", lambda: fake)

    hits = [{"path": "env.md", "section": "系统", "text": "Python 3.14", "score": 2.5}]

    async def fake_ctx(q):
        return "【相关文档/环境】\n[1] 系统 (env.md)\nPython 3.14", hits

    import core.orchestrator.executor as ex
    monkeypatch.setattr(ex, "build_context_with_sources", fake_ctx)

    events: asyncio.Queue = asyncio.Queue()
    s = Session()
    s.channel = _Channel([])
    r = await execute_task(Task("t", "查环境", risk="read"), s, CancellationToken(), events)
    assert r["status"] == "done"

    evts = []
    while not events.empty():
        evts.append(events.get_nowait())
    src = next(e for e in evts if e.get("type") == "block" and e["block"].get("type") == "sources")
    assert src["block"]["payload"]["items"][0]["n"] == 1
    assert src["block"]["payload"]["items"][0]["path"] == "env.md"
    assert src["block"]["meta"].get("tts") == "skip"

    sys_prompt = fake.hist[0][0]["content"]
    assert "[n]" in sys_prompt and "标注" in sys_prompt, "引用尾注必须进 system 提示"


@pytest.mark.asyncio
async def test_tool_output_llm_feed_capped(monkeypatch):
    """LLM 口径截断（docs/designs/08 批1）：喂给模型的 tool 正文按
    tools.llm_max_output_chars 截断并附指引；steps/块仍用原文（四口径独立）。
    LLM-side cap (docs/designs/08 batch 1): the tool body fed to the model is capped
    with a hint; steps/blocks keep the raw text (four independent conventions)."""
    from core import config as config_mod
    monkeypatch.setattr(config_mod.settings.tools, "llm_max_output_chars", 50)

    class _Rec:
        def __init__(self, script):
            self.script = script
            self.hist: list[list[dict]] = []

        def retry_stream_chat(self, history, tools=None):
            self.hist.append(history)

            async def gen():
                for evt in self.script.pop(0):
                    yield evt
            return gen()

    fake = _Rec([
        [_done(tool="get_datetime", args="{}")],
        [_done(content="完成")],
    ])
    monkeypatch.setattr("core.orchestrator.executor.get_llm_client", lambda: fake)

    import core.orchestrator.executor as ex

    async def fake_acall(name, args, cancel=None, session=None):
        return "长" * 5000

    monkeypatch.setattr(ex.TOOLS, "acall", fake_acall)

    s = Session()
    s.channel = _Channel([])
    r = await execute_task(Task("t", "查时间", risk="read"), s, CancellationToken())
    assert r["status"] == "done"

    # LLM 口径：第二次调用的 history 里 tool 正文 = 50 字 + 截断指引。
    # LLM-side convention: the tool body in the second call's history = 50 chars + hint.
    tool_msg = next(m for m in fake.hist[1] if m.get("role") == "tool")
    assert len(tool_msg["content"]) < 200
    assert tool_msg["content"].startswith("长" * 50)
    assert "输出已截断" in tool_msg["content"] and "共 5000 字" in tool_msg["content"]

    # 展示/落库口径用原文（full_len = 原始长度）。Display/persistence keep the raw text.
    tool_blocks = [b for m in s.messages for b in m.get("blocks", []) if b.get("type") == "tool"]
    assert tool_blocks, "工具必须以 tool 块入会话"
    p = tool_blocks[-1]["payload"]
    assert p["full_len"] == 5000
    assert len(p["output"]) == 4000   # HISTORY_LEN 口径。HISTORY_LEN convention.


@pytest.mark.asyncio
async def test_tool_rejection_feeds_reason_to_llm(monkeypatch, asking_policy):
    """操作者拒绝并附理由 → 回喂 LLM 的 tool 消息携带理由与纠偏指引。

    没有理由回传时，模型只看到一句干巴巴的「被拒绝」，大概率把同一调用原样重试；
    理由 + 指引让它能换方案（OpenAI Agents SDK 的 rejection-reason 模式）。
    """
    fake = _FakeLLM([
        [_done(tool="write_file", args=json.dumps({"path": "a.txt", "content": "x"}))],
        [_done(content="完成")],
    ])
    monkeypatch.setattr("core.orchestrator.executor.get_llm_client", lambda: fake)
    s = Session()
    s.channel = _Channel([Answer(choice="no", text="这个文件不能动")])
    r = await execute_task(Task("t", "写文件", risk="write"), s, CancellationToken())
    assert r["status"] == "done"
    result = r["steps"][0]["result"]
    assert result.startswith("Error: 操作者拒绝调用 write_file")
    assert "这个文件不能动" in result, "拒绝理由必须回喂给 LLM"
    assert "请调整方案" in result, "应包含纠偏指引，防止原样重试"
