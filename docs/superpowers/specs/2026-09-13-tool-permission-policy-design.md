# 工具权限策略层 设计文档（P5 / 子系统 A）

日期：2026-09-13
状态：待实施
上游：[Agent 能力扩展路线图](2026-09-13-agent-capabilities-roadmap-design.md) 的子系统 A

## 背景

需求原文：「权限分层级，参考 openclaw 和 DSH，在设置里设置默认工具调用不用询问」。

现状：工具是否需询问由 `@tool(risk=...)` 装饰器硬编码的静态值决定，消费点有三处，**没有任何配置入口**：

| 消费点 | 现状 |
|---|---|
| `core/orchestrator/confirm.py:102` | `TOOLS.risk(name) != "read"` → 进入询问 |
| `core/orchestrator/executor.py:143-144` | 按 risk 做并发分流（read 并发 / 其余串行） |
| `core/api/tools.py:56-62` | 客户端传 `confirm: true` 即放行非 read 工具 |

参照实现映射（openclaw / DSH）：三桶动作 `allow / ask / deny`、优先级 `规则 > 例外 > 默认`（`dsh-permgate`）、`deny` 单调不可翻案（`dsh-path-guard`）、无审批通道时 `ask` 即 `deny`（DSH 原生，**本项目已实现**）。

## 一处更正（本设计推翻了路线图中的断言）

路线图曾写「**`TOOLS.risk()` 对未知工具返回 `"read"` 是 fail-open，A 必须先修**」。经核实**该断言不成立**：

- 未注册的工具名**根本不会执行** —— `TOOLS.acall` 对未知名字直接返回 `Error: unknown tool '{name}'`；
- 动态注册的 MCP 工具是显式 `risk="exec"`（`core/tools/mcp_bridge.py:61`），并非默认 read。这是唯一的动态注册点（另一处 `TOOLS.register` 是 `@tool` 装饰器本身）。

因此那只是显示/并发分流的怪癖，**不构成可执行路径上的漏洞**。路线图已同步更正。本设计仍会对未知工具名按最严格处理，但那是**纵深防御**，不是补漏。

## 已确认决策

| # | 决策 | 说明 |
|---|---|---|
| 1 | **按风险层级设默认 + 单工具/通配规则覆盖** | 求值顺序 `deny 短路 > rules > tiers > default_action` |
| 2 | **默认值刻意等价于现状** | read 免询问、write/exec 询问 → 升级后行为不变（关键迁移属性） |
| 3 | **不做 `allow-always`** | 弹窗只有「允许本次 / 拒绝」；想永久免询问就到设置页把该工具配成 `allow` |
| 4 | **并发分流改为按「是否需要确认」** | `allow` 的并发（含 write/exec），需确认的逐个串行 |

> **决策 4 已接受的风险**：两个被 `allow` 的写操作会并发执行，同时写同一目录/同一文件时可能交错。默认 tiers 下 `write`/`exec` 为 `ask`，故只有**被显式 allow 的工具**才会并发 —— 风险由配置者明示承担。若日后发现实际交错问题，可改为「按工具名分组：同名串行、异名并发」，本期不做。

## 配置结构

`core/config/schema.py` 新增：

```python
class PermissionRule(BaseModel):
    """一条权限规则：match 为工具名或 glob（fnmatch 语义）。

    A permission rule: match is a tool name or a glob (fnmatch semantics).
    """
    match: str
    action: Literal["allow", "ask", "deny"]


class PermissionTiers(BaseModel):
    """按工具风险层级设的默认动作。Per-tier default action, keyed by tool risk."""

    read: Literal["allow", "ask", "deny"] = "allow"
    write: Literal["allow", "ask", "deny"] = "ask"
    exec: Literal["allow", "ask", "deny"] = "ask"


class PermissionsSection(BaseModel):
    """工具权限策略。Tool permission policy."""

    default_action: Literal["allow", "ask", "deny"] = "ask"
    tiers: PermissionTiers = Field(default_factory=PermissionTiers)
    rules: list[PermissionRule] = Field(default_factory=list)
```

`Settings` 增字段 `permissions: PermissionsSection = Field(default_factory=PermissionsSection)`。

**默认值等价现状**：`read→allow`（现状 read 免确认）、`write/exec→ask`（现状需确认）。既有用户的 `config.yaml` 无 `permissions` 段 → 用默认值 → 行为不变。

## 求值算法

新增 `core/tools/policy.py`：

