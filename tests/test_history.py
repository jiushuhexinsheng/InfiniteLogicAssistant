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
    """测试保存会话后可完整读取消息与状态；tool_calls 已随块协议退役（写入被忽略、
    读回不再出现）。Tests that a saved conversation reads back with messages and status;
    tool_calls retired with the block protocol (writes ignored, absent on read)."""
    await store.save_conversation("c1", [
        {"role": "user", "content": "你好"},
        {"role": "assistant", "content": "你好呀", "tool_calls": [{"name": "get_datetime"}]},
    ], status="done", summary="任务完成")
    conv = await store.get_conversation("c1")
    assert conv["id"] == "c1"
    assert len(conv["messages"]) == 2
    assert conv["messages"][1]["content"] == "你好呀"
    assert "tool_calls" not in conv["messages"][1]
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
async def test_save_conversation_keeps_other_turns(store):
    """历史覆盖竞态（docs/designs/10 5.3）：旧回合晚收尾时只替换自己那一回合，
    新回合已写入的消息必须保留，且顺序仍按真实时间。

    History overwrite race (docs/designs/10 5.3): when an older turn retires late it
    replaces only its own turn; messages already written by the newer turn survive,
    in real-time order.
    """
    def msg(role, content, turn_id, ts):
        return {"role": role, "content": content, "turn_id": turn_id, "ts": ts}

    # 新回合先落盘：turn1 + turn2。
    await store.save_conversation("c1", [
        msg("user", "问题一", "t1", "2026-11-08T10:00:00"),
        msg("assistant", "回答一", "t1", "2026-11-08T10:00:05"),
        msg("user", "问题二", "t2", "2026-11-08T10:01:00"),
        msg("assistant", "回答二", "t2", "2026-11-08T10:01:05"),
    ], status="done", summary="")

    # 旧回合（只有 turn1）迟到收尾：不得删掉 turn2。
    await store.save_conversation("c1", [
        msg("user", "问题一", "t1", "2026-11-08T10:00:00"),
        msg("assistant", "回答一", "t1", "2026-11-08T10:00:05"),
    ], status="done", summary="")

    conv = await store.get_conversation("c1")
    assert [m["content"] for m in conv["messages"]] == ["问题一", "回答一", "问题二", "回答二"]


@pytest.mark.asyncio
async def test_seed_without_ts_stays_before_this_turn(store):
    """前端历史种子没有 ts：必须排在本轮带时间戳的消息之前，不能盖成保存时刻。
    Frontend seeds carry no ts: they must sort before this turn's timestamped messages,
    never be stamped with the save time (which would put them after the reply).
    """
    await store.save_conversation("c1", [
        {"role": "user", "content": "旧问题"},
        {"role": "assistant", "content": "旧回答"},
        {"role": "user", "content": "本轮问题", "ts": "2026-11-08T10:00:00", "turn_id": "t1"},
        {"role": "assistant", "content": "本轮回答", "ts": "2026-11-08T10:00:05", "turn_id": "t1"},
    ], status="done", summary="")

    conv = await store.get_conversation("c1")
    assert [m["content"] for m in conv["messages"]] == ["旧问题", "旧回答", "本轮问题", "本轮回答"]


@pytest.mark.asyncio
async def test_runtime_turns_survive_old_turn_resave(store):
    """真实 Session 的回合打标 + 旧回合迟到重存：新回合消息必须保留。
    Real Session turn tagging + a late old-turn re-save: the newer turn must survive.
    """
    from core.orchestrator.session import Session

    s = Session(session_id="c1")
    s.begin_turn()
    s.append("user", "第一问")
    s.append("assistant", "第一答")
    turn1 = s.turn_id
    s.begin_turn()
    s.append("user", "第二问")
    s.append("assistant", "第二答")
    assert all(m["turn_id"] for m in s.messages), "运行时的消息必须带 turn_id"

    # 新回合先落盘（含全部消息）。
    await store.save_conversation("c1", s.messages)
    # 旧回合迟到收尾：只带第一轮 —— 不得删掉第二轮。
    await store.save_conversation("c1", [m for m in s.messages if m["turn_id"] == turn1])

    conv = await store.get_conversation("c1")
    assert [m["content"] for m in conv["messages"]] == ["第一问", "第一答", "第二问", "第二答"]


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


@pytest.mark.asyncio
async def test_migration_drops_legacy_rows_and_tolerates_tool_calls_column(tmp_path):
    """迁移时清除无 blocks 的旧平铺消息行（用户决定不做新旧共存），会话记录保留；
    老库遗留的 tool_calls 列必须被容忍 —— 迁移后写入/读回照常（显式列名绕开遗留列）。

    Migration deletes legacy flat message rows without blocks (the user opted out of
    new/old coexistence); conversation records remain. A legacy tool_calls column
    must be tolerated — writes and reads work after migration (explicit column
    names sidestep the leftover column).
    """
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

    # 遗留列仍在（SQLite 不删列），但读写不受影响。
    with sqlite3.connect(str(path)) as conn:
        cols = [r[1] for r in conn.execute("PRAGMA table_info(messages)").fetchall()]
    assert "tool_calls" in cols

    await store.save_conversation("c1", [{"role": "user", "content": "新消息"}],
                                  status="done", summary="s")
    conv = await store.get_conversation("c1")
    assert conv["messages"][0]["content"] == "新消息"
    assert "tool_calls" not in conv["messages"][0]
