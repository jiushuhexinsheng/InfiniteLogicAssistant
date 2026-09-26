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


# ─── 块协议：blocks/turn_id/ts_iso 读写 + 旧历史清除 ───
# Block protocol: blocks/turn_id/ts_iso round-trip + old-history drop.


@pytest.mark.asyncio
async def test_save_and_get_blocks_round_trip(store):
    """块结构完整往返：blocks / turn_id / ts 原样读回。
    Blocks round-trip intact: blocks / turn_id / ts read back unchanged."""
    blk = {"v": 1, "id": "blk_1", "type": "tool", "ts": "2026-09-26T10:00:00",
           "turn_id": "turn_1", "agent": "main", "meta": {"tts": "skip"},
           "payload": {"name": "run_shell_tool", "output": "ok"}}
    await store.save_conversation("c1", [
        {"role": "user", "content": "跑个命令", "blocks": [{"type": "text", "payload": {"md": "跑个命令"}}],
         "turn_id": "turn_1", "ts": "2026-09-26T09:59:00"},
        {"role": "assistant", "content": "run_shell_tool: ok", "blocks": [blk],
         "turn_id": "turn_1", "ts": "2026-09-26T10:00:00"},
    ], status="done", summary="s")
    conv = await store.get_conversation("c1")
    m0, m1 = conv["messages"]
    assert m0["blocks"][0]["type"] == "text"
    assert m0["turn_id"] == "turn_1"
    assert m0["ts"] == "2026-09-26T09:59:00"
    assert m1["blocks"] == [blk]
    assert m1["ts"] == "2026-09-26T10:00:00"


@pytest.mark.asyncio
async def test_messages_without_blocks_read_as_empty_list(store):
    """无 blocks 的消息读回为空数组（blocks 恒为数组，不再有 None）。
    Messages without blocks read back as an empty list (blocks is always a list)."""
    await store.save_conversation("c1", [{"role": "user", "content": "hi"}], status="done", summary="s")
    conv = await store.get_conversation("c1")
    assert conv["messages"][0]["blocks"] == []


def test_migration_drops_legacy_rows_without_blocks(tmp_path):
    """迁移时清除无 blocks 的旧平铺消息行（用户决定不做新旧共存），会话记录保留。
    Migration deletes legacy flat message rows without blocks (the user opted out
    of new/old coexistence); conversation records remain."""
    import sqlite3

    path = tmp_path / "legacy.db"
    # 造一个旧库：只有原 6 列，插一条旧消息
    with sqlite3.connect(str(path)) as conn:
        conn.execute(
            "CREATE TABLE messages (id INTEGER PRIMARY KEY AUTOINCREMENT, conversation_id TEXT, "
            "role TEXT, content TEXT, tool_calls TEXT, ts TEXT)"
        )
        conn.execute("INSERT INTO messages (conversation_id, role, content) VALUES ('c1', 'user', '旧消息')")
    store = HistoryStore(path)  # 构造即迁移
    with sqlite3.connect(str(path)) as conn:
        rows = conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
    assert rows == 0  # 旧消息行已清除
