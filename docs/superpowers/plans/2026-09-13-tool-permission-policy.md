# 工具权限策略层 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把硬编码的「按 `risk` 决定要不要问」换成可在设置页配置的 allow / ask / deny 策略层。

**Architecture:** 新增纯函数求值核心 `core/tools/policy.py`，按 `未注册→deny > 任一 deny 规则短路 > 首条匹配规则 > tier > default_action` 求值；新增 `permissions` 配置段；改造三个既有的 `TOOLS.risk()` 消费点（确认、并发分流、单工具端点）改为走策略。

**Tech Stack:** Python 3.14 / FastAPI / pydantic v2 / pytest / mypy；Vue 3.4 + TypeScript + Vite 5 / vue-tsc / Vitest 4。

**Spec:** `docs/superpowers/specs/2026-09-13-tool-permission-policy-design.md`

## Global Constraints

- Python 3.14+；后端沿用 `core/` 结构，**新增/修改的 docstring 必须中英双语**（`1d5e4db` 起的全库要求）。
- 前端注释同样中英双语。
- **默认值必须等价于改造前的行为**：`read→allow`、`write/exec→ask`、`default_action→ask`。既有用户无 `permissions` 段 → 行为不变。这是本次的关键迁移属性，必须有回归测试守住。
- **`TOOLS.risk()` 不改**：它仍供 executor 审计与 `TOOLS.meta()` 展示使用，策略层是叠加在其上。
- **接口变更必须与全部实现方同时落地**：本计划已按此原则合并了「schema 变更 + 类型重生成」（Task 2）。前几轮因此踩过三次，不要再拆。
- **必须重新生成 `web/src/api/generated.ts`**：`EditableSnapshot`（`core/api/schemas.py:456`）是显式 pydantic 模型且经 openapi 暴露，新增字段会改变 schema，CI 的 `gen:api` 同步门禁会校验。
- 后端验证：`python -m pytest tests/ -q` + `python -m mypy core/ server.py`。
- 前端验证：`cd web && npm test` + `cd web && npm run build`。
- TDD：先写失败测试 → 运行确认失败 → 最小实现 → 运行确认通过 → 提交。
- **测试中所有 `await queue.get()` 必须包 `asyncio.wait_for(..., timeout=1.0)`**：被依赖的函数若提前抛异常，事件永不入队会让测试永久挂起而不是失败（前几轮踩过）。

---

## 文件结构

| 文件 | 职责 | 动作 |
|---|---|---|
| `core/tools/policy.py` | 权限求值核心：`Decision` + `decide()` | Create |
| `core/config/schema.py` | 新增 `PermissionRule` / `PermissionTiers` / `PermissionsSection`；`Settings` 加字段 | Modify |
| `core/config/__init__.py` | 导出新模型 | Modify |
| `core/config/runtime.py` | `editable_snapshot()` 加 `permissions` | Modify |
| `core/api/schemas.py` | `PermissionsOut` 等 + `EditableSnapshot` 加 `permissions` | Modify |
| `core/orchestrator/confirm.py` | `confirm_tool` 走 policy；`_ask_operator` 加 `source`；`CONFIRM_OPTIONS` 文案 | Modify |
| `core/orchestrator/executor.py` | 并发分流改为按 policy | Modify |
| `core/api/tools.py` | `tools_call` 加 deny/ask/allow 三分支 | Modify |
| `core/detection/validator.py` | 校验规则 `match` 是否命中已注册工具 | Modify |
| `config.yaml.example` | 补 `permissions` 段示例 | Modify |
| `web/src/api/generated.ts` | 重新生成 | Modify |
| `web/src/components/console/settings/PermissionsCard.vue` | 权限设置卡 | Create |
| `web/src/components/console/settings/configDefs.ts` | `menuDefs` 加「权限」 | Modify |
| `web/src/components/console/ConsoleSettings.vue` | 挂载权限卡 | Modify |
| `tests/test_tools_policy.py` | 求值矩阵测试 | Create |

---

## Task 1: `policy.decide` 求值引擎

**Files:**
- Create: `core/tools/policy.py`
- Test: `tests/test_tools_policy.py`

**Interfaces:**
- Consumes: `core.config.schema.PermissionsSection`（Task 2 创建；本任务先在测试中用等价的最小构造）—— **注意**：为避免循环依赖，`policy.py` 用 `TYPE_CHECKING` 导入类型，运行时只做属性访问。
- Produces: `Decision(action: str, source: str)`（frozen dataclass）；`decide(name: str, section: Any | None = None) -> Decision`

- [ ] **Step 1: 写失败测试**

新建 `tests/test_tools_policy.py`：

```python
# -*- coding: utf-8 -*-
"""工具权限策略求值（decide）的测试。
Tests for tool permission policy evaluation (decide).
"""
from types import SimpleNamespace

import pytest

from core.tools.policy import Decision, decide


def _section(default="ask", read="allow", write="ask", exec_="ask", rules=()):
    """构造一个等价的权限段替身（避免依赖尚未存在的 schema 类）。
    Build an equivalent permissions-section stand-in (avoiding a dependency on the not-yet-existing schema class)."""
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
    d = decide("read_file", _section())
    assert d.source == "tier:read"


# ─── tier 与 default ───

def test_tier_override():
    """改 tier 立即改变该层的行为。Overriding a tier changes that level's behaviour."""
    s = _section(read="deny", exec_="allow")
    assert decide("read_file", s).action == "deny"
    assert decide("run_shell_tool", s).action == "allow"


def test_default_action_used_for_unmatched():
    """未命中任何规则也不在 tier 覆盖内时用 default_action。An unmatched tool falls back to default_action."""
    s = _section(default="deny")
    # read 有 tier 覆盖，故仍按 tier；构造一个 tier 缺失的场景用规则命中不到的工具
    d = decide("read_file", SimpleNamespace(default_action="deny", tiers=SimpleNamespace(), rules=[]))
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
    assert decide("read_file", s).action == "allow"  # 走 tier，非规则
    assert decide("run_shell_tool", s).source == "rule:run_*"


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
```

