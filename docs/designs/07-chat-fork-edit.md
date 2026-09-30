# 07 · 会话分叉（Fork）与消息编辑重发

> 借鉴：LibreChat（消息树 + 三种 fork 粒度）、Open WebUI（从任意消息 fork 为新会话）。
> 优先级 P3。**架构决策：线性编辑 + 显式分叉，不做消息树**——本项目 `save_conversation`
> 是整段覆盖式（`history.py:102-132`），树形分支需引入 parent 指针并改写全部读写路径，
> 收益覆盖不到 10% 场景；「保留旧路径」由 fork 承担即可（LibreChat 的树本质也是为保留旧路径）。

## 实施状态

- **批1-3 已完成（2026-09-30）**：
  - 后端：`HistoryStore.fork_conversation`（前缀复制 + 名字标注「分叉自」，源只读）+
    `POST /api/sessions/{sid}/fork`（400 越界/缺参、404 无源、409 正在等待回答、audit
    `session-fork`；响应复用 SessionCreateResponse/SessionOut——**不带 messages**，前缀核对
    走存储，前端本地截断不依赖响应消息）；
  - store/useChat：`forkAt`（成功 → 本地截断 + 切换会话 id + 清 pending/用量；失败写系统
    消息）、`sendEdited`（非末条**必须先 fork**、末条防御性截尾，改写后 runTurn）、
    `regenerate`（分叉到原问题含该条 → 去掉本条回复 → 原话重跑）；三者经 useAssistant
    暴露；
  - UI：MessageItem hover 动作条（user=编辑/分叉，assistant=重新生成/分叉）+ 内联编辑
    （保存并重发/取消/Esc）；`canAct = 回合空闲 && 有服务端会话` 由 ConsoleConversation
    计算下发；ConsoleMessageList 透传 index/emits。
- **边界（按设计）**：回合进行中动作禁用；无 `currentSessionId`（纯本地线程）禁用分叉——
  本地 localStorage 单线程无法保旧路径，宁可禁用；树形分支明确不做。
- 测试：pytest 514 绿（fork 前缀/源只读/参数校验 2 例）、vitest 259 绿（forkAt 成败、
  末条/非末条编辑、regenerate 4 例 + 既有 mock 补丁）、mypy 干净、gen:api/build 通过。

## 1. 现状（问题定位）

| # | 现状 | 位置 | 机会 |
|---|---|---|---|
| 1 | 零编辑/零 fork/零重发能力（全库 grep 无） | — | 补功能 |
| 2 | **后端种子入口已备好**：`streamUtter(..., messages)` 可传任意多轮历史；`run_pipeline(messages=...)` 接受并规范化 | `web/src/api.ts:270-282`、`pipeline.py:207-245` | 编辑重发 = 传截断后的 messages，**后端零改动** |
| 3 | `buildHistory()` 只取最近 6 条喂下一轮 | `store.ts:325-345` | 编辑后自动生效，无需改 |
| 4 | 会话/历史 API：`GET/POST/PATCH/DELETE /sessions`、`GET /history/{id}`，**无 fork** | `core/api/sessions.py`、`history.py` | 加一个端点 |
| 5 | `persist()` = 该会话消息 **DELETE 后全量 INSERT** | `history.py:102-132` | ⚠️ 编辑截断若直接重跑会**覆盖原记录** → fork 必须先行 |
| 6 | 消息级操作只有工具级 retry/cancel | `useChat.ts:193-245`、`ConsoleMessageList.vue:18-19` | UI 挂载点现成 |
| 7 | `MAX_MESSAGES=200`（localStorage）+ 旧快照丢弃 | `store.ts:69,192-230` | fork 载入沿用上限 |

## 2. 目标行为

1. **Fork**：任意消息处「从这里分叉」→ 复制前缀消息为新会话并切换；原会话原样保留。
2. **编辑重发**：编辑某条用户消息 → 若其后还有消息则**自动先 fork 再改发**（原路径保留）；若其后无消息则原会话直接重发。
3. **重新生成**：对某条助手回复「重新生成」→ 自动 fork 到该回复之前的用户消息，用**原话**重跑一轮。
4. 分叉后的会话在历史列表可见（名字标注来源），其余能力（归档/重命名/清空）全兼容。

## 3. 设计

### 3.1 后端：fork 端点（唯一新增）

```
POST /api/sessions/{sid}/fork
body: { "up_to": <int 消息下标, 含该条> }          # 或 { "up_to_msg_id": ... }（阶段二）
200 → { "ok": true, "session": { id, name, ... } }
400 越界 / 404 不存在 / 409 会话正在等待回答
```

实现：`core/session/history.py` 新增

