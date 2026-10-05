# -*- coding: utf-8 -*-
"""通话漏斗 L0（确定性粗筛）+ L2 意图闸门测试。Call funnel L0 (deterministic screen)
+ L2 intent gate tests."""
import asyncio
import json
from pathlib import Path

import pytest

from core.voice.call_funnel import FunnelDeps, SegmentMeta, judge_call_intent, run_funnel, screen_l0

_VECTORS = json.loads((Path(__file__).parent / "data" / "call_funnel_vectors.json").read_text(encoding="utf-8"))


def _pass(**kw):
    return screen_l0(SegmentMeta(**kw), duration_s=2.0, rms=0.1,
                     min_seconds=0.5, min_rms=0.02)


def test_l0_passes_normal_segment():
    assert _pass(tab_focused=True) is None


def test_l0_drops_no_session():
    assert _pass(session_active=False, tab_focused=True) == "no_session"


def test_l0_drops_tts_active():
    """Review Focus #1：播报期的段绝不能进漏斗（回声自触发）。"""
    assert _pass(tts_active=True, tab_focused=True) == "echo"


def test_l0_drops_echo_guard():
    assert _pass(echo_guard=True, tab_focused=True) == "echo"


def test_l0_drops_short_and_quiet():
    assert screen_l0(SegmentMeta(tab_focused=True), duration_s=0.2, rms=0.1,
                     min_seconds=0.5, min_rms=0.02) == "too_short"
    assert screen_l0(SegmentMeta(tab_focused=True), duration_s=2.0, rms=0.001,
                     min_seconds=0.5, min_rms=0.02) == "low_rms"


def test_l0_unfocused_dropped_unless_open_window():
    assert _pass(tab_focused=False) == "unfocused"
    assert _pass(tab_focused=False, in_open_window=True) is None


@pytest.mark.parametrize("case", _VECTORS["quick_screen"]["positives"], ids=lambda c: c["text"] or "empty")
def test_quick_screen_positives(case):
    """正例必须放行（判「是否对AI说」是 L2 的事，L1 不许越权杀掉正常指令）。"""
    from core.voice.call_funnel import quick_screen
    assert quick_screen(case["text"]) is case["expect"]


@pytest.mark.parametrize("case", _VECTORS["quick_screen"]["negatives"], ids=lambda c: c["text"] or "empty")
def test_quick_screen_negatives(case):
    from core.voice.call_funnel import quick_screen
    assert quick_screen(case["text"]) == case["expect"]


# ── L2 意图闸门（judge_call_intent 四分类）/ L2 intent gate ──


def _fake_llm(verdict: str, seen: dict):
    """假 LLM：记录收到的 messages/tools，按预设 verdict 返回 done 事件。"""
    async def run(messages, tools=None, temperature=None):
        seen["messages"] = messages
        seen["tools"] = tools
        yield {"type": "done", "message": {"tool_calls": [{"function": {
            "name": "judge", "arguments": {"verdict": verdict, "note": "t"}}}]}}
    return run


def test_judge_parses_tool_verdict():
    seen: dict = {}
    v = asyncio.run(judge_call_intent("帮我打开记事本", "", relax=False, llm=_fake_llm("command", seen)))
    assert v == "command"
    assert any("闸门" in str(m.get("content", "")) for m in seen["messages"] if m["role"] == "system")


def test_judge_maps_all_verdicts_and_fallback():
    for verdict, expect in [("chitchat", "chitchat"), ("bystander", "bystander"),
                            ("unsure", "unsure"), ("bogus", "unsure")]:
        v = asyncio.run(judge_call_intent("x", "", relax=False, llm=_fake_llm(verdict, {})))
        assert v == expect


def test_judge_relax_mentions_policy():
    seen: dict = {}
    asyncio.run(judge_call_intent("x", "最近片段", relax=True, llm=_fake_llm("unsure", seen)))
    sys_msg = next(m["content"] for m in seen["messages"] if m["role"] == "system")
    assert "宁可误报" in sys_msg
    assert "最近片段" in next(m["content"] for m in seen["messages"] if m["role"] == "user")


def test_judge_error_falls_back_unsure():
    async def boom(*a, **k):
        raise RuntimeError("net down")
        yield  # pragma: no cover
    assert asyncio.run(judge_call_intent("x", "", relax=False, llm=boom)) == "unsure"


def test_judge_client_construction_failure_falls_back_unsure(monkeypatch):
    """裁决 R13：client 构造路径（惰性 import + get_llm_client()）在 try 内——
    构造本身抛出也必须静默兜底 unsure，不得把异常抛给调用方。"""
    def boom():
        raise RuntimeError("client construct fail")
    monkeypatch.setattr("core.llm.client.get_llm_client", boom)
    assert asyncio.run(judge_call_intent("x", "", relax=False)) == "unsure"


# ── run_funnel 三级漏斗集成 / run_funnel three-stage integration ──

WAV = b"RIFFfake"  # 假件不解码 wav，仅作透传标记


def _deps(**over):
    base = dict(
        local_transcribe=lambda w: "帮我打开记事本",
        cloud_transcribe=None,          # 下面统一给 async
        smart_turn=None,
        judge=None,
        min_seconds=0.5, min_rms=0.02, smart_turn_enabled=False,
    )
    base.update(over)
    if base["cloud_transcribe"] is None:
        async def cloud(w): return "云端精转"
        base["cloud_transcribe"] = cloud
    if base["judge"] is None:
        async def judge(t, r, relax): return "command"
        base["judge"] = judge
    return FunnelDeps(**base)