- [ ] **Step 2: 运行确认失败**

Run: `python -m pytest tests/test_tools_policy.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'core.tools.policy'`

- [ ] **Step 3: 实现**

新建 `core/tools/policy.py`：

```python
# -*- coding: utf-8 -*-
"""工具权限策略 — 决定一次工具调用该放行、询问还是拒绝。

求值顺序（deny 单调，不可被后续规则翻案）：
1. 工具未注册 → deny（必须先于 tier 判定：TOOLS.risk 对未知名返回 "read"，
   若放到后面会被 tiers["read"] 提前放行）
2. 扫描全部规则，任一条匹配且为 deny → 立即 deny
3. 否则取第一条匹配规则的 action
4. 否则 tiers[TOOLS.risk(name)]
5. 否则 default_action

Tool permission policy — decides whether a tool call is allowed, asked about, or
denied. Evaluation order (deny is monotonic and cannot be overridden):
1. unregistered tool → deny (must precede the tier lookup: TOOLS.risk returns "read"
   for unknown names, so tiers["read"] would otherwise allow it early)
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


def _section(section: Any | None) -> Any:
    """取得权限配置段（缺省用全局 settings）。Get the permissions section (defaults to global settings)."""
    if section is not None:
        return section
    from core import config  # 延迟导入，避免测试期即绑定全局单例

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

    sec = _section(section)
    rules = list(getattr(sec, "rules", []) or [])

    # 2. deny 单调：任一条匹配的 deny 规则直接短路
    #    Monotonic deny: any matching deny rule short-circuits.
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
    return Decision(getattr(sec, "default_action", "ask"), "default")
```

- [ ] **Step 4: 运行确认通过**

Run: `python -m pytest tests/test_tools_policy.py -q`
Expected: PASS（13 个用例）

- [ ] **Step 5: 提交**

```bash
git add core/tools/policy.py tests/test_tools_policy.py
git commit -m "feat(权限): 工具权限求值核心 policy.decide

求值顺序：未注册→deny > 任一 deny 规则短路 > 首条匹配规则 > tier > default。
未注册名的 deny 刻意放在 tier 之前 —— TOOLS.risk 对未知名返回 read，
放到后面会被 tiers[\"read\"] 提前放行。"
```

---

## Task 2: `permissions` 配置段 + API schema + 类型重生成

> **本任务把「schema 变更」与「前端类型重生成」绑在一起**：`EditableSnapshot` 是显式
> pydantic 模型，新增字段即改变 openapi，CI 的 `gen:api` 同步门禁会校验 —— 分两个
> commit 会让中间那个的 CI 变红。

**Files:**
- Modify: `core/config/schema.py`（`ToolsSection` 之后插入新模型；`Settings` 加字段）
- Modify: `core/config/__init__.py`（导入 + `__all__`）
- Modify: `core/config/runtime.py`（`editable_snapshot()` 加 `permissions`）
- Modify: `core/api/schemas.py`（新增 `PermissionsOut` 等；`EditableSnapshot` 加字段）
- Modify: `config.yaml.example`（补示例段）
- Modify: `web/src/api/generated.ts`（重新生成）
- Test: `tests/test_config.py`

**Interfaces:**
- Consumes: 无
- Produces: `PermissionRule(match: str, action: str)`、`PermissionTiers(read/write/exec: str)`、`PermissionsSection(default_action: str, tiers: PermissionTiers, rules: list[PermissionRule])`；快照键 `editable["permissions"]`

- [ ] **Step 1: 写失败测试**

在 `tests/test_config.py` 追加：

```python
def test_permissions_section_defaults_match_prior_behaviour():
    """权限段缺省时等价于改造前的行为：read 免询问、write/exec 询问。
    The permissions section defaults to the pre-change behaviour: read auto-allowed,
    write/exec asked."""
    s = Settings()
    assert s.permissions.default_action == "ask"
    assert s.permissions.tiers.read == "allow"
    assert s.permissions.tiers.write == "ask"
    assert s.permissions.tiers.exec == "ask"
    assert s.permissions.rules == []


def test_permissions_section_rejects_invalid_action():
    """非法动作被 pydantic 拒绝（配置写错启动即报错）。An invalid action is rejected by pydantic (a bad config fails at startup)."""
    import pytest as _pytest
    from pydantic import ValidationError
    with _pytest.raises(ValidationError):
        Settings(permissions={"tiers": {"read": "maybe"}})


def test_permissions_snapshot_exposed():
    """可编辑快照必须暴露 permissions —— 否则前端设置页拿不到。
    The editable snapshot must expose permissions, or the settings page cannot read it."""
    from core.config.runtime import editable_snapshot
    snap = editable_snapshot()
    assert "permissions" in snap
    assert snap["permissions"]["tiers"]["read"] == "allow"
```

（`tests/test_config.py` 顶部应已有 `from core.config import Settings`；若名字不同按该文件现有风格对齐。）

- [ ] **Step 2: 运行确认失败**

Run: `python -m pytest tests/test_config.py -q -k permissions`
Expected: FAIL — `AttributeError: 'Settings' object has no attribute 'permissions'`

- [ ] **Step 3: 实现**

`core/config/schema.py` —— 在 `ToolsSection` 之后插入：

