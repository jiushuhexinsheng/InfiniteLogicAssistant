# 01 · 确认链韧性：持久化/断线恢复 + 拒绝理由回传 + 安全清单核对

> 借鉴：OpenAI Agents SDK（RunState 可序列化审批）、Claude Code（拒绝附评论回传）、
> OpenHands（WAITING_FOR_CONFIRMATION 原子挂起）。**不含沙箱**。
> 优先级 P0。依赖：无（06 SSE 回放完成后其能力被进一步放大）。

## 实施状态

- **批 1 已完成（2026-09-29）**：§3.3 拒绝理由（`ConfirmResult` 贯穿 confirm_tool /
  confirm_if_needed / executor / agent-base / skills / pipeline 摘要）+ §3.5 超时
  （`agent.confirm_timeout_s`，timeout 源 answer 事件收卡）与空回答短路（不再对空文本
  调 LLM）。落地与设计的两处偏差：① `/api/tools/call` 实为 confirm 标记机制、不走
  `confirm_tool`，故只改了两个确认调用点 + skills/pipeline 两个消费点；② 审计行新增
  `reason=` 字段。批 2/3/4 未实施。
- 测试：pytest 494 绿（新增 9 个用例）、mypy 干净、vitest 223 绿、vue-tsc/build 通过、
  `gen:api` 已重跑。

## 1. 现状（问题定位）

| # | 现状 | 位置 | 后果 |
|---|---|---|---|
| 1 | `ask()` = `await self.answers.get()` **无限期阻塞、无超时** | `core/orchestrator/pipeline.py:151` | 没人应答则协程永久挂起 |
| 2 | 等待状态全在进程内存（`answers` 队列、`awaiting_answer`、`pending_qid`） | `pipeline.py:114-124` | 进程重启全丢，问题无痕 |
| 3 | SSE 断开 → `finally` 里 `runner.cancel()` **整条管线立即中止**（含挂起的 ask） | `core/api/voice.py:376-381` | 刷新页面/断网 = 任务死亡 + 待答问题丢失 |
| 4 | 落盘只在流结束时 `state.persist()`，best-effort | `voice.py:380`、`core/api/state.py:101-137` | 中途崩溃无任何痕迹 |
| 5 | 工具级拒绝回传固定串 `"Error: 操作者拒绝调用 {name}"` | `core/orchestrator/executor.py:141-143` | LLM 不知被拒原因，可能原样重试 |
| 6 | 任务级拒绝不回传 LLM、直接 `cancelled` 收束 | `pipeline.py:285-289` | 合理（不续跑），但用户理由无处展示 |
| 7 | 定时任务 `_SilentChannel` 返回空 `Answer()` → `_resolve_confirm` 返回 None → **对空文本发起一次 LLM 判定** | `core/scheduler/runner.py:19-40`、`confirm.py:95-100,125` | 无人值守每次确认都白烧一次 LLM 调用 |
| 8 | `qid` 已有配对校验（错 qid 409、`pending_qid` 答后清空） | `pipeline.py:174-179`、`voice.py:416-421` | ✅ 已达标项，保持 |

## 2. 目标行为

1. **断线不丢**：SSE 断开时若正等确认，runner 与问题保留一个宽限期；页面刷新后问题可恢复展示并正常作答。
2. **重启可界定**：进程重启后，待答问题从 DB 可查；**任务级**确认可重放（执行未开始），**工具级**确认 fail-closed 标失效并通知（执行已中途，不盲目续跑）。
3. **拒绝可纠偏**：操作者拒绝时可附理由，理由回传 LLM；注入前截断防滥用。
4. **确认可超时**：可配置超时，超时 = fail-closed 拒绝（默认 0 = 维持无限等待）。
5. **安全清单**：审批状态服务端权威、qid 单次消费、防双次投递、定时任务不再空打 LLM。

## 3. 设计

### 3.1 待答问题持久化表（data/history.db 新表）

```sql
CREATE TABLE IF NOT EXISTS pending_questions (
  qid          TEXT PRIMARY KEY,
  session_id   TEXT NOT NULL,
  turn_id      TEXT,
  kind         TEXT NOT NULL,            -- choice | text | composite
  question     TEXT NOT NULL,
  options      TEXT,                     -- JSON 数组
  ctx_kind     TEXT NOT NULL,            -- tool | task | clarify | other
  ctx_json     TEXT,                     -- tool:{name,args} / task:{risk,plan}
  resume_json  TEXT,                     -- 任务级重放载荷 {text, mode, seed_msgs}
  state        TEXT NOT NULL DEFAULT 'waiting',  -- waiting|answered|expired|cancelled
  answer_json  TEXT,                     -- {text, choice, source, reason}
  created      TEXT NOT NULL,
  expires      TEXT                      -- ISO8601, NULL=不过期
);
CREATE INDEX IF NOT EXISTS idx_pq_session ON pending_questions(session_id, state);
```

**写入时机**（全部在后端单点）：
- `EventQueueChannel.ask()` 发出 `QuestionEvent` 后 INSERT（state=waiting）；
- `answer()` 通过 CAS 更新：`UPDATE pending_questions SET state='answered', answer_json=? WHERE qid=? AND state='waiting'`，`rowcount==0` → 拒绝（防双次投递），CAS 成功才 `answers.put_nowait(...)`；
- run 正常结束时该问题仍 waiting → 标 `cancelled`（回合已收束）；
- 宽限期/超时到期 → 标 `expired` + audit。

### 3.2 断线宽限期（对 `voice.py` SSE finally 的改造）