```python
@dataclass(frozen=True)
class Decision:
    """一次工具调用的权限判定结果。

    action 为 allow / ask / deny；source 说明依据（供审计与设置页展示），
    形如 "rule:run_*" / "tier:exec" / "default" / "unknown"。
    """
    action: str
    source: str


def decide(name: str) -> Decision:
    """判定工具调用该放行、询问还是拒绝。

    求值顺序（deny 单调不可翻案）：
    1. **工具未注册 → deny**（必须先于 tier 判定：TOOLS.risk 对未知名返回 "read"，
       若放到后面会被 tiers["read"] 提前放行）—— 纵深防御，正常路径下 acall 本就会拒绝
    2. 扫描全部规则，**任一条匹配且为 deny → 立即 deny**
    3. 否则取**第一条**匹配规则的 action
    4. 否则 tiers[TOOLS.risk(name)]
    5. 否则 default_action

    Decide whether a tool call is allowed, asked about, or denied. Order: an
    unregistered name is denied first (it must precede the tier lookup, since
    TOOLS.risk returns "read" for unknown names and tiers["read"] would otherwise
    allow it early) — defence-in-depth, as acall already rejects it on the normal
    path; then any matching deny rule wins outright (deny is monotonic and cannot be
    overridden); otherwise the first matching rule; otherwise the tier for the tool's
    risk; otherwise default_action.
    """
```

用 `fnmatch.fnmatchcase(name, rule.match)` 做匹配（大小写敏感，工具名是小写标识符）。

## 三个消费点的改造

### 1. `core/orchestrator/confirm.py`

`confirm_tool` 改为按 policy 决定，`_resolve_confirm` 不动；`_ask_operator` 增一个
**仅用于审计**的 `source` 形参（默认空串，既有调用点不受影响）：

```python
async def confirm_tool(session: Session, name: str, args: dict) -> bool:
    decision = policy.decide(name)
    if decision.action == "allow":
        return True
    if decision.action == "deny":
        audit(f"tool={name} decision=denied source={decision.source}")
        return False
    plan = f"调用工具 {name}，参数 {json.dumps(args, ensure_ascii=False)}"
    return await _ask_operator(session, plan, TOOLS.risk(name), "tool", source=decision.source)
```

`_ask_operator(session, plan, risk, kind, source="")` 的审计行末追加 ` source={source}`，
使日志能回答「这条判定依据是哪来的」（`rule:run_*` / `tier:exec` / `default`）。

**弹窗文案（决策 3）**：`CONFIRM_OPTIONS` 的 label 由「确认 / 取消」改为「**允许本次 / 拒绝**」，**value 保持 `yes`/`no` 不变** —— 故 `_resolve_confirm` 与全部既有回归用例不受影响。语义上明确「这次而已」，因为不存在永久允许。

### 2. `core/orchestrator/executor.py:143-144`

```python
            # 免确认的工具并发执行；需确认的逐个串行（确认本身必须串行问）
            # Tools needing no confirmation run concurrently; those needing it run one at a
            # time (the confirmation itself must be asked serially).
            auto_idx = [i for i, tc in enumerate(tool_calls)
                        if decide(tc["function"]["name"]).action == "allow"]
            ask_idx = [i for i, tc in enumerate(tool_calls) if i not in set(auto_idx)]
```

### 3. `core/api/tools.py` 的 `tools_call`

当前用客户端传的 `confirm: true` 作闸门。改为 policy 优先，且 **`confirm: true` 永远不能覆盖 `deny`**：

```python
    decision = decide(name)
    if decision.action == "deny":
        return JSONResponse(
            {"ok": False, "error": f"操作者策略禁止调用 {name}（{decision.source}）"}, status_code=403)
    if decision.action == "ask" and not params.get("confirm"):
        return JSONResponse({
            "ok": False,
            "error": f"工具 {name} 需要操作者确认（{decision.source}）",
            "needs_confirm": True,
        })
    # allow → 直接执行（不再要求 confirm 标记）
```

新增 403 状态码用于 deny —— 这是本设计唯一的 API 行为新增（**不新增字段**，故 `generated.ts` 无需重新生成）。

## 校验

`core/detection/validator.py` 增加：`permissions.rules[].match` 若**匹配不到任何已注册工具**，报 warning。理由：`match` 拼错会被静默忽略（既不报错也不生效），用户会以为策略已生效。用 `any(fnmatch.fnmatchcase(n, r.match) for n in tool_names)` 判定，`tool_names` 取自 `TOOLS.meta()`。