```python
class PermissionRule(BaseModel):
    """一条权限规则：match 为工具名或 glob（fnmatch 语义，大小写敏感）。

    A permission rule: match is a tool name or a glob (fnmatch semantics, case-sensitive).
    """

    model_config = ConfigDict(extra="forbid")

    match: str
    action: Literal["allow", "ask", "deny"]


class PermissionTiers(BaseModel):
    """按工具风险层级设的默认动作。Per-tier default action, keyed by tool risk."""

    model_config = ConfigDict(extra="forbid")

    read: Literal["allow", "ask", "deny"] = "allow"
    write: Literal["allow", "ask", "deny"] = "ask"
    exec: Literal["allow", "ask", "deny"] = "ask"


class PermissionsSection(BaseModel):
    """工具权限策略：层级默认 + 规则覆盖。默认值等价于「read 免询问、write/exec 询问」。

    Tool permission policy: per-tier defaults plus rule overrides. The defaults match
    "read is auto-allowed, write/exec are asked".
    """

    model_config = ConfigDict(extra="forbid")

    default_action: Literal["allow", "ask", "deny"] = "ask"
    tiers: PermissionTiers = Field(default_factory=lambda: PermissionTiers())
    rules: list[PermissionRule] = Field(default_factory=list)
```

确认 `schema.py` 顶部已导入 `Literal`（若没有则加 `from typing import Literal`）。

`Settings` 增字段（放在 `tools` 之后）：

```python
    permissions: PermissionsSection = Field(default_factory=lambda: PermissionsSection())
```

`core/config/__init__.py` —— schema 的导入行加 `PermissionRule, PermissionsSection, PermissionTiers`；`__all__` 的 schema 分组加 `"PermissionRule", "PermissionsSection", "PermissionTiers"`。

`core/config/runtime.py` —— `editable_snapshot()` 的返回字典加：

```python
        "permissions": s.permissions.model_dump(),
```

`core/api/schemas.py` —— 在 `EditableSnapshot` 之前新增，并给 `EditableSnapshot` 加字段：

```python
class PermissionRuleOut(BaseModel):
    """权限规则（前端展示与编辑用）。A permission rule (for front-end display and editing)."""

    match: str
    action: str


class PermissionTiersOut(BaseModel):
    """各风险层级的默认动作。The default action per risk tier."""

    read: str
    write: str
    exec: str


class PermissionsOut(BaseModel):
    """工具权限策略快照。Tool permission policy snapshot."""

    default_action: str
    tiers: PermissionTiersOut
    rules: list[PermissionRuleOut]
```

```python
    permissions: PermissionsOut
```

`config.yaml.example` —— 追加（放在 `tools:` 段之后）：

```yaml
# 工具权限策略：工具调用是否需要操作者确认
#   allow 直接执行 / ask 询问操作者 / deny 拒绝执行
# 求值顺序：未注册工具→拒绝 > 任一 deny 规则短路 > 首条匹配规则 > 层级默认 > default_action
# Tool permission policy: whether a tool call needs operator confirmation.
#   allow runs directly / ask prompts / deny refuses.
# Order: unregistered→deny > any deny rule > first matching rule > tier > default_action.
permissions:
  default_action: ask          # 未命中任何规则时的兜底
  tiers:
    read: allow                # 只读工具免询问（与改造前行为一致）
    write: ask
    exec: ask
  rules: []                    # 形如 - {match: "web_search", action: allow}
```

- [ ] **Step 4: 运行确认通过 + 重新生成前端类型**

Run: `python -m pytest tests/test_config.py -q -k permissions && python -m mypy core/ server.py`
Expected: PASS，mypy 无问题

Run:
```bash
cd web && PYTHONIOENCODING=utf-8 python ../scripts/gen_openapi.py && npx --yes openapi-typescript@7.13.0 src/api/openapi.json -o src/api/generated.ts
cd .. && git diff --stat web/src/api/generated.ts
```
Expected: `generated.ts` 出现 `permissions` 相关类型（diff 非空）

- [ ] **Step 5: 全量回归 + 提交**

Run: `python -m pytest tests/ -q && cd web && npm test && npm run build`
Expected: 全部通过（`vue-tsc` 通过 —— `EditableSnapshot` 新增必填字段后，前端若有构造该类型的地方会报错；若报错，按报错点补 `permissions` 字段）

```bash
git add core/config core/api/schemas.py config.yaml.example tests/test_config.py web/src/api/generated.ts
git commit -m "feat(配置): 新增 permissions 段（工具权限策略）+ 同步 API 类型

默认值刻意等价于改造前的行为：read 免询问、write/exec 询问、default=ask，
既有用户无该段时行为不变。

EditableSnapshot 是显式 pydantic 模型且经 openapi 暴露，新增 permissions
字段会改变 schema，故 generated.ts 必须同步重新生成（CI 的 gen:api 门禁
会校验）—— 与 schema 变更同一个 commit 落地。"
```

---

## Task 3: 确认消费点走 policy（含弹窗文案）

**Files:**
- Modify: `core/orchestrator/confirm.py`
- Test: `tests/test_orchestrator_confirm.py`

**Interfaces:**
- Consumes: Task 1 的 `decide(name, section=None) -> Decision`；Task 2 的 `PermissionsSection`
- Produces: `confirm_tool` 按 policy 三分支；`_ask_operator(session, plan, risk, kind, source="")`；`CONFIRM_OPTIONS` 文案改为「允许本次 / 拒绝」（value 不变）

- [ ] **Step 1: 写失败测试**

在 `tests/test_orchestrator_confirm.py` 追加（本任务直接 monkeypatch `decide`，
不构造真实权限段 —— 求值逻辑的覆盖在 `tests/test_tools_policy.py`，此处只验消费点）：

