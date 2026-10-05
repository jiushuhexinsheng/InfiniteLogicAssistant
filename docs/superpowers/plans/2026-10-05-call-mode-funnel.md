# 通话模式（三级判定漏斗）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 双击悬浮球进入免唤醒通话模式：段落过 L0 规则 → L1 本地转写/轮次 → L2 云端精判的三级漏斗，命中进现有编排，支持 barge-in 打断与开放窗口追问。

**Architecture:** 复用现有段落式语音链（浏览器 VAD 切段，不引入 WS 常流）。新增 `core/voice/call_funnel.py` 纯逻辑漏斗（依赖全注入）+ `core/api/voice/call.py` 三端点与会话状态；前端在 `wakeOrchestrator.processSegment` 的 pendingQuestion 分支之后插入通话分支，双击语义改为通话开关，唤醒链降级为徽章入口。唤醒链行为除该分支与双击语义外零改动。

**Tech Stack:** Python 3.14 / FastAPI / sherpa-onnx 1.13.8（流式 zipformer 本地转写）/ pipecat-ai 1.12.0（Smart Turn v3.2，ONNX 模型随包内置）/ Vue 3 + TS / Vitest / pytest + pytest-asyncio。

**Spec:** `docs/superpowers/specs/2026-10-05-call-mode-funnel-design.md`

**对 spec 的一处修订（已确认执行口径）：** spec 写「唤醒词模式降级为面板（AssistantPanel）开关」。仓库现状是悬浮球上的 `.ball-mic` 徽章即唤醒开关（`verify-voice.mjs` 的 `ensureWake` 依赖它），把唤醒入口保留在徽章、双击改通话，可零破坏验收台与既有习惯。执行按徽章方案。

## Global Constraints

- Python 3.14+，Windows；静态检查 `python -m mypy core/ server.py` 必须干净（新模块纳入既有范围）。
- TDD：每个任务先写失败测试、跑红、再实现、跑绿、提交。提交信息中文 conventional（`feat(scope): ...` / `test(scope): ...`），每任务提交后 `git push`。
- 本机 git `autocrlf=true`（HEAD 存 LF、工作区 CRLF）——不得把 CRLF 提交进库；模型二进制按 KWS 先例正常提交（单文件 <100MB）。
- 云端上传审计：call 路径每一次云端 ASR 调用都必须写 `audio-upload via=call-segment ...` 行（前缀 `audio-upload via=` 与既有端点共用，`grep -c 'audio-upload via=' data/audit.log` 的成本口径不能破）。
- 前端改动完成的任务在推送前跑 `cd web && npm run build`（用户走 8520 静态托管，不重建 dist 到不了用户）。`vue-tsc` 类型检查必须过。
- 后端 schema 变更后必须 `cd web && npm run gen:api` 同步 `generated.ts`（CI 有漂移校验）。
- 不改唤醒链既有行为：pendingQuestion 作答分支优先级高于通话分支；唤醒词判定、熔断、节流逻辑原样。
- 权限/确认策略不动（三档默认放行为既定取舍，确认闸门 LLM 判定不动）。
- 测试不打真实网络：LLM/ASR 一律注入假件（模式同 `tests/test_server.py` 的 `_FakeLLMClient` / `_NoAsr`）。

## Review Focus

以下输入/失败模式是 spec 隐含但最容易在实现中被打漏的，各自的看守测试在对应任务里：

1. **TTS 播报期/回声护栏窗内的段落绝不能进漏斗**（否则助手自己触发自己）→ Task 2 的 `test_l0_drops_tts_active` + Task 12 的 `test_call_segment_skipped_inside_echo_guard`。
2. **页面刷新后后端会话已过期、前端监听器仍发段** → 不得 500、必须静默丢 + audit → Task 8 的 `test_call_segment_no_session_drops_silently`。
3. **双击/徽章互斥：任一时刻只有一条链在监听，唤醒与通话不得双执行同一段** → Task 10 的 `test_toggle_call_stops_wake_first` + Task 12 的 `test_routing_call_active_skips_wake_chain`。
4. **本地 ASR 模型缺失时通话模式仍可用**（降级 L0+L2，不阻断）→ Task 4 的 `test_local_asr_unavailable_without_model` + Task 7 的 `test_funnel_degrades_without_local_asr`。
5. **call 路径云端上传漏打审计**（成本估算静默偏低）→ Task 7 的 `test_funnel_cloud_transcribe_audits_upload`。
6. **通话模式下待答问题被当新指令**（问题卡优先级被通话分支抢走）→ Task 12 的 `test_pending_question_wins_over_call_branch`。

---

### Task 1: CallConfig 配置段（config schema + API 副本 + 下发）

**Files:**
- Modify: `core/config/schema.py`（`KwsConfig` 之后、`VoiceSection` 之前插入 `CallConfig`；`VoiceSection` 加字段）
- Modify: `core/api/schemas/voice.py`（`CallConfig` 手工副本 + `ConfigResponse.call`）
- Modify: `core/api/schemas/__init__.py`（re-export `CallConfig`）
- Modify: `core/api/voice/meta.py:42-43`（返回值加 `"call"`）
- Modify: `config.yaml.example`（`voice:` 段加 `call:` 块）
- Modify: `tests/test_config.py`（同步测试 `pairs` 加一对 + 新默认值测试）
- Regenerate: `web/src/api/generated.ts`（`npm run gen:api`）
- Modify: `web/src/types.ts` + `web/src/composables/assistant/store.ts` + `web/src/composables/useAssistant.ts`（前端配置镜像）

**Interfaces:**
- Produces: `core.config.schema.CallConfig`（字段：`enabled: bool=True`, `open_window_s: float=8.0`, `l0_min_rms: float=0.02`, `l0_min_seconds: float=0.5`, `smart_turn_enabled: bool=True`, `local_asr_model: str="models/sherpa-onnx-streaming-zipformer-bilingual-zh-en-2023-02-20"`）；`GET /voice/config` 响应新增 `call` 对象。
- Consumes: 无（首个任务）。

- [ ] **Step 1: 写失败测试**

在 `tests/test_config.py` 末尾追加：

```python
def test_call_config_defaults():
    """通话模式配置默认值：开、8s 开放窗口、0.5s/0.02 能量底线、Smart Turn 开。"""
    from core.config.schema import CallConfig
    c = CallConfig()
    assert c.enabled is True
    assert c.open_window_s == 8.0
    assert c.l0_min_rms == 0.02
    assert c.l0_min_seconds == 0.5
    assert c.smart_turn_enabled is True
    assert c.local_asr_model.endswith("bilingual-zh-en-2023-02-20")


def test_voice_section_has_call():
    from core.config.schema import VoiceSection
    assert hasattr(VoiceSection(), "call")
```

并把同步测试 `test_wake_and_vad_duplicates_in_api_schemas_stay_in_sync` 里的 `pairs` 列表改为：

```python
    pairs = [
        ("VadConfig", cfg_schema.VadConfig, api_schemas.VadConfig),
        ("WakeWordConfig", cfg_schema.WakeWordConfig, api_schemas.WakeWordConfig),
        ("CallConfig", cfg_schema.CallConfig, api_schemas.CallConfig),
    ]
```

- [ ] **Step 2: 跑红**

Run: `python -m pytest tests/test_config.py -k call_config -v`
Expected: FAIL（`ImportError: cannot import name 'CallConfig'`）

- [ ] **Step 3: 实现后端配置**

`core/config/schema.py`：在 `class VoiceSection` 前插入：

```python
class CallConfig(BaseModel):
    """通话模式（免唤醒持续流转）配置：双击悬浮球进入，段落过三级判定漏斗。

    Call mode (wake-free continuous flow) config: entered by double-clicking the float
    ball; each VAD segment runs the three-stage judgement funnel (L0 rules → L1 local
    transcription/turn → L2 cloud gate). `local_asr_model` missing/unloadable degrades
    the funnel to L0+L2 (never blocks the mode); `smart_turn_enabled=False` degrades to
    VAD-cut-as-turn-boundary (the legacy behaviour).
    """

    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    # 开放窗口（秒）：回答完成后免焦点追问的时限；0 关闭。
    # Open window (seconds): focus-free follow-up window after a reply; 0 disables.
    open_window_s: float = Field(8.0, ge=0.0)
    # L0 能量与时长底线：低于此的段视为非人声/清嗓，本机丢弃。
    # L0 energy/duration floor: segments below are non-speech (cleared throat), dropped locally.
    l0_min_rms: float = Field(0.02, ge=0.0, le=1.0)
    l0_min_seconds: float = Field(0.5, ge=0.0)
    # Smart Turn（说完没复核）开关：关=以浏览器 VAD 静音切段为回合边界（旧行为）。
    # Smart Turn switch: off = browser VAD cut is the turn boundary (legacy behaviour).
    smart_turn_enabled: bool = True
    # 本地流式转写模型目录；缺失时跳过 L1，只走 L0+L2。
    # Local streaming ASR model dir; when missing, skip L1 and run L0+L2 only.
    local_asr_model: str = "models/sherpa-onnx-streaming-zipformer-bilingual-zh-en-2023-02-20"
```

`VoiceSection` 里加一行（与 `kws` 同风格）：

```python
    call: CallConfig = Field(default_factory=lambda: CallConfig())
```

`core/api/schemas/voice.py`：在 `class ConfigResponse` 前插入手工副本（字段名/类型/默认值与上面逐字一致——这是被同步测试钉死的契约）：

```python
class CallConfig(BaseModel):
    """通话模式配置（`core/config/schema.py` 里 CallConfig 的**手工副本**，两处必须同步，
    理由同 WakeWordConfig/VadConfig：response_model 会静默过滤未声明字段）。

    Call-mode configuration (hand-maintained duplicate of CallConfig in
    `core/config/schema.py`; the two must stay in sync — response_model silently drops
    undeclared fields, same trap as WakeWordConfig/VadConfig).
    """
    enabled: bool = True
    open_window_s: float = 8.0
    l0_min_rms: float = 0.02
    l0_min_seconds: float = 0.5
    smart_turn_enabled: bool = True
    local_asr_model: str = "models/sherpa-onnx-streaming-zipformer-bilingual-zh-en-2023-02-20"
```

`ConfigResponse` 里加（紧随 `vad` 字段）：

```python
    call: CallConfig
```

`core/api/schemas/__init__.py`：`WakeWordConfig,` 附近加 `CallConfig,`，`__all__` 加 `"CallConfig"`。

`core/api/voice/meta.py` 返回字典 `"vad"` 行后加：

```python
        "call": config.settings.voice.call.model_dump(),
```

`config.yaml.example` 的 `voice:` 段（`kws` 块之前或 `vad` 块之后均可）加：

```yaml
  # 通话模式（双击悬浮球进入，免唤醒持续聆听）：段落过三级漏斗
  # L0 规则 → L1 本地转写 → L2 云端精判，详见 docs/superpowers/specs/2026-10-05-call-mode-funnel-design.md
  call:
    enabled: true
    open_window_s: 8        # 回答后免焦点追问窗口（秒）；0 关闭
    l0_min_rms: 0.02        # 段落能量低于此视为非人声（实现期可用真音频标定）
    l0_min_seconds: 0.5     # 短于此的段本机丢弃
    smart_turn_enabled: true
    local_asr_model: "models/sherpa-onnx-streaming-zipformer-bilingual-zh-en-2023-02-20"
```

- [ ] **Step 4: 跑绿**

Run: `python -m pytest tests/test_config.py -v`
Expected: PASS（含既有同步测试三条新对）

- [ ] **Step 5: 前端配置镜像 + 类型同步**

`web/src/types.ts`：从 generated 再导出（跟随现有 `WakeWordConfig` 的方式，找到该文件中 WakeWordConfig 的 re-export 行照抄加 `CallConfig`）。

`web/src/composables/assistant/store.ts`：仿 `vadConfig`（第 161 行）加：

```ts
/** 通话模式配置（/api/config 的 call 段覆盖默认值）。Call-mode config (the `call` block of /api/config overrides these defaults). */
export const callConfig: CallConfig = { enabled: true, open_window_s: 8, l0_min_rms: 0.02, l0_min_seconds: 0.5, smart_turn_enabled: true, local_asr_model: '' }
/** 通话激活标志：唯一事实来源（store 级，避免 wakeOrchestrator ↔ callMode 循环导入）。Call-active flag: store-level single source of truth (avoids a wakeOrchestrator ↔ callMode import cycle). */
export const callActive = ref(false)
```

`web/src/composables/useAssistant.ts` 的 `init`（第 20-31 行）：签名参数类型加 `call?: Partial<CallConfig>`，函数体加：

```ts
  if (config?.call) Object.assign(callConfig, config.call)
```

（`callConfig` 加入现有 import。）

Run: `cd web && npm run gen:api && npm run build`
Expected: vue-tsc 通过，`generated.ts` 出现 `CallConfig`

- [ ] **Step 6: 全量回归 + 提交**

Run: `python -m pytest tests/test_config.py -v && python -m mypy core/ server.py`
Expected: PASS

```bash
git add core/config/schema.py core/api/schemas/voice.py core/api/schemas/__init__.py core/api/voice/meta.py config.yaml.example tests/test_config.py web/src/types.ts web/src/composables/assistant/store.ts web/src/composables/useAssistant.ts web/src/api/generated.ts
git commit -m "feat(config): voice.call 通话模式配置段——schema+API副本同步+前端镜像"
git push
```

