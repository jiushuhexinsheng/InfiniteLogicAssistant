# 悬浮球桌面化方案 — 关闭浏览器后悬浮球仍常驻

> 版本 v1 · 2026-08-13 · 目标：把浏览器里的悬浮球改造成**独立桌面进程的常驻浮窗**，浏览器可关。
> 决策待定：Tauri / Electron / 纯 Python(PySide6)。

## 0. 目标与约束

- 悬浮球（状态环 + 迷你历史 + 输入 + 语音开关）作为**桌面常驻浮窗**，关浏览器不影响。
- 完整控制台（8 Tab）可开在**桌面壳自带的窗口**里，也可开在默认浏览器。
- 语音监听（WakeListener，已有）继续在**后端 Python 侧**跑，与桌面壳无关。
- 后端 FastAPI（8520）本就常驻，桌面壳只是**薄客户端 + 后端启动器**。
- 数据流完全复用现有 `web/src/api.ts`（SSE `streamUtter`、`/api/*`）。

## 1. 架构总览（三条路线通用）

```
桌面壳应用（新进程，关浏览器不影响）
├── 悬浮球窗口：无边框 / 置顶 / 透明 / 可拖拽（~56px 圆球）
├── 控制台窗口：普通窗口，加载 8-Tab 页面
├── 系统托盘：显示/隐藏球、打开控制台、退出
└── 启动器：随应用启动/停止 Python 后端（sidecar/子进程）
        │
        └──▶ 后端 FastAPI 127.0.0.1:8520（既有全部能力）
                 │  SSE / /api/*
        ◀── 数据流（api.ts 原样复用）
```

关键点：**难点不在功能，在「置顶无边框窗口 + 托盘 + 打包 + 随启后端」四件事**。

## 2. 三路线对比

| 维度 | Tauri | Electron | 纯 Python(PySide6) |
|---|---|---|---|
| 复用现有 Vue 前端 | ✅ 全部 | ✅ 全部 | ❌ 需重写或用 QWebEngineView |
| 包体 | ~5MB | ~80MB+ | ~40MB（Qt） |
| 技术门槛 | 需 Rust 工具链（一次性） | 纯 JS | 纯 Python，无 Node/Rust |
| 托盘 | Tauri v2 原生支持 | electron.Tray | QSystemTrayIcon |
| 打包 | `tauri build` → exe | electron-builder | PyInstaller |
| 后端随启 | Tauri sidecar（PyInstaller 打包后端） | spawn python 子进程 | 同进程/子进程 uvicorn |
| 桌面球 UI | 前端直出（现成 FloatBall） | 前端直出 | 原生重画（QPainter）或嵌 webview |

**推荐**：能接受装 Rust → **Tauri**（体验/体积最优，前端零改动）；否则 **Electron**（纯 JS）。只有想全 Python 才选 PySide6，且要接受球 UI 重写。

---

## 3. 方案 A：Tauri（推荐）

### 目录结构
```
desktop/                       # 新增（仓库内）
├── src-tauri/
│   ├── Cargo.toml
│   ├── tauri.conf.json        # 两个窗口 + 托盘 + sidecar 配置
│   ├── src/main.rs            # 托盘/窗口/后端启动逻辑
│   └── icons/
├── sidecar/                   # Python 后端打包产物（PyInstaller onefile exe）
│   └── assistant-server.exe
└── src/                       # 前端：直接复用 web/src，只加两个入口页
    ├── ball.html / ball.ts    # 悬浮球独立入口（只挂 FloatBall + MiniHistory）
    └── console.html / console.ts  # 控制台入口
```

### 窗口配置（tauri.conf.json 要点）
```json
{
  "app": {
    "windows": [
      { "label": "ball",   "url": "ball.html",   "width": 80, "height": 80,
        "decorations": false, "transparent": true, "alwaysOnTop": true, "skipTaskbar": true, "resizable": false },
      { "label": "console","url": "console.html","width": 1100, "height": 760, "decorations": true }
    ],
    "trayIcon": { "iconPath": "icons/tray.png", "tooltip": "无限逻辑·语音助手" }
  },
  "bundle": { "externalBin": ["sidecar/assistant-server.exe"] }
}
```

### 关键逻辑（main.rs）
- 启动：`Command::new_sidecar("assistant-server")` → spawn 后端（`main.py serve` 的 PyInstaller 版）。
- 托盘菜单：显示/隐藏 ball 窗口、打开 console 窗口、退出（退出时 kill 后端）。
- 拖拽：ball 窗口用 `tauri-plugin-window-state` 或前端 `data-tauri-drag-region` 属性即可拖拽（前端 FloatBall 已实现拖拽逻辑，可直接复用）。

### 前端复用
- `ball.ts`：`useAssistant()`（单例）+ `FloatBall` + `MiniHistory` + `ChatInput`，几乎从 `FloatingAssistant.vue` 拆出。
- `console.ts`：现有 `ConsolePage` 整页。
- `api.ts`/`streamUtter`：**原样复用**，base 指向 `127.0.0.1:8520`。

