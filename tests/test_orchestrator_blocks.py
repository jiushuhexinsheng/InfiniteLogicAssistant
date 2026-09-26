# -*- coding: utf-8 -*-
"""消息块协议（blocks.py）的测试：块信封、缺省 meta、纯文本投影、截断常量。
Tests for the message block protocol (blocks.py): envelope, default meta, plain
text projection, truncation constants.
"""
from core.orchestrator.blocks import (
    BLOCK_ANSWER, BLOCK_CODE, BLOCK_NOTICE, BLOCK_QUESTION, BLOCK_TEXT, BLOCK_THINKING,
    BLOCK_TOOL, DEFAULT_META, HISTORY_LEN, PREVIEW_LEN, Block, make_block,
    new_block_id, new_turn_id, text_projection,
)


def test_make_block_envelope():
    """块信封字段齐全且 v=1。The block envelope has all fields and v=1."""
    blk = make_block(BLOCK_TEXT, {"md": "你好"}, turn_id="turn_1", agent="main")
    assert blk["v"] == 1
    assert blk["type"] == "text"
    assert blk["turn_id"] == "turn_1"
    assert blk["agent"] == "main"
    assert blk["payload"] == {"md": "你好"}
    assert blk["id"].startswith("blk_")
    assert blk["ts"]  # ISO 时间戳


def test_make_block_merges_default_meta():
    """缺省 meta 按类型填充，调用方可覆盖。
    Default meta is filled per type and overridable by the caller."""
    thinking = make_block(BLOCK_THINKING, {"text": "想"})
    assert thinking["meta"] == DEFAULT_META[BLOCK_THINKING]  # collapsed=True, tts=skip
    overridden = make_block(BLOCK_THINKING, {"text": "想"}, meta={"tts": "summary", "collapsed": False})
    assert overridden["meta"] == {"tts": "summary", "collapsed": False}


def test_make_block_unknown_type_meta():
    """未注册类型缺省 tts=skip（安全侧：不乱播报）。
    Unregistered types default to tts=skip (safe side: never speak unexpectedly)."""
    blk = make_block("ext:chart", {"data": []})
    assert blk["meta"]["tts"] == "skip"


def test_ids_are_prefixed():
    """块/回合 ID 带前缀且唯一。Block/turn IDs are prefixed and unique."""
    assert new_block_id().startswith("blk_")
    assert new_turn_id().startswith("turn_")
    assert new_block_id() != new_block_id()


def test_block_model_validates_envelope():
    """Block 模型可校验信封（读取侧用）。
    The Block model validates envelopes (read side)."""
    blk = make_block(BLOCK_TOOL, {"name": "t"}, turn_id="turn_x")
    m = Block.model_validate(blk)
    assert m.type == BLOCK_TOOL
    assert m.turn_id == "turn_x"


def test_text_projection_mainline():
    """投影：text 取正文、tool 行 name: output[:200]、question 加 ❓、answer/notice 原文。
    Projection: text body, tool line name: output[:200], question with ❓,
    answer/notice verbatim."""
    blocks = [
        make_block(BLOCK_TEXT, {"md": "好的，已完成"}),
        make_block(BLOCK_TOOL, {"name": "run_shell", "output": "x" * 300}),
        make_block(BLOCK_QUESTION, {"question": "哪个城市？"}),
        make_block(BLOCK_ANSWER, {"text": "上海", "source": "voice"}),
        make_block(BLOCK_NOTICE, {"text": "参考了历史任务"}),
    ]
    proj = text_projection(blocks)
    lines = proj.split("\n")
    assert lines[0] == "好的，已完成"
    assert lines[1] == "run_shell: " + "x" * 200  # 截 200
    assert len(lines[1]) == len("run_shell: ") + 200
    assert lines[2] == "❓ 哪个城市？"
    assert lines[3] == "上海"
    assert lines[4] == "参考了历史任务"


def test_text_projection_skips_thinking_and_summary():
    """thinking / summary 不进投影（防上下文膨胀）；code 取代码正文。
    thinking / summary are excluded from the projection (keep context compact);
    code contributes its code body."""
    blocks = [
        make_block(BLOCK_THINKING, {"text": "内心戏"}),
        make_block(BLOCK_CODE, {"language": "python", "code": "print(1)"}),
        make_block("summary", {"summary_text": "汇总"}),
    ]
    proj = text_projection(blocks)
    assert "内心戏" not in proj
    assert "汇总" not in proj
    assert "print(1)" in proj


def test_text_projection_handles_garbage():
    """投影对非 dict / 空 payload 稳健。The projection is robust to non-dict / empty payloads."""
    assert text_projection([]) == ""
    assert text_projection([None, "str", {"type": BLOCK_TEXT, "payload": {}}]) == ""


def test_truncation_constants():
    """截断常量口径（SSE 预览 500 / 入库 4000）。
    Truncation constants (SSE preview 500 / persistence 4000)."""
    assert PREVIEW_LEN == 500
    assert HISTORY_LEN == 4000


# ─── Session 块写入：append 恒带 blocks、append_block 合并进末条消息 ───
# Session block writes: append always carries blocks, append_block merges into
# the last message.


def test_session_append_derives_text_block():
    """append 缺省 blocks 时从 content 生成单 text 块（消息恒带 blocks）。
    append derives a single text block from content when blocks is omitted."""
    from core.orchestrator.session import Session

    s = Session()
    s.append("user", "你好")
    msg = s.messages[-1]
    assert msg["content"] == "你好"
    assert msg["blocks"][0]["type"] == BLOCK_TEXT
    assert msg["blocks"][0]["payload"]["md"] == "你好"
    assert msg["ts"]  # 真实时间戳


def test_session_append_block_merges_into_last_message():
    """append_block 向末条同角色消息追加块并重算 content 投影。
    append_block appends to the last same-role message and recomputes the projection."""
    from core.orchestrator.session import Session

    s = Session()
    s.append("assistant", "开始")
    s.append_block("assistant", make_block(BLOCK_TOOL, {"name": "t", "output": "ok"}))
    assert len(s.messages) == 1  # 合并进末条，不新建
    assert [b["type"] for b in s.messages[0]["blocks"]] == [BLOCK_TEXT, BLOCK_TOOL]
    assert "t: ok" in s.messages[0]["content"]


def test_session_append_block_starts_new_message_on_role_change():
    """角色不匹配时 append_block 新建消息。append_block starts a new message on role change."""
    from core.orchestrator.session import Session

    s = Session()
    s.append("user", "问题")
    s.append_block("assistant", make_block(BLOCK_ANSWER, {"text": "回答"}))
    assert len(s.messages) == 2
    assert s.messages[-1]["role"] == "assistant"
    assert s.messages[-1]["content"] == "回答"
