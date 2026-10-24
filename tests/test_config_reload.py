# -*- coding: utf-8 -*-
"""配置热重载：按变更段触发钩子 + 来源日志。

Config hot reload: section-scoped hooks plus a source-tagged log line.
"""
import pytest
from loguru import logger as loguru_logger

from core import config as cfg
from core.config import runtime as rt
from core.config.schema import Settings


@pytest.fixture
def isolated(monkeypatch):
    """隔离全局单例与钩子表。Isolate the singleton and the hook table."""
    monkeypatch.setattr(cfg, "_settings", Settings())
    monkeypatch.setattr(cfg, "_reload_hooks", [])
    yield


def test_voice_hook_skipped_when_other_section_changes(isolated, monkeypatch):
    """只改 agent 段时，voice 作用域的钩子不执行（本地引擎/子进程池不该重建）。
    A voice-scoped hook must not run when only the agent section changed."""
    hits: list[str] = []
    cfg.add_reload_hook(lambda: hits.append("voice"), sections=("voice",))
    cfg.add_reload_hook(lambda: hits.append("always"))
    monkeypatch.setattr(rt, "_build", lambda: Settings(agent={"recursion_limit": 5}))

    rt.reload_settings(source="test-agent")

    assert hits == ["always"]


def test_voice_hook_runs_when_voice_changes(isolated, monkeypatch):
    """voice 段变化时，voice 作用域钩子与无作用域钩子都执行。
    When the voice section changes, both scoped and unscoped hooks run."""
    hits: list[str] = []
    cfg.add_reload_hook(lambda: hits.append("voice"), sections=("voice",))
    cfg.add_reload_hook(lambda: hits.append("always"))
    monkeypatch.setattr(rt, "_build",
                        lambda: Settings(voice={"streaming": {"enabled": False}}))

    rt.reload_settings(source="test-voice")

    assert hits == ["voice", "always"]


def test_reload_runs_every_hook_on_first_build(isolated, monkeypatch):
    """首次构建（无旧配置）时无从比较，所有钩子照常执行。
    With no previous settings there is nothing to compare, so every hook runs."""
    monkeypatch.setattr(cfg, "_settings", None)
    hits: list[str] = []
    cfg.add_reload_hook(lambda: hits.append("voice"), sections=("voice",))
    monkeypatch.setattr(rt, "_build", lambda: Settings())

    rt.reload_settings(source="test-first")

    assert hits == ["voice"]


def test_reload_logs_source_and_changed_sections(isolated, monkeypatch):
    """重载日志必须带来源，便于定位「谁把引擎打掉了」。
    The reload log must carry the source so engine rebuilds can be traced."""
    monkeypatch.setattr(rt, "_build", lambda: Settings(agent={"recursion_limit": 7}))
    messages: list[str] = []
    sink = loguru_logger.add(lambda m: messages.append(m.record["message"]), level="INFO")
    try:
        rt.reload_settings(source="unit-test-source")
    finally:
        loguru_logger.remove(sink)

    assert any("unit-test-source" in m and "agent" in m for m in messages)
