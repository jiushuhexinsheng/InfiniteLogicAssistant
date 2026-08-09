# FloatingAssistant 组件 RGB 重构 — 设计文档

日期：2026-08-09
状态：已确认（用户审批通过）

## 背景

`FloatingAssistant.vue`（约 860 行）是悬浮球语音助手组件，当前为单体结构：

- 模板内含 悬浮球 / 迷你播放条 / 悬浮窗 / 状态栏 / 消息列表 / 操作栏 六个区块
- 样式为纯 slate 灰蓝配色，与整体「深空背景 + 品牌三色渐变」风格脱节
- 状态视觉（图标 / 文案 / 颜色 / 特效类）分散在 `useAssistant.ts` 与组件模板 / CSS 多处硬编码

本次重构目标：

1. 让组件更符合整体风格（深空背景 `#020617~#1e293b` + 品牌渐变标题同款配色）
2. 增加 RGB 效果：默认品牌渐变，聆听 / 录音状态切换彩虹循环
3. 拆分原子子组件，提升可维护性与可扩展性

## 已确认需求（决策记录）

| 项 | 决定 |
|---|---|
| RGB 含义 | 品牌三色渐变（靛蓝 `#a5b4fc` → 青 `#67e8f9` → 绿 `#6ee7b7`）为默认；聆听 / 录音切彩虹 `hue-rotate` 循环 |
| 作用范围 | 悬浮球光环 / 面板边框 / 状态指示灯 / 气泡与按钮细节 |
| 视觉强度 | 克制高级：渐变描边 + 柔和光晕；状态色保留为识别色点缀；彩虹仅出现在聆听 / 录音 |
| 文件组织 | 拆分子组件（`components/assistant/` 子目录） |
| 模板结构 | 允许整体重构，但行为与对外接口不变 |

## 目标文件结构

```
web/src/
├── styles/
│   └── assistant.css                # 设计令牌（品牌渐变/彩虹/状态色）+ 通用渐变工具类
├── composables/
│   ├── useAssistant.ts              # 状态机（保留对外接口不变）
│   └── useAssistantVisuals.ts       # 状态视觉配置（数据驱动，扩展核心）
└── components/
    ├── FloatingAssistant.vue        # 入口容器：组合子组件 + 面板展开/拖拽位置管理
    └── assistant/
        ├── FloatBall.vue            # 悬浮球：球体 + 品牌渐变环 + 彩虹激活 + 拖拽
        ├── MiniPlayer.vue           # 迷你播放条（聊天实时预览 + eq 渐变）
        ├── AssistantPanel.vue       # 面板容器（渐变边框 + 深空晕染背景）
        ├── StatusBar.vue            # 状态栏（状态灯 + 标签 + 开启/关闭）
        ├── MessageList.vue          # 消息列表（滚动 + 空态提示）
        ├── MessageItem.vue          # 消息项（气泡/工具调用/时间/插槽）
        └── ActionBar.vue            # 操作栏（清空/收起）
```

## 可扩展性机制

### 1. 状态视觉配置化（核心）— `useAssistantVisuals.ts`

导出数据驱动配置 `STATE_VISUALS`，每个状态一行，组件全部按配置渲染：

```ts
export interface StateVisual {
  icon: string        // 状态图标（球体 / 状态栏）
  label: string | ((kw: string) => string)   // 状态文案；函数形态用于动态唤醒词（listening）
  color: string       // 状态识别色（点缀）
  fx: string          // 特效类名（fx-idle / fx-listening …）
  grad: 'brand' | 'rainbow'   // 渐变模式：默认品牌，聆听/录音彩虹
}

export const STATE_VISUALS: Record<AsstState, StateVisual> = {
  idle:         { icon: '🤖', label: '双击唤醒',            color: '#6b7280', fx: 'fx-idle',          grad: 'brand' },
  listening:    { icon: '👂', label: kw => `聆听中…说"${kw}"`, color: '#34d399', fx: 'fx-listening', grad: 'rainbow' },
  recording:    { icon: '🔴', label: '录音中…',             color: '#f87171', fx: 'fx-recording',     grad: 'rainbow' },
  transcribing: { icon: '⏳', label: '识别中…',             color: '#c084fc', fx: 'fx-transcribing',  grad: 'brand' },
  thinking:     { icon: '🤔', label: '思考中…',             color: '#fb923c', fx: 'fx-thinking',      grad: 'brand' },
  tool_calling: { icon: '🔧', label: '执行中…',             color: '#22d3ee', fx: 'fx-tool_calling',  grad: 'brand' },
  responding:   { icon: '💬', label: '',                    color: '#818cf8', fx: 'fx-responding',    grad: 'brand' },
  done:         { icon: '✅', label: '完成',                color: '#34d399', fx: 'fx-done',          grad: 'brand' },
  error:        { icon: '❌', label: '出错了',              color: '#f87171', fx: 'fx-error',         grad: 'brand' },
}
```

- **新增状态 / 调整样式只改这一处**，组件与 CSS 无需改动
- `useAssistant.ts` 的 `stateLabel` / `stateColor` 改为引用本配置，删除内部硬编码 map
- `useAssistant.ts` 返回 `visual`（当前状态的 StateVisual 响应式对象），子组件消费

