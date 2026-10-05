# -*- coding: utf-8 -*-
"""通话漏斗 L0（确定性粗筛）测试。Call funnel L0 (deterministic screen) tests."""
import json
from pathlib import Path

import pytest

from core.voice.call_funnel import SegmentMeta, screen_l0

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
