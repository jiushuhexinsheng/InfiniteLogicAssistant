# -*- coding: utf-8 -*-
"""该模块测试 core.detection.environment 的环境探测与 environment.md 生成。
Tests the environment probing and environment.md generation in core.detection.environment.
"""
import pytest

from core.detection.environment import probe, write_environment_md


@pytest.mark.asyncio
async def test_probe_collects_expected_keys(tmp_path):
    """验证 probe 返回 os/hostname/arch/cpu 等预期字段。Verifies probe returns the expected fields such as os, hostname, arch, and cpu."""
    data = await probe()
    for k in ("os", "hostname", "arch", "cpu", "memory_gb", "path", "shell", "python"):
        assert k in data and data[k]


@pytest.mark.asyncio
async def test_write_environment_md_creates_file(tmp_path):
    """验证 write_environment_md 生成包含系统信息的 Markdown 文件。Verifies write_environment_md creates a Markdown file containing the system information."""
    md = await write_environment_md({"os": "Windows 11", "path": "C:\\x"}, tmp_path / "environment.md")
    text = md.read_text(encoding="utf-8")
    assert "## 系统" in text and "Windows 11" in text
