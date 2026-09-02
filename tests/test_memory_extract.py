# -*- coding: utf-8 -*-
"""测试从任务结果中提取事实并存入记忆库的功能。
Tests extracting facts from task results and storing them into the memory store.
"""
import json

import pytest

from core.memory.extract import extract_and_store
from core.memory.facts import FactStore
from core.orchestrator.task import Task


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
    """按脚本顺序回放事件流的假 LLM 客户端。A fake LLM client that replays event streams in script order."""
    def __init__(self, script):
        self.script = script

    def retry_stream_chat(self, messages, tools=None, **kwargs):
        async def gen():
            for evt in self.script.pop(0):
                yield evt
        return gen()


@pytest.mark.asyncio
async def test_extract_and_store(tmp_path, monkeypatch):
    """测试任务完成后提取事实并成功存入记忆库。Tests that facts are extracted and stored after a task completes."""
    fake = _FakeLLM([[_done_with_facts([{"topic": "天气偏好", "content": "喜欢看济南天气"}])]])
    monkeypatch.setattr("core.memory.extract.get_llm_client", lambda: fake)
    store = FactStore(tmp_path / "f.sqlite")
    await extract_and_store(
        Task("t", "查天气", risk="read"),
        {"status": "done", "summary": "济南23度", "steps": []},
        store,
    )
    rows = await store.get("天气偏好")
    assert rows and rows[0]["content"] == "喜欢看济南天气"


@pytest.mark.asyncio
async def test_extract_skips_when_status_not_done(tmp_path, monkeypatch):
    """测试任务状态非 done 时跳过事实提取。Tests that fact extraction is skipped when the task status is not done."""
    store = FactStore(tmp_path / "f.sqlite")
    await extract_and_store(
        Task("t", "x", risk="read"),
        {"status": "stopped", "summary": "", "steps": []},
        store,
    )
    assert await store.all() == []