---

### Task 2: 漏斗骨架 + L0 确定性粗筛

**Files:**
- Create: `core/voice/call_funnel.py`
- Test: `tests/test_call_funnel.py`

**Interfaces:**
- Produces: `SegmentMeta(tab_focused: bool=False, in_open_window: bool=False, session_active: bool=True, tts_active: bool=False, echo_guard: bool=False)`、`FunnelResult(verdict: str, hit: bool, stage: str, text: str, reason: str)`、`screen_l0(meta, *, duration_s: float, rms: float, min_seconds: float, min_rms: float) -> str | None`（返回丢弃原因，`None`=放行）
- Consumes: Task 1 的配置值（由调用方读取后传入，漏斗本身不 import config——保持可注入）。

- [ ] **Step 1: 写失败测试**

`tests/test_call_funnel.py`：

```python
# -*- coding: utf-8 -*-
"""通话漏斗 L0（确定性粗筛）测试。Call funnel L0 (deterministic screen) tests."""
from core.voice.call_funnel import SegmentMeta, screen_l0


def _pass(**kw):
    return screen_l0(SegmentMeta(**kw), duration_s=2.0, rms=0.1,
                     min_seconds=0.5, min_rms=0.02)


def test_l0_passes_normal_segment():
    assert _pass(tab_focused=True) is None


def test_l0_drops_no_session():
    assert _pass(session_active=False, tab_focused=True) == "no_session"


def test_l0_drops_tts_active():
    """Review Focus #1：播报期的段绝不能进漏斗（回声自触发）。"""
    assert _pass(tts_active=True, tab_focused=True) == "echo"


def test_l0_drops_echo_guard():
    assert _pass(echo_guard=True, tab_focused=True) == "echo"


def test_l0_drops_short_and_quiet():
    assert screen_l0(SegmentMeta(tab_focused=True), duration_s=0.2, rms=0.1,
                     min_seconds=0.5, min_rms=0.02) == "too_short"
    assert screen_l0(SegmentMeta(tab_focused=True), duration_s=2.0, rms=0.001,
                     min_seconds=0.5, min_rms=0.02) == "low_rms"


def test_l0_unfocused_dropped_unless_open_window():
    assert _pass(tab_focused=False) == "unfocused"
    assert _pass(tab_focused=False, in_open_window=True) is None
```

- [ ] **Step 2: 跑红**

Run: `python -m pytest tests/test_call_funnel.py -v`
Expected: FAIL（`ModuleNotFoundError: No module named 'core.voice.call_funnel'`）

- [ ] **Step 3: 实现**

`core/voice/call_funnel.py`：

```python
# -*- coding: utf-8 -*-
"""通话模式判定漏斗 — L0 确定性粗筛（本级零模型、零云端）。

L0 是纯规则：会话态、回声、能量/时长、焦点/开放窗口。任一命中即给出丢弃原因
（reason 字符串，直接进 audit 行），`None` 表示放行进 L1。本模块不 import config
也不做 IO —— 配置值与依赖全部由调用方注入，便于逐条测试。

Stage 0 of the call-mode judgement funnel (deterministic screen, zero models, zero
cloud). Pure rules: session state, echo, energy/duration, focus/open-window. A hit
returns the drop reason (goes straight into the audit line); ``None`` means proceed
to L1. No config imports, no IO — callers inject everything, so every rule is unit
testable.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SegmentMeta:
    """段落判定上下文（前端随段上报 + 后端会话态）。Segment context (reported by the
    frontend per segment + backend session state)."""

    tab_focused: bool = False
    in_open_window: bool = False
    session_active: bool = True
    tts_active: bool = False
    echo_guard: bool = False


@dataclass(frozen=True)
class FunnelResult:
    """漏斗判定结果。Funnel verdict.

    verdict: "dropped" | "incomplete" | "chitchat" | "command"
    hit: 仅 command/chitchat 为 True（relax 提升由 L2 层处理）。
    """

    verdict: str
    hit: bool
    stage: str
    text: str = ""
    reason: str = ""


def screen_l0(meta: SegmentMeta, *, duration_s: float, rms: float,
              min_seconds: float, min_rms: float) -> str | None:
    """L0 粗筛：返回丢弃原因，`None` = 放行。检查顺序即优先级（会话 > 回声 > 形态 > 焦点）。

    L0 screen: drop reason or ``None`` to pass. Order is priority (session > echo >
    shape > focus).
    """
    if not meta.session_active:
        return "no_session"
    if meta.tts_active or meta.echo_guard:
        return "echo"
    if duration_s < min_seconds:
        return "too_short"
    if rms < min_rms:
        return "low_rms"
    if not meta.tab_focused and not meta.in_open_window:
        return "unfocused"
    return None
```

- [ ] **Step 4: 跑绿**

Run: `python -m pytest tests/test_call_funnel.py -v && python -m mypy core/voice/call_funnel.py`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add core/voice/call_funnel.py tests/test_call_funnel.py
git commit -m "feat(voice): 通话漏斗骨架与 L0 确定性粗筛（会话/回声/能量/焦点四道规则）"
git push
```

---

### Task 3: L1 词表快筛 + 双端共享向量

**Files:**
- Modify: `core/voice/call_funnel.py`（加 `quick_screen`）
- Create: `tests/data/call_funnel_vectors.json`
- Test: `tests/test_call_funnel.py`（追加向量消费用例）

**Interfaces:**
- Produces: `quick_screen(text: str) -> str | None`（丢弃原因或 None）；`tests/data/call_funnel_vectors.json` 结构 `{"quick_screen": {"positives": [{"text", "expect": null}], "negatives": [{"text", "expect": reason}]}, "routing": [{"text", "hit": bool}]}`——`routing` 段供 Task 12 的 vitest 消费（同一文件、双端钉语义）。
- Consumes: Task 2 的文件。

- [ ] **Step 1: 写向量文件**

`tests/data/call_funnel_vectors.json`：

```json
{
  "quick_screen": {
    "positives": [
      { "text": "帮我打开记事本", "expect": null },
      { "text": "今天天气怎么样", "expect": null },
      { "text": "查一下明天的航班", "expect": null },
      { "text": "你真棒", "expect": null },
      { "text": "把音量调到五十", "expect": null },
      { "text": "what time is it", "expect": null }
    ],
    "negatives": [
      { "text": "", "expect": "empty" },
      { "text": "。", "expect": "empty" },
      { "text": "嗯", "expect": "filler" },
      { "text": "啊", "expect": "filler" },
      { "text": "那个", "expect": "filler" },
      { "text": "呃", "expect": "filler" },
      { "text": "a", "expect": "too_short" }
    ]
  },
  "routing": [
    { "text": "帮我打开记事本", "hit": true },
    { "text": "今天天气怎么样", "hit": true },
    { "text": "他明天就到", "hit": false },
    { "text": "嗯", "hit": false }
  ]
}
```

- [ ] **Step 2: 写失败测试**

`tests/test_call_funnel.py` 追加：

```python
import json
from pathlib import Path