```
SSE 生成器退出（客户端断开）时：
  if channel.awaiting_answer or runner 仍在跑:
      run.connected = False
      启动宽限定时器（server.resume_grace_s，默认 120s）
      不 cancel、不 persist、不 cleanup —— 收尾移交看门狗任务
  else:
      维持现状（cancel + persist + cleanup）

宽限期内重连（06 的 resume 端点；本设计阶段一可先用 3.4 的 pending 查询恢复问题展示）：
  重置定时器，事件继续流动
到期:
  cancel runner + persist + cleanup + pending 标 expired + audit
```

看门狗 = 每会话一个 `asyncio.Task`，挂在 `core/api/state.py` 的注册表上，随 `sweep()` 一并清理。**任务级确认**（`confirm_if_needed`，执行尚未开始）在 `resume_json` 里保存 `{text, mode, seed_messages}`，重启后回答命中时直接 `run_pipeline(..., messages=seed, auto_confirm=True)` 重放；**工具级确认**重启后无 runner 可续 → 标 expired，前端提示「进程已重启，确认失效，任务中止」。

### 3.3 拒绝理由回传

1. `Answer` 增加字段 `reason: str = ""`（`session.py:18-33`）；`_ask_operator` 返回 `ConfirmResult(ok: bool, reason: str)`（新增 dataclass），`confirm_tool` / `confirm_if_needed` 改为返回 `ConfirmResult`（三个调用点同步：`executor.py:141`、`agent/base.py:120-135` 回调、`/api/tools/call`）。
2. **理由来源**：choice=`no` 且同请求带非空 `text` → 该 text 即理由（`/api/voice/answer` 无需改协议，`text`+`choice` 组合已可表达）。
3. 工具级回传 LLM（`executor.py:143` 改）：

```python
msg = f"Error: 操作者拒绝调用 {name}"
if reason: msg += f"（理由：{reason[:200]}）"      # 截断防注入
msg += "。请调整方案、换用其他工具，或先向用户说明后再请求。"
```

4. 任务级：不回传 LLM（保持不续跑），但 `TaskStateEvent(summary=)` 携带理由，前端 summary 卡可见。
5. audit 增补 `reason=` 字段（已有 decision/source 口径不变）。

### 3.4 恢复查询端点 + 前端恢复

- 新端点 `GET /api/voice/pending?session_id=` → `{qid, question, kind, options, ctx_kind}` 或 null（仅 state=waiting 且未过期）。
- 前端：`useAssistant.init` / `switchSession` 时若本地 `pendingQuestion` 为空则查询；命中 → 装载 `pendingQuestion`，QuestionBlock 按现状渲染作答（走既有 `/voice/answer`）。
- 配合 3.2：宽限期内 runner 还活着，answer 照常入队 → 任务无缝续跑。

### 3.5 确认超时（fail-closed）

- 配置 `agent.confirm_timeout_s: int = 0`（0=不限，兼容现行为）。
- 实现：`ask()` 改 `await asyncio.wait_for(self.answers.get(), timeout or None)`，超时 → `Answer(choice="no")` + audit `reason=timeout` + pending 标 expired。
- **定时任务空回答短路**：`_resolve_confirm` 中 `text==""` 且 `choice is None` → 直接返回 None，**跳过 `_resolve_confirm_llm("")`**（一行改动，省掉每次定时确认的白烧调用）。

### 3.6 审批安全清单核对（对照 OpenAI Agents SDK）

| 清单项 | 现状 | 本设计动作 |
|---|---|---|
| 审批状态留服务端 | ✅ answers 队列在后端 | 保持；DB 化见 3.1 |
| 客户端只拿 opaque id | ✅ qid（uuid 片段） | 保持 |
| qid 单次消费 | ✅ pending_qid 答后清空 | 补 DB 层 CAS（3.1）双保险 |
| 防双次投递 | ⚠️ 仅内存检查 | CAS 成功才入队（3.1） |
| 过期机制 | ❌ 无 | `confirm_timeout_s`（3.5） |
| 拒绝理由长度约束 | — | 截断 200 字（3.3） |
| 审批人身份 | localhost 无鉴权（设计边界） | 文档化：非 localhost 已有 `X-API-Token`；README 安全节补一句「answer 端点与全 API 同鉴权」 |

## 4. 实施步骤

| 批次 | 内容 | 可独立验收 |
|---|---|---|
| **批 1** | 3.3 拒绝理由（ConfirmResult 贯穿三点）+ 3.5 超时与空回答短路 | ✅ 全 pytest 绿；LLM 收到理由串 |
| **批 2** | 3.1 pending 表 + CAS + 3.4 端点与前端恢复查询 + QuestionBlock「拒绝理由（可选）」输入 | ✅ 刷新页面问题还在 |
| **批 3** | 3.2 断线宽限 + 看门狗 | ✅ 流式中断 10s 内重连，确认仍可作答 |
| **批 4** | 3.2 任务级重放 / 工具级失效通知（跨重启） | ✅ 重启后任务级确认可续 |

## 5. 测试计划

- **pytest**：`tests/test_orchestrator_confirm.py` 扩展——超时→`choice='no'`+audit；空文本不触发 LLM（mock 计数=0）；`ConfirmResult.reason` 进 executor tool 消息；CAS 双答第二次 409；pending 端点 waiting/过期/answered 三态；SSE 断开宽限（直接驱动 `event_stream` 生成器 close 后断言 runner 未死、看门狗到期后 cleanup）。
- **vitest**：`QuestionBlock.spec` 拒绝理由输入与 `sendAnswer(text,'no')` 透传；`useChat.spec` 启动时 `GET /voice/pending` 恢复 `pendingQuestion`。
- **手动**：语音说「不，先别删」→ LLM 收到理由并改方案；语音拒绝走既有选项匹配（无理由）不回归。
