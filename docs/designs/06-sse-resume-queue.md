# 06 · SSE 断线恢复（seq + ring buffer + resume）+ 消息排队

> 借鉴：Dify（ping 保活、run_id + 断线 state snapshot 回放）、LibreChat（Resumable Streams）、
> Open WebUI（回复期间消息队列）。优先级 P3。**放大 01 批 3 的宽限能力**：先有「断线不死」，再有「重连续播」。

## 实施状态

- **全三批已完成（2026-09-30）**：
  - 批1：`state.RunHandle`（seq + ring buffer maxlen=500）；`_stream_run` 为唯一
    seq 编号/入 buffer 点；15s 空闲 `{"type":"ping"}` 保活；前端 seq 游标去重 +
    ping 看门狗（35s 无帧判死）；
  - 批2：断线 → `server.resume_grace_s`（默认 120，0=旧行为）宽限看门狗，到期未重连
    fail-closed 收尾落盘；`POST /api/voice/resume`（缺口回放 + 挂接实况，抽成
    `_replay_then_live` 便于直驱测试）；404 `no_run` → 前端固定兜底文案；同 id 新
    utter 先 `_retire_run` 旧运行（新回合取代语义）；收尾幂等（`closed` 护栏 +
    看门狗不自 cancel）；
  - 批3：useChat `outbox` 排队 + `outboxCount` 徽标（ChatInput 可点击清空）+
    `runGen` 代际守卫（根治 onAbort done 覆盖 thinking 的竞态，全部 handler 过
    `alive()`）+ 待答问题时 sendText 转作答语义（选项 trim 精确匹配 → choice）+
    取消词立即中止清队。
- **与设计的偏差**：① ping **不占 seq 不进 buffer**（只做心跳，回放只需真实事件）；
  ② `abortChat` 补调 `/task/{sid}/stop` —— 宽限机制下「断线不再自动杀任务」，
  取消按钮必须显式停服端（新回合取代路径由 utter 侧 `_retire_run` 负责）；
  ③ resume 404 前端只给固定文案，历史重载交由用户刷新（自动 switchSession 重载未做）；
  ④ TestClient 的流式断连在本环境不可靠 → 断连/回放测试改为事件循环内直驱生成器
  （`gen.aclose()` 等价 HTTP 断开）。
- **触发的既有守卫**：`test_audio_upload_audit_prefix_is_shared` 按设计把
  `/api/voice/resume` 归入「不携带音频」白名单（新端点必须显式分类）。
- **回归修复（2026-09-30 真人验收发现）**：排队闸门首版把「非 done/error/idle」一律
  当回合中 —— 而唤醒指令落在 `listening`、续聊接话落在 `followup`，这些语音链状态没有
  在跑的回合会触发 `flushOutbox`，消息入队即**永久卡在「排队」**（现场：唤醒后说「你好」
  只显示排队）。修复：闸门收窄为**仅** `thinking/tool_calling/responding` 三个真正的回合
  状态，语音链状态一律直发；回归测试覆盖 5 个语音态直发 + 3 个回合态入队。
- 测试：pytest 512 绿（新增 `test_sse_resume.py` 6 例）、vitest 267 绿（新增
  seq/ping/resume 3 例 + 排队与状态闸门 11 例，另更新 2 例断线文案契约）、mypy 干净、
  build/gen:api 通过。

## 1. 现状（问题定位）

| # | 现状 | 位置 | 问题 |
|---|---|---|---|
| 1 | 唯一 SSE 端点 `POST /voice/utter`；**无 ping 保活、无 id/seq、无 resume** | `core/api/voice.py:351-383` | 中段断线无法续 |
| 2 | 断开 → `finally` cancel runner + persist + cleanup | `voice.py:376-381` | 任务死亡（01 批 3 先解「等确认时不死」） |
| 3 | 前端 `MAX_RETRY=1` 且**仅「零事件时网络错」重试**；中段断 → `onError` 不重试（防重复执行——合理，但没有恢复路径） | `web/src/api.ts:283,378-393` | 刷新/瞬断 = 丢半回合 |
| 4 | `sendText` fire-and-forget：发送中再发 → abort 旧流；**onAbort 异步置 `state='done'` 与新回合 `state='thinking'` 有时序竞态**（代码注释自认） | `useChat.ts:24-34,126-134` | 用户连发两条会丢/乱序 |
| 5 | 事件有公共 `turn_id` 字段，无序号 | `core/orchestrator/events.py:30` | 回放没有游标 |
| 6 | 会话占用判定：`awaiting_answer` → 409；其他情况同 id 再 utter 会覆盖注册表 | `voice.py:311-349` | 保持此语义，resume 不与之冲突 |

