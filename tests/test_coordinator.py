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

    async def fake_subagent(role, goal, context="", cancel=None, max_steps=None, confirm=None,
                            events=None, agent="", pause=None, session=None):
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

    async def fake_subagent(role, goal, context="", cancel=None, max_steps=None, confirm=None,
                            events=None, agent="", pause=None, session=None):
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

    async def fake_subagent(role, goal, context="", cancel=None, max_steps=None, confirm=None,
                            events=None, agent="", pause=None, session=None):
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


# ─── 子任务上限 / 类型白名单 / 产物路径 / 暂停传播 / 摘要口径（docs/designs/10 5.5）───


def _stub_coordinator(monkeypatch, subtasks, on_sub=None):
    """搭一个最小协调器环境：拆解结果固定，子代理按需回调。"""
    async def fake_decompose(task, ctx=""):
        return subtasks

    async def fake_subagent(role, goal, context="", cancel=None, max_steps=None, confirm=None,
                            events=None, agent="", pause=None, session=None):
        if on_sub is not None:
            on_sub(role, goal, agent, pause, session)
        if "审查" in goal:
            return SimpleNamespace(status="done", output="审查通过", used_tools=[])
        return SimpleNamespace(status="done", output=f"结果:{goal}", used_tools=[])

    async def fake_build(q):
        return ""

    monkeypatch.setattr("core.agent.coordinator._decompose", fake_decompose)
    monkeypatch.setattr("core.agent.coordinator.run_subagent", fake_subagent)
    monkeypatch.setattr("core.agent.coordinator.build_context", fake_build)


@pytest.mark.asyncio
async def test_coordinator_caps_subtasks_and_normalizes_agent_type(monkeypatch):
    """子任务数受 agent.max_subtasks 限制；未知 agent_type 一律按 doer 执行。"""
    from core import config as config_mod
    monkeypatch.setattr(config_mod.settings.agent, "max_subtasks", 2)
    roles: list[str] = []
    _stub_coordinator(monkeypatch, [
        {"goal": "一", "agent_type": "hacker", "independent": False},
        {"goal": "二", "agent_type": "searcher", "independent": False},
        {"goal": "三", "agent_type": "planner", "independent": False},
    ], on_sub=lambda role, goal, agent, pause, session: roles.append(agent))

    r = await run_coordinator(Task("t", "主任务"), Session(), CancellationToken())

    assert len(r["subtasks"]) == 2
    assert [x["agent_type"] for x in r["subtasks"]] == ["doer", "searcher"]
    assert roles[:2] == ["sub:doer", "sub:searcher"]


@pytest.mark.asyncio
async def test_coordinator_artifact_sanitizes_path(monkeypatch, tmp_path):
    """产物白名单类型 + 目标必须落在 data/agent_outputs/ 内（session.id 也可疑时不越界）。"""
    from pathlib import Path
    from core import config as config_mod
    monkeypatch.setattr(config_mod, "ROOT_DIR", tmp_path)
    _stub_coordinator(monkeypatch, [
        {"goal": "写文件", "agent_type": "../../escape", "independent": False},
    ])

    s = Session(session_id="../../evil")
    await run_coordinator(Task("t", "主任务"), s, CancellationToken())

    root = (tmp_path / "data" / "agent_outputs").resolve()
    written = list((tmp_path / "data").rglob("*.md"))
    assert written, "应至少产出一个产物文件"
    for p in written:
        assert p.resolve().is_relative_to(root), f"产物越界: {p}"


@pytest.mark.asyncio
async def test_coordinator_passes_pause_and_session(monkeypatch):
    """暂停控制器与会话透传给子代理（子代理据此在步骤边界等待、并走统一技能确认链）。"""
    seen: dict = {}
    pause = object()
    session = Session(session_id="sid-1")

    def on_sub(role, goal, agent, pause_arg, session_arg):
        seen["pause"] = pause_arg
        seen["session"] = session_arg

    _stub_coordinator(monkeypatch, [
        {"goal": "子任务", "agent_type": "doer", "independent": False},
    ], on_sub=on_sub)

    await run_coordinator(Task("t", "主任务"), session, CancellationToken(), pause=pause)

    assert seen["pause"] is pause
    assert seen["session"] is session


@pytest.mark.asyncio
async def test_coordinator_summary_is_voice_short_with_full_report(monkeypatch):
    """done.summary 只放 ≤60 字语音摘要；完整报告单独返回（steps 用）。"""
    detailed = "详细结论：" + "很长的内容" * 40
    _stub_coordinator(monkeypatch, [
        {"goal": "子任务", "agent_type": "doer", "independent": False},
    ])

    async def fake_sub(role, goal, context="", cancel=None, max_steps=None, confirm=None,
                       events=None, agent="", pause=None, session=None):
        if "审查" in goal:
            return SimpleNamespace(status="done", output="审查通过", used_tools=[])
        return SimpleNamespace(status="done", output=detailed, used_tools=[])

    monkeypatch.setattr("core.agent.coordinator.run_subagent", fake_sub)
    r = await run_coordinator(Task("t", "主任务"), Session(), CancellationToken())

    assert len(r["summary"]) <= 60
    assert detailed in r["report"]
    assert r["summary"] != r["report"]
