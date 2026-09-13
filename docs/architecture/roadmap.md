# 语音全控智能体 · 实施路线追踪

> 架构：`docs/architecture/01-voice-control-agent.md`
> 各阶段计划：`docs/superpowers/plans/`（勾选记录完成状态，每 Task 独立测试 + 独立 commit，完成后对照各计划末尾的「审查清单」）

| 阶段 | 主题 | 状态 | 计划 | 验收要点 |
|------|------|------|------|----------|
| P0 | 地基：环境感知 / 执行层 / 基础工具 / 编排闭环 / 停止 / 语音监听 | ✅ 已完成 | [2026-08-12-agent-p0-foundation.md](../superpowers/plans/2026-08-12-agent-p0-foundation.md) | 语音全链路冒烟通过（唤醒→ASR→意图→澄清→工具执行→回复）；答案通道当前为文字，语音回答待后续增强 |
| P1 | 记忆三级 + RAG | ✅ 已完成 | [2026-08-12-agent-p1-memory-rag.md](../superpowers/plans/2026-08-12-agent-p1-memory-rag.md) | 长期事实记忆 + 任务后自动提取 + RAG 上下文注入 + 前端记忆浏览/删除 |
| P2 | MCP + Skills | ✅ 已完成 | [2026-08-12-agent-p2-capabilities.md](../superpowers/plans/2026-08-12-agent-p2-capabilities.md) | MCP 客户端/桥/生命周期 + Skills 热加载/执行器；/api/tools 含 mcp_* 与 skill 工具 |
| P3 | 多智能体 + 定时 + GUI | ✅ 已完成 | [2026-08-12-agent-p3-advanced.md](../superpowers/plans/2026-08-12-agent-p3-advanced.md) | 子代理/协调者（复杂任务转多智能体）+ cron 定时（无人值守）+ GUI 工具 + 前端定时 Tab |
| P4 | 询问类型扩展 + 问答入聊天记录（子系统 B+D） | ✅ 已完成 | [2026-09-13-question-types-and-qa-history.md](../superpowers/plans/2026-09-13-question-types-and-qa-history.md) | 询问支持 choice / text / composite 三态（`confirm` 并入 `choice`）；`missing` 结构化为 `MissingItem`；提问与回答进入消息列表 |
| P5 | 工具权限策略层（子系统 A） | ✅ 已完成 | [2026-09-13-tool-permission-policy.md](../superpowers/plans/2026-09-13-tool-permission-policy.md) | 设置页可配 allow / ask / deny（deny 短路 > 规则 > 层级 > 默认）；默认等价改造前行为；三个消费点全部走策略 |
| P6 | 语音作答 + 无应答待机 + 再唤醒续答（子系统 C） | ✅ 已完成 | [2026-09-13-voice-answering.md](../superpowers/plans/2026-09-13-voice-answering.md) | 播报后自动开录、直接语音作答；无应答进待机；再唤醒续答本题；播报期间暂停监听 **（⚠️ 4 项验收均待重做：其中「播报期不自触发」曾被记为「已由验收台验证」，那是一次**真观测**（当时 `WakeWordEngine` 尚在，样本里非零的「播报前 12/22」可证），但它测的引擎与门控机制**已随唤醒链路重构整体删除并替换**，结论无法迁移到当前实现 —— 该「已验证」作废。此后引擎删除、探针目标消失，同一份检查才退化成只能报空洞 PASS 的假保障，故检查 4 已在 P8 重写。需真人有声环境跑 `npm run verify:voice` 重做，详见计划「撤回说明」）** |
| P7 | 任务知识库（子系统 E） | ✅ 已完成 | [2026-09-13-task-knowledge-base.md](../superpowers/plans/2026-09-13-task-knowledge-base.md) | 完成时询问是否完成；成功任务存入独立模块；相似任务检索预填参数、减少询问（按**用户原话**匹配，非 LLM 归一化的 goal） |
| P8 | 唤醒链路重构（**子项目 1 / 4**：VAD → KWS(API) → ASR） | ⏳ 待人工验收 | [2026-09-13-wake-detection-rework.md](../superpowers/plans/2026-09-13-wake-detection-rework.md) | 唤醒重新可用且支持一句话说完：浏览器本地 VAD 切段 → `POST /api/voice/wake` 云端转写并判定「衍衡」「洛吉斯」→ 命中即起一轮；Vosk 引擎与 43MB 模型全部删除。**子项目 2（本地 KWS sherpa-onnx）/ 3（本地 ASR）/ 4（有序回退链 + 能力探测）待做** —— 三者各走独立 spec → 计划 → 实施。⚠️ spec 的硬门槛（人工验收 6 项，spec:198-212 风险表）**尚未执行**：spec 里所有实测用的都是 SAPI 合成音，对合成音识别好不代表对真人好 —— 验收通过前不得称「已完成」 |

