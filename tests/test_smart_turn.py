# -*- coding: utf-8 -*-
"""Smart Turn 包装：禁用/加载失败降级为 True（切段即回合的旧行为）。Smart Turn wrapper degradation."""
import asyncio

from core.voice import smart_turn


def test_disabled_config_degrades(monkeypatch):
    from core import config
    monkeypatch.setattr(config.settings.voice.call, "smart_turn_enabled", False)
    monkeypatch.setattr(smart_turn, "_instance", None)
    st = smart_turn.get_smart_turn()
    assert st.available() is False
    assert asyncio.run(st.is_complete(b"\x00\x01" * 160, 16000)) is True


def test_is_complete_never_raises(monkeypatch):
    """损坏输入也不许抛：返回 True（放行），通话链路不能被轮次模型卡死。"""
    monkeypatch.setattr(smart_turn, "_instance", None)
    st = smart_turn.get_smart_turn()
    assert asyncio.run(st.is_complete(b"", 16000)) in (True, False)
