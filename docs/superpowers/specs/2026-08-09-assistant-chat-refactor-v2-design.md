# FloatingAssistant 第二轮重构 — 设计文档

日期：2026-08-09
状态：已确认（用户审批通过）

## 背景

`FloatingAssistant.vue` 刚完成第一轮重构（拆分子组件 + 品牌渐变/彩虹 RGB 视觉）。本轮在上一轮基础上做第二轮重构：

- **视觉**：SVG 图标集替换 emoji、悬浮球分层、气泡精致化、工具时间轴
- **功能**：手写轻量 markdown、角色头像、录音进度环、工具重试/取消
- **结构**：面板重构为「三段式聊天窗口」并**新增文字输入**

## 已确认需求（决策记录）

| 项 | 决定 |
|---|---|
| 整体方向 | 视觉升级 + 功能增强，**先出整体方案，分阶段实施** |
| 图标体系 | 自建 SVG 集（~30 个手写 inline 组件，零依赖，颜色随主题） |
| 内容渲染 | 手写轻量 markdown（粗体/斜体/行内代码/代码块/链接/列表/换行，XSS 安全） |
| 悬浮球结构 | 多层组合球（渐变环 + 状态特效 + SVG 图标 + 状态徽章 + 录音进度环） |
| 工具显示 | 纵向时间轴（步骤图标+名称+状态+耗时，展开详情，重试/取消） |
| 面板结构 | 三段式聊天窗口（顶栏 / 消息区 / 输入栏） |
| 语音归属 | 语音状态/开关保留在悬浮球上，面板顶栏只放只读状态指示 |
| 文字输入 | 自适应 textarea（1~4 行），Enter 发送 / Shift+Enter 换行 |
| 语音关系 | 文字与语音可同时进行，共用一条 LLM 管线 |

## 目标文件结构

```
web/src/
├── components/
│   ├── Icon.vue                      # SVG 图标组件（统一图标源）
│   ├── MarkdownRenderer.vue          # 手写轻量 markdown 渲染（纯展示）
│   └── assistant/
│       ├── FloatBall.vue             # 重构：多层组合球（语音状态/开关）
│       ├── AssistantPanel.vue        # 重构：三段式聊天窗口骨架
│       ├── PanelHeader.vue           # 新增：顶栏（头像+名称+状态+关闭）
│       ├── MessageList.vue           # 重构：纯消息区（滚动+空态）
│       ├── MessageItem.vue           # 重构：头像+头部+markdown+工具时间轴
│       ├── ToolTimeline.vue          # 新增：工具纵向时间轴
│       ├── ChatInput.vue             # 新增：自适应文字输入栏
│       └── ActionBar.vue             # 删除（功能并入 PanelHeader / ChatInput）
├── composables/
│   ├── useAssistant.ts               # 新增 sendText()；state/visual 等保留
│   └── useAssistantVisuals.ts        # icon 字段 emoji → SVG 名
```

## 各模块设计

### 1. SVG 图标集 — `Icon.vue`

统一组件 API：`<Icon name="mic" :size="20" color="currentColor" />`

- 24×24 viewBox 描边风格（stroke=currentColor，stroke-width=1.8）
- ~30 个手写图标路径，按组：
  - **状态**：wave / ear / mic / sparkles / clock / brain / wrench / chat / check / alert
    （对应 idle / listening / recording / transcribing / thinking / tool / responding / done / error）
  - **工具**：chat / wrench / 通用 tool
  - **操作**：trash / chevron-down / close / play / stop / dots / send
  - **角色**：小逻头像（渐变圆底 + 图案）、用户（person）
- 图标名常量导出 `ICON_NAMES`，`STATE_VISUALS.icon` 从 emoji 改为 SVG 名
- 颜色默认 `currentColor`，状态图标由 `visual.color` 传入
- 替换全部 emoji：状态球图标、工具标签图标、操作按钮、顶栏/输入栏图标

### 2. 多层组合球 — `FloatBall.vue`

```
┌─ 外层：品牌渐变环 + 状态特效(fx-*) ─┐
│  ┌─ 状态环：recording 时 conic 进度环 ─┐
│  │   ┌─ 内核：SVG 图标(visual.icon) ─┐  │
│  │   └──────────────────────────────┘  │
│  └────────────────────────────────────┘
│  徽章：状态点(visual.color) / 新消息红点
└───────────────────────────────────────┘
```

- 聆听/录音彩虹 `hue-rotate` 循环保留
- **录音进度环**：recording 状态显示 conic 进度环（随 VAD 计时/时长上限推进）
- **语音开关保留在球上**：新增可点击 mic 徽章（👂 状态点击 = toggleWake，与双击一致），面板顶栏不再放开关

### 3. 三段式聊天窗口

**PanelHeader**（顶栏）
- 小逻渐变头像 + 名称"小逻" + **只读状态指示**（状态点 + 状态文字，来自 `visual`）
- 右侧：清空（🗑）、关闭（✕）
- 不含语音开关（语音在球上）

**MessageList**（消息区）
- 纯滚动容器 + 空态提示（保留）；去掉原状态栏职责

