# -*- coding: utf-8 -*-
"配置 schema — agent/tools/permissions/mcp/rag/server/memory 子模块（自 schema.py 拆出，纯移动）。"

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

class AgentSection(BaseModel):
    """Agent 段配置：递归上限、多智能体开关与结构化输出温度。

    Agent section config: recursion limit, multi-agent toggle, and structured-output temperature.
    """

    model_config = ConfigDict(extra="forbid")

    recursion_limit: int = Field(12, gt=0)
    multi_agent: bool = False
    models_failover: list[str] = Field(default_factory=list)  # 主模型故障时的备选模型
    # 结构化输出阶段（意图/任务形成/拆解/事实提取）的温度，单独调低以稳定 JSON 输出
    structured_temperature: float = Field(0.2, ge=0.0, le=2.0)
    # True=write/exec 高风险工具/任务不再询问操作者，自动放行（含子代理与技能；无人值守通道仍默认拒绝）
    auto_approve: bool = False  # True=auto-approve write/exec tools/tasks without asking the operator (incl. sub-agents & skills; channel-less runs still reject)
    # 操作者提问（澄清/确认）超时秒数：0=不限（无限期等待，旧行为）；>0 到期按拒绝处理
    # （fail-closed），前端问题卡随 timeout 源 answer 事件收起。
    # Timeout in seconds for operator questions (clarify/confirm): 0 = no limit (the old
    # wait-forever behaviour); on expiry the answer counts as a rejection (fail-closed)
    # and the frontend folds the question card via the timeout-sourced answer event.
    confirm_timeout_s: int = Field(0, ge=0)  # 0 = no limit (seconds); expiry counts as rejection (fail-closed)
    # 滚动压缩阈值（docs/designs/08 批2）：ReAct 历史估算字符超过此值时折叠中间段为摘要
    # （只动本轮 LLM 视角，不改会话持久化）；0=关闭。
    # Rolling-condense threshold (docs/designs/08 batch 2): fold the middle of the ReAct
    # history into a summary once the estimated characters exceed this (LLM view only,
    # never the persisted session); 0 = off.
    condense_threshold_chars: int = Field(12000, ge=0)


class LlmClientSection(BaseModel):
    """LLM 客户端段配置：重试、熔断与请求超时参数。

    LLM client section config: retry, circuit-breaker, and request-timeout parameters.
    """

    model_config = ConfigDict(extra="forbid")

    retry_max: int = Field(3, ge=0)
    retry_backoff_base: float = Field(0.5, gt=0)
    retry_backoff_max: float = Field(10.0, gt=0)
    circuit_breaker_threshold: int = Field(5, gt=0)
    circuit_breaker_cooldown: float = Field(30.0, gt=0)
    request_timeout: int = Field(60, gt=0)


class ToolsSection(BaseModel):
    """工具段配置：搜索/天气参数 + LLM 口径输出截断 + 渐进式 schema 分组。

    Tools section config: search/weather parameters + LLM-side output cap +
    progressive schema grouping.
    """

    model_config = ConfigDict(extra="forbid")

    search_max_results: int = Field(5, gt=0)
    weather_timeout: int = Field(10, gt=0)
    # LLM 口径输出截断（docs/designs/08 批2）：喂给模型的 tool 消息上限，超出截断并附
    # 「如何取更多」指引；0=不限。与展示口径（PREVIEW_LEN）/落库口径（HISTORY_LEN）独立。
    # LLM-side output cap (docs/designs/08 batch 2): limit for tool messages fed to the
    # model, truncated with a "how to get more" hint; 0 = unlimited. Independent of the
    # display (PREVIEW_LEN) and persistence (HISTORY_LEN) conventions.
    llm_max_output_chars: int = Field(8000, ge=0)
    # 渐进式工具 schema（docs/designs/08 批4）：这些组降级为一行简介（完整参数需先调
    # tools_describe）；默认空 = 全量下发（现状零变化）。例: ["mcp"]。
    # Progressive tool schemas (docs/designs/08 batch 4): groups in this list degrade to
    # one-line stubs (full parameters via tools_describe first); empty = full schemas
    # (today's behaviour unchanged). E.g. ["mcp"].
    lazy_groups: list[str] = Field(default_factory=list)


class PermissionRule(BaseModel):
    """一条权限规则：match 为工具名或 glob（fnmatch 语义，大小写敏感）。

    A permission rule: match is a tool name or a glob (fnmatch semantics, case-sensitive).
    """

    model_config = ConfigDict(extra="forbid")

    match: str
    action: Literal["allow", "ask", "deny"]


class PermissionTiers(BaseModel):
    """按工具风险层级设的默认动作。Per-tier default action, keyed by tool risk.

    ⚠️ 三档默认**全放行**（2026-09-13 按用户要求改）。本项目无沙箱，这道确认是任意命令
    执行前的唯一闸门 —— 全放行意味着**该闸门默认不生效**（`run_shell_tool` 可执行任意
    命令而不询问）。想收紧时改这里、或用 `permissions.rules` 里的 deny/ask 规则（规则按
    工具名 glob 匹配），也可在控制台「设置 → 权限」里改。

    ⚠️ All three tiers default to **allow** (changed 2026-09-13 at the user's request). There is
    no sandbox here and this confirmation is the only gate before arbitrary command execution, so
    allow-by-default means **the gate is off by default** (`run_shell_tool` runs any command
    without asking). To tighten it, edit these values, add deny/ask entries to
    `permissions.rules` (which glob against tool names), or use the console's Settings → Permissions.
    """

    model_config = ConfigDict(extra="forbid")

    read: Literal["allow", "ask", "deny"] = "allow"
    write: Literal["allow", "ask", "deny"] = "allow"
    exec: Literal["allow", "ask", "deny"] = "allow"


