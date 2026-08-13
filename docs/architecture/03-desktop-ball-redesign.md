# 桌面悬浮球 · 架构重设计

> 版本 v2 · 2026-08-13 · 目标：一个真正可靠、常驻、可用的桌面悬浮球。
> 背景：v1 用「Tauri + webview 加载远程 URL」做透明无边框球，反复出问题（远程页 IPC/安全限制、透明窗口与 DPI、webview 的坑）。

## 0. 问题复盘（为什么 v1 不行）

| v1 的问题 | 根因 |
|---|---|
| 拖动不生效 | 球页从 `http://127.0.0.1:8520` 远程加载，Tauri 默认不注入 IPC → `data-tauri-drag-region` 失效；要能力文件+安全配置才放行 |
| 悬浮球「在页面里面」 | 做了 380×520 的 webview 面板，不是小圆球 |
| 透明/窗口/DPI 怪异 | webview 渲染在透明无边框窗口上，Windows 的 DPI 缩放、合成、命中测试都容易出偏差 |
| 改样式要重建 | 前端打进 exe 才生效；走远程 URL 又引来安全限制 |
| 编译/打包重 | Rust + MSVC 工具链 + 几百个 crate + PyInstaller sidecar |

**本质**：把「常驻桌面小球」这种*原生窗口*需求，硬套在「网页/webview」上，两头都不讨好。

## 1. 架构原则（重新确立）

1. **后端是唯一大脑**：P0–P3 全部能力（编排/工具/记忆/MCP/定时/语音监听）都在 FastAPI(8520)，不动。
2. **桌面球 = 薄的原生窗口客户端**：只负责「一个圆 + 状态环 + 点击交互 + 迷你历史」，用**原生控件**画，不嵌 webview。
3. **完整控制台留在浏览器**：现有 Vue 8-Tab 版已完善，球点击在浏览器打开 `/console`。关浏览器不影响球。
4. **语音监听在后端**（WakeListener 已有），球只调用后端端点开关。
5. **样式可改**：球用 Qt 样式表（QSS）集中管理主题（颜色/圆角/发光），改一处全局生效。

## 2. 目标架构

```
┌─ 桌面悬浮球（原生 PySide6，新）─────────────────┐
│  ● 无边框透明置顶小圆窗（~80px，QPainter 画球+状态环）│
│  ● 拖拽移动 / 单击弹迷你面板 / 双击语音 / 右键菜单     │
│  ● 迷你面板：近期对话摘要（原生列表）+ 输入框          │
└───────────────┬─────────────────────────────┘
                │ HTTP / SSE (127.0.0.1:8520)
┌─ 后端 FastAPI（既有，唯一大脑）────────────────┐
│  编排/工具/记忆/MCP/定时/WakeListener/SSE       │
│  +新增 3 个轻量端点（见 §4）                    │
└─────────────────────────────────────────────┘
        │ 打开浏览器
        └─▶ /console（现有 Vue 控制台，未变）
```

## 3. 为什么选原生 PySide6（而非继续 Tauri）

| 维度 | 原生 PySide6 小球 | Tauri webview 球（v1） |
|---|---|---|
| 透明无边框置顶圆窗 | Qt 原生支持，成熟可靠，DPI 自适应 | webview 合成透明，有坑 |
| 拖拽 | 原生鼠标事件，天然可靠 | 依赖 IPC/data-tauri-drag-region + 安全配置 |
| 命中测试（透明区不挡桌面） | `setMask`/形状窗口 | 需额外配置 click-through |
| 依赖 | 仅 PySide6（纯 Python，可 PyInstaller 打包） | Rust+MSVC+sidecar |
| 样式 | QSS（集中主题，改样式即改 QSS） | CSS（更灵活但受 webview 限制） |
| 迷你历史/输入 | 原生 QListWidget/QLineEdit | 依赖前端 Vue 组件重载 |

**结论**：对「一个圆 + 状态 + 几个交互」这种需求，原生 Qt 远比 webview 简单可靠。控制台那种重 UI 才值得用 web，而它留在浏览器即可。