## 2. 目标行为

1. **ping 保活**：流空闲每 15s 发 ping，前端 watchdog 35s 无任何帧 → 判定断线。
2. **可回放**：每个事件带递增 `seq`；服务端每会话保留 ring buffer；`POST /api/voice/resume {session_id, last_seq}` 重连续播（缺口回放 + 挂接实况）。
3. **断线任务不死**：连接丢失进入 grace（与 01 批 3 合并实现），期间 runner 继续跑、事件继续进 buffer。
4. **消息排队**：回合进行中用户再发 → 入队，回合收束自动连发；显式取消/打断仍立即生效；顺带修 `state` 竞态。

## 3. 设计

### 3.1 服务端：RunHandle + seq + ring buffer

`core/api/state.py` 注册表扩展（每 session 一个）：

```python
@dataclass
class RunHandle:
    run_id: str                 # = turn_id，首事件下发
    runner: asyncio.Task
    channel: EventQueueChannel
    buffer: deque[tuple[int, dict]]   # (seq, payload)，maxlen=500
    next_seq: int = 1
    connected: bool = True
    grace_task: asyncio.Task | None = None
```

- **seq 注入点唯一**：`event_stream` 的 yield 前（`voice.py:351-375` 循环内）——`payload["seq"] = run.next_seq` 后 append buffer 再 yield。`ping` 帧也占 seq（`{"type":"ping","seq":n}`），保证「收到的每帧都有序号」。
- **断线判定**：yield 抛 `GeneratorExit` / `CancelledError` → `connected=False`；若 runner 未完成 → 启动/保留 grace（01 批 3 逻辑：`server.resume_grace_s` 默认 120s，awaiting_answer 时按 01 规则），**不 cancel**；到期 cancel + persist + cleanup + buffer 清空。
- **重连** `POST /api/voice/resume`（新文件挂 voice router）：
  1. 查 RunHandle：有 → 从 buffer 回放 `seq > last_seq`，然后挂接实况（复用 `event_stream` 的循环体，抽出为 `_stream_run(run, from_seq)`）；
  2. run 已完成（buffer 尚在 grace 前）→ 回放剩余 + `done`；
  3. 无 RunHandle → 查 history.db 该会话最近消息 → 返回 404 语义 `{"ok": false, "recovered": "history"}`，前端走「重载历史」兜底；
  4. `awaiting_answer` 且带 `last_seq` 落后于 QuestionEvent → 回放中自然重发 question，前端 `pendingQuestion` 幂等重建（qid 相同 → 覆盖无害）。
- **ping**：`event_stream` 循环 `events.get()` 包 `asyncio.wait_for(..., timeout=15)`，超时 yield ping 帧。
- **与 409 关系**：resume 不创建新 runner，与「同 id 新 utter」互斥——同 id 在 run 存活期（含 grace）收到新 utter：若 `connected=False` 且在 grace → 视为「前端重发」冲突，仍 409 `正在执行中`（前端有排队队列后不会走到这里）；`connected=True` 维持现状语义。

### 3.2 前端：watchdog + 自动恢复（`api.ts`）

