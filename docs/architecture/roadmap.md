# 语音全控智能体 · 实施路线追踪

> 架构：`docs/architecture/01-voice-control-agent.md`
> 各阶段计划：`docs/superpowers/plans/`（勾选记录完成状态，每 Task 独立测试 + 独立 commit，完成后对照各计划末尾的「审查清单」）

| 阶段 | 主题 | 状态 | 计划 | 验收要点 |
|------|------|------|------|----------|
| P0 | 地基：环境感知 / 执行层 / 基础工具 / 编排闭环 / 停止 / 语音监听 | ✅ 已完成 | [2026-08-12-agent-p0-foundation.md](../superpowers/plans/2026-08-12-agent-p0-foundation.md) | 语音全链路冒烟通过（唤醒→ASR→意图→澄清→工具执行→回复）；答案通道当前为文字，语音回答待后续增强 |
| P1 | 记忆三级 + RAG | ✅ 已完成 | [2026-08-12-agent-p1-memory-rag.md](../superpowers/plans/2026-08-12-agent-p1-memory-rag.md) | 长期事实记忆 + 任务后自动提取 + RAG 上下文注入 + 前端记忆浏览/删除 |
| P2 | MCP + Skills | ✅ 已完成 | [2026-08-12-agent-p2-capabilities.md](../superpowers/plans/2026-08-12-agent-p2-capabilities.md) | MCP 客户端/桥/生命周期 + Skills 热加载/执行器；/api/tools 含 mcp_* 与 skill 工具 |
| P3 | 多智能体 + 定时 + GUI | ✅ 已完成 | [2026-08-12-agent-p3-advanced.md](../superpowers/plans/2026-08-12-agent-p3-advanced.md) | 子代理/协调者（复杂任务转多智能体）+ cron 定时（无人值守）+ GUI 工具 + 前端定时 Tab |
| P4 | 询问类型扩展 + 问答入聊天记录（子系统 B+D） | 📋 待启动 | [分解文档](../superpowers/specs/2026-09-13-agent-capabilities-roadmap-design.md) | 询问支持 choice / text / composite 三态；提问与回答进入消息列表与会话历史 |
| P5 | 工具权限策略层（子系统 A） | 📋 待启动 | 同上 | 设置里可配 allow / ask / deny（规则>例外>默认）；常用工具默认免询问；修 `TOOLS.risk()` 未知工具 fail-open |
| P6 | 语音作答 + 无应答待机 + 再唤醒续答（子系统 C） | 📋 待启动 | 同上 | 提问时进入语音监听；语音优先且可文本作答；无应答进待机；再唤醒回到未答完的提问；播报期间门控麦克风 |
| P7 | 任务知识库（子系统 E） | 📋 待启动 | 同上 | 完成时询问是否完成；成功任务存入独立模块；相似任务检索预填参数、减少询问 |

> P4–P7 的完整分解（接口边界、待决问题、风险、spec 大纲）见
> [2026-09-13-agent-capabilities-roadmap-design.md](../superpowers/specs/2026-09-13-agent-capabilities-roadmap-design.md)。
> 每个阶段单独走 spec → plan → 实施；P4 与 P5 可并行。

## 总体进度

- **P0**：13 / 13 个 Task ✅
- **P1**：6 / 6 个 Task ✅
- **P2**：5 / 5 个 Task ✅
- **P3**：6 / 6 个 Task ✅
- **P4–P7**：尚未开始（阶段划分与顺序见分解文档）

> 每完成一个 Task：在对应计划里勾选 `[x]`，并更新上方「总体进度」计数。
> 每完成一个阶段：对照该计划末尾的「验收清单」与「审查清单」，通过后把状态改为 ✅，并做阶段小结提交。

## 桌面端（暂停开发，不再迁移）

桌面原生悬浮球（PySide6 窗口 + 托盘）与本地常驻语音监听曾作为 P4 方向开发：

- **桌面悬浮球 UI**（PySide6 / 早期 Tauri 尝试）：已完成 WIP 快照，代码迁移至 **`desktop-ball` 分支**，主分支已移除。
- **本地常驻语音监听**：已随桌面端一并移除，代码在 `desktop-ball` 分支。

**决策**：桌面端**不再迁移回主分支**。当前语音交互由浏览器端 Vosk WASM 唤醒 + 后端 ASR 承担，
主分支以此为唯一语音入口；`desktop-ball` 分支保留为历史快照。

## 当前主分支功能基线

| 能力 | 说明 |
|------|------|
| 语音交互 | 浏览器 Vosk WASM 唤醒（小逻小逻）+ 后端 OpenAI 兼容 ASR/TTS + SpeechSynthesis 播报 |
| 任务编排 | 意图 → 任务 → 澄清 → 确认 → 执行 → 汇报，SSE 事件流 + 人类在环问答通道 |
| 执行层 | Shell / Python（独立进程、可 kill 进程树）、文件系统（10+ 通用格式）、GUI 自动化、环境感知 |
| 记忆/RAG | 长期事实记忆（facts.sqlite）+ 任务后 LLM 提取 + 关键词 RAG 上下文注入 |
| 能力扩展 | MCP 客户端与桥、Skills 热加载、cron 定时（无人值守）、多智能体协调者 |
| 控制 | CancellationToken 贯穿全链路：stop_task / stop_step / pause + taskkill /T 兜底 |
| 测试 | 40 个 pytest 文件覆盖各层（`python -m pytest tests/ -q`） |
| 定时被拒提醒 | 定时任务无人应答的高风险操作自动拒绝后，记 warning + 落盘会话历史（控制台可见） |