```python
@pytest.mark.asyncio
async def test_confirm_allowed_tool_skips_asking(monkeypatch):
    """策略 allow 的工具直接放行，不提问。A policy-allowed tool passes without asking."""
    from core.orchestrator import confirm as confirm_mod
    monkeypatch.setattr(confirm_mod, "decide", lambda name, section=None: _allow())
    s = Session()
    s.channel = _Channel([])          # 没有可用的答案 → 一旦提问就会 IndexError
    assert await confirm_tool(s, "run_shell_tool", {"command": "x"}) is True
    assert s.channel.notified == []   # 没有发起任何询问


@pytest.mark.asyncio
async def test_confirm_denied_tool_refused_without_asking(monkeypatch):
    """策略 deny 的工具直接拒绝，不提问。A policy-denied tool is refused without asking."""
    from core.orchestrator import confirm as confirm_mod
    monkeypatch.setattr(confirm_mod, "decide", lambda name, section=None: _deny())
    s = Session()
    s.channel = _Channel([])
    assert await confirm_tool(s, "run_shell_tool", {"command": "x"}) is False
    assert s.channel.notified == []


@pytest.mark.asyncio
async def test_confirm_ask_tool_still_asks(monkeypatch):
    """策略 ask 的工具照旧提问（回归：默认行为不变）。A policy-ask tool still prompts (regression: default behaviour unchanged)."""
    s = Session()
    s.channel = _Channel([Answer(choice="yes")])
    assert await confirm_tool(s, "write_file", {"path": "x", "content": "y"}) is True
    assert "需要确认" in s.channel.notified[0]


def test_confirm_options_labels_changed_but_values_unchanged():
    """弹窗文案改为「允许本次 / 拒绝」，但 value 保持 yes/no —— 判定逻辑与既有用例不受影响。"""
    from core.orchestrator.confirm import CONFIRM_OPTIONS
    assert CONFIRM_OPTIONS == [
        {"value": "yes", "label": "允许本次"},
        {"value": "no", "label": "拒绝"},
    ]
```

在文件顶部补两个小助手：

```python
def _allow():
    from core.tools.policy import Decision
    return Decision("allow", "rule:test")


def _deny():
    from core.tools.policy import Decision
    return Decision("deny", "rule:test")
```

- [ ] **Step 2: 运行确认失败**

Run: `python -m pytest tests/test_orchestrator_confirm.py -q`
Expected: FAIL — `confirm_tool` 未走 policy（allow 场景仍会提问 → `IndexError`）；文案断言失败

- [ ] **Step 3: 实现**

`core/orchestrator/confirm.py` —— 导入加：

```python
from core.tools.policy import decide
```

`CONFIRM_OPTIONS` 改为：

```python
CONFIRM_OPTIONS = [
    {"value": "yes", "label": "允许本次"},
    {"value": "no", "label": "拒绝"},
]
```

`_ask_operator` 增可选 `source` 形参并写进审计：

```python
async def _ask_operator(session: Session, plan: str, risk: str, kind: str, source: str = "") -> bool:
```

并在该函数末尾的三条 `audit(...)` 调用各追加 ` source={source}`（保持既有字段顺序不变，只在末尾追加）。

`confirm_tool` 改为：

```python
async def confirm_tool(session: Session, name: str, args: dict) -> bool:
    """工具级确认：由权限策略决定放行 / 询问 / 拒绝。

    Tool-level confirmation: the permission policy decides allow / ask / deny.
    """
    decision = decide(name)
    if decision.action == "allow":
        return True
    if decision.action == "deny":
        audit(f"tools policy denied name={name} source={decision.source}")
        return False
    plan = f"调用工具 {name}，参数 {json.dumps(args, ensure_ascii=False)}"
    return await _ask_operator(session, plan, TOOLS.risk(name), "tool", source=decision.source)
```

- [ ] **Step 4: 运行确认通过 + 全量后端回归**

Run: `python -m pytest tests/test_orchestrator_confirm.py -q && python -m pytest tests/ -q && python -m mypy core/ server.py`
Expected: 全部通过。

> **实施修正（2026-09-13）**：原计划漏了一处 —— 既有用例
> `test_confirm_asks_as_choice_with_two_options` **断言的是 `CONFIRM_OPTIONS` 的 label
> 文案**（`{"value":"yes","label":"确认"}`），故改文案后它会失败，需一并更新为
> 「允许本次 / 拒绝」。其余确认用例断言的是 `value` 或 `Answer`，不受影响。

- [ ] **Step 5: 提交**

```bash
git add core/orchestrator/confirm.py tests/test_orchestrator_confirm.py
git commit -m "feat(确认): 确认判定改由权限策略决定

confirm_tool 走 policy.decide：allow 直放 / ask 询问 / deny 拒绝。
_ask_operator 增 source 形参（仅审计），日志可回答「依据来自哪条规则或层级」。

弹窗文案改为「允许本次 / 拒绝」，value 保持 yes/no —— 因为不做
allow-always，文案需表达「这次而已」；值不变使得 _resolve_confirm
与全部既有回归用例不受影响。"
```

---

## Task 4: executor 并发分流改按 policy

**Files:**
- Modify: `core/orchestrator/executor.py:143-144`
- Test: `tests/test_orchestrator_executor.py`

**Interfaces:**
- Consumes: Task 1 的 `decide()`
- Produces: 无新接口

- [ ] **Step 1: 写失败测试**

在 `tests/test_orchestrator_executor.py` 追加：

