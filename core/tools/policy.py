# -*- coding: utf-8 -*-
"""工具权限策略 — 决定一次工具调用该放行、询问还是拒绝。

求值顺序（deny 单调，不可被后续规则翻案）：
1. 工具未注册 → deny（**必须先于 tier 判定**：TOOLS.risk 对未知名返回 "read"，
   若放到后面会被 tiers["read"] 提前放行）
2. 扫描全部规则，任一条匹配且为 deny → 立即 deny
3. 否则取第一条匹配规则的 action
4. 否则 tiers[TOOLS.risk(name)]
5. 否则 default_action

Tool permission policy — decides whether a tool call is allowed, asked about, or
denied. Evaluation order (deny is monotonic and cannot be overridden):
1. unregistered tool → deny (this MUST precede the tier lookup: TOOLS.risk returns
   "read" for unknown names, so tiers["read"] would otherwise allow it early)
2. any matching deny rule → deny outright
3. otherwise the first matching rule
4. otherwise tiers[TOOLS.risk(name)]
5. otherwise default_action
"""
import fnmatch
from dataclasses import dataclass
from typing import Any

from core.tools.base import TOOLS  # 从 base 导入，避免 core.tools.__init__ 循环


@dataclass(frozen=True)
class Decision:
    """一次工具调用的权限判定结果。

    action 为 allow / ask / deny；source 说明依据，形如 "rule:run_*" / "tier:exec" /
    "default" / "unknown"，供审计与设置页展示。

    The outcome of a permission evaluation. action is allow / ask / deny; source
    explains why (e.g. "rule:run_*" / "tier:exec" / "default" / "unknown"), for audit
    and for display in the settings page.
    """

    action: str
    source: str


def _get_section(section: Any | None) -> Any:
    """取得权限配置段；未显式传入时取全局 settings.permissions。

    Get the permissions section; falls back to global settings.permissions.

    Args:
        section: 显式传入的权限段，或 None。An explicitly supplied section, or None.

    Returns:
        权限配置段。The permissions section.
    """
    if section is not None:
        return section
    from core import config  # 延迟导入：避免模块导入期即绑定全局单例

    return config.settings.permissions


def decide(name: str, section: Any | None = None) -> Decision:
    """判定工具调用该放行、询问还是拒绝。

    Decide whether a tool call is allowed, asked about, or denied.

    Args:
        name: 工具名。Tool name.
        section: 权限配置段；缺省取全局 settings.permissions。The permissions section; defaults to global settings.permissions.

    Returns:
        判定结果。The decision.
    """
    # 1. 未注册工具 —— 纵深防御，且必须在 tier 之前（否则 risk() 的 "read" 会提前放行）
    #    Unregistered tool — defence-in-depth, and it must precede the tier lookup.
    if not TOOLS.has(name):
        return Decision("deny", "unknown")

    sec = _get_section(section)
    rules = list(getattr(sec, "rules", None) or [])

    # 2. deny 单调：任一条匹配的 deny 规则直接短路，不可被其它规则翻案
    #    Monotonic deny: any matching deny rule short-circuits and cannot be overridden.
    for rule in rules:
        if rule.action == "deny" and fnmatch.fnmatchcase(name, rule.match):
            return Decision("deny", f"rule:{rule.match}")

    # 3. 第一条匹配的规则
    #    The first matching rule.
    for rule in rules:
        if fnmatch.fnmatchcase(name, rule.match):
            return Decision(rule.action, f"rule:{rule.match}")

    # 4. 该工具风险层级对应的默认动作
    #    The default action for the tool's risk tier.
    tiers = getattr(sec, "tiers", None)
    risk = TOOLS.risk(name)
    tier_action = getattr(tiers, risk, None) if tiers is not None else None
    if tier_action:
        return Decision(tier_action, f"tier:{risk}")

    # 5. 兜底
    #    Fallback.
    return Decision(getattr(sec, "default_action", "allow"), "default")


def decide_tier(risk: str, section: Any | None = None) -> Decision:
    """按**风险层级**判定 —— 供任务级确认使用（那里没有具体工具名，只有一个 risk）。

    与 `decide` 共用同一份 `permissions` 配置，这样「默认放行」是一个开关同时管住两级确认；
    否则把工具级放宽了、任务级照样拦，用户仍会被问。

    任务级没有工具名，故不适用「未注册工具 → deny」与「规则匹配」两步 —— 规则是按工具名
    glob 匹配的。想按任务收紧时，直接调 `permissions.tiers`。

    Judge by **risk tier**, for the task-level gate (which has a risk but no tool name). It shares
    the same `permissions` section as `decide`, so "allow by default" is one switch covering both
    gates — otherwise the tool level could be relaxed while the task level kept blocking. With no
    tool name, the "unregistered tool → deny" and rule-matching steps do not apply (rules glob
    against tool names); tighten the task level via `permissions.tiers`.

    Args:
        risk: 风险层级（read / write / exec）。The risk tier.
        section: 权限配置段；缺省取全局 settings.permissions。The permissions section; defaults
            to global settings.permissions.

    Returns:
        判定结果。The decision.
    """
    sec = _get_section(section)
    tiers = getattr(sec, "tiers", None)
    tier_action = getattr(tiers, risk, None) if tiers is not None else None
    if tier_action:
        return Decision(tier_action, f"tier:{risk}")
    return Decision(getattr(sec, "default_action", "allow"), "default")
