# -*- coding: utf-8 -*-
"""原子写：成功替换且无临时文件残留；失败保留旧内容并清理临时文件。

Atomic write: a successful replace leaves no temp file; a failed replace keeps the
old content and cleans up the temp file.
"""
import pytest

import core.atomic_io as atomic_mod
from core.atomic_io import atomic_write_text


def test_atomic_write_replaces_and_cleans(tmp_path):
    """写入成功后内容完整、无 .tmp 残留。"""
    target = tmp_path / "config.yaml"
    target.write_text("old", encoding="utf-8")

    atomic_write_text(target, "new\n")

    assert target.read_text(encoding="utf-8") == "new\n"
    assert not list(tmp_path.glob(".*.tmp"))


def test_atomic_write_failure_keeps_old(tmp_path, monkeypatch):
    """os.replace 失败时目标保持旧内容，临时文件被清理。"""
    target = tmp_path / "config.yaml"
    target.write_text("old", encoding="utf-8")

    def boom(_src, _dst):
        raise OSError("replace failed")

    monkeypatch.setattr(atomic_mod.os, "replace", boom)
    with pytest.raises(OSError):
        atomic_write_text(target, "new\n")

    assert target.read_text(encoding="utf-8") == "old"
    assert not list(tmp_path.glob(".*.tmp"))
