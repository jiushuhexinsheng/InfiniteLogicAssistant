# 无限逻辑 · 语音全控智能体

用语音（或文字）控制电脑上的一切：**唤醒 → 说话 → 意图判断 → 任务编排（澄清/确认/执行/汇报）→ 多智能体协作 + 工具执行 → 记忆/RAG 上下文**。

- 浏览器 VAD 切段 + **本地 KWS 唤醒判定**（sherpa-onnx，发音级/拼音级）+ 轻量 Python 后端（FastAPI）
- OpenAI 兼容接口，支持 DeepSeek / OpenAI / 通义 / 小米 MiMo 等多 provider
- 无沙箱设计，以**权限策略 + 审计日志**兜底（确认默认已放行，可在设置页收紧）
- 完全自研编排状态机（不依赖 LangGraph/CrewAI）；对话内容按**消息块协议**模块化渲染（思考/工具/正文/提问/汇总卡）

## 快速开始

```bash
# 1. 安装依赖（Python 3.14+）
pip install -r requirements.txt      # 或双击 install_deps.bat（在线→离线 wheel 兜底）

# 2. 配置（非敏感 / 密钥分离）
cp config.yaml.example config.yaml                  # endpoint / model / 多 profile 等非敏感项
cp config.secrets.yaml.example config.secrets.yaml  # 密钥（不入库；环境变量优先，支持 ${ENV_VAR}）

# 3. 启动（一键前端+后端）
python main.py serve                 # 浏览器自动打开 http://127.0.0.1:8520
```

Windows 一键脚本：`start.bat`（含 LLM/ASR 连通性测试）。

## 功能一览

| 模块 | 说明 |
|------|------|
| 悬浮球助手 | 可拖拽悬浮球 + 聊天气泡面板 + 迷你播放条 + 内联澄清问答卡片 |
| 语音唤醒 | VAD 切段 → 本地 KWS 判定「衍衡」/「洛吉斯」（发音级，同音字免疫）→ 命中才上云 ASR 抬指令；背景声/闲聊本机丢弃不上云。模式：auto/local/cloud/webspeech |
| 通话模式 | 双击悬浮球免唤醒持续聆听，三级漏斗（本地规则/本地转写/云端精判），播报可打断、回答后 8s 开放追问 |
| 语音输入/播报 | OpenAI 兼容 ASR 转写；浏览器 SpeechSynthesis / 后端 TTS 播报 |
| 任务编排 | 意图判断 → 任务形成 → 澄清 → 操作确认（**默认已放行**，见 [安全](Security)）→ 执行 → 汇报（SSE 实时） |
| 多智能体 | 复杂任务拆解：规划/执行/检索/批评 子代理并发协作（含实时进度事件） |
| 工具执行 | 29 个内置工具，`@tool` 注册中心，read 级并发执行 |
| 记忆/RAG | SQLite FTS5 全文记忆 + BM25 检索上下文注入 |
| 会话/任务库 | 会话历史与分叉编辑；任务完成存档，相似任务按用户原话检索预填 |
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
