# -*- coding: utf-8 -*-
"""工具权限策略求值（decide）的测试。
Tests for tool permission policy evaluation (decide).
"""
from types import SimpleNamespace

from core.tools.policy import decide


def _section(default="ask", read="allow", write="ask", exec_="ask", rules=()):
    """构造一个等价的权限段替身（避免依赖 schema 的具体类型）。
    Build an equivalent permissions-section stand-in (avoiding a dependency on the schema types).
    """
    return SimpleNamespace(
        default_action=default,
        tiers=SimpleNamespace(read=read, write=write, **{"exec": exec_}),
        rules=[SimpleNamespace(match=m, action=a) for m, a in rules],
    )


# ─── 默认值必须等价于改造前的行为（关键迁移属性）───

def test_defaults_match_prior_behaviour():
    """默认配置下：read 免询问、write/exec 询问 —— 与改造前完全一致。
    Under defaults: read is auto-allowed, write/exec ask — identical to before the change."""
    s = _section()
    assert decide("read_file", s).action == "allow"      # read 级
    assert decide("write_file", s).action == "ask"       # write 级
    assert decide("run_shell_tool", s).action == "ask"   # exec 级


def test_defaults_source_is_tier():
    """默认命中来自 tier，而非规则。The default hit comes from a tier, not a rule."""
    assert decide("read_file", _section()).source == "tier:read"


# ─── tier 与 default ───

def test_tier_override():
    """改 tier 立即改变该层的行为。Overriding a tier changes that level's behaviour."""
    s = _section(read="deny", exec_="allow")
    assert decide("read_file", s).action == "deny"
    assert decide("run_shell_tool", s).action == "allow"


def test_default_action_used_when_no_tier():
    """tiers 中查不到对应风险层级时用 default_action。
    default_action is used when the risk level has no tier entry."""
    s = SimpleNamespace(default_action="deny", tiers=SimpleNamespace(), rules=[])
    d = decide("read_file", s)
    assert d.action == "deny"
    assert d.source == "default"


# ─── 规则：优先级与 deny 单调 ───

def test_rule_overrides_tier():
    """规则优先于 tier。A rule takes precedence over a tier."""
    s = _section(rules=[("run_shell_tool", "allow")])
    d = decide("run_shell_tool", s)
    assert d.action == "allow"
    assert d.source == "rule:run_shell_tool"


def test_glob_rule_matches():
    """glob 规则命中同前缀的多个工具。A glob rule matches every tool sharing the prefix."""
    s = _section(rules=[("run_*", "allow")])
    assert decide("run_shell_tool", s).action == "allow"
    assert decide("run_python_tool", s).action == "allow"
    assert decide("run_shell_tool", s).source == "rule:run_*"
    # 不匹配的工具仍走 tier
    assert decide("read_file", s).source == "tier:read"


def test_first_matching_rule_wins():
    """多条规则命中时取第一条。The first matching rule wins."""
    s = _section(rules=[("read_file", "deny"), ("read_*", "allow")])
    assert decide("read_file", s).action == "deny"


def test_deny_rule_short_circuits_even_if_listed_last():
    """deny 单调：即使排在最后也短路，不能被前面的 allow 规则翻案。
    deny is monotonic: it short-circuits even when listed last, and cannot be overridden
    by an earlier allow rule."""
    s = _section(rules=[("read_*", "allow"), ("read_file", "deny")])
    d = decide("read_file", s)
    assert d.action == "deny"
    assert d.source == "rule:read_file"


# ─── 未注册工具：纵深防御 ───

def test_unregistered_tool_denied():
    """未注册的工具名一律拒绝 —— 必须先于 tier 判定，否则 risk() 的 "read" 会提前放行。
    An unregistered tool name is always denied; this must precede the tier lookup, or
    risk()'s "read" default would allow it early."""
    d = decide("no_such_tool", _section())
    assert d.action == "deny"
    assert d.source == "unknown"


def test_unregistered_tool_denied_despite_allow_rule():
    """未注册名的 deny 也不能被 allow 规则覆盖（它先于规则判定）。
    The unknown-name denial is not overridable by an allow rule either (it precedes rule matching)."""
    s = _section(rules=[("*", "allow")])
    assert decide("no_such_tool", s).action == "deny"