### 2. CSS 设计令牌 — `assistant.css`

集中定义视觉令牌，供所有子组件引用：

```css
:root {
  --brand-c1: #a5b4fc;                       /* 靛 */
  --brand-c2: #67e8f9;                       /* 青 */
  --brand-c3: #6ee7b7;                       /* 绿 */
  --brand-grad: linear-gradient(135deg, var(--brand-c1), var(--brand-c2), var(--brand-c3));
  --rainbow: conic-gradient(from 0deg,
    #ef4444, #f97316, #eab308, #22c55e, #06b6d4, #3b82f6, #a855f7, #ef4444);
  --panel-bg: rgba(15, 23, 42, .92);
  --border-base: #334155;
}
```

另提供通用工具类：`.grad-text`（渐变文字）、`.grad-border`（渐变描边圆角容器）、`.grad-glow`（品牌光晕）。

### 3. Slot 扩展点

- `FloatingAssistant.vue` 暴露 `#actions`、`#footer` 插槽（面板底部扩展区）
- `MessageItem.vue` 暴露 `#tool-actions` 插槽（未来工具按钮挂载点）
- 未使用的插槽保持默认渲染，避免破坏现有界面

## 各子组件职责

| 组件 | 职责 | Props（主要） | 事件 |
|---|---|---|---|
| FloatingAssistant | 入口容器：组合子组件；面板展开/收起；悬浮球拖拽位置管理 | asst | — |
| FloatBall | 悬浮球球体、品牌渐变环、彩虹激活特效、拖拽/点击/双击交互、新消息红点 | pos, state, visual, messageDot | drag, click, dblclick |
| MiniPlayer | 面板收起时的迷你播放条（实时预览 + eq 渐变条 + 隐藏按钮 + 边界翻转） | pos, state, visual, lastMsg, partialText | click(展开), dismiss |
| AssistantPanel | 面板骨架：渐变边框、深空晕染背景、拖拽手柄、插槽接线 | state, visual, panelStyle | close |
| StatusBar | 状态点/标签/状态行/开启关闭按钮 | state, visual, statusLine, wakeEnabled | toggleWake |
| MessageList | 滚动容器 + 空态提示（按状态显示） + 滚动到底 + 新消息红点 | messages, state, visual | — |
| MessageItem | 单条消息：气泡、工具调用标签与详情、时间、插槽 | message | toggleToolDetail |
| ActionBar | 清空 / 收起按钮 | — | clear, close |

所有子组件**单向收 Props、发事件**，状态机 `useAssistant` 仍是唯一数据源。

## RGB 视觉方案（方案A）

### 悬浮球 FloatBall
- 默认：品牌渐变描边环（1.5px，`grad-border` 技巧）+ 慢呼吸光晕（三色晕染，`box-shadow` 动画）
- `listening` / `recording`：描边与光晕切换彩虹 + `hue-rotate` 360° 循环
- 保留现有 radar / spin / shake 等状态特效，配色改为品牌渐变基调

### 面板 / 迷你播放条
- 面板：1px 品牌渐变细边框（`background-clip` 双层技巧，支持圆角）；激活状态边框切彩虹
- 背景顶部叠加品牌色 `radial-gradient` 晕染，贴近 App 深空背景
- 迷你条：同款渐变边框 + eq 音量条从纯绿改为品牌渐变

### 状态指示灯
- 状态点默认品牌渐变；聆听 / 录音时渐变 + 呼吸发光
- 状态识别色（STATE_VISUALS.color）保留为小色点/徽章点缀，保证可读性

### 气泡 / 按钮
- 用户气泡：品牌渐变背景 + 白字（替换现纯蓝 `#3b82f6`）
- 助手气泡：暗色底 + 品牌渐变左边框（2px）
- 操作按钮：hover 渐变背景或渐变下划线

### 性能
- 彩虹 `hue-rotate` / 渐变动画只作用于小元素（球体、状态点、迷你 eq），不做大面 filter
- 动画仅用 `transform` / `opacity` / `filter`，必要时 `will-change`
- 保留深色底保证文字对比度；渐变只作点缀不作大面积背景

## 保持不变（迁移安全）

- **对外接口**：`App.vue` 仍 `import FloatingAssistant` 并传 `:asst`，调用方零改动
- **行为**：拖拽、双击唤醒、迷你条边界翻转、消息滚动到底、新消息红点、状态机流转全部保留
- **状态机**：`useAssistant` 的返回接口（state / messages / wakeKeyword / partialText / statusLine / init / toggleWake / clearMessages / destroy …）不变，仅内部 label/color 改引用共享配置

## 验收标准

1. `npm run build`（vue-tsc + vite build）通过，无类型错误
2. 拆分子组件后行为与原版一致：拖拽 / 双击唤醒 / 迷你条 / 消息滚动 / 状态灯 / 清空收起均正常
3. RGB 视觉生效：球体默认品牌渐变、聆听 / 录音切彩虹；面板 / 迷你条 / 气泡 / 按钮应用渐变
4. 新增一个测试状态可仅通过 `STATE_VISUALS` 一处配置完成（可扩展性自检）
5. `App.vue` 与 `useAssistant` 调用方无改动（`git diff` 校验）
