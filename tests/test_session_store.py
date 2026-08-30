# -*- coding: utf-8 -*-
"""会话存储测试 — HistoryStore 演进：name 字段 + create/rename 会话方法"""
import pytest

from core.session.history import HistoryStore


@pytest.fixture
def store(tmp_path):
    return HistoryStore(tmp_path / "history.db")


@pytest.mark.asyncio
async def test_create_conversation_default_name(store):
    cid = await store.create_conversation()
    assert cid
    conv = await store.get_conversation(cid)
    assert conv["name"] == "新会话"


@pytest.mark.asyncio
async def test_create_conversation_with_name(store):
    cid = await store.create_conversation("工作计划")
    conv = await store.get_conversation(cid)
    assert conv["name"] == "工作计划"


@pytest.mark.asyncio
async def test_rename_conversation(store):
    cid = await store.create_conversation("旧名")
    await store.rename_conversation(cid, "新名")
    conv = await store.get_conversation(cid)
    assert conv["name"] == "新名"


@pytest.mark.asyncio
async def test_list_includes_name(store):
    await store.create_conversation("会话A")
    await store.create_conversation("会话B")
    lst = await store.list_conversations()
    names = {c["name"] for c in lst}
    assert names == {"会话A", "会话B"}


@pytest.mark.asyncio
async def test_save_conversation_preserves_name(store):
    cid = await store.create_conversation("保留名")
    await store.save_conversation(cid, [{"role": "user", "content": "hi"}], status="done", summary="s")
    conv = await store.get_conversation(cid)
    assert conv["name"] == "保留名"  # save 不覆盖 name
    assert conv["messages"][0]["content"] == "hi"


@pytest.mark.asyncio
async def test_delete_conversation(store):
    cid = await store.create_conversation("待删")
    await store.delete(cid)
    assert await store.get_conversation(cid) is None


# ─── 清除上下文 / 归档 ───


@pytest.mark.asyncio
async def test_clear_messages_keeps_session(store):
    cid = await store.create_conversation("清空测试")
    await store.save_conversation(cid, [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "yo"},
    ], status="done", summary="s")
    await store.clear_messages(cid)
    conv = await store.get_conversation(cid)
    assert conv["messages"] == []
    assert conv["name"] == "清空测试"  # 会话记录保留


@pytest.mark.asyncio
async def test_archive_and_filter(store):
    cid = await store.create_conversation("归档会话")
    # 默认列表含（未归档）
    assert any(c["id"] == cid for c in await store.list_conversations())

    await store.set_archived(cid, True)
    conv = await store.get_conversation(cid)
    assert conv["archived"] is True
    # 默认列表排除归档；归档分区可见；全部含
    assert all(c["id"] != cid for c in await store.list_conversations())
    assert any(c["id"] == cid for c in await store.list_conversations(archived=True))
    assert any(c["id"] == cid for c in await store.list_conversations(archived=None))

    # 取消归档恢复显示
    await store.set_archived(cid, False)
    assert any(c["id"] == cid for c in await store.list_conversations())
