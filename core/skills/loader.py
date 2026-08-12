# -*- coding: utf-8 -*-
"""Skills 加载器 — 读 skills/*.yaml（文件名=技能名），按 mtime 热重载"""
import yaml
from dataclasses import dataclass, field
from pathlib import Path

from core.config import ROOT_DIR

SKILLS_DIR = ROOT_DIR / "skills"


@dataclass
class SkillStep:
    tool: str
    args_template: dict = field(default_factory=dict)
    note: str = ""


@dataclass
class Skill:
    name: str
    description: str = ""
    requires: list[str] = field(default_factory=list)
    steps: list[SkillStep] = field(default_factory=list)
    validate: str = ""
    dangerous: bool = False


def _parse_skill(path: Path, default_name: str) -> Skill:
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
    def __init__(self, directory: Path = SKILLS_DIR):
        self.directory = directory
        self._mtime: dict[str, float] = {}
        self._skills: dict[str, Skill] = {}

    def load_all(self) -> dict[str, Skill]:
        self.directory.mkdir(parents=True, exist_ok=True)
        self._mtime = {}
        self._skills = {}
        return self.reload_if_changed()

    def reload_if_changed(self) -> dict[str, Skill]:
        """mtime 变化才重载；文件删除则移除对应 skill。"""
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
