# -*- coding: utf-8 -*-
"""Skills 加载器 — 读 skills/*.yaml（文件名=技能名），按 mtime 热重载
Skills loader — reads skills/*.yaml (file name = skill name) and hot-reloads them by mtime.
"""
import yaml
from dataclasses import dataclass, field
from pathlib import Path

from core.config import ROOT_DIR

SKILLS_DIR = ROOT_DIR / "skills"


@dataclass
class SkillStep:
    """技能中的一个执行步骤（工具名 + 参数模板 + 说明）。
    A single execution step of a skill (tool name + args template + note)."""

    tool: str
    args_template: dict = field(default_factory=dict)
    note: str = ""


@dataclass
class Skill:
    """一个技能的完整定义（名称、描述、依赖、步骤、校验表达式、危险标记）。
    Full definition of a skill (name, description, requires, steps, validate expression, dangerous flag)."""

    name: str
    description: str = ""
    requires: list[str] = field(default_factory=list)
    steps: list[SkillStep] = field(default_factory=list)
    validate: str = ""
    dangerous: bool = False


def _parse_skill(path: Path, default_name: str) -> Skill:
    """从 YAML 文件解析出一个 Skill；缺失 name 时用文件名作为默认名。
    Parses a Skill from a YAML file; uses the file name as the default name when name is missing."""
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    steps = [
        SkillStep(s.get("tool", ""), dict(s.get("args_template") or {}), s.get("note", ""))
        for s in raw.get("steps", [])
    ]
    return Skill(
        name=str(raw.get("name") or default_name),
        description=str(raw.get("description", "")),
        requires=list(raw.get("requires") or []),
        steps=steps,
        validate=str(raw.get("validate", "")),
        dangerous=bool(raw.get("dangerous", False)),
    )


class SkillLoader:
    """技能加载器：扫描目录并按 mtime 变化热重载技能。
    Skill loader: scans the directory and hot-reloads skills when their mtime changes."""

    def __init__(self, directory: Path = SKILLS_DIR):
        """构造器：记录技能目录与 mtime/技能缓存。
        Constructor: records the skills directory and the mtime/skill caches."""
        self.directory = directory
        self._mtime: dict[str, float] = {}
        self._skills: dict[str, Skill] = {}

    def load_all(self) -> dict[str, Skill]:
        """全量加载技能（先清空缓存再重载）。
        Loads all skills (clears the cache first, then reloads)."""
        self.directory.mkdir(parents=True, exist_ok=True)
        self._mtime = {}
        self._skills = {}
        return self.reload_if_changed()

    def reload_if_changed(self) -> dict[str, Skill]:
        """mtime 变化才重载；文件删除则移除对应 skill。
        Reloads a skill only when its mtime changed; removes the corresponding skill when a file is deleted."""
        files = {p.name: p for p in self.directory.glob("*.yaml")}
        for fname in [n for n in self._mtime if n not in files]:
            self._mtime.pop(fname)
            self._skills.pop(fname[:-5], None)
        for fname, p in files.items():
            mt = p.stat().st_mtime
            if self._mtime.get(fname) != mt:
                try:
                    skill = _parse_skill(p, default_name=fname[:-5])
                    self._skills[skill.name] = skill
                    self._mtime[fname] = mt
                except Exception:
                    continue
        return self._skills