def _meta(**kw):
    kw.setdefault("tab_focused", True)
    return SegmentMeta(**kw)


def test_funnel_l0_drop_skips_all():
    seen = {"cloud": 0, "judge": 0}
    async def cloud(w):
        seen["cloud"] += 1
        return "x"
    async def judge(t, r, relax):
        seen["judge"] += 1
        return "command"
    r = asyncio.run(run_funnel(WAV, _meta(session_active=False),
                                _deps(cloud_transcribe=cloud, judge=judge),
                                recent="", relax=False, rms=0.1, duration_s=2.0))
    assert r.verdict == "dropped" and r.stage == "l0" and not r.hit
    assert seen == {"cloud": 0, "judge": 0}


def test_funnel_l1_quick_screen_drop():
    r = asyncio.run(run_funnel(WAV, _meta(), _deps(local_transcribe=lambda w: "嗯"),
                                recent="", relax=False, rms=0.1, duration_s=2.0))
    assert r.verdict == "dropped" and r.stage == "l1" and r.reason == "filler"


def test_funnel_smart_turn_incomplete_drops():
    async def st(w): return False
    r = asyncio.run(run_funnel(WAV, _meta(), _deps(smart_turn=st, smart_turn_enabled=True),
                                recent="", relax=False, rms=0.1, duration_s=2.0))
    assert r.verdict == "incomplete" and r.stage == "l1"


def test_funnel_full_path_hit_and_miss():
    r = asyncio.run(run_funnel(WAV, _meta(), _deps(), recent="", relax=False,
                                rms=0.1, duration_s=2.0))
    assert r.verdict == "command" and r.hit and r.stage == "l2"
    async def judge_chit(t, r_, relax): return "chitchat"
    r2 = asyncio.run(run_funnel(WAV, _meta(), _deps(judge=judge_chit), recent="",
                                relax=False, rms=0.1, duration_s=2.0))
    assert r2.hit is True and r2.verdict == "chitchat"
    async def judge_by(t, r_, relax): return "bystander"
    r3 = asyncio.run(run_funnel(WAV, _meta(), _deps(judge=judge_by), recent="",
                                relax=False, rms=0.1, duration_s=2.0))
    assert r3.hit is False and r3.stage == "l2"


def test_funnel_relax_lifts_unsure():
    async def judge_u(t, r_, relax): return "unsure"
    r = asyncio.run(run_funnel(WAV, _meta(), _deps(judge=judge_u), recent="",
                                relax=True, rms=0.1, duration_s=2.0))
    assert r.hit is True   # relax：unsure 提升为命中


def test_funnel_degrades_without_local_asr():
    """Review Focus #4：本地转写不可用 → 跳过 L1（含 quick_screen/Smart Turn），直上 L2。"""
    r = asyncio.run(run_funnel(WAV, _meta(), _deps(local_transcribe=None, smart_turn=None),
                               recent="", relax=False, rms=0.1, duration_s=2.0))
    assert r.hit is True and r.stage == "l2"


def test_funnel_cloud_transcribe_audits_upload():
    """Review Focus #5：云转写假件必须带 audio-upload 审计（Task 8 的 call.py 注入时同款前缀）。

    审计发生在 cloud_transcribe 内部（本模块不打审计行），本测试用会记账的桩钉住
    「每一次云端精转写都有且仅有一条 audio-upload 行」的契约。
    """
    calls = []

    async def cloud_audited(w):
        from core.logger import audit
        audit(f"audio-upload via=call-segment chars=4 text='云端'")
        calls.append("audio-upload via=call-segment")
        return "云端精转"

    r = asyncio.run(run_funnel(WAV, _meta(), _deps(local_transcribe=None,
                                                    cloud_transcribe=cloud_audited),
                               recent="", relax=False, rms=0.1, duration_s=2.0))
    assert r.hit and r.verdict == "command"
    assert len(calls) == 1
    assert calls[0] == "audio-upload via=call-segment"


def test_funnel_cloud_failure_degrades_to_judge():
    """L2 云转写失败静默收敛：异常不上抛、链路不断，judge 兜底收 L1 本地文本。"""
    async def cloud_boom(w):
        raise RuntimeError("cloud down")
    seen: dict = {}

    async def judge_keep(t, r, relax):
        seen["text"] = t
        return "command"

    r = asyncio.run(run_funnel(WAV, _meta(), _deps(cloud_transcribe=cloud_boom,
                                                    judge=judge_keep),
                               recent="", relax=False, rms=0.1, duration_s=2.0))
    assert r.hit and r.verdict == "command" and r.stage == "l2"
    assert seen["text"] == "帮我打开记事本"  # 云文本缺位 → L1 本地文本兜底


def test_funnel_judge_relax_passed_positionally():
    """裁决 R3：FunnelDeps.judge 契约是位置参数 relax——run_funnel 必须按位置传
    （位置-only 形参收到关键字传法会 TypeError，把契约漂移钉在测试里）。"""
    seen: dict = {}

    async def judge_pos(t, r, relax, /):
        seen["relax"] = relax
        return "unsure"

    r = asyncio.run(run_funnel(WAV, _meta(), _deps(judge=judge_pos), recent="",
                               relax=True, rms=0.1, duration_s=2.0))
    assert seen["relax"] is True
    assert r.hit is True  # relax 提升 unsure