```python
@pytest.mark.asyncio
async def test_auto_allowed_tools_run_concurrently(monkeypatch):
    """被策略 allow 的工具（含 write 级）并发执行，不再逐个确认。
    Policy-allowed tools (including write-level ones) run concurrently without prompting."""
    import asyncio
    import core.orchestrator.executor as ex
    from core.tools.policy import Decision

    # 两个 write 级工具都被 allow → 应并发，且通道不被询问
    monkeypatch.setattr(ex, "decide", lambda name, section=None: Decision("allow", "rule:test"))
    started: list[str] = []

    # 用在飞计数判定并发，而非墙钟耗时 —— 耗时阈值在负载下会 flaky。
    # Detect concurrency via an in-flight counter rather than wall-clock time: a timing
    # threshold is flaky under load.
    inflight = 0
    max_inflight = 0

    async def fake_acall(name, args, cancel=None, session=None):
        nonlocal inflight, max_inflight
        started.append(name)
        inflight += 1
        max_inflight = max(max_inflight, inflight)
        await asyncio.sleep(0.05)
        inflight -= 1
        return "ok"

    monkeypatch.setattr(ex.TOOLS, "acall", fake_acall)

    msg = {
        "role": "assistant", "content": "",
        "tool_calls": [
            {"id": "c1", "type": "function",
             "function": {"name": "write_file", "arguments": json.dumps({"path": "a", "content": "1"})}},
            {"id": "c2", "type": "function",
             "function": {"name": "write_file", "arguments": json.dumps({"path": "b", "content": "2"})}},
        ],
    }
    fake = _FakeLLM([[{"type": "done", "message": msg}], [_done(content="完成")]])
    monkeypatch.setattr("core.orchestrator.executor.get_llm_client", lambda: fake)

    s = Session()
    s.channel = _Channel([])               # 一旦询问就会 IndexError
    r = await execute_task(Task("t", "写两个文件", risk="write"), s, CancellationToken())
    assert r["status"] == "done"
    assert len(started) == 2
    assert max_inflight == 2, "两个工具应同时在飞（并发），而非串行"
```

- [ ] **Step 2: 运行确认失败**

Run: `python -m pytest tests/test_orchestrator_executor.py -q -k concurrently`
Expected: FAIL — `AttributeError: module 'core.orchestrator.executor' has no attribute 'decide'`（或耗时超阈值）

- [ ] **Step 3: 实现**

`core/orchestrator/executor.py` —— 导入加：

```python
from core.tools.policy import decide
```

把分流段替换为：

```python
            # 免确认的工具并发执行；需确认的逐个串行（确认本身必须串行问）
            # Tools needing no confirmation run concurrently; those needing it run one at a
            # time (the confirmation itself must be asked serially).
            auto_idx = [i for i, tc in enumerate(tool_calls)
                        if decide(tc["function"]["name"]).action == "allow"]
            auto_set = set(auto_idx)
            ask_idx = [i for i in range(len(tool_calls)) if i not in auto_set]
            results: dict[int, tuple[dict, dict]] = {}
            if auto_idx:
                outs = await asyncio.gather(*(run_one_tc(tool_calls[i], step) for i in auto_idx))
                for i, o in zip(auto_idx, outs):
                    if o is not None:
                        results[i] = o
            for i in ask_idx:
                o = await run_one_tc(tool_calls[i], step)
                if o is not None:
                    results[i] = o
```

- [ ] **Step 4: 运行确认通过 + 全量后端回归**

Run: `python -m pytest tests/ -q && python -m mypy core/ server.py`
Expected: 全部通过（既有 `test_execute_read_tools_run_concurrently` 仍需绿 —— 默认 tiers 下 read 级为 allow，行为不变）

- [ ] **Step 5: 提交**

```bash
git add core/orchestrator/executor.py tests/test_orchestrator_executor.py
git commit -m "feat(执行): 并发分流改按权限策略

原先按 risk 分流（read 并发 / 其余串行，理由是「非 read 需逐个确认」）。
改为按「是否需要确认」：allow 的并发（含 write/exec），需确认的串行。

已接受的风险：两个被 allow 的写操作可能交错（默认 tiers 下 write/exec 为
ask，故仅显式 allow 的工具会并发）。"
```

---

## Task 5: `/api/tools/call` 走 policy（deny 不可被 confirm 覆盖）

**Files:**
- Modify: `core/api/tools.py`
- Test: `tests/test_server.py`

**Interfaces:**
- Consumes: Task 1 的 `decide()`
- Produces: `/api/tools/call` 对 deny 返 403；对 ask 且无 `confirm` 返 `needs_confirm`；allow 不再要求 `confirm`

- [ ] **Step 1: 写失败测试**

在 `tests/test_server.py` 追加：

```python
def test_tool_call_denied_by_policy_returns_403(client, monkeypatch):
    """策略 deny 的工具即使带 confirm: true 也拒绝 —— confirm 不能覆盖 deny。
    A policy-denied tool is refused even with confirm: true — confirm cannot override deny."""
    from core.api import tools as tools_api
    from core.tools.policy import Decision
    monkeypatch.setattr(tools_api, "decide", lambda name, section=None: Decision("deny", "rule:run_*"))
    r = client.post("/api/tools/call", json={"name": "run_shell_tool", "args": {"command": "echo hi"}, "confirm": True})
    assert r.status_code == 403
    assert "禁止" in r.json()["error"]


def test_tool_call_allowed_by_policy_needs_no_confirm(client, monkeypatch):
    """策略 allow 的工具无需 confirm 标记即可执行。
    A policy-allowed tool runs without the confirm flag."""
    from core.api import tools as tools_api
    from core.tools.policy import Decision
    monkeypatch.setattr(tools_api, "decide", lambda name, section=None: Decision("allow", "rule:test"))
    r = client.post("/api/tools/call", json={"name": "get_datetime", "args": {}})
    assert r.status_code == 200
    assert r.json()["ok"] is True


def test_tool_call_ask_without_confirm_returns_needs_confirm(client, monkeypatch):
    """策略 ask 且未带 confirm → 返回 needs_confirm 让前端弹窗。
    A policy-ask tool without confirm returns needs_confirm so the front end can prompt."""
    from core.api import tools as tools_api
    from core.tools.policy import Decision
    monkeypatch.setattr(tools_api, "decide", lambda name, section=None: Decision("ask", "tier:exec"))
    r = client.post("/api/tools/call", json={"name": "run_shell_tool", "args": {"command": "echo hi"}})
    assert r.status_code == 200
    assert r.json().get("needs_confirm") is True
```

