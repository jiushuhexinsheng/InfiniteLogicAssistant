# 更新历史与验收清单

本页收「过程性内容」：更新历史、人工验收清单、语音验收台、成本实测方法。
使用说明见 [README](../README.md)，架构/配置/安全细节见 [wiki/](../wiki/Home.md)。

---

## 更新历史

### 2026-10-07 全项目文档同步（README / wiki / 配置模板）

对全项目做了一轮分析后统一文档口径，均为**文档修正，零行为变更**：

- **README**：API 端点表补 `/api/voice/call/{start,stop,segment}` 三端点；目录结构补
  `core/api/voice/call`、`core/voice/` 的 local_asr / smart_turn / call_funnel；
  测试节补通话漏斗共享向量 `call_funnel_vectors.json`。
- **wiki/API.md**：补通话三端点（会话 TTL 300s、请求/响应字段、hit 才送编排）。
- **wiki/Development.md**：共享测试向量补 `call_funnel_vectors.json`。
- **wiki/Security.md**：审计节补通话口径——`call-start/stop`、`call-funnel`（本地判定非上传）、
  `audio-upload via=call-segment`（L2 云端转写，计入成本口径）。
- **config.yaml.example**：修正两处过时声明——「判定在云端；无本地模型」与「无论是否唤醒
  都上传」（与现行本地 KWS 闸门语义**相反**），并补文档化此前缺示例的 `voice.kws` 段；
  已过 pydantic `Settings` 校验（extra=forbid）。

同日更早的两笔行为修复见 git 历史：93bfb73（悬浮球双击改原生 dblclick）、
c1b995b（通话态/唤醒关闭态提示文案下沉共享层）。

### 2026-10-05 通话模式（免唤醒持续流转 + 三级判定漏斗）

**设计与计划**：spec `docs/superpowers/specs/2026-10-05-call-mode-funnel-design.md`；
实施计划 `docs/superpowers/plans/2026-10-05-call-mode-funnel.md`（15 个 TDD 任务）。
计划头部对 spec 有一处修订：唤醒词入口**保留在悬浮球 `.ball-mic` 徽章**（不挪面板），
双击改为通话开关。

**落点（Task 1-14）**：

- **T1 配置**：`voice.call` 六字段（pydantic schema + API 副本 + 前端镜像 +
  `config.yaml.example`）
- **T2/T3 漏斗骨架**：L0 确定性粗筛（会话/回声/能量/焦点四道规则）+ L1 词表快筛
  （保守策略：只杀白噪）+ 双端共享向量 `tests/data/call_funnel_vectors.json`
  （pytest 与 vitest 双端钉住）
- **T4 本地转写**：sherpa-onnx streaming zipformer 中英双语单例（`core/voice/local_asr.py`，
  缺模型静默降级）+ 模型获取脚本 `python scripts/fetch_local_asr_model.py`
  （约 173MB 模型**不入库**，超 GitHub 单文件限，走 fetch 脚本引导）
- **T5 Smart Turn**：v3「说完没」复核（`pipecat-ai==1.12.0` 只按件采购这一个组件，
  失败降级放行）
- **T6/T7 L2 云端精判**：LLM 意图闸门四分类（command/chitchat/bystander/unsure，
  relax 宁可误报不可漏报、失败兜底 unsure）+ `run_funnel` 三级集成（L1 可缺降级、逐级审计）
- **T8 三端点**：`POST /api/voice/call/{start,stop,segment}`——会话 TTL、漏斗编排、
  relax 复判、审计
- **T9-T12 前端**：API 封装；通话 FSM（双击进入/唤醒互斥/开放窗口计时）；
  双击语义改通话开关（唤醒入口保留徽章、状态胶囊「通话聆听中」）；
  `processSegment` 通话分支（待答作答优先、命中送编排）
- **T13 打断**：通话态强制 barge-in + 播报结束自动开窗（非通话态行为零变化）
- **T14 验收台**：`npm run verify:voice` 加通话场景——免唤醒三证据
  （segment 请求 / utter 命中 / 无 wake 请求），无证据不 PASS

**口径**：命中走 `/api/voice/utter` 进现有编排（澄清/确认/执行/SSE 全复用）；漏斗 miss 记
audit `call-funnel` 行；云端转写共用 `audio-upload via=` 前缀，成本统计口径不变。