> P4–P7 的完整分解（接口边界、待决问题、风险、spec 大纲）见
> [2026-09-13-agent-capabilities-roadmap-design.md](../superpowers/specs/2026-09-13-agent-capabilities-roadmap-design.md)。
> 每个阶段单独走 spec → plan → 实施；P4 与 P5 可并行。
> **P8** 是唤醒链路自身的一次重构，拆成 4 个子项目，本阶段只做子项目 1（云端判定）；
> 子项目 2/3/4 的边界见 [2026-09-13-wake-detection-rework-design.md](../superpowers/specs/2026-09-13-wake-detection-rework-design.md) 文末「后续子项目」。

## 总体进度

- **P0**：13 / 13 个 Task ✅
- **P1**：6 / 6 个 Task ✅
- **P2**：5 / 5 个 Task ✅
- **P3**：6 / 6 个 Task ✅
- **P4**：10 / 10 个 Task ✅
- **P5**：8 / 8 个 Task ✅
- **P6**：9 / 9 个 Task ✅（自动化全绿；**4 项验收全部待人工验收** —— 其中「播报期不自触发」曾记为「已由验收台验证」：那是一次**真观测**，但测的是**已被整体替换的旧实现**（Vosk 引擎 + 停引擎式门控），结论无法迁移到当前代码，故该「已验证」作废；引擎删除后同一份检查才退化为只能报空洞 PASS 的假保障，检查 4 已在 P8 重写。需真人有声环境跑 `npm run verify:voice` 重做；见计划「撤回说明」与 README「语音验收台」）
- **P7**：9 / 9 个 Task ✅（自动化全绿；端到端验证通过 —— 同一句话第二次跑时命中历史、预填参数、不再追问澄清）
- **P8（子项目 1）**：8 / 8 个 Task 已实施 —— 自动化全绿、类型同步门禁通过、服务可绑定。
  ⚠️ **真人有声环境的人工验收 6 项「待人工验收」**，由用户对照麦克风逐条执行
  （见计划 Task 8 与 README「语音验收台」）；**未通过人工验收前不得宣称唤醒可用**。
  子项目 2 / 3 / 4 未开始。

> 每完成一个 Task：在对应计划里勾选 `[x]`，并更新上方「总体进度」计数。
> 每完成一个阶段：对照该计划末尾的「验收清单」与「审查清单」，通过后把状态改为 ✅，并做阶段小结提交。

## 桌面端（暂停开发，不再迁移）

桌面原生悬浮球（PySide6 窗口 + 托盘）与本地常驻语音监听曾作为 P4 方向开发：

- **桌面悬浮球 UI**（PySide6 / 早期 Tauri 尝试）：已完成 WIP 快照，代码迁移至 **`desktop-ball` 分支**，主分支已移除。
- **本地常驻语音监听**：已随桌面端一并移除，代码在 `desktop-ball` 分支。

**决策**：桌面端**不再迁移回主分支**。当前语音交互由浏览器端**本地 VAD 分段 + 云端唤醒判定** + 后端 ASR 承担，
主分支以此为唯一语音入口；`desktop-ball` 分支保留为历史快照。

## 当前主分支功能基线

| 能力 | 说明 |
|------|------|
| 语音交互 | 浏览器本地 VAD 分段 + `POST /api/voice/wake` 云端判定唤醒词（衍衡 / 洛吉斯）+ 后端 OpenAI 兼容 ASR/TTS + SpeechSynthesis 播报 |
| 语音隐私 | ⚠️ 每次检测到人声都会把该片段上传云端 ASR（你 `config.yaml` 里 `asr` 指向的 endpoint，不是某个固定服务商），**无论是否唤醒**；VAD 只减少上传次数，不是隐私屏障（详见 README「安全」/ wiki/Security.md） |
| 任务编排 | 意图 → 任务 → 澄清 → 确认 → 执行 → 汇报，SSE 事件流 + 人类在环问答通道 |
| 执行层 | Shell / Python（独立进程、可 kill 进程树）、文件系统（10+ 通用格式）、GUI 自动化、环境感知 |
| 记忆/RAG | 长期事实记忆（facts.sqlite）+ 任务后 LLM 提取 + 关键词 RAG 上下文注入 |
| 能力扩展 | MCP 客户端与桥、Skills 热加载、cron 定时（无人值守）、多智能体协调者 |
| 控制 | CancellationToken 贯穿全链路：stop_task / stop_step / pause + taskkill /T 兜底 |
| 测试 | 40 个 pytest 文件覆盖各层（`python -m pytest tests/ -q`） |
| 定时被拒提醒 | 定时任务无人应答的高风险操作自动拒绝后，记 warning + 落盘会话历史（控制台可见） |