- [ ] **Step 2: 运行确认失败**

Run: `python -m pytest tests/test_server.py -q -k "policy or needs_confirm"`
Expected: FAIL — 403 用例拿到 200（当前逻辑不认 deny）

- [ ] **Step 3: 实现**

`core/api/tools.py` —— 导入加 `from core.tools.policy import decide`，把确认段替换为：

```python
    # 由权限策略决定：deny 直接 403（confirm 不能覆盖 deny）；ask 需 confirm 标记；
    # allow 直接执行。
    # The permission policy decides: deny returns 403 (confirm cannot override it); ask
    # requires the confirm flag; allow runs directly.
    decision = decide(name)
    if decision.action == "deny":
        return JSONResponse(
            {"ok": False, "error": f"操作者策略禁止调用 {name}（{decision.source}）"},
            status_code=403,
        )
    if decision.action == "ask" and not params.get("confirm"):
        return JSONResponse({
            "ok": False,
            "error": f"工具 {name} 需要操作者确认（{decision.source}）",
            "needs_confirm": True,
        })
```

（删掉原先的 `risk = TOOLS.risk(name)` 与 `if risk != "read" and not params.get("confirm")` 段。）

- [ ] **Step 4: 运行确认通过 + 全量后端回归**

Run: `python -m pytest tests/ -q && python -m mypy core/ server.py`
Expected: 全部通过

- [ ] **Step 5: 提交**

```bash
git add core/api/tools.py tests/test_server.py
git commit -m "feat(API): /tools/call 走权限策略，confirm 不能覆盖 deny

原先用客户端传的 confirm: true 作闸门。改为 policy 优先：
deny → 403（关键安全不变式：confirm 永远不能覆盖 deny）
ask  → 无 confirm 时返回 needs_confirm
allow → 直接执行，不再要求 confirm 标记

响应字段未变（仍是 {ok, error}），前端既有错误处理可直接复用。"
```

---

## Task 6: validator 校验规则命中

**Files:**
- Modify: `core/detection/validator.py`
- Test: `tests/test_detection.py`

**Interfaces:**
- Consumes: Task 2 的 `PermissionsSection`
- Produces: 无新接口；`validate()` 对匹配不到任何工具的 `match` 报 warning

- [ ] **Step 1: 写失败测试**

在 `tests/test_detection.py` 追加：

```python
def test_validator_warns_on_unmatched_permission_rule():
    """规则 match 匹配不到任何已注册工具 → warning（否则拼错会被静默忽略，用户以为已生效）。
    A rule whose match hits no registered tool produces a warning; otherwise a typo is
    silently ignored and the user believes the policy took effect."""
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
```

- [ ] **Step 2: 运行确认失败**

Run: `python -m pytest tests/test_detection.py -q -k permission`
Expected: FAIL — 无 warning（`assert any(...)` 失败）

- [ ] **Step 3: 实现**

`core/detection/validator.py` —— 导入加 `import fnmatch` 与 `from core.tools import TOOLS`，在 `validate()` 的 `return` 之前插入：

```python
    # permissions：规则 match 必须至少命中一个已注册工具，否则是拼写错误会被静默忽略
    # permissions: a rule's match must hit at least one registered tool, otherwise a typo
    # is silently ignored.
    tool_names = [t["name"] for t in TOOLS.meta()]
    for rule in settings.permissions.rules:
        if not any(fnmatch.fnmatchcase(n, rule.match) for n in tool_names):
            issues.append(Issue("warning", f"permissions.rules[{rule.match}]",
                                f"规则 match「{rule.match}」匹配不到任何已注册工具，该规则不会生效（是否拼写错误？）"))
```

- [ ] **Step 4: 运行确认通过 + 全量后端回归**

Run: `python -m pytest tests/ -q && python -m mypy core/ server.py`
Expected: 全部通过

- [ ] **Step 5: 提交**

```bash
git add core/detection/validator.py tests/test_detection.py
git commit -m "feat(检测): 校验权限规则的 match 是否命中已注册工具

match 拼错会被静默忽略（既不报错也不生效），用户会以为策略已生效 ——
现在报 warning 提示。"
```

---

## Task 7: 前端权限设置卡

**Files:**
- Create: `web/src/components/console/settings/PermissionsCard.vue`
- Modify: `web/src/components/console/settings/configDefs.ts`（`menuDefs` 加「权限」）
- Modify: `web/src/components/console/ConsoleSettings.vue`（挂载）
- Test: `web/src/components/console/settings/__tests__/PermissionsCard.spec.ts`

**Interfaces:**
- Consumes: Task 2 的 `editable["permissions"]`（类型 `components['schemas']['PermissionsOut']`）；`useSettings()` 的 `editable` / `saving` / `saveModule`；既有的 `api.getTools()`
- Produces: 组件 `PermissionsCard`

- [ ] **Step 1: 写失败测试**

新建 `web/src/components/console/settings/__tests__/PermissionsCard.spec.ts`：

