# -*- coding: utf-8 -*-
"""测试技能执行器：模板填充、技能运行、危险技能确认与 session 注入。
Tests the skill executor: template filling, skill running, dangerous-skill confirmation, and session injection.
"""
import yaml
import pytest

from core.orchestrator.session import Session
from core.skills.executor import fill_template, run_skill
from core.skills.loader import Skill, SkillLoader, SkillStep
from core.tools import TOOLS


def test_fill_template():
    """测试模板中的占位符被参数替换。Tests placeholders in a template being replaced with parameters."""
    assert fill_template({"command": "echo {{msg}}"}, {"msg": "hi"}) == {"command": "echo hi"}


def test_fill_template_windows_path():
    """测试含反斜杠/引号的 Windows 路径参数不会导致整体回退。Tests Windows path parameters with backslashes/quotes not causing a full fallback."""
    # 参数含反斜杠/引号（Windows 路径）不得导致整体回退
    path = r"C:\Users\许广瑞\Downloads\my file.txt"
    assert fill_template({"command": 'dir "{{path}}"', "meta": {"p": "{{path}}"}},
                         {"path": path}) == {
        "command": f'dir "{path}"',
        "meta": {"p": path},
    }


def test_fill_template_nested_and_multiple():
    """测试嵌套结构与多个占位符同时替换。Tests replacement of placeholders in nested structures and multiple occurrences."""
    assert fill_template(
        {"a": {"b": "{{x}}", "c": "x={{x}} y={{y}}"}, "list": ["{{x}}", "{{y}}"], "n": 1},
        {"x": "X", "y": "Y"},
    ) == {"a": {"b": "X", "c": "x=X y=Y"}, "list": ["X", "Y"], "n": 1}


def test_fill_template_missing_param_keeps_placeholder():
    """测试缺少参数时占位符原样保留。Tests placeholders staying intact when a parameter is missing."""
    # 缺参数时占位符原样保留，但不影响其他已替换部分
    assert fill_template({"a": "{{x}}", "b": "{{y}}"}, {"y": "Y"}) == {"a": "{{x}}", "b": "Y"}


@pytest.mark.asyncio
async def test_run_skill_with_params():
    """测试带参数运行技能并得到执行结果。Tests running a skill with parameters and getting the execution result."""
    skill = Skill("显示", steps=[SkillStep("run_shell_tool", {"command": "echo {{msg}}"})])
    r = await run_skill(skill, {"msg": "hi"})
    assert "hi" in r and "exit=0" in r


@pytest.mark.asyncio
async def test_run_skill_dangerous_rejected():
    """测试危险技能在无 session 时被拒绝执行。Tests a dangerous skill being rejected without a session."""
    class _Channel:
        def __init__(self):
            self.answers = ["取消"]

        async def ask(self, q):
            return self.answers.pop(0)

        async def notify(self, text):
            pass

    s = Session()
    s.channel = _Channel()
    skill = Skill("危险", dangerous=True, steps=[SkillStep("run_shell_tool", {"command": "echo x"})])
    r = await run_skill(skill, {}, session=s)
    assert r.startswith("Error")


@pytest.mark.asyncio
async def test_run_skill_tool(tmp_path, monkeypatch):
    """测试通过 skill 工具执行 YAML 定义的技能。Tests running a YAML-defined skill through the skill tool."""
    import core.tools.skill_tools as st
    (tmp_path / "示例.yaml").write_text(yaml.safe_dump({
        "description": "演示技能",
        "steps": [{"tool": "get_datetime"}],
    }, allow_unicode=True), encoding="utf-8")
    monkeypatch.setattr(st, "_loader", SkillLoader(tmp_path))
    out = await st.run_skill_tool("示例", {})
    assert "年" in out  # get_datetime 返回中文日期


def test_skill_schema_excludes_session():
    """测试 session 作为服务注入参数不出现在 LLM schema 中。Tests session, a service-injected parameter, not appearing in the LLM schema."""
    # session 是服务注入参数，不进 LLM schema
    by_name = {s["function"]["name"]: s for s in TOOLS.schemas()}
    params = by_name["run_skill_tool"]["function"]["parameters"]
    assert "session" not in params["properties"]
    assert "session" not in params.get("required", [])


class _ConfirmChannel:
    """测试用的确认通道：按预设答案回复提问并记录通知。
    A test confirmation channel that answers questions from a preset list and records notifications.
    """
    def __init__(self, answers):
        self.answers = list(answers)
        self.notified: list[str] = []

    async def ask(self, q):
        return self.answers.pop(0)

    async def notify(self, text):
        self.notified.append(text)


@pytest.mark.asyncio
async def test_run_skill_tool_dangerous_with_session(tmp_path, monkeypatch):
    """测试携带 session 的危险技能经确认后可以执行。Tests a dangerous skill with a session being executable after confirmation."""
    # 危险技能携带 session 后：确认通道可用 → 可执行（此前传 None 恒被拒）
    import core.tools.skill_tools as st
    (tmp_path / "危险.yaml").write_text(yaml.safe_dump({
        "description": "危险技能",
        "dangerous": True,
        "steps": [{"tool": "get_datetime"}],
    }, allow_unicode=True), encoding="utf-8")
    monkeypatch.setattr(st, "_loader", SkillLoader(tmp_path))

    s = Session()
    s.channel = _ConfirmChannel(["确认"])
    out = await st.run_skill_tool("危险", {}, session=s)
    assert "年" in out  # get_datetime 成功执行
    assert "需要确认" in s.channel.notified[0]  # 危险技能先经确认


@pytest.mark.asyncio
async def test_run_skill_tool_acall_injects_session(tmp_path, monkeypatch):
    """测试 TOOLS.acall 注入 session 后危险技能经 LLM 工具路径可确认执行。Tests a dangerous skill run via the LLM tool path after TOOLS.acall injects a session."""
    # TOOLS.acall 注入 session 后，危险技能经 LLM 工具路径可确认执行
    import core.tools.skill_tools as st
    (tmp_path / "危险.yaml").write_text(yaml.safe_dump({
        "description": "危险技能",
        "dangerous": True,
        "steps": [{"tool": "get_datetime"}],
    }, allow_unicode=True), encoding="utf-8")
    monkeypatch.setattr(st, "_loader", SkillLoader(tmp_path))

    s = Session()
    s.channel = _ConfirmChannel(["确认"])
    out = await TOOLS.acall("run_skill_tool", {"name": "危险", "params": {}}, session=s)
    assert "年" in out
