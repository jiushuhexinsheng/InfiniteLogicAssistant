# -*- coding: utf-8 -*-
import os
import time

import yaml

from core.skills.loader import SkillLoader


def _write_skill(dir, name, data):
    (dir / name).write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")


def test_load_skills(tmp_path):
    _write_skill(tmp_path, "整理.yaml", {
        "description": "归档下载目录",
        "requires": ["download_path"],
        "steps": [{"tool": "run_shell_tool", "args_template": {"command": "dir {{download_path}}"}, "note": "列出"}],
    })
    loader = SkillLoader(tmp_path)
    skills = loader.load_all()
    assert "整理" in skills
    s = skills["整理"]
    assert s.requires == ["download_path"]
    assert s.steps and s.steps[0].tool == "run_shell_tool"


def test_hot_reload(tmp_path):
    _write_skill(tmp_path, "整理.yaml", {"description": "v1", "steps": [{"tool": "get_datetime"}]})
    loader = SkillLoader(tmp_path)
    loader.load_all()
    _write_skill(tmp_path, "整理.yaml", {"description": "v2 改了", "steps": [{"tool": "get_datetime"}]})
    # 强制改 mtime，保证触发重载
    os.utime(tmp_path / "整理.yaml", (time.time() + 2, time.time() + 2))
    skills = loader.reload_if_changed()
    assert skills["整理"].description == "v2 改了"


def test_remove_skill(tmp_path):
    _write_skill(tmp_path, "整理.yaml", {"description": "x", "steps": []})
    loader = SkillLoader(tmp_path)
    loader.load_all()
    (tmp_path / "整理.yaml").unlink()
    skills = loader.reload_if_changed()
    assert "整理" not in skills