```ts
// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'

vi.mock('../../../../api', () => ({
  api: { patchConfig: vi.fn(), getConfigFull: vi.fn(), getProviders: vi.fn(), getTools: vi.fn(), getDetection: vi.fn() },
}))

import { api } from '../../../../api'
import { editable } from '../state'
import PermissionsCard from '../PermissionsCard.vue'

/** 权限设置卡：三个层级下拉 + 默认动作 + 规则增删。 */
const PERMS = {
  default_action: 'ask',
  tiers: { read: 'allow', write: 'ask', exec: 'ask' },
  rules: [{ match: 'run_shell_tool', action: 'deny' }],
}

describe('PermissionsCard', () => {
  beforeEach(() => {
    vi.mocked(api.getTools).mockReset()
    vi.mocked(api.getTools).mockResolvedValue({ ok: true, tools: [] } as any)
    editable.value = { permissions: structuredClone(PERMS) } as any
  })

  /** 渲染三个层级下拉，当前值来自 editable。 */
  it('渲染三个层级下拉并反映当前配置', () => {
    const w = mount(PermissionsCard)
    const selects = w.findAll('select')
    expect(selects.length).toBeGreaterThanOrEqual(4) // read/write/exec + default_action
    expect(w.html()).toContain('run_shell_tool')
  })

  /** 改变 read 层级会写回 editable。 */
  it('改变层级写回 editable', async () => {
    const w = mount(PermissionsCard)
    const readSelect = w.findAll('select')[0]
    await readSelect.setValue('deny')
    expect((editable.value as any).permissions.tiers.read).toBe('deny')
  })

  /** 新增规则追加一条空规则。 */
  it('新增规则追加一条空规则', async () => {
    const w = mount(PermissionsCard)
    await w.findAll('button').find((b) => b.text().includes('新增'))!.trigger('click')
    expect((editable.value as any).permissions.rules).toHaveLength(2)
  })

  /** 删除规则移除对应项。 */
  it('删除规则移除对应项', async () => {
    const w = mount(PermissionsCard)
    await w.findAll('button').find((b) => b.text() === '删除')!.trigger('click')
    expect((editable.value as any).permissions.rules).toHaveLength(0)
  })
})
```

- [ ] **Step 2: 运行确认失败**

Run: `cd web && npx vitest run src/components/console/settings/__tests__/PermissionsCard.spec.ts`
Expected: FAIL — 组件不存在，`Failed to resolve import "../PermissionsCard.vue"`

- [ ] **Step 3: 实现**

新建 `web/src/components/console/settings/PermissionsCard.vue`：

```vue
<template>
  <!-- 权限设置卡：按风险层级设默认动作 + 单工具/通配规则覆盖。
       Permission settings card: per-tier default actions plus per-tool / glob rule overrides. -->
  <UiCard class="cs-card">
    <div class="cs-card-head">
      <span class="cs-card-title">工具权限</span>
      <UiButton variant="primary" size="sm" :disabled="!s.editable.value || s.saving.value" @click="s.saveModule('permissions')">
        {{ s.saving.value ? '保存中…' : '保存' }}
      </UiButton>
    </div>

    <p class="cs-note">
      求值顺序：未注册工具 → 拒绝；任一 <code>deny</code> 规则短路（不可被后续规则翻案）；
      首条匹配规则；层级默认；最后 <code>default_action</code>。
    </p>

    <SettingsField label="默认动作（未命中任何规则时）">
      <UiSelect v-model="perms.default_action">
        <option v-for="a in ACTIONS" :key="a.value" :value="a.value">{{ a.label }}</option>
      </UiSelect>
    </SettingsField>

    <div class="cs-subcard">
      <div class="cs-subcard-title">按风险层级的默认动作</div>
      <SettingsField v-for="t in TIERS" :key="t.key" :label="t.label">
        <UiSelect v-model="perms.tiers[t.key]">
          <option v-for="a in ACTIONS" :key="a.value" :value="a.value">{{ a.label }}</option>
        </UiSelect>
      </SettingsField>
      <p class="cs-note">把 <code>exec</code> 设为「允许」意味着所有执行类工具不再询问 —— 请确认你接受该风险。</p>
    </div>

    <div class="cs-subcard">
      <div class="cs-subcard-title">规则（优先级高于层级默认）</div>
      <div v-for="(r, i) in perms.rules" :key="i" class="cs-profrow">
        <SettingsField label="工具名或通配" grow>
          <UiInput v-model="r.match" list="perm-tool-names" placeholder="如 run_* 或 read_file" />
        </SettingsField>
        <SettingsField label="动作">
          <UiSelect v-model="r.action">
            <option v-for="a in ACTIONS" :key="a.value" :value="a.value">{{ a.label }}</option>
          </UiSelect>
        </SettingsField>
        <UiButton variant="secondary" size="sm" hover="danger" @click="perms.rules.splice(i, 1)">删除</UiButton>
      </div>
      <datalist id="perm-tool-names">
        <option v-for="n in toolNames" :key="n" :value="n" />
      </datalist>
      <UiButton variant="secondary" size="sm" @click="perms.rules.push({ match: '', action: 'ask' })">＋ 新增规则</UiButton>
    </div>
  </UiCard>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { api } from '../../../../api'
import SettingsField from './SettingsField.vue'
import { UiButton, UiCard, UiInput, UiSelect } from '../../ui'
import { useSettings } from './useSettings'

/** 设置页单例（保留对象引用以维持响应式）。Settings singleton (kept as an object to preserve reactivity). */
const s = useSettings()

/** 可选的权限动作。The available permission actions. */
const ACTIONS = [
  { value: 'allow', label: '允许（不问）' },
  { value: 'ask', label: '询问' },
  { value: 'deny', label: '拒绝' },
]

/** 三个风险层级。The three risk tiers. */
const TIERS = [
  { key: 'read' as const, label: '只读工具' },
  { key: 'write' as const, label: '写入工具' },
  { key: 'exec' as const, label: '执行工具' },
]

/** 已注册工具名（规则的 datalist 提示）。Registered tool names (datalist hints for rules). */
const toolNames = ref<string[]>([])

/** 权限段的响应式视图（editable 未加载时给一份安全默认，避免模板空引用）。 */
const perms = computed(() => {
  const p = (s.editable.value as any)?.permissions
  return p ?? { default_action: 'ask', tiers: { read: 'allow', write: 'ask', exec: 'ask' }, rules: [] }
})

onMounted(async () => {
  try {
    const r = await api.getTools()
    if (r.ok) toolNames.value = r.tools.map((t) => t.function.name)
  } catch { /* 工具名仅作输入提示，拉取失败不影响编辑 / tool names are hints only */ }
})
</script>

<style scoped>
.cs-card { display: flex; flex-direction: column; gap: 12px; }
.cs-card-head { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.cs-card-title { font-size: var(--fs-sm); font-weight: 600; color: var(--text-1); letter-spacing: .02em; }
.cs-subcard {
  display: flex; flex-direction: column; gap: 8px;
  padding: 10px 12px; border: 1px solid var(--border-soft); border-radius: var(--r-md);
  background: rgba(15, 23, 42, .4);
}
.cs-subcard-title { font-size: var(--fs-xs); font-weight: 600; color: var(--text-2); letter-spacing: .02em; }
.cs-profrow { display: flex; align-items: flex-end; gap: 8px; }
.cs-note { font-size: var(--fs-2xs); color: var(--text-3); line-height: 1.6; margin: 4px 0 0; }
</style>
```

