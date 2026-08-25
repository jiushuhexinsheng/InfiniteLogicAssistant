# -*- coding: utf-8 -*-
"""detection 域测试 — 配置校验 + 聚合"""
import pytest

from core import config as config_mod
from core.detection import run_all
from core.detection.validator import validate


def test_validator_ok_for_defaults():
    health = validate(config_mod.Settings())
    assert health.ok is True


def test_validator_non_localhost_requires_token():
    health = validate(config_mod.Settings(server=config_mod.ServerSection(host="0.0.0.0", api_token="")))
    assert health.ok is False
    assert any(i.key == "server.api_token" for i in health.issues)


def test_validator_token_satisfies():
    health = validate(config_mod.Settings(server=config_mod.ServerSection(host="0.0.0.0", api_token="x")))
    assert health.ok is True


@pytest.mark.asyncio
async def test_run_all_returns_aggregate(monkeypatch):
    monkeypatch.setattr(config_mod, "get_settings", lambda: config_mod.Settings())
    report = await run_all()
    assert set(report) == {"environment", "config", "connectivity"}
    assert len(report["connectivity"]) == 3
    # 未配置 → 全部 skip，不发真实网络
    assert all(c["status"] == "skip" for c in report["connectivity"])
