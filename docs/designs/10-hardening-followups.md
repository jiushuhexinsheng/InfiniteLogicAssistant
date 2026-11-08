# 加固与缺陷修复执行清单（2026-11）

> 来源：2026-11-05 全仓分析。批次 1–3 已落地；批次 4–6 是剩余工作。
> 每项都给出可执行改动点与验收口径，接手时按顺序做即可。

## 状态

| 批次 | 内容 | 状态 |
|---|---|---|
| 1 | KWS 上传闸门 + 唤醒/partial 配置生效 | ✅ 已完成（`27e7481`） |
| 2 | 本地服务来源校验 + 子进程环境 + 原子写 | ✅ 已完成（`27e7481`） |
| 3 | 拼音逐字符对齐 + 共享向量中英混合用例 | ✅ 已完成（本清单同批提交） |
| 4 | 前端四个已确认缺陷 + 低风险附带修复 | ✅ 已完成 |
| 5 | 会话生命周期 / 执行层 / 多智能体 / LLM 客户端 | ✅ 已完成 |
| 6 | 死功能清理与文档对账 | ✅ 已完成 |

**已定决策**：工具权限默认保持三档全放行（用户 2026-11-05 明确要求），后续不再改默认值。

**待定决策**：任务知识库是「下线 UI/API」还是「重新接线」。建议先下线（当前无任何写入方），产品定义「成功任务」后再恢复。

---

## 批次 4：前端缺陷

### 4.1 `--rainbow` / `rainbow-hue` 未定义

- 现状：`AssistantPanel.vue:77-83`、`FloatBall.vue:445-455` 使用 `var(--rainbow)` 与
  `animation: rainbow-hue`，全仓无定义 → 聆听/作答/录音状态的面板与悬浮球背景可能整条失效。
- 改动：`web/src/styles/tokens.css` 增加 conic-gradient 变量与 keyframes；若 `filter`
  与发光冲突，改用 `@property --rainbow-angle` 旋转；`prefers-reduced-motion` 下关闭动画。
- 验收：点击 mic 进入聆听后，面板/悬浮球边框呈彩色且动画运行；`shot-all.mjs` 增加
  「点击 mic 后的 listening 态」截图。

### 4.2 设置保存后运行时配置不热同步

- 现状：`useAssistant.init()` 有 `initialized` 幂等闸（`useAssistant.ts:18-42`），设置页
  `refreshConfig()` 只更新 `app.config`，不会重新应用到 `wakeKeywords/vadConfig/callConfig/
  hardwareConfig/streamingEnabled`。
- 改动：抽出 `applyServerConfig(config)`；`App.vue` watch `app.config` 深度调用；
  `wakeKeywords` 整体替换，其余配置先重置默认再合并。
- 验收：修改唤醒词/续聊窗/idle 超时/输入设备后保存，不刷新页面即生效。

### 4.3 起始页「语音设置」落到空白菜单

- 现状：`OrbHero.vue:73-77` 设 `activeMenu='tts'`，但设置菜单只有
  `llm/voice/permissions/advanced`（`configDefs.ts:46-53`），`ConsoleSettings.vue:24-40`
  无 fallback → 右侧空白。
- 改动：改为 `activeMenu='voice'`；如需直达合成页，在 settings state 增加
  `activeVoiceTab` 并让 `VoiceSettingsPage` 初始化读取。
- 验收：点击后进入语音设置概览（或合成 Tab），页面非空。

### 4.4 「清空对话」不重置后端会话

- 现状：`storeMessages.clearMessages()` 只清 `messages/tokenUsage`
  （`storeMessages.ts:68-71`），`currentSessionId` / `pendingQuestion` 仍保留；下一次发送
  继续带旧 `session_id`。
- 改动：清空前 `abortChat()`；同时重置 `currentSessionId`、`pendingQuestion`、
  `tokenUsage`，并清理 localStorage 中对应会话。
- 验收：清空后下一次 `sendText` 的请求体不带旧 `session_id`；后端历史不被续写。

### 4.5 附带低风险修复

| 项 | 文件 | 改动 |
|---|---|---|
| 按钮作答 source 错误 | `QuestionBlock.vue:68-78` | `sendAnswer` 传 `source='button'` |
| 工具状态被折叠为 error | `blocks/normalize.ts:195` | 保留 `cancelled/denied` |
| 长 TTS 吃掉续聊窗 | `wake/watches.ts` | 播报结束时若回合已完成，重新进入/续期 followup |
| WS 断线不重连 | `stream/streamClient.ts`、`micControl.ts` | `onClose` 在非主动停止时指数退避重连，代际号防覆盖 |
| 并发 final 去重 | `wake/orchState.ts`、`streamFlow.ts` | 恢复 `turnToken` 的实际消费（异步段结束后校验代际） |
| 历史切换并发 | `ConsoleHistory.vue:105-122` | 回合进行中先 `abortChat()` 或禁止切换 |

---

## 批次 5：会话生命周期与执行层

### 5.1 会话 TTL 误清扫

- `core/api/state.py:101-164`：`session_ts` 只在注册时写；`sweep()` 会 pop 仍在运行的
  sessions/controllers/runs，且不取消 runner。
- 改动：事件产生时刷新 `session_ts`；`sweep()` 跳过 `runs[sid]` 未完成的会话；
  `cleanup()` 先取消 runner 并收尾再移除。