`configDefs.ts` 的 `menuDefs` 追加一项：

```ts
  { id: 'permissions', label: '权限', icon: 'shield' },
```

`ConsoleSettings.vue` —— 模板中在 `<AdvancedCard ... />` 之后加：

```vue
        <!-- 权限模块：工具权限策略（层级默认 + 规则覆盖）。Permission module: tool permission policy. -->
        <PermissionsCard v-if="s.editable.value && s.activeMenu.value === 'permissions'" />
```

并在 `<script setup>` 的 import 段加：

```ts
import PermissionsCard from './settings/PermissionsCard.vue'
```

- [ ] **Step 4: 运行确认通过**

Run: `cd web && npx vitest run src/components/console/settings/__tests__/PermissionsCard.spec.ts && npx vue-tsc --noEmit`
Expected: PASS，类型检查无错

- [ ] **Step 5: 提交**

```bash
git add web/src/components/console
git commit -m "feat(web): 设置页新增「权限」卡（层级默认 + 规则覆盖）

三层级下拉 + 默认动作下拉 + 规则增删；规则的 match 输入带已注册工具名
datalist 提示。附求值顺序说明，让用户理解为何某条规则未生效。"
```

---

## Task 8: 全量验证与端到端

**Files:**
- Modify: `README.md`（安全表述 + 权限说明）

- [ ] **Step 1: 后端全量**

Run: `python -m pytest tests/ -q && python -m mypy core/ server.py`
Expected: 全部通过

- [ ] **Step 2: 前端全量 + 类型同步门禁**

Run:
```bash
cd web && npm test && npm run build
cd web && PYTHONIOENCODING=utf-8 python ../scripts/gen_openapi.py && npx --yes openapi-typescript@7.13.0 src/api/openapi.json -o src/api/generated.ts
git diff --exit-code src/api/generated.ts && echo "OK: generated.ts 已同步"
```
Expected: 全绿，且 `generated.ts` 无 diff（已在 Task 2 提交）

- [ ] **Step 3: 端到端人工验证（不可省）**

先确认端口空闲再起服务（**Windows 上 `pkill` 不生效，务必用 `taskkill` 并检查无 bind 冲突**）：

```bash
taskkill //F //FI "IMAGENAME eq python.exe" ; sleep 2
netstat -ano | grep ":8520.*LISTENING" || echo "端口空闲"
python main.py serve > /tmp/server.log 2>&1 &
sleep 7 && (grep -qa "10048" /tmp/server.log && echo "❌ 跑的是旧进程" || echo "✓ 绑定成功")
```

四条验证：

1. **默认行为不变**：发一条高风险删除任务 → 仍出现确认卡（`read/write/exec` 默认未变）
2. **deny 生效**：设置页把 `read_file` 的层级改成「拒绝」保存 → 让助手读文件 → 应被拒绝，且 `data/audit.log` 有 `policy denied` 记录
3. **allow 生效**：设置页新增规则 `run_shell_tool → 允许` 保存 → 发一条需要 shell 的任务 → 应**不再出现确认卡**直接执行
4. **规则拼错有提示**：新增规则 `match: no_such_*` → 检测页应出现 warning

验证完毕后把配置改回默认（或删除测试规则），避免留下放宽的安全设置。

- [ ] **Step 4: 同步安全表述**

`README.md` 的「安全」节现写「**无沙箱 + 人类在环**」：高风险工具执行前经操作者明确确认。A 落地后该表述不再完整 —— 免询问的工具变多。改为说明：确认由**可配置的权限策略**决定（默认 read 免确认、write/exec 询问），并提示放宽策略会降低安全边界。

- [ ] **Step 5: 提交并推送**

```bash
git add README.md
git commit -m "docs: 安全表述同步权限策略（确认由可配置策略决定，非固定规则）"
git push origin main
```

---

## 完成标准

- [ ] `python -m pytest tests/ -q` 全绿（含求值矩阵、三个消费点、默认等价回归）
- [ ] `python -m mypy core/ server.py` 无问题
- [ ] `cd web && npm test` 全绿；`npm run build` 通过
- [ ] `generated.ts` 与后端 schema 同步（`git diff --exit-code` 无输出）
- [ ] 端到端四条验证通过，且验证后配置已还原为默认
- [ ] `README.md` 的安全表述已更新
- [ ] 全仓无残留 `TOOLS.risk(` 用于「是否询问」的判定（仅保留审计/展示/并发以外的用途）