## 4. 模块设计

### 4.1 桌面球应用（新 `desktop_py/`）
```
desktop_py/
├── main.py              # QApplication 入口：起/停后端、建球窗口、托盘
├── backend_runner.py    # 启动/停止 uvicorn(8520)（或探测外部已运行）
├── ball.py              # 球窗口：QPainter 画圆+状态环，鼠标拖拽/点击/双击
├── mini_panel.py        # 迷你面板：近期对话摘要列表(QListWidget) + 输入框(QLineEdit)
├── tray.py              # QSystemTrayIcon：显示/隐藏、打开控制台、退出
├── api.py               # 薄 HTTP 客户端：/api/status、/api/voice/utter(SSE)、/api/config…
└── theme.py             # QSS 主题集中管理（颜色/圆角/发光）
```
- 球状态：轮询 `/api/status`（idle/listening/recording/thinking/done…）→ 换环色/图标。
- 迷你面板数据：`/api/session/recent` 返回最近几轮 `[你:..., 小逻:..., 工具...]`，原生列表展示。
- 输入：SSE 调 `/api/voice/utter`，流式把回复 append 到面板 + 刷新 recent。

### 4.2 后端新增（轻量，3 个端点）
| 端点 | 作用 |
|---|---|
| `GET /api/status` | 返回当前助手状态 + 最近 activity 摘要（供球轮询，~1s） |
| `GET /api/session/recent` | 最近 N 轮对话（编排管线每次落 `data/recent_turns.json` 滚动缓冲） |
| `POST /api/voice/toggle` | 开关后端 WakeListener（麦克风常驻） |

后端其余全部复用；`data/recent_turns.json` 由 pipeline 完成一轮后写一条。

### 4.3 交互
- **拖拽**：球本体 mousedown→move→up 移动窗口（原生）。
- **单击**：切换迷你面板（近球弹出）。
- **双击**：`POST /api/voice/toggle`（语音唤醒）。
- **右键**：菜单（打开控制台 / 显示隐藏 / 退出）。
- **托盘**：常驻图标，保证球被误关也能恢复。

### 4.4 打包
`pyinstaller --onefile --noconsole desktop_py/main.py` → `无限逻辑悬浮球.exe`。随它内联（或要求）8520 后端；不依赖浏览器。

## 5. 样式方案
- 所有颜色/圆角/发光集中在 `theme.py` 的 QSS 字符串 + 少量常量。
- 改主题（换品牌色/深色浅色/发光强弱）= 改 QSS 一处，重启球生效（可做热重载）。
- 球本体圆环颜色按状态映射（idle 灰 / listening 青 / recording 红 / thinking 橙…），与浏览器一致。

## 6. 里程碑与验收
| 阶段 | 内容 | 验收 |
|---|---|---|
| M1 原生球 | ball.py + tray + 后端 /api/status | 桌面上一个小圆球，拖得动、置顶、透明、托盘在 |
| M2 迷你面板 | mini_panel + /api/session/recent + 输入 SSE | 点球出面板，显示最近几轮，能输入对话 |
| M3 语音+收尾 | /api/voice/toggle + 双击唤醒 + 打包 | 双击开麦克风，关浏览器球仍常驻，exe 可用 |

## 7. 备选：仍想用 Tauri
若坚持 Tauri，v2 修正方向：
- 前端**打进资源**（frontendDist），不走远程 URL → IPC/拖拽/安全全通；
- 透明窗口用 `windows_transparent` 特性，球页面 CSS `background:transparent`；
- 放弃「改样式不重编」（Tauri 打包后改样式需重编，除非仍走 URL）。
代价仍高（Rust+MSVC+sidecar），收益不大。**建议不选**。

## 8. 结论
- **采用原生 PySide6 小球**：可靠、简单、纯 Python、可打包，控制台留在浏览器，后端不动。
- 保留 v1 已产出的**前端 `ball.html` 独立入口**（后续若想给球加网页版界面仍可用），但桌面球本体不再依赖它。
