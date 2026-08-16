# -*- coding: utf-8 -*-
import pytest

from core.history import HistoryStore


@pytest.fixture
def store(tmp_path):
    return HistoryStore(tmp_path / "history.db")


@pytest.mark.asyncio
async def test_save_and_get_conversation(store):
    await store.save_conversation("c1", [
        {"role": "user", "content": "你好"},
        {"role": "assistant", "content": "你好呀", "tool_calls": [{"name": "get_datetime"}]},
    ], status="done", summary="任务完成")
    conv = await store.get_conversation("c1")
    assert conv["id"] == "c1"
    assert len(conv["messages"]) == 2
    assert conv["messages"][1]["content"] == "你好呀"
    assert conv["messages"][1]["tool_calls"] == [{"name": "get_datetime"}]
    assert conv["status"] == "done"


@pytest.mark.asyncio
async def test_save_overwrites(store):
    await store.save_conversation("c1", [{"role": "user", "content": "v1"}], status="done", summary="s")
    await store.save_conversation("c1", [{"role": "user", "content": "v2"}], status="done", summary="s2")
    conv = await store.get_conversation("c1")
    assert conv["messages"][0]["content"] == "v2"  # 覆盖而非追加
    assert conv["summary"] == "s2"


@pytest.mark.asyncio
async def test_list_conversations_orders_by_updated(store):
    await store.save_conversation("c1", [{"role": "user", "content": "a"}], summary="旧")
    await store.save_conversation("c2", [{"role": "user", "content": "b"}], summary="新")
    lst = await store.list_conversations()
    assert [c["id"] for c in lst] == ["c2", "c1"]  # updated DESC
    assert lst[0]["message_count"] == 1
    assert lst[0]["summary"] == "新"


@pytest.mark.asyncio
async def test_delete(store):
    await store.save_conversation("c1", [{"role": "user", "content": "a"}])
    await store.delete("c1")
    assert await store.get_conversation("c1") is None
    assert await store.list_conversations() == []