class PermissionsSection(BaseModel):
    """工具权限策略：层级默认 + 规则覆盖。

    默认值**三档全放行、兜底也放行**（2026-09-13 按用户要求从「read 免询问、write/exec
    询问」改为全放行）。想收紧就用 `rules`（按工具名 glob，deny 单调短路）或改 `tiers`。

    Tool permission policy: per-tier defaults plus rule overrides. Every tier — and the
    fallback — defaults to **allow** (changed 2026-09-13 at the user's request, from
    "read auto-allowed, write/exec asked"). To tighten it, use `rules` (globbed against tool
    names, with monotonic deny short-circuiting) or override `tiers`.
    """

    model_config = ConfigDict(extra="forbid")

    default_action: Literal["allow", "ask", "deny"] = "allow"
    tiers: PermissionTiers = Field(default_factory=lambda: PermissionTiers())
    rules: list[PermissionRule] = Field(default_factory=list)


class McpServer(BaseModel):
    """MCP 服务器条目：名称、启动命令与参数。

    MCP server entry: name, launch command, and arguments.
    """

    model_config = ConfigDict(extra="forbid")

    name: str
    command: str
    args: list[str] = Field(default_factory=list)


class McpSection(BaseModel):
    """MCP 段配置：服务器列表。

    MCP section config: the server list.
    """

    model_config = ConfigDict(extra="forbid")

    servers: list[McpServer] = Field(default_factory=list)


class RagSection(BaseModel):
    """RAG 段配置：自动索引与精排档位（docs/designs/05）。

    RAG section config: auto-index and rerank tier (docs/designs/05).
    """

    model_config = ConfigDict(extra="forbid")

    auto_index: bool = True
    # 精排档位：none=纯 BM25（默认，零成本）；llm=BM25 粗排候选后单次 LLM 打分精排，
    # 任何失败静默回退 BM25 序（retriever.rerank 内 catch）。
    # Rerank tier: none = pure BM25 (default, zero cost); llm = one LLM scoring pass
    # over BM25 candidates, any failure silently falls back to BM25 order (caught
    # inside retriever.rerank).
    rerank: Literal["none", "llm"] = "none"
    rerank_candidates: int = Field(12, gt=0)   # 粗排候选数。BM25 candidate count.
    rerank_top_k: int = Field(5, gt=0)         # 精排后注入数（= none 档的 top-k）。Rows injected after rerank (= top-k in the none tier).


class ServerSection(BaseModel):
    """服务器段配置：监听地址、端口、自动开浏览器与 API Token。

    Server section config: listen host, port, auto-open browser, and API token.
    """

    model_config = ConfigDict(extra="forbid")

    host: str = "127.0.0.1"
    port: int = Field(8520, ge=1, le=65535)
    open_browser: bool = True
    api_token: str = ""  # 由 loader 从 secrets/环境注入
    cors_origins: list[str] = Field(default_factory=list)
    # SSE 断线宽限（docs/designs/06）：断开后 runner 继续跑的秒数，期内可 /voice/resume
    # 续播；0=断线即收尾（旧行为）。仅配置文件可改（与 kws 段同为 config-file-only）。
    # SSE disconnect grace (docs/designs/06): seconds the runner keeps alive after a
    # disconnect, resumable via /voice/resume inside the window; 0 = wrap up on
    # disconnect (legacy behaviour). Config-file only (same as the kws section).
    resume_grace_s: int = Field(120, ge=0)


class MemorySection(BaseModel):
    """长期记忆段配置（docs/designs/04）：新近度加权、注入预算、提取回看深度。

    Long-term memory section config (docs/designs/04): recency weighting, injection
    budget, extraction lookback depth.
    """

    model_config = ConfigDict(extra="forbid")

    # 检索新近度加权：score' = bm25 × (1 + w × 0.5^(age_days/τ))；w=0 关闭（纯 bm25）。
    # Search recency weight: score' = bm25 × (1 + w × 0.5^(age_days/τ)); 0 disables.
    recency_half_life_days: float = Field(30.0, gt=0)
    recency_weight: float = Field(0.5, ge=0.0, le=5.0)
    # 注入预算：top-k 条数 + 字符上限（双闸，system prompt 不随命中数膨胀）。
    # Injection budget: top-k rows + character cap (two gates; the system prompt
    # cannot swell with hit count).
    inject_top_k: int = Field(5, gt=0)
    inject_max_chars: int = Field(800, gt=0)
    # 任务后提取回看的最近对话条数（用户/助手各 n；解「他/那里」类指代）。
    # Recent dialog lines the post-task extraction sees (n of each role; resolves
    # "he/there"-style references).
    extract_recent_messages: int = Field(2, ge=0)
