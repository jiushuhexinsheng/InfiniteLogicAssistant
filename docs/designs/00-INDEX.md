# 改进落地设计集（2026-09）

> 来源：与 GitHub 知名同类项目（OpenClaw / Pipecat / Claude Code / OpenAI Agents SDK / Dify /
> mem0 / Open WebUI / Leon / OpenHands 等）逐项对比后，除「工具执行沙箱」外全部改进项的
> 具体落地设计。每份设计 = 现状（file:line 引用）→ 方案 → 分步实施 → 测试计划。
> 现状引用基于 2026-09-29 的代码，实施时若行号漂移以符号名为准。
>
> **实施状态（2026-09-30）：01 批1、02 全部、03 全部（B 节 Go/No-Go=No-Go）、
> 04 全部、05 批1-2、06 全部、07 全部、08 全部 —— 已完成并验证**
> （pytest 524 绿 / vitest 259 绿 / mypy 干净 / gen:api+build 通过）。
> 未做项见各文件「实施状态」节：01 批2-4（pending 表/断线宽限复用 06/跨重启重放）、
> 05 批3（chips 跳转）、08 中 lazy_groups 设置页控件（config-file only）。

## 目录

| 文件 | 覆盖改进项 | 优先级 |
|---|---|---|
| [01-confirm-resilience.md](01-confirm-resilience.md) | 确认状态持久化/断线恢复、拒绝理由回传、审批安全清单核对 | **P0** |
| [02-interruption-streaming.md](02-interruption-streaming.md) | 打断语义（interruptible 白名单）、停止朗读、句级流式 TTS | **P1** |
| [03-voice-conversation.md](03-voice-conversation.md) | 追问/续聊窗口正式化、浏览器端 sherpa-onnx KWS 落地 | **P1** |
| [04-memory-evolution.md](04-memory-evolution.md) | 记忆 ADD-only+有效期+溯源、时间打分、注入预算、path 分层、工具化修正 | **P2** |
| [05-rag-citation.md](05-rag-citation.md) | RAG 引用溯源（citation 事件+来源块）、可选 rerank | **P2** |
| [06-sse-resume-queue.md](06-sse-resume-queue.md) | SSE 断线恢复（seq+ring buffer+resume）、消息排队 | **P3** |
| [07-chat-fork-edit.md](07-chat-fork-edit.md) | 会话分叉（Fork）、消息编辑重发（线性+显式分叉） | **P3** |
| [08-context-agent-governance.md](08-context-agent-governance.md) | 滚动压缩（Condenser）、工具输出截断与渐进式 schema、多智能体委派规范 | **P4** |

## 依赖关系与实施顺序

```
01 确认链韧性 ──依赖──> （无，可立即开工）
06 SSE 恢复   ──受益──> 01（恢复后确认链才能跨断线存活；01 先做「宽限期内不 cancel」，06 做完整回放）
02 打断/流式  ──依赖──> 无；与 03 共用 speaking 状态与回声护栏改动
03 追问窗口   ──依赖──> 02 的 barge-in（阶段二）可后置，阶段一独立
04 记忆进化   ──依赖──> 无（需改 config schema，注意 extra=forbid）
05 RAG 溯源   ──弱依赖──> 04（都动 build_context，建议同一批做）
07 分叉/编辑  ──依赖──> 06（回放避免编辑期间断线丢改写）
08 上下文治理 ──依赖──> 无（纯 executor/coordinator 内部）
```

**建议批次**：① 01 → ② 02+03 → ③ 04+05 → ④ 06 → ⑤ 07 → ⑥ 08。
每份设计内部再分「阶段一（最小可用）/ 阶段二（完整形态）」，可独立验收回滚。

## 横切约定（所有设计共同遵守）

1. **事件契约 additive**：SSE 事件只增字段/增类型，不改既有语义；前端 `normalize.ts` 对未知事件类型必须容忍（现状 `usage`/`done` 不入块，未知类型应同样忽略而非抛错）。
2. **配置同步三处**：`core/config/schema.py`（顶层 `Settings` 是 `extra="forbid"`，新段/字段必须加）→ `core/api/schemas.py`（API 镜像）→ `web/src/components/console/settings/configDefs.ts`（设置页）。
3. **提示词单点**：全部 prompt 改动只动 `core/prompts.py`。
4. **测试三件套**：pytest 后端行为 + vitest 前端行为 + 涉及唤醒/作答语义的走 `tests/data/wake_vectors.json` 共享向量。
5. **审计**：凡影响放行/拒绝/上传的行为变化，延续 `data/audit.log` 记账口径。
