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


# ─── permissions：规则 match 必须命中已注册工具 ───


def test_validator_warns_on_unmatched_permission_rule():
    """规则 match 匹配不到任何已注册工具 → warning。

    match 拼错会被静默忽略（既不报错也不生效），用户会以为策略已生效。
    A rule whose match hits no registered tool produces a warning: a typo is otherwise
    silently ignored and the user believes the policy took effect.
    """
    from core.config import Settings
    from core.detection.validator import validate
    s = Settings(permissions={"rules": [{"match": "no_such_tool_*", "action": "deny"}]})
    health = validate(s)
    assert any(i.level == "warning" and "no_such_tool_*" in i.message for i in health.issues)


def test_validator_silent_on_matching_permission_rule():
    """能命中的规则不报警。A rule that matches something produces no warning."""
    from core.config import Settings
    from core.detection.validator import validate
    s = Settings(permissions={"rules": [{"match": "read_*", "action": "allow"}]})
    health = validate(s)
    assert not any("read_*" in i.message for i in health.issues)


def test_validator_silent_when_no_rules():
    """空规则列表是完全合法的配置，不应报警。An empty rule list is a perfectly valid config and warns about nothing."""
    from core.config import Settings
    from core.detection.validator import validate
    health = validate(Settings())
    assert not any("permissions" in i.key for i in health.issues)