### 打包
- 前端：`vite build` 产物喂给 Tauri。
- 后端：`pyinstaller --onefile main.py` 产出 sidecar exe（含离线依赖）。
- `tauri build` → `安装包.exe`。双击即：起后端 → 出悬浮球 → 托盘常驻。

---

## 4. 方案 B：Electron

### 目录结构
```
desktop-electron/
├── package.json
├── main.js                 # 窗口/托盘/后端子进程
├── preload.js
└── dist/                   # 现有 web 构建产物（vite build 输出）
```

### 关键逻辑（main.js）
- 创建两个 BrowserWindow：
  - ball：`frame:false, transparent:true, alwaysOnTop:true, skipTaskbar:true, resizable:false, 80x80`，加载 `dist/ball.html`。
  - console：普通窗口，加载 `dist/console.html`。
- 托盘：`new Tray(icon)` + 菜单（显示/隐藏球、开控制台、退出）。
- 后端：`app.start` 时 `spawn('python', ['main.py','serve'])`（或 PyInstaller exe），`app.quit` 时 kill。
- 拖拽：ball 窗口 `-webkit-app-region: drag`（前端加 CSS）或复用 FloatBall 的 JS 拖拽。

### 打包
`electron-builder` → NSIS exe（~80MB，含 Python 后端随装或不含）。

---

## 5. 方案 C：纯 Python（PySide6）

### 目录结构
```
desktop-pyside/
├── app.py                  # QApplication：球窗口 + 托盘 + 起后端
├── ball.py                 # 无边框置顶球窗口（QPainter 画状态环/图标）
├── mini_panel.py           # 迷你历史面板（QListWidget 原生行，或 QWebEngineView 嵌现有页面）
├── tray.py                 # QSystemTrayIcon
└── backend_runner.py       # 线程里起 uvicorn（127.0.0.1:8520）
```

### 关键点
- 球窗口：`Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool`，`setAttribute(Qt.WA_TranslucentBackground)`，QPainter 画圆环；鼠标事件实现拖拽。
- 迷你历史：原生 QWidget 列表（状态文字 + 工具名徽章）→ **UI 要重写**；或 `QWebEngineView` 加载 `http://127.0.0.1:8520` 的球页面 → 复用前端但 +200MB QtWebEngine。
- 托盘：`QSystemTrayIcon` + `QMenu`。
- 后端：同进程 `threading` 起 uvicorn，或依赖外部已启动的后端。
- 打包：PyInstaller onefile（含 Qt）。

---

## 6. 推荐落地步骤（若选 Tauri）

1. `npm create tauri-app` 初始化 `desktop/`，`vite` 指向现有 `web/`。
2. 前端拆两个入口：`ball.html`（FloatBall+MiniHistory）与 `console.html`（ConsolePage）。
3. Rust 侧：双窗口 + 托盘 + sidecar 后端（`pyinstaller main.py`）。
4. 联调：托盘开关球、球拖拽置顶、迷你历史 SSE 实时、控制台打开。
5. `tauri build` 出安装包，关浏览器验证球常驻。

**里程碑验收**：关掉浏览器后——悬浮球仍在桌面、可拖拽/置顶/托盘隐藏、迷你历史显示最近对话、点「完整记录」能再开控制台、语音唤醒可用。

## 7. 复用清单

| 复用 | 来源 | 用于 |
|---|---|---|
| 后端全部（编排/工具/记忆/MCP/定时/voice） | `server.py` + `core/` | 桌面壳的后端 |
| `web/src/api.ts`（SSE streamUtter / /api/*） | 现有前端 | 球/控制台数据流（三路线通用） |
| `FloatBall` / `MiniHistory` / `ChatInput` / `ConsolePage` | 现有前端 | Tauri/Electron 直接复用；PySide6 需重写或嵌 webview |
| `useAssistant` 单例 | 现有前端 | 状态共享 |
| `WakeListener` | `core/voice/wake.py` | 桌面语音（后端侧，三路线通用） |

## 8. 风险与边界

- **透明置顶窗口**在各平台差异：Tauri/Electron 的透明窗口在 Windows 一般 OK；Linux 需合成器支持（本项目 Windows 为主，风险低）。
- **打包体积**：Electron/PySide6 大；Tauri 小但 sidecar 的 Python 后端（含 vosk/模型）会让包体变大——可把模型放安装目录外首次下载。
- **后端随启**：要处理「端口被占」「后端崩溃重启」「退出时干净 kill」。
- **单例冲突**：浏览器版与桌面版**同时开着**时会争同一端口——方案上以桌面版为唯一后端（浏览器版走同一 8520），无冲突。
- **macOS 打包签名/公证**：本项目 Windows 为主，暂不考虑。

## 9. 结论

- **推荐 Tauri**：包体最小、前端零改动、体验最像原生；代价是一次性装 Rust + 用 PyInstaller 打包 Python 后端为 sidecar。
- 不想碰 Rust → **Electron**，同样复用前端，只是重。
- 坚持全 Python → **PySide6**，但悬浮球 UI 需重写或引入重 webview。