```python
def fork_conversation(src_id: str, up_to: int) -> str:
    msgs = get_conversation(src_id)["messages"][: up_to + 1]
    new_id = uuid4().hex[:12]
    save_conversation(new_id, name=f"分叉自 {原名或src_id短号}", msgs)   # 复用现有整段写入
    return new_id
```

- 走既有 `save_conversation`（全量 INSERT），对原会话**只读**，天然满足 §1.5 的覆盖风险约束。
- 认证/鉴权与 `sessions.py` 其余端点一致；写操作进 audit（`fork from= to= n=..`）。
- 旧库兼容：读路径缺 blocks 的消息已被历史迁移清除（`history.py:63`），fork 无旧格式包袱。

### 3.2 前端：store 与 api

- `api.ts` 新增 `forkSession(sid, upTo)` → 返回新会话元数据。
- `store.ts` 新增动作：

```ts
async function forkAt(index: number) {
  const { session } = await api.forkSession(currentSessionId!, index);
  // 切换：复用 switchSession(session.id, msgs)——msgs 用 GET /history/{new_id} 拉取，
  // 或本地直接截断 messages[0..index] 免一次往返（选后者：离线也快，服务端已持久）
  switchSession(session.id, messages.slice(0, index + 1));
}
```

- `sendEdited(index, newText)`（编辑用户消息）：
  1. `index < messages.length - 1` → `forkAt(index)`（提示条：「已创建分叉以保留原记录」）；
  2. `messages[index] = 改写后的 user 消息（blocks 重置为单 text 块）`；
  3. 截断 `messages = slice(0, index+1)`；
  4. `runTurn()`（种子走 `buildHistory`，现状 6 条窗口自动生效）。
- `regenerate(index)`（编辑助手消息）：找到该回复**之前**最近的 user 消息 `u` → `forkAt(u-1)`（不含原回复）→ `sendText(原 user 文本)`。
- **与排队（06 批 3）协同**：编辑/重发都是显式动作，走 `state==='done'` 断言；回合中点编辑 → 按钮置灰（不做隐式排队）。

### 3.3 UI：消息级操作（`ConsoleMessageList` / `MessageItem`）

- hover 工具条（沿用 retry/cancel 的 emit 模式，`ConsoleConversation.vue:7` 收口）：
  - user 消息：**编辑**（inline textarea，保存即 `sendEdited`）、**从处分叉**（`forkAt`）；
  - assistant 消息：**重新生成**（`regenerate`）、**从处分叉**；
  - 语音悬浮面板不做消息级操作（空间不足，控制台是唯一入口——与 retry/cancel 现状一致）。
- 分叉后 toast + 历史列表刷新（`GET /api/sessions` 现有查询）。
- 确认交互：**fork 与「编辑自动 fork」不弹二次确认**（纯增量、可回原会话）；`regenerate` 不确认（原路径已保留）。

### 3.4 边界与限制（明示）

| 场景 | 处理 |
|---|---|
| fork 超过 `MAX_MESSAGES=200` | 载入时保留**尾部** 200 条并 toast（与现有 switchSession 行为一致） |
| fork 一个正在等待确认的会话 | 409（进行中的 run 不可分叉）；前端按钮在 `state!=='done'` 时禁用 |
| 分叉会话再次分叉 | 允许（纯复制，无深度问题） |
| localStorage 与服务端一致性 | fork 后本地快照即新会话；原会话快照未动 |
| 树形分支 | **不做**（见架构决策）；如将来要做，messages 表加 `parent_id` 是唯一改动面，本设计的 forkAt/index 语义可平移 |

## 4. 实施步骤

| 批次 | 内容 | 验收 |
|---|---|---|
| **批 1** | §3.1 fork 端点 + pytest | curl fork 后原会话不变、新会话前缀一致 |
| **批 2** | §3.2 store/api 三动作 + §3.3 hover UI | 分叉/编辑/重生成全链路可用 |
| **批 3** | 边界加固（409、200 条、toast）+ 06 协同（done 断言） | 回合中按钮禁用；超限截尾 |

## 5. 测试计划

- **pytest**：`tests/test_api_history/sessions` 扩展——fork 前缀正确（含 blocks/turn_id/ts）、越界 400、源不存在 404、audit 落行、原会话字节级未变（fork 前后 `get_conversation` 快照断言）。
- **vitest**：`store.spec`——`forkAt` 截断+切换+id 变更；`sendEdited` 短路径（末条直接改）与长路径（自动 fork）；`regenerate` 找到正确 user 消息；`MAX_MESSAGES` 截尾；`ConsoleMessageList` 工具条 emit 映射。
- **手动**：改一句早先的话 → 生成新分支 → 历史列表两个会话可切换对照。