### 2026-09-26 对话系统模块化 + 唤醒链路大修

**对话系统模块化（消息块协议）**：
- 一条消息 = 有序块列表（thinking / tool / text / code / image / file / question /
  answer / notice / summary / ext:*），块是唯一事实源；`registerBlock` 注册协议，
  新块类型即插即用（未注册走 UnknownBlock 兜底，不丢数据）
- **思考流**：修复 reasoning_delta 断链（此前被静默丢弃），前端折叠块展示
- **回合汇总卡**：聚合本轮回看 + 语音播报统一出口（summary.tts_text）
- **三路径收敛**：完整视图（BlockHost）/ 摘要视图（registry.summarize）/ 任务视图
  消费同一份块协议；提问交互唯一实现是 QuestionBlock
- 历史持久化：messages 表加 blocks/turn_id/ts_iso，切换会话完整还原结构与真实时间戳
- TTS 不再朗读 markdown 记号（stripMarkdown）

**唤醒链路**：
- 判定改**拼音级**（pypinyin 无声调 + 音节序列匹配 + 句首容差 2 字），取代同音字表 ——
  「衍衡」写成任何同音字都命中；前后端语义由共享测试向量（tests/data/wake_vectors.json）
  在 pytest 与 vitest 双端钉住
- **本地 KWS 前置闸门**（sherpa-onnx zipformer-wenetspeech 3.3M）：未命中（背景声/
  闲聊）直接丢弃、不出本机不上云；命中才调云端 ASR。模型已随仓库入库（models/，
  缺模型自动旁路回退云端判定）
- **判定与提取分离（快检快速通道）**：`POST /api/voice/wake/check` 本地毫秒级判定，
  命中立即提示音 + 进入等指令窗口（提示音延迟 3~6s → ~1.7s）；一句话场景的指令由
  后台提取（音频判定优先于文本判定）
- 稳定性三件套：**TTS 回声护栏**（播报结束 1.2s 窗口丢弃音频段——助手自称「衍衡」，
  回声会连锁误唤醒）、**发送权令牌**（同一句语音恰好执行一次）、**段串行化**
  （背靠背段不交错双重触发）
- ASR 瞬时故障重试（Server disconnected 等 3 次退避）；熔断 60s 冷静期自动试探恢复
- 模式语义：`auto`/`local` = KWS 闸门 + ASR；`cloud` = 旁路闸门纯云端（最大召回）；
  `webspeech` = 浏览器 Web Speech 兜底

### 2026-09-13 唤醒链路重构（Vosk → 云端判定）

- 移除 Vosk 引擎与 43MB 模型（新唤醒词下 Vosk 全灭，实测驱动）
- VAD 分段 + `POST /api/voice/wake` 云端判定；唤醒词改「衍衡」「洛吉斯」
- 语音作答（播报后直接开口答问题）、确认三层判定（按钮 → 精确字面量 → LLM 兜底）
- 审计口径：`audio-upload via=wake|transcribe` 共用前缀，一条 grep 数全

### 2026-08-26 多厂商 Provider 配置

- LLM 三协议（openai / anthropic / gemini）按 profile 分派；厂商目录 + `vendor_presets`
- `GET /api/providers`、`POST /api/providers/fetch-models`；模型 failover

### 2026-08-25 配置系统重构

- pydantic 强类型 + 双文件（config.yaml / config.secrets.yaml）；检测域（环境/配置/连通性）
- 控制台设置页（热重载）

---

## 人工验收清单

### 唤醒链路（待真人执行）

⛔ **以下项必须由真人对着麦克风在真实有声环境下逐条执行，实现者不得代劳、不得代填。**
spec 音频实测用的是 SAPI 合成音——云端对合成音识别好**不代表对真人好**。

