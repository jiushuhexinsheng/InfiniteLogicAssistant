# -*- coding: utf-8 -*-
"""该模块测试 core.agent.coordinator.run_coordinator 协调器的行为：合并子任务结果、发送通知事件以及取消处理。
Tests the coordinator run_coordinator in core.agent.coordinator: merging subtask results, emitting notify events, and cancellation handling.
"""
from types import SimpleNamespace

import pytest

from core.agent.coordinator import run_coordinator
from core.orchestrator.control import CancellationToken
from core.orchestrator.session import Session
from core.orchestrator.task import Task


@pytest.mark.asyncio
async def test_coordinator_merges_subtasks(monkeypatch):
    """验证协调器汇总多个子任务的执行结果。Verifies the coordinator merges the execution results of multiple subtasks."""
    async def fake_decompose(task, ctx=""):
        return [
            {"goal": "子任务1", "agent_type": "doer", "independent": True},
            {"goal": "子任务2", "agent_type": "searcher", "independent": True},
        ]

    async def fake_subagent(role, goal, context="", cancel=None, max_steps=None, confirm=None, events=None, agent=""):
        return SimpleNamespace(status="done", output=f"结果:{goal}", used_tools=["get_datetime"])

    async def fake_build(q):
        return "上下文"

    monkeypatch.setattr("core.agent.coordinator._decompose", fake_decompose)
    monkeypatch.setattr("core.agent.coordinator.run_subagent", fake_subagent)
    monkeypatch.setattr("core.agent.coordinator.build_context", fake_build)

    s = Session()
    r = await run_coordinator(Task("t", "主任务"), s, CancellationToken())
    assert r["status"] == "done"
    assert len(r["subtasks"]) == 2
    assert any("子任务1" in x["goal"] for x in r["subtasks"])


@pytest.mark.asyncio
async def test_coordinator_emits_notify_events(monkeypatch):
    """验证协调器在子任务执行期间发出通知事件。Verifies the coordinator emits notify events during subtask execution."""
    async def fake_decompose(task, ctx=""):
        return [{"goal": "子任务", "agent_type": "doer", "independent": False}]

    async def fake_subagent(role, goal, context="", cancel=None, max_steps=None, confirm=None, events=None, agent=""):
        return SimpleNamespace(status="done", output="完成", used_tools=[])

    async def fake_build(q):
        return ""

    monkeypatch.setattr("core.agent.coordinator._decompose", fake_decompose)
    monkeypatch.setattr("core.agent.coordinator.run_subagent", fake_subagent)
    monkeypatch.setattr("core.agent.coordinator.build_context", fake_build)

    events = []

    class _Rec:
        async def notify(self, text):
            events.append(text)
        async def ask(self, q, *, kind="text", options=None):
            return ""

    s = Session()
    s.channel = _Rec()
    r = await run_coordinator(Task("t", "主任务"), s, CancellationToken())
    assert r["status"] == "done"
    assert any("已拆分" in e for e in events)
    assert any("子代理 doer 开始" in e for e in events)
    assert any("子代理 doer 完成" in e for e in events)
    assert any("批评" in e for e in events)


@pytest.mark.asyncio
async def test_coordinator_cancelled_before(monkeypatch):
    """验证运行前已取消时协调器直接返回 stopped 且无子任务。Verifies the coordinator returns stopped with no subtasks when cancelled before running."""
    token = CancellationToken()
    token.cancel()
    s = Session()
    r = await run_coordinator(Task("t", "主任务"), s, token)
    assert r["status"] == "stopped"
    assert r["subtasks"] == []


# ─── 委派规范与产物落文件（docs/designs/08 批3）───


def test_decompose_schema_caps_and_quartet():
    """拆解 schema：子任务 maxItems=6 硬上限 + 委派四要素字段（output_format/boundary）。
    Decomposition schema: maxItems=6 hard cap + delegation-quartet fields."""
    import json as _json
    from core.agent.coordinator import _DECOMPOSE_TOOL
    params = _DECOMPOSE_TOOL["function"]["parameters"]
    assert params["properties"]["subtasks"]["maxItems"] == 6
    item_props = params["properties"]["subtasks"]["items"]["properties"]
    assert "output_format" in item_props and "boundary" in item_props


@pytest.mark.asyncio
async def test_coordinator_artifact_and_critic_paths(monkeypatch, tmp_path):
    """子代理完整产物落文件（critic 读全文）：executed 留 300 字预览 + 路径，
    critic 提示词携带「完整产物」路径。Sub-agent full output lands in a file (the critic
    reads it): executed keeps a 300-char preview + path, and the critic prompt carries the
    artifact path."""
    from core import config as config_mod
    monkeypatch.setattr(config_mod, "ROOT_DIR", tmp_path)

    long_output = "详" * 400
    goals_seen: list[str] = []

    async def fake_decompose(task, ctx=""):
        return [{"goal": "长产出子任务", "agent_type": "doer", "independent": False}]

    async def fake_subagent(role, goal, context="", cancel=None, max_steps=None, confirm=None, events=None, agent=""):
        goals_seen.append(goal)
        if "审查" in goal:
            return SimpleNamespace(status="done", output="审查通过", used_tools=[])
        return SimpleNamespace(status="done", output=long_output, used_tools=["read_file"])

    async def fake_build(q):
        return ""

    monkeypatch.setattr("core.agent.coordinator._decompose", fake_decompose)
    monkeypatch.setattr("core.agent.coordinator.run_subagent", fake_subagent)
    monkeypatch.setattr("core.agent.coordinator.build_context", fake_build)

    s = Session()
    r = await run_coordinator(Task("t", "主任务"), s, CancellationToken())

    entry = r["subtasks"][0]
    assert len(entry["output"]) == 300                 # 预览 300 字。300-char preview.
    assert entry["artifact"] and "agent_outputs" in entry["artifact"]
    from pathlib import Path
    assert Path(entry["artifact"]).read_text(encoding="utf-8") == long_output  # 全文在盘上。Full text on disk.

    critic_goal = next(g for g in goals_seen if "审查" in g)
    assert "完整产物" in critic_goal and entry["artifact"] in critic_goal