**不加**「规则为空即报错」之类的校验 —— 空规则是完全合法的配置。

## 前端

设置页新增「权限」菜单项（`configDefs.ts` 的 `menuDefs` + 新组件 `settings/PermissionsCard.vue`）：

- 三个层级下拉（read / write / exec）+ 默认动作下拉，选项为 允许 / 询问 / 拒绝
- 规则列表：每行 `match` 输入框（`datalist` 提供已注册工具名，数据来自既有的 `GET /api/tools`）+ `action` 下拉 + 删除；底部「新增规则」
- 说明文字：列出求值顺序（deny 短路 > 规则 > 层级 > 默认），让用户理解为什么某条规则没生效

**不做**「逐工具展示生效动作」表格 —— 那需要后端逐工具求值的新接口（→ openapi 变更 → 重新生成类型），而规则+层级已满足需求。YAGNI。

## 迁移与兼容

- 既有 `config.yaml` 无 `permissions` 段 → 默认值 → **行为完全不变**。
- `TOOLS.risk()` **不改** —— 它仍被 executor 的审计与 `TOOLS.meta()` 展示使用；策略层通过 `policy.decide()` 叠加在其上。
- `/api/tools/call` 新增 403 分支，但**响应字段未变**（仍是 `{ok, error}`），前端既有错误处理可直接复用。
- **必须重新生成 `web/src/api/generated.ts`**：`EditableSnapshot`（`core/api/schemas.py:456`）是**显式 pydantic 模型**并经 `ConfigFullResponse` 暴露到 openapi，新增 `permissions` 字段会改变 schema —— CI 的类型同步门禁（`gen:api` + `git diff --exit-code`）会校验，不同步即失败。
  > **更正（2026-09-13）**：本 spec 初稿曾写「不新增 API 字段，无需重新生成」，**该说法是错的**。
  > 漏看了 `EditableSnapshot` 这一个显式模型（PATCH 侧确实无需新字段，`Settings(**merged)` 的 `extra="forbid"` 会自动接受新 Section；但读取侧必须显式加字段，否则 pydantic 会在 response_model 过滤时把它丢掉，前端根本收不到）。
  > 实施清单已加入 `cd web && npm run gen:api` 并提交 `generated.ts`。

## 测试策略

**后端（TDD）**
- `policy.decide` 求值顺序矩阵：deny 短路（含「deny 在列表末尾仍短路」）> 首条匹配 > tier > default；未注册名 → deny
- glob 匹配：`run_*` 命中 `run_shell_tool`；精确名；不命中
- 三个消费点各自的行为：`confirm_tool` 的 allow/ask/deny；executor 的并发分组；`tools_call` 的 403 与 `needs_confirm`
- **`confirm: true` 不能覆盖 `deny`**（关键安全用例）
- 默认配置下的行为**等价于改造前**（回归：read 免询问、write/exec 询问）
- `validator` 对拼错的 `match` 报 warning
- `CONFIRM_OPTIONS` 的 label 变更不影响 `_resolve_confirm`（既有 51 个确认用例保持全绿）

**前端（Vitest）**
- 权限卡渲染与保存（层级下拉 + 规则增删）
- 规则行的 match 输入带工具名 datalist

**端到端**：起服务，把 `read_file` 配成 `deny` → 让助手读文件 → 应被拒且审计有记录；把 `run_shell_tool` 配成 `allow` → 应免确认执行。

## 风险

| 风险 | 处置 |
|---|---|
| **放宽策略 = 降低安全边界** | README 现写「无沙箱 + 人类在环」，A 落地后免询问工具变多，**该表述必须同步修订**（列入实施清单） |
| **决策 4 的并发写交错** | 已明示接受；默认 tiers 下仅显式 allow 的工具会并发 |
| 用户把 `exec` 层级设为 `allow` | 这是配置者明示承担的风险；设置页该下拉旁需有醒目说明（实施时加） |
| `confirm: true` 绕过确认 | 只对 `ask` 有效，**永远不能覆盖 `deny`**（已列为关键测试用例） |

## 不做（明确排除）

- `allow-always` 按钮与「危险模式不可持久化」名单（本期不做，决策 3）
- 沙箱 / 文件系统范围控制（本策略只管「问不问」，不管「能否执行」）
- `dsh-tiered-approval` 式的 LLM 审查层
- 逐工具生效动作的展示接口（YAGNI）