- 测试：长任务跨 TTL、正在提问、断线宽限三种场景都不被误删。

### 5.2 预投递回答 / ask 竞态

- `pipeline.py:176-199`：`answer()` 不检查 `awaiting_answer`；`ask()` 先入队 question、
  后置标志（`:121-125`），stop 落在窗口内会漏掉弃题。
- 改动：`answer()` 仅在 `awaiting_answer` 为真时投递；`ask()` 先置标志再入队，异常回滚；
  `/api/voice/answer` 失败返回 409。

### 5.3 历史覆盖竞态

- 新回合读历史 → 启动新 run → 收尾旧 run；旧 run 的整段覆盖式 `save_conversation`
  可能覆盖新历史。
- 改动：按 session 串行（会话锁），或 `HistoryStore.save_conversation` 改增量 upsert；
  推荐后者（`core/session/history.py:134-163`）。
- 测试：交错收尾/启动，最终历史包含两轮消息。

### 5.4 shell / python 取消与进程树

- `core/execution/shell.py`：外部取消已补杀树，但仍需覆盖 `run_python` 的临时文件清理与
  子进程退出；确认 POSIX `start_new_session` 与 Windows `taskkill /T` 都有回归测试。
- 测试：取消任务后进程树消失；中文 cmd 输出可读（已在批次 2 完成解码回退）。

### 5.5 多智能体

- `core/agent/coordinator.py`：
  - `run_coordinator(..., pause=..., cancel=...)`，子代理每步检查取消；
  - `agent_type` 必须在 `{planner,doer,searcher}`，否则按 `doer`；
  - 子任务数受 `agent.max_subtasks`（默认 6）限制；
  - `_save_artifact` 用白名单类型并校验目标在 `data/agent_outputs/<session_id>/` 内；
  - 子代理调工具传 `session`（技能确认链路一致）；
  - 多代理 `done.summary` 只放语音摘要（≤60 字），完整报告放 steps/产物路径。
- 测试：路径穿越、空拆解、子任务失败、暂停/取消传播。

### 5.6 LLM 客户端

- 熔断器按 `(provider, endpoint, model)` 分桶，避免一个 profile 阻塞 judge/confirm/RAG；
- 共享 httpx client 的 timeout 按请求传入（connect/write/pool + profile read timeout）；
- 修正 HALF_OPEN 单探针在第一次探针结束后失效的问题；
- 空模型名在配置校验阶段拒绝。
- 测试：per-profile 熔断、timeout 透传、HALF_OPEN 并发探针。

---

## 批次 6：死功能与文档

### 6.1 任务知识库（待决策）

- 现状：`TaskStore.record()/find_similar()` 无运行时调用，`/api/library` 永远为空，
  README 仍描述为生效特性。
- 建议：前端移除「任务库」tab 与 `ConsoleLibrary.vue`；后端 `/api/library` 保留一个版本并
  返回空列表/410；`core/tasks/store.py` 保留但标注 dormant；README 删除相关段落。
- 备选：在成功且调用过工具的回合影 `TaskStore.record()`，恢复「相似任务预填」——需先定义
  「成功」与隐私边界，不建议与本次同批。

### 6.2 文档对账清单

| 文件/位置 | 现状 | 修正 |
|---|---|---|
| `README.md:29,120-122,185` | 对话/任务模式、完成后询问 | 删除，改为“单一 ReAct 管线，必要时只问一次” |
| `README.md:33-34` | 任务知识库 | 删除或标注停用 |
| `README.md:313-314` | `via=wake\|transcribe` | 改为 `via=stream`（已于批次 1 更新） |
| `README.md:408-409` | 旧唤醒目录（wakeChain/webSpeech） | 更新为 `micControl/orchState/wakeOrchestrator/watches` |
| `README.md:268,362` | “模型不入库” | 改为“ONNX/BIN 走 Git LFS，约 1GB” |
| `README.md:220,360` | dev 依赖缺 ruff | 补 `ruff` |
| `wiki/API.md:3,29` | “无 WebSocket”与下文矛盾 | 删除“无 WebSocket”，补全 models/hardware/capabilities/schema/engines/pause |
| `docs/architecture/roadmap.md:16,35,66` | 验收状态矛盾、测试计数过期 | 统一为已通过；计数从实际测试输出生成 |
| `docs/updates.md:285-286` | 旧的 via=wake/transcribe grep | 改为 `via=stream` |
| `docs/designs/09` | `frame_ms`、浏览器 TTS | 删除/标注已退役 |
| `core/api/voice/run.py:70-73` | mode=task 注释 | 改为“兼容字段，已忽略” |
| `core/api/voice/stats.py:2,37` | “三前缀” | 改为“单前缀 stream” |

### 6.3 防漂移

- 新增轻量 `tests/test_docs_consistency.py`：README API 表中的端点必须存在于 openapi；
  已删除路由/文件名不得再出现；`via=` 只允许 `stream`。
- CI 增加该测试；PR 模板增加文档检查项。

---

## 统一验收

```powershell
python -m pytest tests/ -q
python -m mypy core/ server.py
ruff check core/ server.py main.py cli/
npm --prefix web test
npm --prefix web run build
python scripts/gen_openapi.py   # 与 web/src/api/generated.ts 对比无漂移
```

建议按批次 4 / 5 / 6 分别提交，前端缺陷与后端生命周期不要混在一个 commit。