**ChatInput**（输入栏）
- 自适应 textarea（1~4 行自动增高，超出滚动）
- Enter 发送 / Shift+Enter 换行
- 右侧发送按钮（SVG send 图标）
- 发送调用 `useAssistant.sendText(text)`
- 输入框在聆听/录音时**不禁用**（可同时进行）

**ActionBar** 删除：清空/收起已并入 PanelHeader。

### 4. 气泡结构 — `MessageItem.vue`

```
┌ 角色头像 ┬ 角色名 ───────┬ 时间 ┐
│         ├ 消息内容 (MarkdownRenderer) │
│         ├ 工具时间轴 (ToolTimeline)   │
│         └ [插槽 #tool-actions]        │
└─────────┴──────────────────────────┘
```

- **角色头像**：助手 = 小逻渐变头像（与球体视觉一致）；用户 = 用户 SVG 图标/首字母；系统无头像
- **头部**：角色名 + 时间（紧凑）
- **内容**：`MarkdownRenderer` 渲染，XSS 安全
- 结构语义化：msg-avatar / msg-meta / msg-content / msg-footer

### 5. 工具时间轴 — `ToolTimeline.vue`

```ts
interface ToolStep {
  id: string
  name: string
  icon: string            // SVG 名
  status: 'queued' | 'running' | 'done' | 'failed'
  durationMs?: number
  args?: Record<string, any>
  result?: string
}
```

- props: `steps: ToolStep[]`
- emits: `retry(stepId)` / `cancel(stepId)`
- 状态对齐：`queued` 对应现有 `ToolCall.status` 的 `'pending'`（时间轴展示名），映射在接线层处理
- 每步纵向排列：图标 + 名称 + 状态徽章 + 耗时；点击展开参数/结果（保留现有 JSON 详情）
- running/queued 提供取消，failed 提供重试
- 纯数据驱动，新增工具类型只加数据

### 6. 文字输入 + 消息管线

- `useAssistant` 新增 `sendText(text: string)`：
  1. `addMessage('user', text)`
  2. 复用现有 `handleLLM(text)` 管线（与语音转文字完全同路径）
- 并发说明：语音与文字共用单一状态机与 `/api/ai/chat`；若一轮 LLM 进行中又发送，消息按完成顺序追加（多轮并发请求各自 `addMessage('assistant', ...)`），状态以最后完成者为准
- `handleLLM` 内部 `SYSTEM_PROMPT` 不变

### 7. 轻量 markdown — `MarkdownRenderer.vue`

- 纯展示组件：`props { text: string }` → 渲染安全 HTML
- 支持：粗体 `**x**` / 斜体 `*x*` / 行内代码 `` `x` `` / 代码块 ` ``` ` / 链接 `[t](url)` / 无序列表 `- ` / 有序列表 `1. ` / 换行
- 实现：先 HTML 转义（防 XSS），再按 token 正则安全替换
- 不引入第三方依赖

## 分阶段实施

### 阶段 A（视觉）
1. `Icon.vue` 图标集 + 全部 emoji 替换（含 `STATE_VISUALS.icon` 改 SVG 名）
2. 多层组合球 `FloatBall`（分层 + mic 徽章开关）
3. 三段式面板骨架：`PanelHeader` / `MessageList` 重构 / `ChatInput` 外壳 / 删除 `ActionBar` / `AssistantPanel` 调整
4. 气泡头像 + 头部

### 阶段 B（功能）
1. `MarkdownRenderer` 接入气泡内容
2. `ToolTimeline` 数据驱动 + 展开详情 + 重试/取消接线（`useAssistant.handleAction`）
3. 录音进度环
4. `sendText` 文字输入接线（Enter/Shift+Enter）
5. 流式打字效果（可选）

## 保持不变（迁移安全）

- **对外接口**：`App.vue` 仍 `import FloatingAssistant` 传 `:asst`，调用方零改动
- **行为**：球体拖拽、双击唤醒、迷你条边界翻转、消息滚动、新消息红点、状态流转、彩虹/品牌渐变视觉全部保留
- **状态机**：`useAssistant` 对外返回接口保留，仅新增 `sendText`；`visual` 字段沿用

## 验收标准

1. `npm run build`（vue-tsc + vite build）通过，无类型错误
2. 全部 emoji 图标替换为 SVG；`STATE_VISUALS.icon` 为 SVG 名
3. 悬浮球为多层结构：渐变环 + SVG 图标 + 状态徽章；recording 显示进度环；聆听/录音彩虹循环保留
4. 面板为三段式：顶栏（头像+名称+只读状态+清空+关闭）/ 消息区 / 输入栏
5. 文字输入：Enter 发送、Shift+Enter 换行、自适应增高；发送消息与语音共用 LLM 管线，助手回复正常
6. 气泡含头像/头部/内容；助手消息 markdown 渲染正常（粗体/代码/列表/链接）
7. 工具调用以纵向时间轴展示，可展开详情，failed 可重试、running 可取消（事件已接线）
8. `App.vue` 与 `useAssistant` 调用方零改动（`git diff` 校验）