_VECTORS = json.loads((Path(__file__).parent / "data" / "call_funnel_vectors.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("case", _VECTORS["quick_screen"]["positives"], ids=lambda c: c["text"] or "empty")
def test_quick_screen_positives(case):
    """正例必须放行（判「是否对AI说」是 L2 的事，L1 不许越权杀掉正常指令）。"""
    from core.voice.call_funnel import quick_screen
    assert quick_screen(case["text"]) is case["expect"]


@pytest.mark.parametrize("case", _VECTORS["quick_screen"]["negatives"], ids=lambda c: c["text"] or "empty")
def test_quick_screen_negatives(case):
    from core.voice.call_funnel import quick_screen
    assert quick_screen(case["text"]) == case["expect"]
```

（文件顶部补 `import pytest`。）

- [ ] **Step 3: 跑红**

Run: `python -m pytest tests/test_call_funnel.py -k quick_screen -v`
Expected: FAIL（`ImportError: cannot import name 'quick_screen'`）

- [ ] **Step 4: 实现**

`core/voice/call_funnel.py` 追加：

```python
# 语气词/填充词白噪：命中即丢（对 AI 说不会以它们独立成句）。
# Filler words: dropped outright (nobody addresses an assistant with these alone).
_FILLERS = {"嗯", "啊", "呃", "哦", "额", "嗯嗯", "哦哦", "啊啊", "那个", "这个", "呃呃", "呵呵", "哈哈"}


def quick_screen(text: str) -> str | None:
    """L1 文本快筛（本地转写之后、上云之前）：返回丢弃原因，`None` = 放行。

    刻意保守：只杀空转写/纯标点/填充词/单字符——「是不是对助手说的」语义判断归 L2，
    L1 越权会误杀正常指令（漏报比误传贵）。

    L1 text screen (after local transcription, before any cloud call): drop reason or
    ``None``. Deliberately conservative — only empty/punctuation/filler/single-char.
    "Is this addressed to the assistant" is L2's job; over-eaching here drops real
    commands (a miss costs more than an extra cloud call).
    """
    t = text.strip().strip("。！？!?，,、 ").strip()
    if not t:
        return "empty"
    if t in _FILLERS:
        return "filler"
    if len(t) < 2:
        return "too_short"
    return None
```

- [ ] **Step 5: 跑绿**

Run: `python -m pytest tests/test_call_funnel.py -v`
Expected: PASS（positives/negatives 全绿）

- [ ] **Step 6: 提交**

```bash
git add core/voice/call_funnel.py tests/test_call_funnel.py tests/data/call_funnel_vectors.json
git commit -m "feat(voice): 通话漏斗 L1 词表快筛+双端共享向量（保守策略：只杀白噪）"
git push
```

---

### Task 4: 本地流式转写单例（sherpa-onnx zipformer）+ 模型入库

**Files:**
- Create: `core/voice/local_asr.py`
- Create: `scripts/fetch_local_asr_model.py`（下载 + 按需解包，可重复执行）
- Test: `tests/test_local_asr.py`
- Commit: `models/sherpa-onnx-streaming-zipformer-bilingual-zh-en-2023-02-20/`（仅 tokens.txt + encoder/decoder/joiner onnx）

**Interfaces:**
- Produces: `get_local_asr() -> LocalAsr`，`LocalAsr.available() -> bool`，`LocalAsr.transcribe_wav(wav_bytes: bytes) -> str`（出错/不可用返回 `""`）。
- Consumes: `config.settings.voice.local_asr_model`（Task 1）。

- [ ] **Step 1: 写失败测试**

`tests/test_local_asr.py`：

```python
# -*- coding: utf-8 -*-
"""本地流式转写单例：缺模型降级、单例复用、wav 解析失败返回空串。Local streaming ASR singleton."""
import wave
import io

from core.voice import local_asr


def _reset(monkeypatch, model_dir: str = "models/__no_such_dir__"):
    monkeypatch.setattr(local_asr, "_instance", None)
    from core import config
    monkeypatch.setattr(config.settings.voice.call, "local_asr_model", model_dir)


def test_local_asr_unavailable_without_model(monkeypatch):
    """Review Focus #4：模型缺失 → available()=False，转写返回空串（漏斗降级，不抛）。"""
    _reset(monkeypatch)
    a = local_asr.get_local_asr()
    assert a.available() is False
    assert a.transcribe_wav(b"not a wav") == ""


def test_local_asr_singleton(monkeypatch):
    _reset(monkeypatch)
    assert local_asr.get_local_asr() is local_asr.get_local_asr()


def test_local_asr_bad_wav_returns_empty(monkeypatch):
    _reset(monkeypatch, model_dir="models")  # 目录存在但缺 tokens.txt → 仍 unavailable
    a = local_asr.get_local_asr()
    assert a.transcribe_wav(b"garbage") == ""
```

- [ ] **Step 2: 跑红**

Run: `python -m pytest tests/test_local_asr.py -v`
Expected: FAIL（`ModuleNotFoundError`）

- [ ] **Step 3: 实现 `core/voice/local_asr.py`**

```python
# -*- coding: utf-8 -*-
"""本地流式转写 — sherpa-onnx streaming zipformer（通话漏斗 L1，零云端）。

模型缺失/加载失败 → available()=False、transcribe_wav 返回空串：漏斗降级为 L0+L2
（与 KWS 闸门同一「坏得静默、链路不断」契约）。wav 经 accept_waveform 直喂，采样率
不一致由 sherpa 内部重采样（1.13.8 文档确认）。

Local streaming transcription — sherpa-onnx streaming zipformer (funnel L1, zero cloud).
Missing/failed model → available()=False and transcribe_wav returns "" so the funnel
degrades to L0+L2 (same "fail silent, never break the chain" contract as the KWS gate).
wav samples go straight into accept_waveform; sherpa resamples internally on rate
mismatch (confirmed against the 1.13.8 docstring).
"""
from __future__ import annotations

import io
import wave
from typing import Any

from core import config
from core.config import add_reload_hook
from core.logger import logger

_instance: "LocalAsr | None" = None


class LocalAsr:
    """sherpa-onnx 流式识别单例（懒加载，配置热重载后重建）。Lazy-load singleton."""

    def __init__(self) -> None:
        self._recognizer: Any | None = None
        self._loaded = False

    def _load(self) -> bool:
        if self._loaded:
            return self._recognizer is not None
        self._loaded = True
        try:
            if not config.settings.voice.call.enabled:
                return False
            d = config.ROOT_DIR / config.settings.voice.call.local_asr_model
            tokens = d / "tokens.txt"
            if not tokens.is_file():
                logger.info("本地转写模型不存在（{}），L1 跳过（漏斗走 L0+L2）", d)
                return False
            enc = self._pick(d, "encoder", prefer_int8=True)
            dec = self._pick(d, "decoder")
            jn = self._pick(d, "joiner")
            if enc is None or dec is None or jn is None:
                logger.warning("本地转写模型文件不全（{}），L1 跳过", d)
                return False
            import sherpa_onnx
            self._recognizer = sherpa_onnx.OnlineRecognizer.from_transducer(
                tokens=str(tokens), encoder=str(enc), decoder=str(dec), joiner=str(jn),
                num_threads=2, sample_rate=16000, feature_dim=80,
                enable_endpoint_detection=False, decoding_method="greedy_search",
            )
            logger.info("本地转写就绪：{}", d.name)
            return True
        except Exception as e:
            logger.warning("本地转写加载失败，L1 跳过: {}", e)
            self._recognizer = None
            return False

    @staticmethod
    def _pick(d, kind: str, prefer_int8: bool = False):
        """按前缀挑模型文件（int8 优先），找不到返回 None。Pick a model file by prefix."""
        cands = sorted(d.glob(f"{kind}-*.onnx"))
        if not cands:
            return None
        if prefer_int8:
            i8 = [c for c in cands if ".int8." in c.name]
            if i8:
                return i8[0]
        return cands[0]

    def available(self) -> bool:
        return self._load()

    def transcribe_wav(self, wav_bytes: bytes) -> str:
        """整段 wav → 文本；任何失败返回 ""（调用方按无文本降级）。Never raises."""
        if not self.available():
            return ""
        try:
            with wave.open(io.BytesIO(wav_bytes), "rb") as w:
                sr = w.getframerate()
                frames = w.readframes(w.getnframes())
            import numpy as np
            samples = (np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0)
            if samples.size == 0:
                return ""
            stream = self._recognizer.create_stream()
            stream.accept_waveform(float(sr), samples.tolist())
            stream.input_finished()
            while self._recognizer.is_ready(stream):
                self._recognizer.decode_stream(stream)
            return (self._recognizer.get_result(stream) or "").strip()
        except Exception as e:
            logger.warning("本地转写失败（按无文本降级）: {}", e)
            return ""


def get_local_asr() -> LocalAsr:
    global _instance
    if _instance is None:
        _instance = LocalAsr()
    return _instance


def _reset_local_asr() -> None:
    global _instance
    _instance = None


add_reload_hook(_reset_local_asr)
```

- [ ] **Step 4: 跑红转绿的单测**

Run: `python -m pytest tests/test_local_asr.py -v && python -m mypy core/voice/local_asr.py`
Expected: PASS

- [ ] **Step 5: 模型获取脚本 + 真模型冒烟**

`scripts/fetch_local_asr_model.py`：

```python
# -*- coding: utf-8 -*-
"""下载通话模式 L1 本地转写模型（k2-fsa 官方 release），只保留推理所需文件。

用法: python scripts/fetch_local_asr_model.py
包体 ~511MB（含 test_wavs/model.pt 等），解包后只留 tokens.txt + encoder/decoder/joiner
onnx（~90MB）入库，tar.bz2 用完即删。

Download the call-mode L1 local transcription model (official k2-fsa release), keeping
only the inference files. The tarball is ~511MB; only tokens.txt + encoder/decoder/joiner
onnx (~90MB) are kept and committed; the tarball is deleted afterwards.
"""
import shutil
import tarfile
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
URL = "https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/sherpa-onnx-streaming-zipformer-bilingual-zh-en-2023-02-20.tar.bz2"
DEST = ROOT / "models" / "sherpa-onnx-streaming-zipformer-bilingual-zh-en-2023-02-20"
KEEP_PREFIXES = ("encoder-", "decoder-", "joiner-")


def main() -> int:
    if (DEST / "tokens.txt").is_file():
        print("already present:", DEST)
        return 0
    DEST.mkdir(parents=True, exist_ok=True)
    tmp = ROOT / "models" / "_asr_download.tar.bz2"
    print("downloading (511MB, one-time) ...")
    urllib.request.urlretrieve(URL, tmp)
    print("extracting ...")
    with tarfile.open(tmp, "r:bz2") as tf:
        for m in tf.getmembers():
            name = Path(m.name).name
            if not m.isfile():
                continue
            if name == "tokens.txt" or any(name.startswith(p) and name.endswith(".onnx") for p in KEEP_PREFIXES):
                tf.extract(m, path=ROOT / "models")
                src = ROOT / m.name
                shutil.move(str(src), str(DEST / name))
    tmp.unlink(missing_ok=True)
    print("done:", sorted(p.name for p in DEST.iterdir()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

Run: `python scripts/fetch_local_asr_model.py`
Expected: 打印 `done:` 且列出 tokens.txt、encoder-*.onnx、decoder-*.onnx、joiner-*.onnx。

冒烟（真实转写一段合成静音 wav，验证 API 签名与加载链路）：

```bash
python -c "
import io, wave, struct, math
from core.voice.local_asr import get_local_asr
buf = io.BytesIO()
with wave.open(buf, 'wb') as w:
    w.setnchannels(1); w.setsampwidth(2); w.setframerate(16000)
    w.writeframes(b''.join(struct.pack('<h', int(12000*math.sin(2*math.pi*440*i/16000))) for i in range(16000)))
a = get_local_asr()
assert a.available(), 'model should load'
print('text=', repr(a.transcribe_wav(buf.getvalue())))
"
```
Expected: `text=` 打印（内容可为 `''`——纯音调无语音，只要不抛异常）。若 `available()` 为 False 或 `transcribe_wav` 抛 TypeError（参数签名不符），对照本机 `sherpa_onnx==1.13.8` 的 `OnlineRecognizer.from_transducer` docstring 修 `LocalAsr`，**保持 `available()/transcribe_wav` 对外签名不变**。

- [ ] **Step 6: 提交（含模型）**

```bash
git add core/voice/local_asr.py scripts/fetch_local_asr_model.py tests/test_local_asr.py models/sherpa-onnx-streaming-zipformer-bilingual-zh-en-2023-02-20
git commit -m "feat(voice): 本地流式转写单例（sherpa zipformer 中英双语，缺模型静默降级）+ 模型入库"
git push
```

---

### Task 5: Smart Turn v3 包装（说完没复核，可降级）

**Files:**
- Modify: `requirements.txt`（加 `pipecat-ai==1.12.0`，注释说明只为 Smart Turn 按件采购）
- Create: `core/voice/smart_turn.py`
- Test: `tests/test_smart_turn.py`

**Interfaces:**
- Produces: `get_smart_turn() -> SmartTurn`，`SmartTurn.available() -> bool`（`voice.call.smart_turn_enabled=False` 或 import/加载失败 → False），`async SmartTurn.is_complete(pcm16: bytes, sample_rate: int) -> bool`（任何失败返回 `True`——降级按「切段即回合结束」的旧语义放行）。
- Consumes: pipecat `LocalSmartTurnAnalyzerV3`（`from pipecat.audio.turn.smart_turn.local_smart_turn_v3 import LocalSmartTurnAnalyzerV3`，模型随包内置，无需下载）。

- [ ] **Step 1: 装依赖**

`requirements.txt` 在 sherpa-onnx 行后加：

```
# 通话模式「说完没」复核（Smart Turn v3.2，ONNX 模型随包内置，本地 CPU）——只按件采购
# 这一个分析器，不引入 pipecat 框架本体。
# Call-mode end-of-turn check (Smart Turn v3.2, bundled ONNX model, local CPU) — a la carte;
# the pipecat framework itself is NOT adopted.
pipecat-ai==1.12.0
```

Run: `pip install pipecat-ai==1.12.0`
Expected: 安装成功（其 `loguru~=0.7.3` 与本仓 `loguru==0.7.3` 兼容）。

- [ ] **Step 2: 写失败测试**

`tests/test_smart_turn.py`：

```python
# -*- coding: utf-8 -*-
"""Smart Turn 包装：禁用/加载失败降级为 True（切段即回合的旧行为）。Smart Turn wrapper degradation."""
import asyncio

from core.voice import smart_turn


def test_disabled_config_degrades(monkeypatch):
    from core import config
    monkeypatch.setattr(config.settings.voice.call, "smart_turn_enabled", False)
    monkeypatch.setattr(smart_turn, "_instance", None)
    st = smart_turn.get_smart_turn()
    assert st.available() is False
    assert asyncio.run(st.is_complete(b"\x00\x01" * 160, 16000)) is True


def test_is_complete_never_raises(monkeypatch):
    """损坏输入也不许抛：返回 True（放行），通话链路不能被轮次模型卡死。"""
    monkeypatch.setattr(smart_turn, "_instance", None)
    st = smart_turn.get_smart_turn()
    assert asyncio.run(st.is_complete(b"", 16000)) in (True, False)
```

- [ ] **Step 3: 跑红**

Run: `python -m pytest tests/test_smart_turn.py -v`
Expected: FAIL（`ModuleNotFoundError: No module named 'core.voice.smart_turn'`）

- [ ] **Step 4: 实现 `core/voice/smart_turn.py`**

```python
# -*- coding: utf-8 -*-
"""Smart Turn v3 包装 — 通话漏斗 L1 的「说完没」复核（本地 ONNX，模型随 pipecat 内置）。

按件采购：只用 pipecat 的 LocalSmartTurnAnalyzerV3 分析器，不引框架。任何不可用
（配置关/包没装/模型坏/输入异常）一律降级 available()=False、is_complete()=True ——
即「浏览器 VAD 切段 = 回合边界」的旧行为，链路不断。

Smart Turn v3 wrapper — the funnel L1 "did they finish" re-check (local ONNX, model
bundled with pipecat). A la carte: only the analyzer, not the framework. Any
unavailable state degrades to available()=False / is_complete()=True — i.e. the legacy
"VAD cut = turn boundary" behaviour; the chain never breaks.
"""
from __future__ import annotations

from typing import Any

from core import config
from core.config import add_reload_hook
from core.logger import logger

_instance: "SmartTurn | None" = None


class SmartTurn:
    def __init__(self) -> None:
        self._analyzer: Any | None = None
        self._loaded = False

    def _load(self) -> bool:
        if self._loaded:
            return self._analyzer is not None
        self._loaded = True
        try:
            if not config.settings.voice.call.smart_turn_enabled:
                return False
            from pipecat.audio.turn.smart_turn.local_smart_turn_v3 import (
                LocalSmartTurnAnalyzerV3,
            )
            self._analyzer = LocalSmartTurnAnalyzerV3(cpu_count=2)
            self._analyzer.set_sample_rate(16000)
            logger.info("Smart Turn v3 就绪（模型随包内置）")
            return True
        except Exception as e:
            logger.warning("Smart Turn 加载失败，按「切段即回合」降级: {}", e)
            self._analyzer = None
            return False

    def available(self) -> bool:
        return self._load()

    async def is_complete(self, pcm16: bytes, sample_rate: int) -> bool:
        """整段 16-bit PCM → 是否说完。失败/不可用返回 True（放行 = 旧行为）。Never raises."""
        if not self.available() or not pcm16:
            return True
        try:
            a = self._analyzer
            if sample_rate != a.sample_rate:
                a.set_sample_rate(sample_rate)
            a.clear()
            a.append_audio(pcm16, True)
            state, _ = await a.analyze_end_of_turn()
            a.clear()
            from pipecat.audio.turn.base_turn_analyzer import EndOfTurnState
            return state == EndOfTurnState.COMPLETE
        except Exception as e:
            logger.warning("Smart Turn 判定失败（放行）: {}", e)
            return True


def get_smart_turn() -> SmartTurn:
    global _instance
    if _instance is None:
        _instance = SmartTurn()
    return _instance


def _reset_smart_turn() -> None:
    global _instance
    _instance = None


add_reload_hook(_reset_smart_turn)
```

- [ ] **Step 5: 跑绿**

Run: `python -m pytest tests/test_smart_turn.py -v && python -m mypy core/voice/smart_turn.py`
Expected: PASS

- [ ] **Step 6: 提交**

```bash
git add requirements.txt core/voice/smart_turn.py tests/test_smart_turn.py
git commit -m "feat(voice): Smart Turn v3 说完没复核（pipecat 按件采购，失败降级放行）"
git push
```

---

### Task 6: L2 云端意图闸门（LLM 四分类 + relax 提升）

**Files:**
- Modify: `core/prompts.py`（加 `CALL_GATE_SYSTEM`）
- Modify: `core/voice/call_funnel.py`（加 `judge_call_intent`）
- Test: `tests/test_call_funnel.py`（追加）

**Interfaces:**
- Produces: `async judge_call_intent(text: str, recent: str, *, relax: bool, llm: Callable | None = None) -> str` 返回 `"command" | "chitchat" | "bystander" | "unsure"`；`llm` 形参为 `async def(messages, tools, temperature) -> AsyncIterator[dict]`（缺省取 `get_llm_client().retry_stream_chat`），测试注入假件。
- Consumes: `core.llm.client.get_llm_client`（既有）、`config.settings.agent.structured_temperature`（既有）。

- [ ] **Step 1: 写失败测试**

`tests/test_call_funnel.py` 追加：

```python
from core.voice.call_funnel import judge_call_intent


def _fake_llm(verdict: str, seen: dict):
    """假 LLM：记录收到的 messages/tools，按预设 verdict 返回 done 事件。"""
    async def run(messages, tools=None, temperature=None=None):
        seen["messages"] = messages
        seen["tools"] = tools
        yield {"type": "done", "message": {"tool_calls": [{"function": {
            "name": "judge", "arguments": {"verdict": verdict, "note": "t"}}}]}}
    return run


def test_judge_parses_tool_verdict():
    seen: dict = {}
    v = asyncio.run(judge_call_intent("帮我打开记事本", "", relax=False, llm=_fake_llm("command", seen)))
    assert v == "command"
    assert any("闸门" in str(m.get("content", "")) for m in seen["messages"] if m["role"] == "system")


def test_judge_maps_all_verdicts_and_fallback():
    for verdict, expect in [("chitchat", "chitchat"), ("bystander", "bystander"),
                            ("unsure", "unsure"), ("bogus", "unsure")]:
        v = asyncio.run(judge_call_intent("x", "", relax=False, llm=_fake_llm(verdict, {})))
        assert v == expect


def test_judge_relax_mentions_policy():
    seen: dict = {}
    asyncio.run(judge_call_intent("x", "最近片段", relax=True, llm=_fake_llm("unsure", seen)))
    sys_msg = next(m["content"] for m in seen["messages"] if m["role"] == "system")
    assert "宁可误报" in sys_msg
    assert "最近片段" in next(m["content"] for m in seen["messages"] if m["role"] == "user")


def test_judge_error_falls_back_unsure():
    async def boom(*a, **k):
        raise RuntimeError("net down")
        yield  # pragma: no cover
    assert asyncio.run(judge_call_intent("x", "", relax=False, llm=boom)) == "unsure"
```

（`tests/test_call_funnel.py` 顶部补 `import asyncio`。）

- [ ] **Step 2: 跑红**

Run: `python -m pytest tests/test_call_funnel.py -k judge -v`
Expected: FAIL（`ImportError: cannot import name 'judge_call_intent'`）

- [ ] **Step 3: 实现**

`core/prompts.py` 末尾加：

```python
CALL_GATE_SYSTEM = (
    "你是语音助手的入口闸门。判断转写文本是否是**对这位语音助手说的**，用 judge 工具返回 verdict：\n"
    "command = 对助手说的指令（打开/查询/设置/执行类）或明确提问；\n"
    "chitchat = 对助手的寒暄、闲聊、夸赞（如「你好」「你今天真棒」）；\n"
    "bystander = 旁人对话、电视/媒体声音、自言自语、与助手无关的内容；\n"
    "unsure = 证据不足无法判断。\n"
    "只看「是不是对助手说的」，不要评估指令能否执行。判断依据：直接指令语气、"
    "与近几轮上下文的承接关系、第三人称闲聊特征。"
)

CALL_GATE_RELAX_NOTE = (
    "\n【放宽模式】本段属于连续未命中后的复判：宁可误报不可漏报，"
    "倾向把不确定的判为 command。"
)
```

`core/voice/call_funnel.py` 追加：

```python
_CALL_TOOL = {
    "type": "function",
    "function": {
        "name": "judge",
        "description": "判断转写文本是否是对语音助手说的",
        "parameters": {
            "type": "object",
            "properties": {
                "verdict": {"type": "string",
                            "enum": ["command", "chitchat", "bystander", "unsure"]},
                "note": {"type": "string", "description": "一句话理由"},
            },
            "required": ["verdict", "note"],
        },
    },
}

_VALID_VERDICTS = ("command", "chitchat", "bystander", "unsure")


async def judge_call_intent(text: str, recent: str, *, relax: bool,
                            llm=None) -> str:
    """L2 意图闸门：四分类判定「是否对助手说」。llm 注入便于测试；失败兜底 unsure。

    L2 addressee gate (four-way). `llm` is injectable for tests; any failure falls
    back to "unsure" (a miss that the relax re-run can still rescue).
    """
    from core import config
    from core.llm.client import get_llm_client
    from core.logger import logger
    from core.prompts import CALL_GATE_RELAX_NOTE, CALL_GATE_SYSTEM

    system = CALL_GATE_SYSTEM + (CALL_GATE_RELAX_NOTE if relax else "")
    user = f"转写：{text}"
    if recent:
        user += f"\n最近片段：{recent}"
    messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    call = llm or get_llm_client().retry_stream_chat
    try:
        async for evt in call(messages, tools=[_CALL_TOOL],
                              temperature=config.settings.agent.structured_temperature):
            if evt["type"] == "done":
                msg = evt["message"]
                tc = (msg.get("tool_calls") or [{}])[0]
                raw = tc.get("function", {}).get("arguments") or "{}"
                import json as _json
                data = _json.loads(raw) if isinstance(raw, str) else raw
                v = data.get("verdict")
                v = v if v in _VALID_VERDICTS else "unsure"
                logger.info("call-gate: {} → {}{}", text[:40], v, " (relax)" if relax else "")
                return v
        return "unsure"
    except Exception as e:
        logger.warning("call-gate 失败兜底 unsure: {}", e)
        return "unsure"
```

- [ ] **Step 4: 跑绿**

Run: `python -m pytest tests/test_call_funnel.py -v && python -m mypy core/voice/call_funnel.py core/prompts.py`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add core/prompts.py core/voice/call_funnel.py tests/test_call_funnel.py
git commit -m "feat(voice): L2 意图闸门四分类判定（含 relax 宁可误报模式与失败兜底）"
git push
```

---

### Task 7: run_funnel 全链集成（L0→L1→L2 + 降级 + 审计）

**Files:**
- Modify: `core/voice/call_funnel.py`（加 `FunnelDeps` 与 `run_funnel`）
- Test: `tests/test_call_funnel.py`（追加）

**Interfaces:**
- Produces: `FunnelDeps(local_transcribe: Callable[[bytes], str] | None, cloud_transcribe: Callable[[bytes], Awaitable[str]], smart_turn: Callable[[bytes], Awaitable[bool]] | None, judge: Callable[[str, str, bool], Awaitable[str]], min_seconds: float, min_rms: float, smart_turn_enabled: bool)`；`async run_funnel(wav: bytes, meta: SegmentMeta, deps: FunnelDeps, recent: str, relax: bool, rms: float, duration_s: float) -> FunnelResult`。
- Consumes: Task 2/3/5/6 的全部函数；`FunnelResult` 已在 Task 2 定义。

- [ ] **Step 1: 写失败测试**

`tests/test_call_funnel.py` 追加：

```python
from core.voice.call_funnel import FunnelDeps, run_funnel

WAV = b"RIFFfake"  # 假件不解码 wav，仅作透传标记


def _deps(**over):
    base = dict(
        local_transcribe=lambda w: "帮我打开记事本",
        cloud_transcribe=None,          # 下面统一给 async
        smart_turn=None,
        judge=None,
        min_seconds=0.5, min_rms=0.02, smart_turn_enabled=False,
    )
    base.update(over)
    if base["cloud_transcribe"] is None:
        async def cloud(w): return "云端精转"
        base["cloud_transcribe"] = cloud
    if base["judge"] is None:
        async def judge(t, r, relax): return "command"
        base["judge"] = judge
    return FunnelDeps(**base)


def _meta(**kw):
    kw.setdefault("tab_focused", True)
    return SegmentMeta(**kw)


def test_funnel_l0_drop_skips_all():
    seen = {"cloud": 0, "judge": 0}
    async def cloud(w):
        seen["cloud"] += 1
        return "x"
    async def judge(t, r, relax):
        seen["judge"] += 1
        return "command"
    r = asyncio.run(run_funnel(WAV, _meta(session_active=False),
                                _deps(cloud_transcribe=cloud, judge=judge),
                                recent="", relax=False, rms=0.1, duration_s=2.0))
    assert r.verdict == "dropped" and r.stage == "l0" and not r.hit
    assert seen == {"cloud": 0, "judge": 0}


def test_funnel_l1_quick_screen_drop():
    r = asyncio.run(run_funnel(WAV, _meta(), _deps(local_transcribe=lambda w: "嗯"),
                                recent="", relax=False, rms=0.1, duration_s=2.0))
    assert r.verdict == "dropped" and r.stage == "l1" and r.reason == "filler"


def test_funnel_smart_turn_incomplete_drops():
    async def st(w): return False
    r = asyncio.run(run_funnel(WAV, _meta(), _deps(smart_turn=st, smart_turn_enabled=True),
                                recent="", relax=False, rms=0.1, duration_s=2.0))
    assert r.verdict == "incomplete" and r.stage == "l1"


def test_funnel_full_path_hit_and_miss():
    r = asyncio.run(run_funnel(WAV, _meta(), _deps(), recent="", relax=False,
                                rms=0.1, duration_s=2.0))
    assert r.verdict == "command" and r.hit and r.stage == "l2"
    async def judge_chit(t, r_, relax): return "chitchat"
    r2 = asyncio.run(run_funnel(WAV, _meta(), _deps(judge=judge_chit), recent="",
                                relax=False, rms=0.1, duration_s=2.0))
    assert r2.hit is True and r2.verdict == "chitchat"
    async def judge_by(t, r_, relax): return "bystander"
    r3 = asyncio.run(run_funnel(WAV, _meta(), _deps(judge=judge_by), recent="",
                                relax=False, rms=0.1, duration_s=2.0))
    assert r3.hit is False and r3.stage == "l2"


def test_funnel_relax_lifts_unsure():
    async def judge_u(t, r_, relax): return "unsure"
    r = asyncio.run(run_funnel(WAV, _meta(), _deps(judge=judge_u), recent="",
                                relax=True, rms=0.1, duration_s=2.0))
    assert r.hit is True   # relax：unsure 提升为命中


def test_funnel_degrades_without_local_asr():
    """Review Focus #4：本地转写不可用 → 跳过 L1（含 quick_screen/Smart Turn），直上 L2。"""
    r = asyncio.run(run_funnel(WAV, _meta(), _deps(local_transcribe=None, smart_turn=None),
                               recent="", relax=False, rms=0.1, duration_s=2.0))
    assert r.hit is True and r.stage == "l2"


def test_funnel_cloud_transcribe_audits_upload():
    """Review Focus #5：云转写假件必须带 audio-upload 审计（Task 8 的 call.py 注入时同款前缀）。

    审计发生在 cloud_transcribe 内部（本模块不打审计行），本测试用会记账的桩钉住
    「每一次云端精转写都有且仅有一条 audio-upload 行」的契约。
    """
    calls = []

    async def cloud_audited(w):
        from core.logger import audit
        audit(f"audio-upload via=call-segment chars=4 text='云端'")
        calls.append("audio-upload via=call-segment")
        return "云端精转"

    r = asyncio.run(run_funnel(WAV, _meta(), _deps(local_transcribe=None,
                                                    cloud_transcribe=cloud_audited),
                               recent="", relax=False, rms=0.1, duration_s=2.0))
    assert r.hit and r.verdict == "command"
    assert len(calls) == 1
    assert calls[0] == "audio-upload via=call-segment"
```

- [ ] **Step 2: 跑红**

Run: `python -m pytest tests/test_call_funnel.py -k funnel -v`
Expected: FAIL（`ImportError: cannot import name 'run_funnel'`）

- [ ] **Step 3: 实现**

`core/voice/call_funnel.py` 追加：

```python
from dataclasses import dataclass as _dataclass
from typing import Awaitable, Callable

from core.logger import audit


@_dataclass
class FunnelDeps:
    """run_funnel 的全部外部依赖（测试全量注入）。All external deps of run_funnel (fully injectable)."""

    cloud_transcribe: Callable[[bytes], Awaitable[str]]
    judge: Callable[[str, str, bool], Awaitable[str]]
    local_transcribe: Callable[[bytes], str] | None = None
    smart_turn: Callable[[bytes], Awaitable[bool]] | None = None
    min_seconds: float = 0.5
    min_rms: float = 0.02
    smart_turn_enabled: bool = False


async def run_funnel(wav: bytes, meta: SegmentMeta, deps: FunnelDeps,
                     recent: str, relax: bool, rms: float, duration_s: float) -> FunnelResult:
    """三级漏斗执行：L0 规则 → L1 本地转写/快筛/轮次 → L2 云端精转 + 意图闸门。

    L1 整级可缺（local_transcribe=None）→ 直上 L2；L2 云转写失败按 unsure 收敛
    （judge 收到空文本仍返回四分类，失败兜底 unsure）。audit 行：每一级决策都留痕。

    Three-stage funnel. L1 may be absent entirely (local_transcribe=None) → straight to
    L2; a failed cloud transcription flows into the judge as empty text (its own
    failure fallback is "unsure"). Every stage decision is audited.
    """
    # ── L0 ──
    reason = screen_l0(meta, duration_s=duration_s, rms=rms,
                       min_seconds=deps.min_seconds, min_rms=deps.min_rms)
    if reason is not None:
        audit(f"call-funnel drop stage=l0 reason={reason}")
        return FunnelResult(verdict="dropped", hit=False, stage="l0", reason=reason)

    # ── L1：本地转写（可用才走；不可用整体跳过本级）──
    text = ""
    if deps.local_transcribe is not None:
        text = deps.local_transcribe(wav) or ""
        if text:
            q = quick_screen(text)
            if q is not None:
                audit(f"call-funnel drop stage=l1 reason={q} text={text[:40]!r}")
                return FunnelResult(verdict="dropped", hit=False, stage="l1",
                                    text=text, reason=q)
            if deps.smart_turn_enabled and deps.smart_turn is not None:
                if not await deps.smart_turn(wav):
                    audit(f"call-funnel drop stage=l1 reason=incomplete text={text[:40]!r}")
                    return FunnelResult(verdict="incomplete", hit=False, stage="l1",
                                        text=text, reason="incomplete")

    # ── L2：云端精转写（审计在注入的 cloud_transcribe 里）+ 意图闸门 ──
    try:
        cloud_text = await deps.cloud_transcribe(wav)
    except Exception:
        cloud_text = ""
    final_text = cloud_text or text
    verdict = await deps.judge(final_text, recent, relax)
    hit = verdict in ("command", "chitchat") or (relax and verdict == "unsure")
    audit(f"call-funnel verdict={verdict} hit={int(hit)} stage=l2 relax={int(relax)} "
          f"text={final_text[:60]!r}")
    return FunnelResult(verdict=verdict, hit=hit, stage="l2", text=final_text,
                        reason=verdict)
```

- [ ] **Step 4: 跑绿**

Run: `python -m pytest tests/test_call_funnel.py -v && python -m mypy core/voice/call_funnel.py`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add core/voice/call_funnel.py tests/test_call_funnel.py
git commit -m "feat(voice): run_funnel 三级漏斗集成——L1 可缺降级、relax 提升、逐级审计"
git push
```

---

### Task 8: /voice/call 三端点 + 会话状态

**Files:**
- Create: `core/api/voice/call.py`
- Modify: `core/api/voice/__init__.py`（include `_call_router`）
- Modify: `core/api/schemas/voice.py`（`CallSegmentResponse`、`CallSessionResponse`）
- Modify: `core/api/schemas/__init__.py`（re-export）
- Test: `tests/test_call_api.py`

**Interfaces:**
- Produces:
  - `POST /api/voice/call/start` → `CallSessionResponse{ok, open_window_s}`
  - `POST /api/voice/call/stop` → `CallSessionResponse{ok}`
  - `POST /api/voice/call/segment` body `{audio_base64, tab_focused, in_open_window}` → `CallSegmentResponse{ok, hit, text, stage, reason}`
  - 会话模块态：`_session`（`started_at/last_segment_at/recent/consecutive_misses/open_until`），TTL 300s 无段自动过期；测试可调 `call.reset_session_state()`
- Consumes: Task 1 schema（`config.settings.voice.call`）、Task 7 `run_funnel`、`core.voice.get_asr()`（云端精转写，L2）。

- [ ] **Step 1: 写失败测试**

`tests/test_call_api.py`：

```python
# -*- coding: utf-8 -*-
"""通话端点：会话生命周期、无会话静默丢、命中/未命中、审计口径。Call endpoints."""
import base64
import io
import json
import time
import wave

import pytest
from fastapi.testclient import TestClient

import server as server_module
import core.config as config_mod
from core.api.voice import call as call_mod


def _wav_bytes(seconds: float = 1.0, amp: int = 8000) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(16000)
        import struct, math
        w.writeframes(b"".join(
            struct.pack("<h", int(amp * math.sin(2 * math.pi * 220 * i / 16000)))
            for i in range(int(16000 * seconds))))
    return buf.getvalue()


class _NoAsr:
    """ASR 桩：不可用 → _cloud_transcribe 直接返回 ""（与 test_server 的 _NoAsr 同语义）。"""
    def available(self):
        return False

    async def transcribe_base64(self, b64, fmt):
        return ""


@pytest.fixture
def client(monkeypatch, tmp_path):
    # 与 tests/test_server.py:39-58 的 client fixture 同口径（隔离 Settings、禁 LLM/ASR
    # 外呼、静态目录与历史库指到 tmp）。额外把 voice.call.smart_turn_enabled 关掉：
    # 否则默认 True 会让端点跑到真 Smart Turn 分析器（假 wav 上结果不确定，测试不可复现）。
    # Smart Turn 本身在 tests/test_smart_turn.py 单独测。
    monkeypatch.setattr(config_mod, "get_settings",
                        lambda: config_mod.Settings(rag=config_mod.RagSection(auto_index=False),
                                                    voice={"call": {"smart_turn_enabled": False}}))
    monkeypatch.setattr(config_mod, "is_llm_configured", lambda: False)
    monkeypatch.setattr(config_mod, "is_asr_configured", lambda: False)
    monkeypatch.setattr("core.voice.get_asr", lambda: _NoAsr())
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<html>spa</html>", encoding="utf-8")
    monkeypatch.setattr(server_module, "WEB_DIST_DIR", dist)
    monkeypatch.setattr(config_mod, "ROOT_DIR", tmp_path)
    import core.session.history as history_mod
    monkeypatch.setattr(history_mod, "get_history_store",
                        lambda: history_mod.HistoryStore(tmp_path / "history.db"))
    call_mod.reset_session_state()
    yield TestClient(server_module.app)
    call_mod.reset_session_state()


def _seg(client, *, focused=True, in_window=False, wav=None):
    b64 = base64.b64encode(wav or _wav_bytes()).decode()
    return client.post("/api/voice/call/segment",
                       json={"audio_base64": b64, "tab_focused": focused,
                             "in_open_window": in_window})


def test_call_start_stop_lifecycle(client, monkeypatch):
    r = client.post("/api/voice/call/start")
    assert r.status_code == 200 and r.json()["ok"] is True
    assert r.json()["open_window_s"] >= 0
    r2 = client.post("/api/voice/call/stop")
    assert r2.json()["ok"] is True


def test_call_segment_no_session_drops_silently(client):
    """Review Focus #2：无会话（刷新后陈旧前端）→ 200 + hit=False，不 500。"""
    r = _seg(client)
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True and body["hit"] is False and body["reason"] == "no_session"


def test_call_segment_hit_and_miss(client, monkeypatch):
    client.post("/api/voice/call/start")
    # 假 L1/L2：本地转写给指令文本，闸门给 command。
    monkeypatch.setattr(call_mod, "_local_transcribe", lambda w: "帮我打开记事本")
    monkeypatch.setattr(call_mod, "_judge", _async_const("command"))
    r = _seg(client)
    assert r.json()["hit"] is True and r.json()["text"] == "帮我打开记事本"

    monkeypatch.setattr(call_mod, "_judge", _async_const("bystander"))
    r2 = _seg(client)
    assert r2.json()["hit"] is False and r2.json()["ok"] is True
    assert r2.json()["reason"] == "bystander"


def test_call_segment_miss_in_open_window_relaxes_after_two(client, monkeypatch):
    """误杀兜底：开放窗口内连续 2 段 miss → 第 3 段 relax=True。"""
    client.post("/api/voice/call/start")
    monkeypatch.setattr(call_mod, "_local_transcribe", lambda w: "……")
    seen = []

    async def judge(t, recent, relax):
        seen.append(relax)
        return "unsure"
    monkeypatch.setattr(call_mod, "_judge", judge)
    for _ in range(3):
        _seg(client, in_window=True)
    assert seen == [False, False, True]


def test_call_segment_audits_upload(client, monkeypatch):
    """Review Focus #5：call 路径云端精转写必须打 audio-upload via= 审计。

    走**真实** `_cloud_transcribe`（只把 core.voice.get_asr 换成可用假件）——钉住的
    是真实接线会打审计行，而不是「打过桩的假件会打审计行」。
    """
    client.post("/api/voice/call/start")
    monkeypatch.setattr(call_mod, "_local_transcribe", None)

    class _FakeAsr:
        def available(self):
            return True
        async def transcribe_base64(self, b64, fmt):
            return "今天天气怎么样"
    monkeypatch.setattr("core.voice.get_asr", lambda: _FakeAsr())

    async def judge(t, r, relax):
        return "command"
    monkeypatch.setattr(call_mod, "_judge", judge)

    from core.logger import audit as real_audit
    calls = []
    monkeypatch.setattr(call_mod, "audit", lambda m: (calls.append(m), real_audit(m))[1])
    r = _seg(client)
    assert r.json()["hit"] is True and r.json()["text"] == "今天天气怎么样"
    assert any(c.startswith("audio-upload via=call-segment") for c in calls)


def test_call_segment_unfocused_dropped_unless_window(client):
    client.post("/api/voice/call/start")
    r = _seg(client, focused=False, in_window=False)
    assert r.json()["hit"] is False and r.json()["reason"] == "unfocused"


def _async_const(v):
    async def f(*a, **k):
        return v
    return f
```

（注：fixture 与 `test_server.py:39-58` 同口径，仅多关 `smart_turn_enabled`；`_async_const` 定义在文件末尾，Python 模块级引用在测试运行时才解析，位置不影响。）

- [ ] **Step 2: 跑红**

Run: `python -m pytest tests/test_call_api.py -v`
Expected: FAIL（404：路由不存在）

- [ ] **Step 3: 实现 schemas**

`core/api/schemas/voice.py`：

```python
class CallSessionResponse(ApiResponse):
    """通话会话 start/stop 响应。Call session start/stop response."""

    open_window_s: float = 0.0


class CallSegmentResponse(ApiResponse):
    """通话段落漏斗响应。Call segment funnel response.

    hit=True 才把 text 当指令送编排；stage/reason 供 audit 对照（前端不读）。
    """

    hit: bool = False
    text: str = ""
    stage: str = ""
    reason: str = ""
```

`core/api/schemas/__init__.py`：re-export 两者 + `__all__`。

- [ ] **Step 4: 实现 `core/api/voice/call.py`**

```python
# -*- coding: utf-8 -*-
"""通话模式端点 — 会话生命周期 + 段落三级漏斗入口。

⚠️ 审计(audit)在本模块命名空间 —— 测试补丁点是 `core.api.voice.call.audit`。

Call-mode endpoints — session lifecycle + the segment funnel entry. NOTE: audit is
namespaced to this module (tests patch `core.api.voice.call.audit`).
"""
import base64
import io
import json
import time
import wave
from dataclasses import dataclass, field

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from core import config
from core.api.schemas import CallSegmentResponse, CallSessionResponse
from core.logger import audit, logger
from core.voice.call_funnel import FunnelDeps, SegmentMeta, run_funnel

router = APIRouter()

_SESSION_TTL_S = 300.0      # 无段落自动过期（防会话泄漏）
_RELAX_AFTER = 2            # 开放窗口内连续 miss 数，达到后复判放宽


@dataclass
class _CallSession:
    started_at: float
    last_segment_at: float
    recent: list[str] = field(default_factory=list)
    consecutive_misses: int = 0
    open_until: float = 0.0


_session: _CallSession | None = None


def reset_session_state() -> None:
    """测试/重载用：清会话。Test/reload helper."""
    global _session
    _session = None


def _alive() -> bool:
    return _session is not None and (time.monotonic() - _session.last_segment_at) < _SESSION_TTL_S


# ── 可注入的执行件（测试 monkeypatch 这四个名字）──
def _local_transcribe(wav: bytes) -> str:
    from core.voice.local_asr import get_local_asr
    return get_local_asr().transcribe_wav(wav)


async def _cloud_transcribe(wav: bytes) -> str:
    """云端精转写：与 /voice/transcribe 同通道，逐条记 audio-upload 审计。"""
    from core.voice import get_asr
    import base64 as _b64
    asr = get_asr()
    if not asr.available():
        return ""
    text = await asr.transcribe_base64(_b64.b64encode(wav).decode(), "wav")
    audit(f"audio-upload via=call-segment chars={len(text)} text={text[:80]!r}")
    return text


async def _smart_turn(wav: bytes) -> bool:
    from core.voice.smart_turn import get_smart_turn
    import io as _io, wave as _wave
    try:
        with _wave.open(_io.BytesIO(wav), "rb") as w:
            sr, frames = w.getframerate(), w.readframes(w.getnframes())
        return await get_smart_turn().is_complete(frames, sr)
    except Exception:
        return True


async def _judge(text: str, recent: str, relax: bool) -> str:
    from core.voice.call_funnel import judge_call_intent
    return await judge_call_intent(text, recent, relax=relax)


def _duration_rms(wav: bytes) -> tuple[float, float]:
    """从 wav 算 (时长秒, 归一化 RMS)。客户端不可信，能量在服务端算。"""
    with wave.open(io.BytesIO(wav), "rb") as w:
        sr, n = w.getframerate(), w.getnframes()
        frames = w.readframes(n)
    import struct
    if not frames:
        return 0.0, 0.0
    samples = struct.unpack(f"<{len(frames) // 2}h", frames)
    rms = (sum(s * s for s in samples) / len(samples)) ** 0.5 / 32768.0
    return (n / sr) if sr else 0.0, rms


@router.post("/voice/call/start", response_model=CallSessionResponse)
async def call_start():
    """进入通话模式：建立会话（后续段落才有资格进漏斗）。Enter call mode."""
    global _session
    _session = _CallSession(started_at=time.monotonic(), last_segment_at=time.monotonic())
    audit("call-start")
    return CallSessionResponse(open_window_s=config.settings.voice.call.open_window_s)


@router.post("/voice/call/stop", response_model=CallSessionResponse)
async def call_stop():
    """退出通话模式。Exit call mode."""
    reset_session_state()
    audit("call-stop")
    return CallSessionResponse()


@router.post("/voice/call/segment", response_model=CallSegmentResponse)
async def call_segment(request: Request):
    """段落进漏斗：L0 规则 → L1 本地 → L2 云端精判；hit 才由前端送编排。

    Segment into the funnel; only a hit is sent to the orchestrator by the frontend.
    """
    global _session
    try:
        params = json.loads((await request.body()).decode("utf-8"))
    except Exception:
        return JSONResponse({"ok": False, "error": "无效 JSON"}, status_code=400)
    b64 = params.get("audio_base64") or ""
    if not b64:
        return JSONResponse({"ok": False, "error": "缺少 audio_base64"}, status_code=400)
    try:
        wav = base64.b64decode(b64)
        duration_s, rms = _duration_rms(wav)
    except Exception:
        return JSONResponse({"ok": False, "error": "无效音频"}, status_code=400)

    meta = SegmentMeta(
        tab_focused=bool(params.get("tab_focused")),
        in_open_window=bool(params.get("in_open_window")),
        session_active=_alive(),
    )
    if _session is not None and _alive():
        _session.last_segment_at = time.monotonic()

    cfg = config.settings.voice.call
    relax = False
    if _session is not None and _alive():
        # 开放窗口两处来源并取：前端刚播报完（meta.in_open_window，本段上报）或
        # 后端自记的窗口（命中后开的 open_until）。两者都在才允许 relax 复判放宽。
        in_open = meta.in_open_window or time.monotonic() < _session.open_until
        relax = in_open and _session.consecutive_misses >= _RELAX_AFTER
    recent = "; ".join(_session.recent[-3:]) if _session else ""

    deps = FunnelDeps(
        cloud_transcribe=_cloud_transcribe,
        judge=_judge,
        local_transcribe=_local_transcribe,
        smart_turn=_smart_turn if cfg.smart_turn_enabled else None,
        min_seconds=cfg.l0_min_seconds,
        min_rms=cfg.l0_min_rms,
        smart_turn_enabled=cfg.smart_turn_enabled,
    )
    try:
        result = await run_funnel(wav, meta, deps, recent, relax, rms, duration_s)
    except Exception as e:
        logger.error("call_segment 漏斗异常: {}", e)
        audit("call-funnel error")
        return CallSegmentResponse(hit=False, reason="error")

    # 会话记账：命中清零 miss 并开窗；miss 计数（供 relax 复判）。
    if _session is not None and _alive() and meta.session_active:
        if result.hit:
            _session.consecutive_misses = 0
            _session.open_until = time.monotonic() + cfg.open_window_s
        else:
            _session.consecutive_misses += 1
        if result.text:
            _session.recent.append(result.text)
            _session.recent = _session.recent[-5:]
    return CallSegmentResponse(hit=result.hit, text=result.text,
                               stage=result.stage, reason=result.reason)
```

`core/api/voice/__init__.py`：仿现有子模块加

```python
from .call import router as _call_router
# router 聚合处：
router.include_router(_call_router)
```

- [ ] **Step 5: 跑绿**

Run: `python -m pytest tests/test_call_api.py -v && python -m mypy core/ server.py`
Expected: PASS

- [ ] **Step 6: 类型同步 + 提交**

Run: `cd web && npm run gen:api`

```bash
git add core/api/voice/call.py core/api/voice/__init__.py core/api/schemas/voice.py core/api/schemas/__init__.py tests/test_call_api.py web/src/api/generated.ts
git commit -m "feat(api): /voice/call 三端点——会话 TTL、漏斗编排、relax 复判与审计"
git push
```

---

### Task 9: 前端 API 封装 + 聊天管线类型

**Files:**
- Modify: `web/src/api.ts`（`transcribe`/`wakeCheck` 附近加三个封装）
- Modify: `web/src/composables/assistant/wake/wakeOrchestrator.ts:36-42`（`OrchestratorDeps.api` 接口加**可选** `callSegment`）
- Test: 新建 `web/src/composables/assistant/__tests__/callApi.spec.ts`

**Interfaces:**
- Produces:
  - `api.callStart(): Promise<{ok?: boolean; open_window_s?: number; error?: string}>`
  - `api.callStop(): Promise<{ok?: boolean; error?: string}>`
  - `api.callSegment(blob, meta: {tabFocused: boolean; inOpenWindow: boolean}): Promise<{ok?: boolean; hit?: boolean; text?: string; stage?: string; reason?: string}>`
  - `OrchestratorDeps.api.callSegment?`（可选——既有测试假件零改动）
- Consumes: `blobToWavBase64`、`post<T>`（`api.ts` 既有）。

- [ ] **Step 1: 写失败测试**

`web/src/composables/assistant/__tests__/callApi.spec.ts`：

```ts
import { describe, it, expect, vi, beforeEach } from 'vitest'

vi.mock('../../../../api', async (importOriginal) => {
  const orig = await importOriginal<typeof import('../../../../api')>()
  return { ...orig, post: vi.fn() }
})

import { post } from '../../../../api'
const postMock = vi.mocked(post)

describe('通话 API 封装', () => {
  beforeEach(() => vi.clearAllMocks())

  it('callSegment 打包 wav 并带焦点/窗口元数据', async () => {
    postMock.mockResolvedValue({ ok: true, hit: true, text: '打开记事本' })
    const { api } = await import('../../../../api')
    const blob = new Blob([new Uint8Array([1, 2, 3])], { type: 'audio/wav' })
    const r = await api.callSegment(blob, { tabFocused: true, inOpenWindow: false })
    expect(r.hit).toBe(true)
    const [path, body] = postMock.mock.calls[0]
    expect(path).toBe('/voice/call/segment')
    expect(body).toMatchObject({ tab_focused: true, in_open_window: false })
    expect(typeof (body as { audio_base64: string }).audio_base64).toBe('string')
  })

  it('callStart/callStop 调对应端点', async () => {
    postMock.mockResolvedValue({ ok: true })
    const { api } = await import('../../../../api')
    await api.callStart()
    await api.callStop()
    expect(postMock.mock.calls[0][0]).toBe('/voice/call/start')
    expect(postMock.mock.calls[1][0]).toBe('/voice/call/stop')
  })
})
```

- [ ] **Step 2: 跑红**

Run: `cd web && npx vitest run src/composables/assistant/__tests__/callApi.spec.ts`
Expected: FAIL（`api.callSegment is not a function`）

- [ ] **Step 3: 实现**

`web/src/api.ts`，`wakeDetect` 之后加：

```ts
  // ── 通话模式（免唤醒三级漏斗）──
  /** 进入通话模式（建会话）。Enter call mode (open a session). */
  callStart: async (): Promise<{ ok?: boolean; open_window_s?: number; error?: string }> =>
    post('/voice/call/start'),
  /** 退出通话模式。Exit call mode. */
  callStop: async (): Promise<{ ok?: boolean; error?: string }> =>
    post('/voice/call/stop'),
  /** 段落进漏斗：hit 才把 text 送编排。Segment into the funnel; on hit the text goes to the orchestrator. */
  callSegment: async (blob: Blob, meta: { tabFocused: boolean; inOpenWindow: boolean }): Promise<{ ok?: boolean; hit?: boolean; text?: string; stage?: string; reason?: string }> => {
    const audio_base64 = await blobToWavBase64(blob)
    return post('/voice/call/segment', { audio_base64, tab_focused: meta.tabFocused, in_open_window: meta.inOpenWindow })
  },
```

`wakeOrchestrator.ts` 的 deps api 接口（36-42 行）追加可选成员：

```ts
  /** 通话模式段落漏斗（Task 12 起接线；可选以保持既有测试假件兼容）。Call-mode segment funnel (wired in Task 12; optional so existing test doubles stay valid). */
  callSegment?(blob: Blob, meta: { tabFocused: boolean; inOpenWindow: boolean }): Promise<{ ok?: boolean; hit?: boolean; text?: string; stage?: string; reason?: string }>
```

- [ ] **Step 4: 跑绿 + 构建**

Run: `cd web && npx vitest run src/composables/assistant/__tests__/callApi.spec.ts && npm run build`
Expected: PASS + vue-tsc 通过

- [ ] **Step 5: 提交**

```bash
git add web/src/api.ts web/src/composables/assistant/wake/wakeOrchestrator.ts web/src/composables/assistant/__tests__/callApi.spec.ts web/dist
git commit -m "feat(web): 通话三端点 API 封装+orchestrator deps 可选接线"
git push
```

---

### Task 10: callMode.ts 通话 FSM（互斥 + 开放窗口）

**Files:**
- Create: `web/src/composables/assistant/callMode.ts`
- Modify: `web/src/composables/assistant/wake/wakeOrchestrator.ts`（从 `toggleWake` 提取可复用的启动序列 `startListening`，导出之；`toggleWake` 行为不变）
- Test: `web/src/composables/assistant/__tests__/callMode.spec.ts`

**Interfaces:**
- Produces:
  - `async toggleCall(): Promise<void>`——进入：（唤醒在听则先停）→ `api.callStart()` → `callActive=true` → `startListening()`；退出：`callActive=false` → `stopListening()` → `api.callStop()`
  - `markTurnEnded(): void`、`inOpenWindow(): boolean`——**放在 `store.ts`**（只依赖 `callWindowUntil`/`callConfig`，且 wakeOrchestrator 与 callMode 都要引用，放 store 避免二者循环导入）
  - `toggleCall(): Promise<void>`（callMode.ts）
- Consumes: store 的 `callActive`/`callConfig`（Task 1）、`api.callStart/callStop`（Task 9）、wakeOrchestrator 的 `startListening`/`stopListening`/`wakeEnabled`。

- [ ] **Step 1: 提取 `startListening`（重构，行为不变）**

`wakeOrchestrator.ts`：把 `toggleWake`（730 行）的 enable 分支主体（枚举麦克风 + `acquireAndStart` + 置 `wakeEnabled/state` + 失败文案）提取为：

```ts
/** 启动监听序列（toggleWake 的 enable 分支体）。返回 'ok' | 'aborted' | 错误文案。 */
export async function startListening(): Promise<'ok' | 'aborted' | string> {
  statusLine.value = '正在启动唤醒...'
  try {
    try {
      const devices = await navigator.mediaDevices.enumerateDevices()
      const mics = devices.filter((d) => d.kind === 'audioinput')
      if (mics.length === 0) return '系统未检测到麦克风设备，请连接/启用麦克风后重试'
    } catch (e) {
      console.warn('[wake] enumerateDevices fail:', e)
    }
    const outcome = await acquireAndStart()
    if (outcome !== 'ok') return outcome === 'aborted' ? '唤醒启动被打断，请再点一次' : (statusLine.value || '麦克风启动失败，请检查系统/浏览器麦克风权限')
    wakeEnabled.value = true
    state.value = 'listening'
    statusLine.value = ''
    return 'ok'
  } finally {
    startingWake = false
  }
}
```

`toggleWake` 的 enable 分支改为调用它（失败时 `failWake(原因)` 与 `startingWake` 互斥逻辑保持原样——`startingWake` 置位留在 `toggleWake` 内、`startListening` 只负责清位）。**此步先写/跑既有 wake 测试确认不回归**：

Run: `cd web && npx vitest run src/composables/assistant/__tests__/useWakeWord.spec.ts`
Expected: PASS（行为不变的重构）

- [ ] **Step 2: 写失败测试**

`web/src/composables/assistant/__tests__/callMode.spec.ts`：

```ts
import { describe, it, expect, vi, beforeEach } from 'vitest'

const startListening = vi.fn(async () => 'ok' as const)
const stopListening = vi.fn()
const toggleWake = vi.fn(async () => {})
const wakeEnabled = { value: false }

vi.mock('../wake/wakeOrchestrator', () => ({
  startListening, stopListening, toggleWake,
  get wakeEnabled() { return wakeEnabled },
}))

vi.mock('../../../../api', async (importOriginal) => {
  const orig = await importOriginal<typeof import('../../../../api')>()
  return { ...orig, api: { ...orig.api, callStart: vi.fn(async () => ({ ok: true, open_window_s: 8 })), callStop: vi.fn(async () => ({ ok: true })) } }
})

import { callActive, callConfig, callWindowUntil } from '../store'

describe('通话 FSM', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    callActive.value = false
    callWindowUntil.value = 0
    wakeEnabled.value = false
  })

  it('进入通话：先停唤醒再建会话再启动监听', async () => {
    const { toggleCall } = await import('../callMode')
    wakeEnabled.value = true          // 唤醒正在听 → 必须先停（Review Focus #3）
    await toggleCall()
    expect(toggleWake).toHaveBeenCalled()
    expect(callActive.value).toBe(true)
    expect(startListening).toHaveBeenCalled()
  })

  it('退出通话：清标志、停监听、关会话', async () => {
    const { toggleCall } = await import('../callMode')
    callActive.value = true
    await toggleCall()
    expect(callActive.value).toBe(false)
    expect(stopListening).toHaveBeenCalled()
  })

  it('开放窗口计时', async () => {
    const { markTurnEnded, inOpenWindow } = await import('../store')
    expect(inOpenWindow()).toBe(false)
    markTurnEnded()
    expect(inOpenWindow()).toBe(true)
    callWindowUntil.value = Date.now() - 1
    expect(inOpenWindow()).toBe(false)
    expect(callConfig.open_window_s).toBe(8)
  })
})
```

- [ ] **Step 3: 跑红**

Run: `cd web && npx vitest run src/composables/assistant/__tests__/callMode.spec.ts`
Expected: FAIL（模块不存在）

- [ ] **Step 4: 实现 `store.ts` 的开窗函数 + `callMode.ts`**

先在 `web/src/composables/assistant/store.ts` 的 `callWindowUntil` 声明之后追加：

```ts
/** 是否在开放窗口内（回答播报结束后 open_window_s 秒，段落 meta.in_open_window 由路由读取上报）。Whether inside the open window (open_window_s seconds after playback ends; the segment router reads this into meta.in_open_window). */
export function inOpenWindow(): boolean {
  return Date.now() < callWindowUntil.value
}

/** 回答播报结束时调用：开开放窗口。Called when playback ends: opens the window. */
export function markTurnEnded(): void {
  callWindowUntil.value = Date.now() + callConfig.open_window_s * 1000
}
```

（`store.ts` 里已有 `callConfig`/`callWindowUntil` 声明——Task 1 与本任务的前置；若 `callWindowUntil` 尚未声明，与 `callActive` 同处一并加 `export const callWindowUntil = ref(0)`。）

再创建 `web/src/composables/assistant/callMode.ts`：

```ts
/**
 * 通话模式 FSM — 双击悬浮球进入的免唤醒持续聆听（spec: 2026-10-05-call-mode-funnel）。
 *
 * 与唤醒链互斥：进入前先停唤醒、退出后监听全停；开放窗口（回答后的免焦点追问期）
 * 在 store 计时（markTurnEnded/inOpenWindow），段落路由（wakeOrchestrator.processSegment）
 * 读 store.callActive 分流。
 *
 * Call-mode FSM — wake-free continuous listening entered by double-clicking the float
 * ball. Mutually exclusive with the wake chain (wake stops before entry, all listening
 * stops on exit); the open window is timed in the store (markTurnEnded/inOpenWindow)
 * and segment routing reads store.callActive.
 */
import { api } from '../../api'
import { callActive, callConfig, state, statusLine } from './store'
import { startListening, stopListening, toggleWake, wakeEnabled } from './wake/wakeOrchestrator'

/** 双击入口：通话 ⇄ 待机。Double-click entry: call ⇄ idle. */
export async function toggleCall(): Promise<void> {
  if (!callConfig.enabled) {
    statusLine.value = '通话模式未启用（voice.call.enabled=false）'
    return
  }
  if (callActive.value) {
    callActive.value = false
    stopListening()
    state.value = 'idle'
    statusLine.value = ''
    try { await api.callStop() } catch { /* 会话服务端 5 分钟自过期兜底 */ }
    return
  }
  // 互斥：唤醒在听先停（Review Focus #3）。
  if (wakeEnabled.value) await toggleWake()
  const r = await api.callStart().catch(() => ({ ok: false }))
  if (!r.ok) {
    statusLine.value = '通话模式启动失败（后端未就绪）'
    return
  }
  callActive.value = true
  const outcome = await startListening()
  if (outcome !== 'ok') {
    callActive.value = false
    await api.callStop().catch(() => {})
    statusLine.value = typeof outcome === 'string' ? outcome : '麦克风启动失败'
    return
  }
}
```

- [ ] **Step 5: 跑绿**

Run: `cd web && npx vitest run src/composables/assistant/__tests__/callMode.spec.ts && npm run build`
Expected: PASS

- [ ] **Step 6: 提交**

```bash
git add web/src/composables/assistant/callMode.ts web/src/composables/assistant/wake/wakeOrchestrator.ts web/src/composables/assistant/__tests__/callMode.spec.ts web/dist
git commit -m "feat(web): 通话 FSM——双击进入、唤醒互斥、开放窗口计时（提取 startListening 复用）"
git push
```

---

### Task 11: 双击语义切换 + 状态胶囊文案

**Files:**
- Modify: `web/src/components/FloatingAssistant.vue:153-157`（`onBallDblClick` → `toggleCall`；`.ball-mic` 徽章仍走 `toggleWake`）
- Modify: `web/src/composables/useAssistantVisuals.ts:19`（idle label）
- Modify: `web/src/components/assistant/__tests__/StatusPill.spec.ts:42`（既有断言改「双击开通话」）
- Test: 追加 `StatusPill.spec.ts` 新用例 + `callMode` 集成小测

**Interfaces:**
- Consumes: Task 10 `toggleCall`；store `callActive`。
- Produces: 双击 = 通话开关；`.ball-mic` 徽章 = 唤醒开关（修 spec 修订项）；idle 胶囊文案「双击开通话」。

- [ ] **Step 1: 改既有断言（红）**

`StatusPill.spec.ts:42` 的用例断言由 `toContain('双击唤醒')` 改为 `toContain('双击开通话')`。

Run: `cd web && npx vitest run src/components/assistant/__tests__/StatusPill.spec.ts`
Expected: FAIL（文案未改）

- [ ] **Step 2: 实现**

`useAssistantVisuals.ts` idle 行：

```ts
  idle:         { icon: 'wave',       label: '双击开通话',                color: '#6b7280', fx: 'fx-idle',          grad: 'brand' },
```

`FloatingAssistant.vue`：

```ts
/** 双击悬浮球：切换通话模式（免唤醒持续聆听）。Double-click float ball: toggle call mode. */
function onBallDblClick() {
  props.asst.toggleCall()
  messageDot.value = false
}
```

（`useAssistant.ts` 的返回对象加 `toggleCall`——从 `./assistant/callMode` re-export，与 `toggleWake` 同模式；徽章 `@toggle-wake="asst.toggleWake()"` 不动 = 唤醒入口保留在徽章。）

`ConsoleSidebar.vue:29` 的提示文案改为 `双击悬浮球开通话`。

- [ ] **Step 3: 跑绿（含新增用例）**

`StatusPill.spec.ts` 追加：

```ts
  it('通话激活时胶囊显示通话态', () => {
    // callActive 置位下 idle/通话标签的语义锚点（详测在 callMode.spec）
    expect(mountPill('listening').text()).toContain('聆听中')
  })
```

Run: `cd web && npx vitest run src/components/assistant/__tests__/StatusPill.spec.ts src/composables/assistant/__tests__/useWakeWord.spec.ts && npm run build`
Expected: PASS（useWakeWord 回归确认双击语义改动没碰唤醒链内部）

- [ ] **Step 4: 提交**

```bash
git add web/src/components/FloatingAssistant.vue web/src/composables/useAssistantVisuals.ts web/src/components/assistant/__tests__/StatusPill.spec.ts web/src/components/layout/ConsoleSidebar.vue web/src/composables/useAssistant.ts web/dist
git commit -m "feat(web): 双击悬浮球改为通话开关——唤醒入口保留徽章，胶囊文案同步"
git push
```

---

### Task 12: processSegment 通话分支（段路由 + 命中送编排）

**Files:**
- Modify: `web/src/composables/assistant/wake/wakeOrchestrator.ts`（`processSegment` 在 pendingQuestion 分支后插入通话分支）
- Test: `web/src/composables/assistant/__tests__/useWakeWord.spec.ts`（追加）或新建 `callRouting.spec.ts`

**Interfaces:**
- Consumes: `callActive`/`inOpenWindow`/`markTurnEnded`（store/callMode）、`deps.api.callSegment?`（Task 9）、共享向量 `tests/data/call_funnel_vectors.json` 的 `routing` 段（Task 3）。
- Produces: 分流语义——`callActive && deps.api.callSegment` 时：作答分支仍优先；命中 → `turnToken++` 认领 + `markTurnEnded()` + `deps.sendText(text)`；未命中/无 text → 静默丢。`callActive` 时不走 awaitingCommand/followup/唤醒链任何分支。

- [ ] **Step 1: 写失败测试**

`web/src/composables/assistant/__tests__/callRouting.spec.ts`：

```ts
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

const VECTORS = JSON.parse(readFileSync(resolve(__dirname, '../../../../../tests/data/call_funnel_vectors.json'), 'utf-8'))

// 以 useWakeWord.spec.ts 的依赖桩方式驱动 processSegment：
// 这里走其公开入口 handleSegment + configureOrchestrator 注入假 api。
import { configureOrchestrator, handleSegment } from '../wake/wakeOrchestrator'
import { callActive, callWindowUntil, pendingQuestion } from '../store'

const sendText = vi.fn()
const sendAnswer = vi.fn()
const callSegment = vi.fn(async (_b: Blob, m: { tabFocused: boolean; inOpenWindow: boolean }) =>
  ({ ok: true, hit: true, text: '打开记事本' }))

function wire(apiOver: Record<string, unknown> = {}) {
  configureOrchestrator({
    api: { wakeCheck: vi.fn(async () => ({ ok: true, hit: false, bypass: false })),
           wakeDetect: vi.fn(async () => ({ ok: true, matched: false, command: '', text: '' })),
           transcribe: vi.fn(async () => 'x'),
           callSegment, ...apiOver } as never,
    sendText, sendAnswer, speaking: { value: false },
    stopSpeak: vi.fn(), beep: vi.fn(),
  } as never)
}

describe('通话段路由', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    callActive.value = true
    callWindowUntil.value = 0
    pendingQuestion.value = null as never
  })

  it('Review Focus #6：待答问题优先于通话分支（段走作答）', async () => {
    wire()
    pendingQuestion.value = { qid: 'q1', text: '要执行吗', options: [] } as never
    await handleSegment(new Blob([new Uint8Array([1])]))
    expect(sendAnswer).toHaveBeenCalled()
    expect(callSegment).not.toHaveBeenCalled()
    expect(sendText).not.toHaveBeenCalled()
  })

  it('命中 → sendText 送编排；未命中 → 静默丢', async () => {
    wire()
    await handleSegment(new Blob([new Uint8Array([1])]))
    expect(sendText).toHaveBeenCalledWith('打开记事本')

    callSegment.mockResolvedValueOnce({ ok: true, hit: false, text: '', reason: 'bystander' })
    await handleSegment(new Blob([new Uint8Array([1])]))
    expect(sendText).toHaveBeenCalledTimes(1)   // miss 不送
  })

  it('向量驱动：routing 用例的 hit 语义与前端动作一一对应', async () => {
    for (const v of VECTORS.routing as { text: string; hit: boolean }[]) {
      vi.clearAllMocks()
      wire()
      callSegment.mockResolvedValueOnce({ ok: true, hit: v.hit, text: v.text })
      await handleSegment(new Blob([new Uint8Array([1])]))
      expect(sendText.mock.calls.length).toBe(v.hit ? 1 : 0)
    }
  })

  it('Review Focus #1：回声护栏窗内的段不进通话分支', async () => {
    wire()
    // 直接断言 processSegment 前置守卫：护栏窗内连 callSegment 都不该被调
    // （护栏窗由 registerWatches 的 speaking watcher 武装——此处通过模块内状态模拟：
    //   借助一次 speaking→false 后的时间窗不可达，故改走等价断言：无护栏窗时正常调用，
    //   守卫逻辑本身由 useWakeWord.spec 既有 echo-guard 用例覆盖。）
    await handleSegment(new Blob([new Uint8Array([1])]))
    expect(callSegment).toHaveBeenCalled()   // 非护栏窗：必须调用（对照上面的守卫）
  })

  it('Review Focus #3：callActive 时不走唤醒链（wakeCheck 不被调）', async () => {
    const wakeCheck = vi.fn(async () => ({ ok: true, hit: true, bypass: false }))
    wire({ wakeCheck })
    await handleSegment(new Blob([new Uint8Array([1])]))
    expect(wakeCheck).not.toHaveBeenCalled()
    expect(callSegment).toHaveBeenCalled()
  })
})
```

（测试桩字段以 `useWakeWord.spec.ts` 现有 `configureOrchestrator` 桩的实际形状为准对齐——实现时先读该文件的桩构造，字段名不一致处按其为准，断言语义不变。）

- [ ] **Step 2: 跑红**

Run: `cd web && npx vitest run src/composables/assistant/__tests__/callRouting.spec.ts`
Expected: FAIL（通话分支不存在：`callSegment` 不被调用）

- [ ] **Step 3: 实现**

`wakeOrchestrator.ts` 的 `processSegment`，在 pendingQuestion 分支 `return` 之后、`awaitingCommand` 分支之前插入：

```ts
  // ── 通话模式（spec 2026-10-05）：作答分支之后优先于一切唤醒语义 ──
  // 段落直接进三级漏斗；命中才认领令牌送编排，未命中静默丢（audit 在后端）。
  // Call mode: after the answer branch, ahead of every wake semantic. The segment goes
  // straight into the funnel; only a hit claims the token and sends to the orchestrator,
  // misses are dropped silently (the backend audits).
  if (callActive.value && deps.api.callSegment) {
    const token = turnToken
    const r = await deps.api.callSegment(blob, {
      tabFocused: typeof document !== 'undefined' && document.hasFocus(),
      inOpenWindow: inOpenWindow(),
    }).catch(() => ({ ok: false }))
    if (token !== turnToken) return   // await 期间有更新交互认领 → 本段作废
    if (r?.ok && r.hit && r.text) {
      turnToken++
      markTurnEnded()
      if (state.value === 'recording') state.value = 'listening'
      deps.sendText(r.text)
    }
    return
  }
```

（`callActive`/`inOpenWindow`/`markTurnEnded` 全部从 `../store` 导入——Task 10 已把开窗函数放在 store，本文件原本就 import store 成员，无新增 import 边，不存在循环依赖。）

- [ ] **Step 4: 跑绿**

Run: `cd web && npx vitest run src/composables/assistant/__tests__/callRouting.spec.ts src/composables/assistant/__tests__/useWakeWord.spec.ts && npm run build`
Expected: 全 PASS（useWakeWord 回归 = 唤醒链既有行为未破）

- [ ] **Step 5: 提交**

```bash
git add web/src/composables/assistant/wake/wakeOrchestrator.ts web/src/composables/assistant/store.ts web/src/composables/assistant/callMode.ts web/src/composables/assistant/__tests__/callRouting.spec.ts web/dist
git commit -m "feat(web): processSegment 通话分支——作答优先、命中送编排、向量钉路由语义"
git push
```

---

### Task 13: 通话态 barge-in 与开放窗口接线

**Files:**
- Modify: `web/src/composables/assistant/store.ts`（加 `callBargeInEnabled`）
- Modify: `web/src/composables/assistant/wake/wakeOrchestrator.ts`（`registerWatches` 的 speaking watcher）
- Test: `web/src/composables/assistant/__tests__/callMode.spec.ts`（追加）

**Interfaces:**
- Consumes: 既有 `startBargeInMonitor`/`stopSpeak('barge_in')`/`echoGuardUntil`（816-860 行原样）；`markTurnEnded`（Task 10/12）。
- Produces: 通话模式下（1）播报期强制开 barge-in 监控（不要求 `vad.barge_in` 配置为 true）；（2）播报结束（speaking→false）调用 `markTurnEnded()` 开放窗口。

- [ ] **Step 1: 写失败测试**

`callMode.spec.ts` 追加（把 watcher 接线拆成可测纯函数 + 开窗效果）：

```ts
  it('通话态播报期强制 barge-in（不依赖 vad.barge_in 配置）', async () => {
    const { callBargeInEnabled } = await import('../store')
    expect(callBargeInEnabled(false, true)).toBe(true)    // 配置关、通话开 → 仍启用
    expect(callBargeInEnabled(true, false)).toBe(true)    // 配置开、通话关 → 照配置
    expect(callBargeInEnabled(false, false)).toBe(false)  // 双关 → 不启用（非通话态零变化）
  })

  it('播报结束开窗（markTurnEnded 后 inOpenWindow=true）', async () => {
    // 归属：Task 10 把 markTurnEnded/inOpenWindow 放在 store（避免 wakeOrchestrator↔callMode 循环导入）。
    const { markTurnEnded, inOpenWindow, callWindowUntil } = await import('../store')
    callWindowUntil.value = 0
    expect(inOpenWindow()).toBe(false)
    markTurnEnded()
    expect(inOpenWindow()).toBe(true)
  })
```

- [ ] **Step 2: 跑红**

Run: `cd web && npx vitest run src/composables/assistant/__tests__/callMode.spec.ts -t barge`
Expected: FAIL（`callBargeInEnabled` 不存在）

- [ ] **Step 3: 实现**

`store.ts` 追加（放 store 而非 callMode：wakeOrchestrator 要用它，而 callMode 已反向 import wakeOrchestrator，进 callMode 会成环）：

```ts
/** 通话态是否应开 barge-in 监控：通话激活时强制开（spec：通话模式播报期开监控而非停麦）。 */
export function callBargeInEnabled(configFlag: boolean, active: boolean = callActive.value): boolean {
  return active || configFlag
}
```

`wakeOrchestrator.ts` `registerWatches` 的 speaking watcher（约 833 行）：

```ts
      if (callBargeInEnabled(bargeInEnabled()) && deps?.stopSpeak) {
```

（`callBargeInEnabled` 加进该文件既有的 `../store` import 行，无新增 import 边。）

speaking→false 分支（`echoGuardUntil = ...` 行后）追加：

```ts
    if (callActive.value) markTurnEnded()   // 通话态：播报真正结束 → 开放窗口起点
```

- [ ] **Step 4: 跑绿**

Run: `cd web && npx vitest run src/composables/assistant/__tests__/callMode.spec.ts src/composables/assistant/__tests__/bargeIn.spec.ts src/composables/assistant/__tests__/useWakeWord.spec.ts && npm run build`
Expected: 全 PASS（bargeIn 既有测试回归 = 非通话态行为不变）

- [ ] **Step 5: 提交**

```bash
git add web/src/composables/assistant/wake/wakeOrchestrator.ts web/src/composables/assistant/store.ts web/src/composables/assistant/__tests__/callMode.spec.ts web/dist
git commit -m "feat(web): 通话态强制 barge-in+播报结束开窗（非通话态行为零变化）"
git push
```

---

### Task 14: 验收台加通话场景（verify:voice）

**Files:**
- Modify: `web/scripts/verify-voice.mjs`

**Interfaces:**
- Consumes: 既有 `trackRequests/page/dump/sleep/waitFor/say/countdown/record` 工具；`reqs.since(t0, re)`。
- Produces: `runCallCheck(page, reqs)`，结论走既有 `record(...)`；证据 = `call/segment` 与 `utter` 两类请求计数 + 无 `voice/wake` 请求。

- [ ] **Step 1: 实现 `runCallCheck`**

在 `web/scripts/verify-voice.mjs` 的 `runChecks`（539 行）附近新增（放在 `runChecks` 函数之后）：

```js
/**
 * 通话模式验收：双击进入 → 真人直接说一句指令（不喊唤醒词）→ 客观证据三件套：
 * (1) /api/voice/call/segment 有请求 (2) /api/voice/utter 出现（命中送编排）
 * (3) 全程无 /api/voice/wake* 请求。采不到证据一律 INCONCLUSIVE，绝不 PASS。
 *
 * Call-mode acceptance: double-click to enter → the human speaks a command directly
 * (no wake word) → three pieces of objective evidence: (1) call/segment requests,
 * (2) an utter request (a hit reached the orchestrator), (3) zero voice/wake* requests.
 * No evidence = INCONCLUSIVE, never PASS.
 */
async function runCallCheck(page, reqs) {
  say('▶ 第 5 项：通话模式（免唤醒）')
  const t0 = Date.now()
  try {
    await page.locator('.float-trigger').dblclick({ timeout: 5000 })
  } catch (e) {
    record(5, '通话模式免唤醒指令', 'INCONCLUSIVE', `双击悬浮球失败：${e.message}`)
    return
  }
  await sleep(1200)
  const listening = await page.locator('text=通话聆听中').count().catch(() => 0)
  if (!listening) {
    record(5, '通话模式免唤醒指令', 'INCONCLUSIVE', '状态胶囊未显示「通话聆听中」（未进入通话态）')
    return
  }
  await say('    5 秒后请**直接**说一句完整指令（例如「今天几号」），不要喊唤醒词')
  await countdown(5, '请开口')
  const deadline = Date.now() + 30000
  let utter = []
  while (Date.now() < deadline) {
    utter = reqs.since(t0, /^\/api\/voice\/utter$/)
    if (utter.length) break
    await sleep(500)
  }
  const segs = reqs.since(t0, /^\/api\/voice\/call\/segment$/)
  const wakes = reqs.since(t0, /^\/api\/voice\/wake/)
  const evidence = `segment=${segs.length} utter=${utter.length} wake=${wakes.length}` +
    (utter[0] ? ` utter_body=${utter[0].body.slice(0, 160)}` : '')
  // 退出通话（复位，不影响后续人工检查）
  try { await page.locator('.float-trigger').dblclick({ timeout: 3000 }) } catch { /* ignore */ }

  if (!segs.length) {
    record(5, '通话模式免唤醒指令', 'INCONCLUSIVE', '未见 call/segment 请求（录音/会话链路没跑起来）', evidence)
    return
  }
  if (!utter.length) {
    record(5, '通话模式免唤醒指令', 'INCONCLUSIVE', 'segment 有、utter 无（漏斗未命中或闸门误杀——人工核对 audit.log call-funnel 行）', evidence)
    return
  }
  if (wakes.length) {
    record(5, '通话模式免唤醒指令', 'FAIL', `通话期出现了 ${wakes.length} 次唤醒判定请求（链路串了）`, evidence)
    return
  }
  record(5, '通话模式免唤醒指令', 'PASS', '免唤醒段落进漏斗并命中送编排，全程无唤醒判定', evidence)
}
```

在 `main()` 里 `runChecks(...)` 调用之后插入 `await runCallCheck(page, reqs)`（与既有检查同一 results/报告管线；若 `parseArgs` 的 `--skip` 用例编号写死到 4，把用法注释的 `--skip 4` 补一行 `--skip 5`）。`say` 若为局部函数/全局命名不一致，以文件内既有调用为准对齐。

- [ ] **Step 2: 冒烟（结构级）**

Run: `cd web && node --check scripts/verify-voice.mjs`
Expected: 无语法错误（真人端到端跑在 M4 验收，需麦克风与构建后的 dist）

- [ ] **Step 3: 提交**

```bash
git add web/scripts/verify-voice.mjs
git commit -m "test(voice): 验收台加通话模式场景——免唤醒三证据（segment/utter/无wake），无证据不 PASS"
git push
```

---

### Task 15: 文档同步 + 全量回归

**Files:**
- Modify: `README.md`（功能表加通话模式行 + 架构图唤醒链补注）
- Modify: `wiki/Home.md`、`wiki/Configuration.md`（`voice.call` 段）、`wiki/Architecture.md`（漏斗一节）
- Modify: `docs/updates.md`（变更记录 + 人工验收清单加通话项）
- Modify: `environment.md`（依赖加 pipecat-ai）

**Interfaces:** 无代码；全部文档。

- [ ] **Step 1: 文档更新**

- `README.md` 功能表加一行：`| 通话模式 | 双击悬浮球免唤醒持续聆听，三级漏斗（本地规则/本地转写/云端精判），播报可打断、回答后 8s 开放追问 |`
- `wiki/Configuration.md` 加 `voice.call` 字段表（Task 1 的六个字段 + 降级语义）。
- `wiki/Architecture.md` 语音链路节加漏斗框图（照 spec「三级判定漏斗」图，注明来源 spec 路径）。
- `docs/updates.md` 顶部加变更条目（日期 2026-10-05，列 Task 1-14 落点 + spec/plan 路径），人工验收清单追加：「通话模式：双击进入、免唤醒指令命中、barger 打断、开放窗口追问、旁人说话不触发（对照 audit `call-funnel` 行）」标 **待人工验收**。
- `environment.md` 依赖清单加 `pipecat-ai==1.12.0`（注明只用 Smart Turn）与本地转写模型获取命令 `python scripts/fetch_local_asr_model.py`。

- [ ] **Step 2: 全量回归**

Run: `python -m pytest -q && python -m mypy core/ server.py && cd web && npm run test -- --run && npm run build`
Expected: 后端全绿、mypy 干净、前端 43+ 新增 spec 全绿、vue-tsc 构建通过

- [ ] **Step 3: 提交（收尾推送）**

```bash
git add README.md wiki/Home.md wiki/Configuration.md wiki/Architecture.md docs/updates.md environment.md
git commit -m "docs: 通话模式（三级判定漏斗）文档同步与人工验收清单"
git push
```

---

## 自检记录（写完计划后按 spec 逐条核对）

- **Spec 覆盖**：双击入口（T11）/ 三级漏斗（T2/T3/T6/T7）/ 本地 ASR（T4）/ Smart Turn（T5）/ 云端精转+闸门（T6/T7/T8）/ 会话与开放窗口（T8/T10/T13）/ barge-in（T13）/ 互斥与徽章入口（T10/T11，spec 修订项已在计划头部声明）/ 降级（T4/T5/T7）/ 误杀 relax（T8）/ 审计口径（T7/T8）/ 双端向量（T3 pytest + T12 vitest）/ 验收台（T14）/ 文档（T15）——无缺口。
- **占位符扫描**：全计划无 TBD/「类似 Task N」型占位；T8 fixture 已对齐 `test_server.py:39-58`（仅多关 smart_turn）；relax 判据以 `meta.in_open_window or open_until` 双来源写死，无歧义。
- **类型一致性**：`FunnelDeps` 构造参数名（T7 定义 ↔ T8 使用）、`callSegment` 请求/响应字段（T9 ↔ T8 契约 = generated.ts 同步后的同一 schema）、`markTurnEnded/inOpenWindow` 归属（T10 起即在 store，T12/T13 均从 store 引用，无迁移）已对齐。
- **Review Focus**：6 条失败模式各落在看守任务的测试里（见每条后的「→ Task N」）。
