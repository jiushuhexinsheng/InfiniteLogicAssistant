# -*- coding: utf-8 -*-
"""测试会话历史存储的保存、覆盖、列表排序与删除功能。
Tests the conversation history store: saving, overwriting, listing order, and deletion.
"""
import pytest

from core.session.history import HistoryStore


@pytest.fixture
def store(tmp_path):
    return HistoryStore(tmp_path / "history.db")


@pytest.mark.asyncio
async def test_save_and_get_conversation(store):
    """测试保存会话后可完整读取消息、工具调用与状态。Tests that a saved conversation can be fully read back with messages, tool calls, and status."""
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
    """测试重复保存同一会话会覆盖旧内容而非追加。Tests that re-saving the same conversation overwrites old content instead of appending."""
    await store.save_conversation("c1", [{"role": "user", "content": "v1"}], status="done", summary="s")
    await store.save_conversation("c1", [{"role": "user", "content": "v2"}], status="done", summary="s2")
    conv = await store.get_conversation("c1")
    assert conv["messages"][0]["content"] == "v2"  # 覆盖而非追加
    assert conv["summary"] == "s2"


@pytest.mark.asyncio
async def test_list_conversations_orders_by_updated(store):
    """测试会话列表按更新时间倒序排列并携带摘要与消息数。Tests that the conversation list is ordered by updated time descending and carries summary and message count."""
    await store.save_conversation("c1", [{"role": "user", "content": "a"}], summary="旧")
    await store.save_conversation("c2", [{"role": "user", "content": "b"}], summary="新")
    lst = await store.list_conversations()
    assert [c["id"] for c in lst] == ["c2", "c1"]  # updated DESC
    assert lst[0]["message_count"] == 1
    assert lst[0]["summary"] == "新"


@pytest.mark.asyncio
async def test_delete(store):
    """测试删除会话后无法再读取且列表为空。Tests that a deleted conversation can no longer be read and the list becomes empty."""
    await store.save_conversation("c1", [{"role": "user", "content": "a"}])
    await store.delete("c1")
    assert await store.get_conversation("c1") is None
    assert await store.list_conversations() == []