- `streamUtter` 维护 `lastFrameAt`；收到任何帧（含 ping）刷新。35s 无帧 或 读流抛网络错 → 进入恢复：
  `POST /voice/resume {session_id, last_seq}`，退避 1s/3s 共 2 次；
  - 成功 → 继续按现有分发逻辑消费（事件天然幂等吗？**注意**：`applyEvent` 对 `content_delta` 是追加合并——回放若重发已收到的 seq 会被跳过：`if (payload.seq && payload.seq <= lastSeq) continue;` **这行是恢复正确性的关键**）；
  - 404 recovered=history → `onError('连接中断，已恢复历史')` + 触发 `switchSession` 重载（现有 `getHistoryDetail` 路径）；
  - 2 次失败 → 现状 `onError`。
- ping 帧在 `api.ts` 分发前拦截（不进 `applyEvent`，未知 type 本来会被 normalize 忽略，但显式拦截可重置 watchdog）。

### 3.3 消息排队（`useChat.ts`）

```ts
const outbox: string[] = [];          // 待发文本

function sendText(t: string) {
  if (isCancelCommand(t)) { abortChat(); outbox.length = 0; return; }  // 「停止/取消/暂停」立即生效
  if (state.value !== 'done') { outbox.push(t); setBadge(); return; }  // 回合中 → 排队
  addMessage('user', t); void runTurn();
}
// onDone / onAbort / onError 收束后：flush outbox（逐条 addMessage+runTurn，队列空才停）
```

- **竞态修复**：引入 `runGen`（回合代际，仿 `speakGen`）——所有 `state` 转移与 `onDone/onAbort/onError` 回调先比对 gen，旧回合的迟到回调直接丢弃。这根治「onAbort 异步 done 覆盖新回合 thinking」的自认竞态。
- **语义边界**：排队 = 用户连发；`abortController.abort()`（新回合打断旧回合）**只保留**在显式取消与 barge-in 新回合（02）路径——排队后 `runTurn` 只在 `done` 态被调，天然不再 abort 活着的回合。
- **语音路径兼容**：语音 `sendText`（唤醒指令/followup 窗口）同样入队——说话人连说两句，第二句排队等第一回合结束，不再触发「abort 杀旧回合」连锁（与 turnToken 防双执行互补：turnToken 防同一段双触发，本机制防回合互杀）。
- UI：输入框上方出「排队中 N 条」小胶囊，可点击清空（`outbox.length=0`）。
- 注意与 01 的关系：回合中带 `pendingQuestion` 时 `state==='done'`? —— 现状 question 到达后流还在跑（state 非 done），**排队会把用户想答的话压住**。规则补充：`pendingQuestion` 存在时 `sendText` 不排队、直接走 `sendAnswer` 语义判断（选项匹配/文本作答）——实际上语音路径已这么走（pendingQuestion 优先通道），文本路径 `sendText` 需同样前置判断：有 pendingQuestion 且输入命中选项/即作答 → 转 `sendAnswer`。**这条防止排队机制吞掉作答。**

## 4. 实施步骤

| 批次 | 内容 | 验收 |
|---|---|---|
| **批 1** | §3.1 seq + buffer + ping；§3.2 前端 seq 去重 + ping watchdog（只保活不恢复） | 弱网 15s 不误报断线 |
| **批 2** | resume 端点 + grace 衔接（01 批 3）+ 前端自动恢复 + history 兜底 | 中途掐网 5s，恢复后续播且不重复 |
| **批 3** | §3.3 排队 + runGen 竞态修复 + pendingQuestion 转发规则 | 连发两条都执行；作答不被排队吞 |

## 5. 测试计划

- **pytest**：seq 单调且每帧有；buffer 回放缺口正确（last_seq=3 → 从 4 起）；ping 超时触发；断线 grace 内 runner 存活、到期 cleanup；resume 四分支（活 run/已完成/无 run/等待确认）；同 id 冲突 409。
- **vitest**：seq ≤ lastSeq 跳过（回放不重复追加）；watchdog 35s 判死；resume 退避 2 次后 onError；history 兜底走 `switchSession`；**排队**：回合中 sendText 入队、done 后自动发、取消命令清队、`pendingQuestion` 时转作答不排队、runGen 丢弃旧回合迟到 onDone（修竞态的回归用例）。
- **手动**：任务执行中掐网 5 秒再恢复；执行中连打两句观察排队徽章。
