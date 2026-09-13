# -*- coding: utf-8 -*-
"""工具权限策略求值（decide）的测试。
Tests for tool permission policy evaluation (decide).
"""
from types import SimpleNamespace

from core.tools.policy import decide, decide_tier


def _section(default="ask", read="allow", write="ask", exec_="ask", rules=()):
    """构造一个等价的权限段替身（避免依赖 schema 的具体类型）。
    Build an equivalent permissions-section stand-in (avoiding a dependency on the schema types).

    注意：默认参数**故意**保持「read 放行 / write+exec 询问」，用来测求值顺序本身；
    真实 schema 的默认值另由 `test_schema_defaults_allow_everything` 覆盖。
    Note: the defaults deliberately keep "read allowed / write+exec ask" to exercise the
    evaluation order itself; the real schema defaults are covered separately by
    `test_schema_defaults_allow_everything`.
    """
    return SimpleNamespace(
        default_action=default,
        tiers=SimpleNamespace(read=read, write=write, **{"exec": exec_}),
        rules=[SimpleNamespace(match=m, action=a) for m, a in rules],
    )


# ─── 仓库默认值：三档全放行（用户选定，2026-09-13）───

def test_schema_defaults_allow_everything():
    """仓库默认配置是**三档全放行**、兜底也放行。

    这条测的是真实 schema 默认值（上面 `_section()` 是显式构造的替身，与它无关）。
    2026-09-13 按用户要求把默认从「read 放行 / write+exec 询问」改为全放行：无沙箱环境下
    这道确认是任意命令执行的唯一闸门，改成放行等于**接受这个闸门默认不生效**；仍可通过
    `permissions.rules` 里的 deny/ask 规则或设置页收紧。

    The repository default is **allow on all three tiers**, fallback included. This asserts the
    real schema defaults (`_section()` above is an explicitly built stand-in and unrelated).
    Changed on 2026-09-13 at the user's request from "read allowed / write+exec ask" to
    allow-everything: with no sandbox this confirmation is the only gate before arbitrary
    command execution, so this default means **the gate is off by default** — it can still be
    tightened via deny/ask rules in `permissions.rules` or the settings page.
    """
    from core.config.schema import PermissionsSection

    p = PermissionsSection()
    assert (p.tiers.read, p.tiers.write, p.tiers.exec) == ("allow", "allow", "allow")
    assert p.default_action == "allow"
    assert p.rules == []


# ─── 求值顺序（用显式构造的 section，与上面默认值无关）───

def test_evaluation_order_by_tier():
    """按层级取默认动作：read 放行、write/exec 询问。
    Tier lookup: read allowed, write/exec asked."""
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


# ─── decide_tier：任务级确认用（没有具体工具名，只有风险层级）───

def test_decide_tier_follows_same_config():
    """任务级确认与工具级共用同一份配置 —— 否则「默认放行」只改一半，任务仍会被拦。
    The task-level gate reads the same config as the tool-level one; otherwise "allow by default"
    would only be half-applied and tasks would still be blocked."""
    assert decide_tier("read", _section()).action == "allow"
    assert decide_tier("write", _section()).action == "ask"
    assert decide_tier("exec", _section()).action == "ask"
    assert decide_tier("exec", _section()).source == "tier:exec"


def test_decide_tier_uses_default_action_when_tier_missing():
    """层级里查不到时用 default_action。Falls back to default_action when the tier is missing."""
    s = SimpleNamespace(default_action="deny", tiers=SimpleNamespace(), rules=[])
    assert decide_tier("exec", s) == decide_tier("exec", s)  # 稳定
    assert decide_tier("exec", s).action == "deny"
    assert decide_tier("exec", s).source == "default"


def test_decide_tier_allows_under_repo_defaults():
    """仓库默认值下，任务级确认对任何层级都放行。

    刻意传显式的 `PermissionsSection()` 而不是省略参数：省略会去读**本机 config.yaml**，
    测试结果就随开发者的本地配置变化（本文件其它用例都同样避免依赖环境）。

    Under the repository defaults every tier is allowed. An explicit `PermissionsSection()` is
    passed rather than omitting the argument, because omitting it reads the **local config.yaml**
    and the result would then vary with the developer's machine — the rest of this file avoids
    depending on the environment the same way.
    """
    from core.config.schema import PermissionsSection

    p = PermissionsSection()
    assert decide_tier("exec", p).action == "allow"
    assert decide_tier("write", p).action == "allow"
    assert decide_tier("read", p).action == "allow"