| # | 验收项 | 结果 |
|---|--------|------|
| 1 | 说「衍衡，帮我查天气」→ 一句话走通（提示音后自动执行） | **待人工验收** |
| 2 | 说「衍衡」→ 提示音 → 说指令 → 走通 | **待人工验收** |
| 3 | 说「洛吉斯，现在几点」→ 走通 | **待人工验收** |
| 4 | 说「衍衡」后不说话 → 不产生任务，不报错 | **待人工验收** |
| 5 | 屋里正常聊天/电视声（不含唤醒词）→ **不误触发** | **待人工验收** |
| 6 | 双击=通话开关进出正常；mic 徽章手动触发唤醒仍可用（回归） | **待人工验收** |
| 7 | 回答提问后立刻说话 → 不得被回声误唤醒/代答（回声护栏） | **待人工验收** |
| 8 | 指令执行完听回答 → 问题正常显示、可作答、不出现重复执行 | **待人工验收** |
| 9 | 通话模式：双击进入、免唤醒指令命中、barger 打断、开放窗口追问、旁人说话不触发（对照 audit `call-funnel` 行） | **待人工验收** |

### 成本实测（待做）

人工验收期间记录**每 10 分钟正常对话约触发几次云端上传**。数上传次数用审计日志的
共用前缀（口径一致，避免漏计）：

```bash
grep -c 'audio-upload via=' data/audit.log     # 云端上传总次数（真正上云的）
grep -o 'via=[a-z-]*' data/audit.log | sort | uniq -c   # 按通道拆分
```

- `audio-upload via=wake`：唤醒命中后为提取指令的转写（`POST /api/voice/wake`）
- `audio-upload via=transcribe`：**作答与指令**两段（`POST /api/voice/transcribe`）
- `kws-gate hit/skip=`：**本地 KWS 判定记账，不是上传**（skip = 被闸门挡掉、没上云）
- `POST /api/voice/answer` 只回传文本，不出音频，不在上传口径内

⚠️ 此前的实测值已过时（KWS 闸门后非唤醒音频不再上传，成本口径已变），**尚无新实测值**——
不要拿估算冒充实测。

---

## 语音验收台

语音链路有 4 项「必须真人对着麦克风说话、用耳朵听播报」的验收，单元测试覆盖不到
（真实的麦克风/扬声器通路驱动不了）。`web/scripts/verify-voice.mjs`
把其中**客观可判**的部分自动化：它负责搭场景、采证据、下结论，人只负责出声和听声。

> **口径：采不到证据就报 `INCONCLUSIVE`，绝不报 `PASS`。** 一个「什么都没看见所以通过」的
> 检查是假保障，比没有检查更糟。

```bash
cd web && npm run verify:voice          # 默认 http://127.0.0.1:8520
npm run verify:voice -- --url http://127.0.0.1:5173   # 指向 dev server
npm run verify:voice -- --skip 4                       # 跳过某项
```

覆盖的 4 项与判据：

| # | 验收项 | 判据（自动采集） |
|---|--------|------------------|
| 1 | 播报结束后直接开口说答案 | 出现 `POST /api/voice/answer` |
| 2 | 播报后沉默 → 待机 | 状态进 `standby` 且耗时贴近 `vad.answer_timeout_ms`（本项可全自动判定） |
| 3 | 待机态唤醒 → 续答本题 | 离开 `standby` **且没有新的 `/api/voice/utter`**（有新 utter = 开成了新一轮） |
| 4 | 播报含唤醒词 → 不自触发 | 播报期麦克风**活轨道数归零**（门控生效）**且**播报窗口内无任何音频上传 |

第 4 项的判据分两层「原因 + 结果」：麦克风是否真的被释放是**原因**，有没有上传是**结果**。
两者任一为 `FAIL` 即判 `FAIL`；而**任一层拿不到证据**一律判 `INCONCLUSIVE`，不判 `PASS`。

前置：后端已启动、本机 Chrome、麦克风与扬声器可用且未静音。结果写入
`docs/superpowers/plans/voice-verification-report.md`。

> **第 2 项要求真正的静音**：待答期间麦克风一旦采到声音，VAD 就会当成人说话录下来并提交，
> 于是永远等不到待答超时。脚本会把这种情形单独指出来（提示换安静环境重跑）。
> **第 4 项的声学部分**取决于扬声器→麦克风的实际通路；扬声器静音时它无判别力，但
> 「播报期麦克风活轨道数归零」这一半直接测轨道，任何情况下都可证伪。脚本会在报告里附上
> **探针是否可用**与**播报前麦克风是否真的开着**，所以「全都 0」不会被误读成通过。
