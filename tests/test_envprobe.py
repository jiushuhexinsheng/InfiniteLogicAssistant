# -*- coding: utf-8 -*-
import pytest

from core.execution.envprobe import probe, write_environment_md


@pytest.mark.asyncio
async def test_probe_collects_expected_keys(tmp_path):
    data = await probe()
    for k in ("os", "hostname", "arch", "cpu", "memory_gb", "path", "shell", "python"):
        assert k in data and data[k]


@pytest.mark.asyncio
async def test_write_environment_md_creates_file(tmp_path):
    md = await write_environment_md({"os": "Windows 11", "path": "C:\\x"}, tmp_path / "environment.md")
    text = md.read_text(encoding="utf-8")
    assert "## 系统" in text and "Windows 11" in text
