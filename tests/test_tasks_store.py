# -*- coding: utf-8 -*-
"""任务知识库存储（TaskStore / similarity / 参数截断）的测试。
Tests for the task knowledge base store (TaskStore / similarity / argument truncation).
"""
import pytest

from core.orchestrator.task import Task
from core.tasks.store import TaskStore, _truncate_args, similarity


# ─── similarity：字符 trigram Jaccard ───

def test_similarity_identical():
    """完全相同 = 1.0。Identical strings score 1.0."""
    assert similarity("复制文件到下载", "复制文件到下载") == 1.0


def test_similarity_no_overlap():
    """完全无交集 = 0.0。Disjoint strings score 0.0."""
    assert similarity("复制文件", "查询天气") == 0.0


def test_similarity_partial_between_zero_and_one():
    """部分重叠落在 (0,1) 开区间。Partial overlap lands strictly between 0 and 1."""
    s = similarity("把 readme 复制到下载", "把 readme 复制到桌面")
    assert 0.0 < s < 1.0


def test_similarity_ignores_whitespace():
    """空白差异不影响判定（内部先剥空白）。Whitespace differences do not affect the score."""
    assert similarity("复制 文件", "复制文件") == 1.0


def test_similarity_short_and_empty():
    """短于 3 字符走单元素分支；空串为 0.0。Short strings use the single-element branch; empty is 0.0."""
    assert similarity("ab", "ab") == 1.0
    assert similarity("ab", "cd") == 0.0
    assert similarity("", "复制文件") == 0.0


# ─── _truncate_args：隐私处置 ───

def test_truncate_short_string_untouched():
    """短字符串原样保留。Short strings are left untouched."""
    assert _truncate_args({"path": "a.txt"}) == {"path": "a.txt"}


def test_truncate_long_string_marked():
    """超长字符串被截断并带标记 —— 避免把当时的文件内容整份留在库里。
    Over-long strings are truncated and marked, so a whole file's contents do not end up
    persisted in the task library."""
    long = "x" * 500
    out = _truncate_args({"content": long})
    assert len(out["content"]) < 500
    assert out["content"].startswith("x" * 200)
    assert "截断" in out["content"]


def test_truncate_keeps_non_strings():
    """非字符串值不受影响。Non-string values are unaffected."""
    assert _truncate_args({"n": 42, "b": True, "lst": [1, 2], "none": None}) == {
        "n": 42, "b": True, "lst": [1, 2], "none": None}


# ─── TaskStore CRUD 与阈值闸门 ───

def _task(goal: str, params: dict | None = None) -> Task:
    return Task(id="t1", goal=goal, params=params or {}, risk="read")


def _result() -> dict:
    return {"status": "done", "summary": "完成", "steps": [
        {"step": 0, "tool": "write_file", "args": {"path": "a.txt", "content": "y" * 500}, "status": "ok"},
    ]}


@pytest.fixture
def store(tmp_path):
    return TaskStore(tmp_path / "tasks.sqlite")


@pytest.mark.asyncio
async def test_record_and_list(store):
    """存档后可列出；steps 里的长参数已被截断。A recorded task is listed, with long step args truncated."""
    await store.record(_task("复制文件到下载", {"src": "a", "dest": "b"}), _result(), session_id="s1")
    rows = await store.list_tasks()
    assert len(rows) == 1
    assert rows[0]["goal"] == "复制文件到下载"
    assert rows[0]["params"] == {"src": "a", "dest": "b"}
    assert "截断" in rows[0]["steps"][0]["args"]["content"]


@pytest.mark.asyncio
async def test_find_similar_above_threshold(store):
    """相似度达阈值 → 返回最高分那条（含 params）。A hit above the threshold returns the best match with its params."""
    await store.record(_task("把 readme.txt 复制到下载目录", {"dest": "下载"}), _result())
    hit = await store.find_similar("把 readme.txt 复制到下载目录")
    assert hit is not None
    assert hit["params"] == {"dest": "下载"}


@pytest.mark.asyncio
async def test_find_similar_below_threshold_returns_none(store):
    """相似度低于阈值必须返回 None —— 这是「不误预填」的闸门。

    刻意用一个**部分重叠但低于阈值**的目标（相似度约 0.38）：若用完全不相干的
    目标（相似度恰好 0），最高分从未被赋值就返回 None 了，测试会**通过得理由错**
    —— 拿掉阈值判定它仍然绿，等于没测到闸门（变异检验时发现的）。
    阈值判定必须让它失败，故必须选落在 (0, threshold) 区间的目标。

    Below the threshold find_similar must return None: the gate that prevents prefilling
    from an unrelated task. The query is deliberately *partially* overlapping but below the
    threshold (≈0.38): with a fully disjoint query the best score is exactly 0 and the
    function returns None before the threshold check ever runs — the test would pass for
    the wrong reason and stay green even with the gate removed (found via mutation testing).
    """
    await store.record(_task("把 readme.txt 复制到下载目录", {"dest": "下载"}), _result())
    assert await store.find_similar("复制 readme.txt 到别处") is None


@pytest.mark.asyncio
async def test_find_similar_on_empty_store(store):
    """空库返回 None。An empty store returns None."""
    assert await store.find_similar("随便什么目标") is None


@pytest.mark.asyncio
async def test_get_and_delete(store):
    """按 id 取详情与删除。Fetch by id and delete."""
    await store.record(_task("任务甲"), _result())
    rows = await store.list_tasks()
    tid = rows[0]["id"]
    assert (await store.get_task(tid))["goal"] == "任务甲"
    await store.delete_task(tid)
    assert await store.get_task(tid) is None
    assert await store.list_tasks() == []


@pytest.mark.asyncio
async def test_record_is_append_only(store):
    """同一 goal 存档两次保留两条 —— 只增不改是本表相对 facts 覆盖式的关键差异。
    Recording the same goal twice keeps both rows: append-only is the key difference from
    the facts store's overwrite semantics."""
    await store.record(_task("同一目标"), _result())
    await store.record(_task("同一目标"), _result())
    assert len(await store.list_tasks()) == 2


@pytest.mark.asyncio
async def test_find_similar_matches_source_text_not_goal(store):
    """匹配认用户原话（source_text），不认 LLM 归一化的 goal。

    端到端实测发现的真问题：同一句「济南现在天气怎么样」两次跑出的 goal 分别是
    「查询济南市当前的天气情况」与「查询济南当前的实时天气情况」，trigram 相似度只有
    0.312 < 阈值 —— 若按 goal 匹配则同一件事永远命中不了。按原话匹配则完全相同。

    Matching uses the user's original utterance, not the LLM-normalised goal. Found via
    end-to-end testing: the same sentence produced goals only 0.312 similar, so matching on
    the goal would never hit for an identical task; the source text is identical.
    """
    await store.record(_task("查询济南市当前的天气情况", {"city": "济南"}), _result(),
                       source_text="济南现在天气怎么样")
    # 同样的原话 → 命中
    hit = await store.find_similar("济南现在天气怎么样")
    assert hit is not None and hit["params"] == {"city": "济南"}
    # 换了说法（但与 goal 文字相近）→ 按原话匹配则不应命中
    assert await store.find_similar("查询济南市当前的天气情况") is None


@pytest.mark.asyncio
async def test_find_similar_falls_back_to_goal_for_old_rows(store):
    """老数据无 source_text 时回退到 goal 匹配。Rows without source_text fall back to the goal."""
    await store.record(_task("把 readme.txt 复制到下载目录", {"dest": "下载"}), _result())  # 无 source_text
    assert await store.find_similar("把 readme.txt 复制到下载目录") is not None
