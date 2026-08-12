# -*- coding: utf-8 -*-
import yaml
import pytest

from core.orchestrator.session import Session
from core.skills.executor import fill_template, run_skill
from core.skills.loader import Skill, SkillLoader, SkillStep


def test_fill_template():
    assert fill_template({"command": "echo {{msg}}"}, {"msg": "hi"}) == {"command": "echo hi"}


@pytest.mark.asyncio
async def test_run_skill_with_params():
    skill = Skill("显示", steps=[SkillStep("run_shell_tool", {"command": "echo {{msg}}"})])
    r = await run_skill(skill, {"msg": "hi"})
    assert "hi" in r and "exit=0" in r


@pytest.mark.asyncio
async def test_run_skill_dangerous_rejected():
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
    import core.tools.skill_tools as st
    (tmp_path / "示例.yaml").write_text(yaml.safe_dump({
        "description": "演示技能",
        "steps": [{"tool": "get_datetime"}],
    }, allow_unicode=True), encoding="utf-8")
    monkeypatch.setattr(st, "_loader", SkillLoader(tmp_path))
    out = await st.run_skill_tool("示例", {})
    assert "年" in out  # get_datetime 返回中文日期
