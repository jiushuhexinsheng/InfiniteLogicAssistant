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
| P6 | 语音作答 + 无应答待机 + 再唤醒续答（子系统 C） | ✅ 已完成 | [2026-09-13-voice-answering.md](../superpowers/plans/2026-09-13-voice-answering.md) | 播报后自动开录、直接语音作答；播报期间暂停监听。**2026-10-07 取消限时回答**：「无应答进待机 / 再唤醒续答本题」机制已删除（回答永不限时），待答期间改为**先判唤醒词、命中即弃题开新轮**，验收台第 2 项随之改判弃题契约 （2026-10-07 起取消限时回答，待答期命中唤醒词即弃题；人工语音验收已在 P8 于 2026-10-12 通过，自动化全绿）真观测**（当时 `WakeWordEngine` 尚在，样本里非零的「播报前 12/22」可证），但它测的引擎与门控机制**已随唤醒链路重构整体删除并替换**，结论无法迁移到当前实现 —— 该「已验证」作废。此后引擎删除、探针目标消失，同一份检查才退化成只能报空洞 PASS 的假保障，故检查 4 已在 P8 重写；现 4 项编号为 1 播报作答 / 2 待答弃题 / 3 播报不自触发 / 4 通话免唤醒。需真人有声环境跑 `npm run verify:voice` 重做，详见计划「撤回说明」与 updates.md 语音验收台节）** |
| P7 | 任务知识库（子系统 E） | ⏹ 已下线 | [2026-09-13-task-knowledge-base.md](../superpowers/plans/2026-09-13-task-knowledge-base.md) | **2026-11 下线**（docs/designs/10 6.1）：TaskStore 无运行时写入方，任务库页面永远是空的；前端 tab 与组件移除，`/api/library` 列表恒空、详情/删除 410，`core/tasks/store.py` 休眠待未来重新接线 |
| P8 | 唤醒链路重构（**子项目 1 / 4**：VAD → KWS(API) → ASR） | ✅ 已完成 | [2026-09-13-wake-detection-rework.md](../superpowers/plans/2026-09-13-wake-detection-rework.md) · [验收记录](../superpowers/plans/2026-09-13-wake-detection-rework-verification.md) | 浏览器本地 VAD 切段 → 本地 sherpa-onnx KWS 闸门判定「衍衡」「洛吉斯」（未命中不上云）→ 云端/本地 ASR 抬指令；Vosk 引擎与 43MB 模型全部删除。**2026-10-12 真人有声环境人工验收通过**（硬门槛解除）。子项目 2（本地 KWS）✅ 2026-09-26；子项目 3（ASR 三模式 local/cloud/hybrid）✅ 2026-10-12；子项目 4（能力探测与链路接线）✅ 随同批交付 |

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
- **P6**：9 / 9 个 Task ✅（自动化全绿；人工语音验收已在 P8 于 2026-10-12 通过）
- **P7**：⏹ 已下线（2026-11，docs/designs/10 6.1）—— 无运行时写入方，任务库不再出现在界面
- **P8（子项目 1）**：8 / 8 个 Task 已实施 —— 自动化全绿、类型同步门禁通过、服务可绑定。
  ✅ **真人有声环境的人工验收已于 2026-10-12 由用户对照麦克风逐条执行并通过**
  （见计划 Task 8 与 README「语音验收台」）；硬门槛解除，唤醒链路自此可宣称可用。
  子项目 2（本地 KWS）✅、子项目 4（有序回退链 + 能力探测）✅ 已于 2026-09-26 随
  唤醒链路大修交付；子项目 3（本地 ASR）✅ **2026-10-12 交付，方向调整为「ASR 三模式设置」
  （`voice.asr.mode`：本地 / 云端 / 混合），未作为回退链的候选档**（见 updates.md 与
  wiki/Configuration.md）。

> 每完成一个 Task：在对应计划里勾选 `[x]`，并更新上方「总体进度」计数。
> 每完成一个阶段：对照该计划末尾的「验收清单」与「审查清单」，通过后把状态改为 ✅，并做阶段小结提交。

## 桌面端（暂停开发，不再迁移）

桌面原生悬浮球（PySide6 窗口 + 托盘）与本地常驻语音监听曾作为 P4 方向开发：

- **桌面悬浮球 UI**（PySide6 / 早期 Tauri 尝试）：已完成 WIP 快照，代码迁移至 **`desktop-ball` 分支**，主分支已移除。
- **本地常驻语音监听**：已随桌面端一并移除，代码在 `desktop-ball` 分支。

**决策**：桌面端**不再迁移回主分支**。当前语音交互由浏览器端**本地 VAD 分段 + 本地 KWS 唤醒判定** + 后端 ASR 承担，
主分支以此为唯一语音入口；`desktop-ball` 分支保留为历史快照。

## 当前主分支功能基线

| 能力 | 说明 |
|------|------|
| 语音交互 | 浏览器本地 VAD 分段 → **本地 sherpa-onnx KWS 闸门**判定唤醒词（衍衡 / 洛吉斯，未命中不上云）→ 命中才调 ASR 抬指令 + 本地 Kokoro / 云端 API 合成播报（浏览器 SpeechSynthesis 已退役） |
| 语音隐私 | **本地 KWS 前置闸门（2026-09-26 起默认开启）**：没说唤醒词的人声段在本机直接丢弃、**不出本机不上云**；只有命中段上传云端 ASR。`kws.enabled: false` 或模型缺失时闸门旁路，才回到「每次人声段都上云」（详见 README「安全」/ wiki/Security.md） |
| 任务编排 | 意图 → 任务 → 澄清 → 确认 → 执行 → 汇报，SSE 事件流 + 人类在环问答通道 |
| 执行层 | Shell / Python（独立进程、可 kill 进程树）、文件系统（10+ 通用格式）、GUI 自动化、环境感知 |
| 记忆/RAG | 长期事实记忆（facts.sqlite）+ 任务后 LLM 提取 + 关键词 RAG 上下文注入 |
| 能力扩展 | MCP 客户端与桥、Skills 热加载、cron 定时（无人值守）、多智能体协调者 |
| 控制 | CancellationToken 贯穿全链路：stop_task / stop_step / pause + taskkill /T 兜底 |
| 测试 | pytest 全量 738 用例覆盖各层（`python -m pytest tests/ -q`）+ 前端 85 个 Vitest spec、461 用例（`npm --prefix web test`） |
| 定时被拒提醒 | 定时任务无人应答的高风险操作自动拒绝后，记 warning + 落盘会话历史（控制台可见） |
