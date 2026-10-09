# -*- coding: utf-8 -*-
"""extract_and_store / _spawn_bg 的失败留痕（此前静默吞异常，排障无从下手）。

Failure traces for extract_and_store / _spawn_bg (exceptions used to be swallowed
silently, leaving nothing to debug from).
"""
import json

import pytest

import core.memory.extract as extract_mod
import core.orchestrator.pipeline as pl
from core.memory.extract import extract_and_store
from core.memory.facts import FactStore
from core.orchestrator.task import Task


class _StubLogger:
    """记录 loguru 调用的桩（只录 debug/warning，够断言用）。Records loguru calls."""

    def __init__(self):
        self.records: list[tuple[str, object]] = []

    def debug(self, msg, *args):
        self.records.append(("debug", msg))

    def warning(self, msg, *args):
        self.records.append(("warning", msg))

    def messages(self, level: str) -> list[str]:
        return [m for lv, m in self.records if lv == level]


def _done_with_facts(facts):
    return {
        "type": "done",
        "message": {
            "role": "assistant", "content": "",
            "tool_calls": [{
                "id": "e", "type": "function",
                "function": {"name": "extract_facts", "arguments": json.dumps({"facts": facts})},
            }],
        },
    }


class _FakeLLM:
    """按脚本回放事件流的假 LLM。Replays event streams in script order."""

    def __init__(self, script):
        self.script = script

    def retry_stream_chat(self, messages, tools=None, **kwargs):
        async def gen():
            for evt in self.script.pop(0):
                yield evt
        return gen()


@pytest.mark.asyncio
async def test_skip_leaves_debug_trace(tmp_path, monkeypatch):
    """状态非 done/failed 的跳过留 debug 痕（可区分「没触发」与「触发后失败」）。"""
    stub = _StubLogger()
    monkeypatch.setattr(extract_mod, "logger", stub)
    store = FactStore(tmp_path / "f.sqlite")
    await extract_and_store(
        Task("t", "x", risk="read"),
        {"status": "stopped", "summary": "", "steps": []},
        store,
    )
    assert any("跳过" in m for m in stub.messages("debug"))


@pytest.mark.asyncio
async def test_stream_without_done_leaves_warning(tmp_path, monkeypatch):
    """流正常结束但无 done 事件 → warning（此前零日志走完，看似提取成功）。"""
    stub = _StubLogger()
    monkeypatch.setattr(extract_mod, "logger", stub)
    monkeypatch.setattr(extract_mod, "get_llm_client",
                        lambda: _FakeLLM([[{"type": "content_delta", "text": "半截"}]]))
    store = FactStore(tmp_path / "f.sqlite")
    await extract_and_store(
        Task("t", "x", risk="read"),
        {"status": "done", "summary": "s", "steps": []},
        store,
    )
    assert any("无 done 事件" in m for m in stub.messages("warning"))


@pytest.mark.asyncio
async def test_config_read_failure_warns_and_keeps_default(tmp_path, monkeypatch):
    """读配置抛异常 → warning + 回退默认值，提取流程不中断。

    ⚠️ 只替换 extract 模块内的 `config` 绑定：直接 setattr `core.config.settings`
    会把模块的动态 __getattr__ 固化成静态属性（monkeypatch 恢复后 get_settings
    不再生效），污染其后所有依赖 patch get_settings 的测试。
    """
    stub = _StubLogger()
    monkeypatch.setattr(extract_mod, "logger", stub)

    class _BoomMemory:
        @property
        def extract_recent_messages(self):
            raise RuntimeError("boom")

    class _ConfigProxy:
        """memory 读取恒抛；其余（含 agent）透传真实 core.config。"""
        def __init__(self, real):
            self._real = real

        @property
        def settings(self):
            real_settings = self._real.settings

            class _S:
                memory = _BoomMemory()
                agent = real_settings.agent

            return _S()

    monkeypatch.setattr(extract_mod, "config", _ConfigProxy(extract_mod.config))
    monkeypatch.setattr(extract_mod, "get_llm_client", lambda: _FakeLLM([[]]))
    store = FactStore(tmp_path / "f.sqlite")
    await extract_and_store(
        Task("t", "x", risk="read"),
        {"status": "done", "summary": "s", "steps": []},
        store,
        session=type("S", (), {"messages": [], "id": "c1"})(),
    )
    assert any("extract_recent_messages" in m for m in stub.messages("warning"))


@pytest.mark.asyncio
async def test_one_bad_row_does_not_swallow_batch(tmp_path, monkeypatch):
    """单条 upsert 失败 → 留 warning，其余事实照常入库。"""
    stub = _StubLogger()
    monkeypatch.setattr(extract_mod, "logger", stub)
    fake = _FakeLLM([[_done_with_facts([
        {"topic": "坏的", "content": "x"},
        {"topic": "好的", "content": "y"},
    ])]])
    monkeypatch.setattr(extract_mod, "get_llm_client", lambda: fake)
    store = FactStore(tmp_path / "f.sqlite")

    orig_upsert = store.upsert

    async def flaky_upsert(topic, content, **kwargs):
        if topic == "坏的":
            raise RuntimeError("坏条目")
        return await orig_upsert(topic, content, **kwargs)

    monkeypatch.setattr(store, "upsert", flaky_upsert)
    await extract_and_store(
        Task("t", "x", risk="read"),
        {"status": "done", "summary": "s", "steps": []},
        store,
    )
    assert any("单条 upsert 失败" in m for m in stub.messages("warning"))
    rows = await store.get("好的")
    assert rows and rows[0]["content"] == "y", "第一条失败不得中断后续 upsert"


@pytest.mark.asyncio
async def test_bg_done_observes_escaped_exception(monkeypatch):
    """_on_bg_done 观察逃逸异常并记 warning（此前无人观察，只进 loop 默认 handler）。"""
    stub = _StubLogger()
    monkeypatch.setattr(pl, "logger", stub)

    async def boom():
        raise RuntimeError("escaped")

    t = pl._spawn_bg(boom())
    with pytest.raises(RuntimeError):
        await t
    pl._on_bg_done(t)
    assert any("后台任务未捕获异常" in m for m in stub.messages("warning"))
