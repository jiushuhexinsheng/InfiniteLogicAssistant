# -*- coding: utf-8 -*-
"""detection 域测试 — 配置校验 + 聚合。
Detection domain tests — configuration validation and aggregation.
"""
import pytest

from core import config as config_mod
from core.detection import run_all
from core.detection.validator import validate


def test_validator_ok_for_defaults():
    """验证默认配置通过校验。Verifies the default configuration passes validation."""
    health = validate(config_mod.Settings())
    assert health.ok is True


def test_validator_non_localhost_requires_token():
    """验证非 localhost 且无 token 时校验失败。Verifies validation fails for a non-localhost host without a token."""
    health = validate(config_mod.Settings(server=config_mod.ServerSection(host="0.0.0.0", api_token="")))
    assert health.ok is False
    assert any(i.key == "server.api_token" for i in health.issues)


def test_validator_token_satisfies():
    """验证非 localhost 配置 token 后校验通过。Verifies validation passes for a non-localhost host once a token is set."""
    health = validate(config_mod.Settings(server=config_mod.ServerSection(host="0.0.0.0", api_token="x")))
    assert health.ok is True


@pytest.mark.asyncio
async def test_run_all_returns_aggregate(monkeypatch):
    """验证 run_all 返回 environment/config/connectivity 聚合报告。Verifies run_all returns the aggregated environment, config, and connectivity report."""
    monkeypatch.setattr(config_mod, "get_settings", lambda: config_mod.Settings())
    report = await run_all()
    assert set(report) == {"environment", "config", "connectivity"}
    assert len(report["connectivity"]) == 3
    # 未配置 → 全部 skip，不发真实网络
    assert all(c["status"] == "skip" for c in report["connectivity"])
