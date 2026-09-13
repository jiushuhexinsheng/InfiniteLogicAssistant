# 无限逻辑 · 语音全控智能体

用语音（或文字）控制电脑上的一切：**唤醒 → 说话 → 意图判断 → 任务编排（澄清/确认/执行/汇报）→ 多智能体协作 + 工具执行 → 记忆/RAG 上下文**。

- 纯浏览器 **Vosk WASM 离线唤醒** + 轻量 Python 后端（FastAPI）
- OpenAI 兼容接口，支持 DeepSeek / OpenAI / 通义 / 小米 MiMo 等多 provider
- 无沙箱设计，以**人类在环确认 + 审计日志**兜底（确认默认已关闭，可在设置页收紧）
- 完全自研编排状态机（不依赖 LangGraph/CrewAI）

## 快速开始

```bash
# 1. 安装依赖（Python 3.14+）
pip install -r requirements.txt      # 或双击 install_deps.bat（在线→离线 wheel 兜底）

# 2. 配置
cp config.yaml.example config.yaml   # 填入 LLM/ASR 凭据（支持 ${ENV_VAR}）

# 3. 启动（一键前端+后端）
python main.py serve                 # 浏览器自动打开 http://127.0.0.1:8520
```

Windows 一键脚本：`start.bat`（含 LLM/ASR 连通性测试）。

## 功能一览

| 模块 | 说明 |
|------|------|
| 悬浮球助手 | 可拖拽悬浮球 + 聊天气泡面板 + 迷你播放条 + 内联澄清问答卡片 |
| 语音唤醒 | 浏览器 Vosk WASM 离线唤醒「衍衡」或「洛吉斯」（可配多个），带下载进度显示 |
| 语音输入/播报 | OpenAI 兼容 ASR 转写；浏览器 SpeechSynthesis / 后端 TTS 播报 |
| 任务编排 | 意图判断 → 任务形成 → 澄清 → 操作确认（**默认已放行**，见 [安全](Security)）→ 执行 → 汇报（SSE 实时） |
| 多智能体 | 复杂任务拆解：规划/执行/检索/批评 子代理并发协作（含实时进度事件） |
| 工具执行 | 26+ 内置工具，`@tool` 注册中心，read 级并发执行 |
| 记忆/RAG | SQLite FTS5 全文记忆 + BM25 检索上下文注入 |
| MCP / Skills | 外部 MCP server 桥接；YAML 技能包热加载 |
| 定时任务 | cron 5 段，无人值守执行 |
| 安全 | 非 localhost 绑定强制 API Token；工具执行与确认决策写入审计日志 |

## Wiki 导航

- [架构总览](Architecture)
- [API 参考](API)
- [配置说明](Configuration)
- [工具 / Skills / MCP](Tools-Skills-MCP)
- [记忆与 RAG](Memory-RAG)
- [安全模型](Security)
- [开发指南](Development)
