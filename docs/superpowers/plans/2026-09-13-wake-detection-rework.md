# 唤醒链路重构（子项目 1）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 用「本地 VAD → 云端 KWS(ASR 匹配) → 现有 ASR」替换失效的 Vosk 唤醒，让「衍衡」或「洛吉斯」重新可用，并支持一句话说完。

**Architecture:** 前端保持单次 `getUserMedia`，用常驻 `AnalyserNode` 做本地 VAD（第一道闸，只上传疑似人声的片段）；分段录音后调新增的 `POST /api/voice/wake`，由后端完成 ASR 转写与唤醒词匹配，返回 `{matched, command, text}`；前端按 `command` 是否为空决定「直接发起任务」还是「提示音后等指令」。Vosk 引擎与 43MB 模型一并移除。

**Tech Stack:** Python 3.14 / FastAPI / pydantic v2 / pytest；Vue 3.4 + TypeScript + Vite 5 / vue-tsc / Vitest 4。

**Spec:** `docs/superpowers/specs/2026-09-13-wake-detection-rework-design.md`

## Global Constraints

- 后端新增/修改的 docstring 必须**中英双语**；前端注释同样双语。
- **唤醒词匹配只做同音字容错，绝不做拼音/模糊/子串匹配** —— 唤醒是执行闸门的前置，宁可漏也不可错触发。
- **匹配只在归一化文本的「开头」生效**：`我昨天说衍衡那个事` 不得命中。
- **`core/api/schemas.py` 存在与 `core/config/schema.py` 重复的手工模型**（`VadConfig`、`WakeWordConfig` 都有副本）：FastAPI 的 `response_model` 会静默丢掉多余字段，**加字段必须两处同步**，且必须与 schema 变更**同一个 commit** 重新生成 `web/src/api/generated.ts`。
- **`.codex-preview/`、`data/`、`memory/`、`web/dist/` 不入库**，不要 `git add -A`。
- 后端验证：`python -m pytest tests/ -q` + `python -m mypy core/ server.py`；前端：`cd web && npm test` + `npm run build`；类型门禁：`cd web && npm run gen:api && git diff --exit-code src/api/generated.ts`。
- TDD：先写失败测试 → 运行确认失败 → 最小实现 → 运行确认通过 → 提交。
- 每个 Task 结束跑**全量**回归（历史上循环导入只在全量下复现）。
- **不实现停顿检测**：`衍衡`+停顿+指令 与 `衍衡，查天气` 两种情况由 VAD 分段天然覆盖（见 spec「为什么不做停顿切分」）。

---

## 文件结构

| 文件 | 职责 | 动作 |
|---|---|---|
| `core/voice/wake.py` | 唤醒词匹配纯函数（归一化 / 同音字 / 开头匹配 / 切分） | Create |
| `core/config/schema.py` | `VadConfig` 新增 `min_speech_ms`、`upload_throttle_ms` | Modify |
| `core/api/schemas.py` | 同步 `VadConfig` 手工副本 + 新增 `WakeResponse` | Modify |
| `core/api/voice.py` | 新增 `POST /api/voice/wake` | Modify |
| `tests/test_voice_wake.py` | 匹配纯函数单测（固化实测样本） | Create |
| `tests/test_server.py` | 端点单测 | Modify |
| `web/src/api.ts` | `wakeDetect(blob)` 客户端方法 | Modify |
| `web/src/composables/assistant/useSegmentRecorder.ts` | 常驻 VAD + 分段录音 | Create |
| `web/src/composables/assistant/useWakeWord.ts` | 重写：调 `/voice/wake`，驱动状态机 | Modify |
| `web/public/lib/wake-word.js` 等 6 个文件 | Vosk 移除 | Delete |
| `README.md` / `wiki/Security.md` | 隐私边界变化说明 | Modify |

---

## Task 1: 唤醒词匹配纯函数（`core/voice/wake.py`）

**Files:**
- Create: `core/voice/wake.py`
- Test: `tests/test_voice_wake.py`

**Interfaces:**
- Consumes: 无
- Produces: `normalize(text: str) -> str`；`WakeResult`（frozen dataclass，字段 `matched: bool` / `command: str` / `text: str`）；`detect(text: str, keywords: list[str]) -> WakeResult`

- [ ] **Step 1: 写失败测试**

新建 `tests/test_voice_wake.py`：

```python
# -*- coding: utf-8 -*-
"""唤醒词匹配（normalize / detect）的测试。

**用例全部来自实测**：下面的「云端实测转写」是把合成音频喂给已配置的 ASR
（mimo-v2.5-asr）拿到的真实输出，不是臆造的。改匹配规则前先看这些样本 ——
它们是本次重构最有价值的回归资产。

Tests for wake-word matching (normalize / detect). Every case comes from **measurement**:
the "measured transcript" strings below are real output from feeding synthesised audio to the
configured ASR (mimo-v2.5-asr). Read these samples before changing the matching rules — they are
the most valuable regression asset of this rework.
"""
import pytest

from core.voice.wake import WakeResult, detect, normalize

KEYWORDS = ["衍衡", "洛吉斯"]


# ─── normalize ───

@pytest.mark.parametrize(
    "raw,expected",
    [
        ("洛吉斯。", "洛吉斯"),
        ("衍衡，帮我查天气。", "衍衡帮我查天气"),
        (" 衍 衡 ", "衍衡"),
        ("洛吉斯！？", "洛吉斯"),
        ("", ""),
    ],
)
def test_normalize_strips_punctuation_and_space(raw, expected):
    """归一化去掉空白与中英文标点。ASR 会自行补句号，必须剥掉。
    Normalisation drops whitespace and CJK/ASCII punctuation; the ASR adds its own full stops."""
    assert normalize(raw) == expected


# ─── detect：正例（全部为实测转写）───

def test_detect_measured_luoji_si():
    """实测：云端把「洛吉斯」转成「洛吉斯。」—— 一字不差，直接命中。
    Measured: the cloud transcribes 洛吉斯 verbatim as "洛吉斯。"."""
    r = detect("洛吉斯。", KEYWORDS)
    assert r == WakeResult(matched=True, command="", text="洛吉斯。")


def test_detect_measured_yan_heng_homophone():
    """实测：云端把「衍衡」转成「燕恒。」—— 靠同音字表命中。
    这是整套同音字容错存在的唯一理由。
    Measured: the cloud renders 衍衡 as "燕恒。" — a hit only via the homophone table, which is the
    sole reason that table exists."""
    r = detect("燕恒。", KEYWORDS)
    assert r.matched is True and r.command == ""


def test_detect_wake_word_plus_command():
    """唤醒词 + 指令：切出后半段作为指令。Wake word plus command splits out the command."""
    r = detect("衍衡，帮我查天气。", KEYWORDS)
    assert r.matched is True
    assert r.command == "帮我查天气"


def test_detect_verbatim_keyword():
    """原字命中也算（不能只认同音字）。A verbatim hit counts too — homophones are a fallback."""
    assert detect("衍衡", KEYWORDS).matched is True


# ─── detect：反例（绝不能命中）───

@pytest.mark.parametrize(
    "text",
    [
        "今天天气怎么样",
        "我昨天说衍衡那个事",          # 唤醒词不在开头 → 不命中
        "帮我看看洛吉斯的情况",         # 同上
        "若缉私",                      # Vosk 的误识别，不该被云端路径接受
        "也行",                        # 实测 Vosk 把「衍衡」听成「也行」—— 极常见短语，绝不能命中
        "若",                          # 实测 Vosk 把「洛吉斯」听成单字「若」
        "",
    ],
)
def test_detect_negatives(text):
    """反例一条都不能命中。唤醒是执行闸门的前置，错触发的代价远大于漏触发。

    尤其注意 `也行` 与 `若`：这两个是 Vosk 的错误输出、且在中文里极常见 —— 若把它们
    写进同音字表，「衍衡」会变成一句日常用语就能唤醒。

    Not one negative may match. A false wake is far costlier than a miss. Note "也行" and "若" in
    particular: they are Vosk's misrecognitions and are extremely common Chinese — folding them into
    the homophone table would make an everyday phrase wake the assistant.
    """
    r = detect(text, KEYWORDS)
    assert r.matched is False, text
    assert r.command == ""
    assert r.text == text


def test_detect_no_keywords_configured():
    """未配置唤醒词时一律不命中，且不改写 text。No keywords configured means no match, text untouched."""
    assert detect("衍衡", []).matched is False


def test_detect_keeps_original_text():
    """text 字段始终是原始转写（审计与排障要用），不被归一化改写。
    The text field always carries the original transcript (needed for audit and debugging)."""
    r = detect("衍衡，帮我查天气。", KEYWORDS)
    assert r.text == "衍衡，帮我查天气。"


def test_detect_longest_match_wins():
    """多个候选命中时取最长的，避免短词抢占（如「衍」先于「衍衡」）。
    The longest matching candidate wins, so a short one cannot pre-empt a longer one."""
    r = detect("衍衡查天气", ["衍", "衍衡"])
    assert r.command == "查天气"
```

- [ ] **Step 2: 运行确认失败**

Run: `python -m pytest tests/test_voice_wake.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'core.voice.wake'`

- [ ] **Step 3: 实现**

新建 `core/voice/wake.py`：

```python
# -*- coding: utf-8 -*-
"""唤醒词检测 —— 从 ASR 转写里判定唤醒词并切出指令。

**为什么要有同音字表**：实测把「衍衡」的音频喂给已配置的云端 ASR，转写结果是
「燕恒」—— 同音不同字。没有这张表，「衍衡」永远唤不醒。

**为什么只收同音字、不做拼音或模糊匹配**：唤醒是执行闸门的前置，错触发的代价
远大于漏触发。实测中 Vosk 曾把「衍衡」听成「也行」、把「洛吉斯」听成「若」——
这两个都是中文里的高频词，一旦写进表里，一句日常用语就能唤醒助手。故本表只收
**声母韵母都相同**的字，且逐条经过评估。

Wake-word detection: decide whether an ASR transcript starts with a wake word and split out the
command. **Why a homophone table exists**: feeding 衍衡's audio to the configured cloud ASR yields
"燕恒" — same sound, different characters; without the table 衍衡 could never wake. **Why only
homophones and never pinyin or fuzzy matching**: a wake is the gateway to execution, so a false
trigger costs far more than a miss. Measurement showed Vosk hearing 衍衡 as "也行" and 洛吉斯 as
"若" — both extremely common Chinese words; folding them in would let an everyday phrase wake the
assistant. The table therefore admits only same-syllable characters, each vetted by hand.
"""
from dataclasses import dataclass

# 同音字容错表：字符 → 与之同音、且实测/预期会被 ASR 混淆的字。
# Homophone fallbacks: character → same-syllable characters the ASR is known or expected to confuse.
_HOMOPHONES: dict[str, tuple[str, ...]] = {
    "衍": ("燕", "演", "眼", "沿"),
    "衡": ("恒", "横", "哼"),
}

# 归一化时剥掉的字符：ASCII 标点 + 中文标点 + 全部空白。
# Characters stripped during normalisation: ASCII punctuation, CJK punctuation, all whitespace.
_STRIP = set(
    " \t\n\r\v\f"
    "!\"#$%&'()*+,-./:;<=>?@[\\]^_`{|}~"
    "，。！？、；：“”‘’（）《》【】〈〉「」『』…—～·"
)


def normalize(text: str) -> str:
    """去掉空白与中英文标点。

    ASR 会自行补句号（实测「洛吉斯。」），故匹配前必须归一化。

    Strip whitespace and CJK/ASCII punctuation. The ASR adds its own full stops (measured:
    "洛吉斯。"), so matching must normalise first.

    Args:
        text: 原始转写。The raw transcript.

    Returns:
        归一化后的文本。The normalised text.
    """
    return "".join(ch for ch in text if ch not in _STRIP)


def _variants(keyword: str) -> list[str]:
    """把唤醒词展开成「原字 ∪ 同音字」的所有组合。

    例：衍衡 → 衍衡 / 衍恒 / 燕衡 / 燕恒 / …（5 × 4 = 20 种）。

    Expand a wake word into every combination of its characters and their homophones. For 衍衡
    that is 5 × 4 = 20 candidates.

    Args:
        keyword: 唤醒词。The wake word.

    Returns:
        候选字面量列表；唤醒词为空时返回空列表。The candidate literals, empty when the keyword is blank.
    """
    key = normalize(keyword)
    if not key:
        return []
    sets = [tuple({ch, *_HOMOPHONES.get(ch, ())}) for ch in key]
    out = [""]
    for chars in sets:
        out = [prefix + ch for prefix in out for ch in chars]
    return out


@dataclass(frozen=True)
class WakeResult:
    """唤醒判定结果。The outcome of a wake-word judgement.

    matched 为是否命中；command 为唤醒词之后的内容（仅唤醒词时为空串）；text 为**原始**转写
    （供审计与排障，不被归一化改写）。

    matched says whether the wake word hit; command is what followed it (empty when only the wake
    word was spoken); text is the **original** transcript, kept unmodified for audit and debugging.
    """

    matched: bool
    command: str
    text: str


def detect(text: str, keywords: list[str]) -> WakeResult:
    """判定转写是否**以**唤醒词开头，并切出其后内容作为指令。

    只在开头匹配 —— 唤醒词出现在句中不算命中（`我昨天说衍衡那个事` 不应触发）。
    多个候选命中时取最长者，避免短词抢占。

    Decide whether the transcript **starts with** a wake word and split out what follows as the
    command. Only a leading match counts: a wake word mid-sentence must not fire ("我昨天说衍衡那个事").
    When several candidates match, the longest wins so a short one cannot pre-empt a longer one.

    Args:
        text: ASR 原始转写。The raw ASR transcript.
        keywords: 已配置的唤醒词列表。The configured wake words.

    Returns:
        判定结果。The judgement.
    """
    norm = normalize(text)
    best = ""
    for keyword in keywords:
        for variant in _variants(keyword):
            if len(variant) > len(best) and norm.startswith(variant):
                best = variant
    if not best:
        return WakeResult(matched=False, command="", text=text)
    return WakeResult(matched=True, command=norm[len(best):], text=text)
```

- [ ] **Step 4: 运行确认通过 + 全量后端回归**

Run: `python -m pytest tests/test_voice_wake.py -q && python -m pytest tests/ -q && python -m mypy core/ server.py`
Expected: 全部通过

- [ ] **Step 5: 提交**

```bash
git add core/voice/wake.py tests/test_voice_wake.py
git commit -m "feat(唤醒): 唤醒词匹配纯函数（同音字容错 + 仅在开头匹配）

实测驱动：云端 ASR 把「衍衡」转成「燕恒」，故需同音字表；把「洛吉斯」转成
「洛吉斯。」，故需去标点归一化。

只收同音字、不做拼音或模糊匹配，且只在**开头**匹配 —— 唤醒是执行闸门的前置，
错触发代价远大于漏触发。反例里特意保留 Vosk 的误识别「也行」「若」：它们是中文
高频词，写进表里就等于一句日常用语能唤醒助手。

用例全部来自实测转写，是本次重构最有价值的回归资产。"
```

---

## Task 2: VAD 配置新增两个字段（含同步手工副本）

**Files:**
- Modify: `core/config/schema.py`（`VadConfig`，约 192-205 行）
- Modify: `core/api/schemas.py`（`VadConfig` 手工副本，约 51 行）
- Test: `tests/test_config.py`

**Interfaces:**
- Consumes: 无
- Produces: `VadConfig.min_speech_ms: int = 300`、`VadConfig.upload_throttle_ms: int = 500`

- [ ] **Step 1: 写失败测试**

在 `tests/test_config.py` 追加：

```python
# ─── 唤醒上传的成本控制字段（子项目 1）───


def test_vad_wake_cost_control_defaults():
    """VAD 段新增两个成本控制字段：最短语音时长与上传节流。

    放在 vad 段而非新建段：这两个都是「收听时序」参数，与既有字段同族，该段已有
    「同族参数放一起」的先例（见 answer_timeout_ms 的注释）。

    Two cost-control fields join the VAD section: a minimum speech duration and an upload throttle.
    They live here rather than in a new section because they are listening-timing parameters like
    their neighbours — the section already set that precedent (see the answer_timeout_ms comment).
    """
    v = c.VadConfig()
    assert v.min_speech_ms == 300
    assert v.upload_throttle_ms == 500


def test_vad_wake_cost_control_bounds():
    """负值被 pydantic 拒绝 —— 配置写错启动即报错，而不是静默降级。
    Negative values are rejected by pydantic: a bad config fails at startup instead of degrading."""
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        c.VadConfig(min_speech_ms=-1)
    with pytest.raises(ValidationError):
        c.VadConfig(upload_throttle_ms=-1)


def test_vad_duplicate_in_api_schemas_stays_in_sync():
    """**手工副本陷阱**：`core/api/schemas.py` 里有 VadConfig 的副本，不同步的话
    FastAPI 的 response_model 会静默丢掉新字段，前端 `/api/config` 收不到。

    这条用例直接对比两份模型的字段集合，任何一边漏改都会红。

    **The duplicate-model trap**: `core/api/schemas.py` carries a copy of VadConfig. If they drift,
    FastAPI's response_model silently drops the new field and the frontend never sees it in
    /api/config. This case compares the two field sets directly, so either side drifting fails.
    """
    from core.api import schemas as api_schemas
    from core.config import schema as cfg_schema
    assert set(cfg_schema.VadConfig.model_fields) == set(api_schemas.VadConfig.model_fields)
```

- [ ] **Step 2: 运行确认失败**

Run: `python -m pytest tests/test_config.py -q -k vad`
Expected: FAIL — `AttributeError: 'VadConfig' object has no attribute 'min_speech_ms'`

- [ ] **Step 3: 实现**

`core/config/schema.py` 的 `VadConfig` 追加两个字段（放在 `answer_timeout_ms` 之后）：

```python
    # 唤醒上传的两道成本闸（子项目 1）：短于此长度的片段不上传（滤掉咳嗽/关门等爆音），
    # 两次上传之间的最小间隔（避免连续误触发时刷接口）。
    # Two cost gates for wake uploads: clips shorter than min_speech_ms are never uploaded
    # (filters coughs, door slams and other transients), and upload_throttle_ms sets the minimum
    # gap between uploads so a burst of false triggers cannot hammer the endpoint.
    min_speech_ms: int = Field(300, ge=0)
    upload_throttle_ms: int = Field(500, ge=0)
```

`core/api/schemas.py` 的 `VadConfig` 手工副本同步追加（字段名与默认值必须一致）：

```python
    min_speech_ms: int = 300
    upload_throttle_ms: int = 500
```

- [ ] **Step 4: 运行确认通过 + 全量后端回归**

Run: `python -m pytest tests/ -q && python -m mypy core/ server.py`
Expected: 全部通过

- [ ] **Step 5: 提交**

```bash
git add core/config/schema.py core/api/schemas.py tests/test_config.py
git commit -m "feat(配置): VAD 新增唤醒上传的成本闸（最短语音时长 + 节流）

放 vad 段而非新建段：都是收听时序参数，与既有字段同族。

core/api/schemas.py 的 VadConfig **手工副本同步更新** —— 不同步的话 FastAPI 的
response_model 会静默丢掉新字段、前端收不到（VadConfig 那次就是这么踩的）。
新增用例直接对比两份模型的字段集合，任一边漏改都会红。"
```

---

## Task 3: `POST /api/voice/wake` 端点 + 类型重生成

> **本任务把「新增端点」与「类型重生成」绑在一起**：新增 `response_model` 会改 openapi，
> CI 的 `gen:api` 门禁会校验 —— 分两个 commit 会让中间那个失败。

**Files:**
- Modify: `core/api/schemas.py`（新增 `WakeResponse`）
- Modify: `core/api/voice.py`
- Modify: `web/src/api/generated.ts`（重新生成）
- Test: `tests/test_server.py`

**Interfaces:**
- Consumes: Task 1 的 `core.voice.wake.detect`；Task 2 的 VAD 配置
- Produces: `POST /api/voice/wake` → `{ok, matched, command, text}`

- [ ] **Step 1: 写失败测试**

在 `tests/test_server.py` 追加：

```python
def test_voice_wake_matches_and_splits(client, monkeypatch):
    """唤醒端点：转写 → 匹配 → 切分，text 始终是原始转写。
    The wake endpoint transcribes, matches and splits, always returning the raw transcript."""
    import core.voice as voice_pkg

    class _Asr:
        def available(self): return True
        async def transcribe_base64(self, b64, fmt="wav"): return "衍衡，帮我查天气。"

    monkeypatch.setattr(voice_pkg, "get_asr", lambda: _Asr())
    r = client.post("/api/voice/wake", json={"audio_base64": "AAAA"})
    assert r.status_code == 200
    d = r.json()
    assert d["matched"] is True
    assert d["command"] == "帮我查天气"
    assert d["text"] == "衍衡，帮我查天气。"


def test_voice_wake_no_match(client, monkeypatch):
    """无关对话不命中，但 text 仍返回（便于排障）。
    Unrelated speech does not match, yet text still comes back for debugging."""
    import core.voice as voice_pkg

    class _Asr:
        def available(self): return True
        async def transcribe_base64(self, b64, fmt="wav"): return "今天天气怎么样。"

    monkeypatch.setattr(voice_pkg, "get_asr", lambda: _Asr())
    d = client.post("/api/voice/wake", json={"audio_base64": "AAAA"}).json()
    assert d["matched"] is False and d["command"] == ""


def test_voice_wake_without_audio(client):
    """缺 audio_base64 → 400，不调 ASR。A missing audio_base64 yields 400 without touching the ASR."""
    r = client.post("/api/voice/wake", json={})
    assert r.status_code == 400
    assert r.json()["ok"] is False


def test_voice_wake_asr_unavailable(client, monkeypatch):
    """ASR 未配置 → 明确报错，不假装成功。An unconfigured ASR reports an error rather than faking success."""
    import core.voice as voice_pkg

    class _Asr:
        def available(self): return False

    monkeypatch.setattr(voice_pkg, "get_asr", lambda: _Asr())
    d = client.post("/api/voice/wake", json={"audio_base64": "AAAA"}).json()
    assert d["ok"] is False
    assert "ASR" in d["error"]


def test_voice_wake_asr_failure_reports_error(client, monkeypatch):
    """ASR 抛异常 → ok=False 带错误信息（前端据此计熔断）。An ASR exception returns ok=False with a
    message, which is what the frontend counts toward its circuit breaker."""
    import core.voice as voice_pkg

    class _Asr:
        def available(self): return True
        async def transcribe_base64(self, b64, fmt="wav"): raise RuntimeError("上游 502")

    monkeypatch.setattr(voice_pkg, "get_asr", lambda: _Asr())
    d = client.post("/api/voice/wake", json={"audio_base64": "AAAA"}).json()
    assert d["ok"] is False and "502" in d["error"]


def test_voice_wake_writes_audit(client, monkeypatch, tmp_path):
    """每次唤醒上传都写审计 —— 这是统计调用量与成本的唯一依据。
    Every wake upload is audited: that record is the only basis for measuring call volume and cost.

    ⚠️ patch 目标是 `core.api.voice.audit`，**不是** `core.logger.audit`：voice.py 用
    `from core.logger import audit` 顶层导入，名字绑定进了本模块命名空间，改源头那个不影响它。
    Patch `core.api.voice.audit`, not `core.logger.audit`: voice.py imports the name at module
    level, so it is bound into this module's namespace and patching the source has no effect.
    """
    import core.voice as voice_pkg
    import core.api.voice as voice_api

    lines: list[str] = []
    monkeypatch.setattr(voice_api, "audit", lambda msg: lines.append(msg))

    class _Asr:
        def available(self): return True
        async def transcribe_base64(self, b64, fmt="wav"): return "衍衡。"

    monkeypatch.setattr(voice_pkg, "get_asr", lambda: _Asr())
    client.post("/api/voice/wake", json={"audio_base64": "AAAA"})
    assert any("wake" in l and "matched" in l for l in lines), lines
```

- [ ] **Step 2: 运行确认失败**

Run: `python -m pytest tests/test_server.py -q -k voice_wake`
Expected: FAIL — 404（端点不存在）

- [ ] **Step 3: 实现**

先在 `core/api/schemas.py` 里 `grep` 确认无同名类：

```bash
grep -n "class WakeResponse" core/api/schemas.py || echo "无同名类 ✓"
```

然后追加：

```python
class WakeResponse(ApiResponse):
    """唤醒检测响应。

    text 是**原始**转写（不被归一化改写），matched 为是否命中，command 为唤醒词之后的内容
    （仅唤醒词时为空串）。

    Wake-detection response. text is the **raw** transcript, matched says whether a wake word hit,
    and command is what followed it (empty when only the wake word was spoken).
    """

    matched: bool = False
    command: str = ""
    text: str = ""
```

在 `core/api/voice.py` 的 import 行加入 `WakeResponse`，并新增端点：

```python
@router.post("/voice/wake", response_model=WakeResponse)
async def voice_wake(request: Request):
    """唤醒检测：接收音频片段 → 转写 → 判定唤醒词 → 切出指令。

    与 /voice/transcribe 分开而不是复用：这一步的产物是**判定**（matched / command），
    不是文本 —— 前端据此决定「直接发起任务」还是「提示音后等指令」，把判定放后端
    可以让它被 pytest 单测，前端保持薄。

    Wake detection: accept an audio clip, transcribe it, judge the wake word and split out the
    command. Kept separate from /voice/transcribe because the product here is a **judgement**
    (matched / command) rather than text: the frontend decides between "start the task now" and
    "chime, then wait for the command", and putting that judgement server-side makes it unit
    testable while keeping the frontend thin.
    """
    from core.voice import get_asr
    from core.voice.wake import detect

    body = await request.body()
    try:
        params = json.loads(body.decode("utf-8")) if body else {}
    except Exception:
        return JSONResponse({"ok": False, "error": "无效 JSON"}, status_code=400)
    b64 = (params.get("audio_base64") or "").strip()
    if not b64:
        return JSONResponse({"ok": False, "error": "请提供 audio_base64 参数"}, status_code=400)

    asr = get_asr()
    if not asr.available():
        return JSONResponse({"ok": False, "error": "ASR 未配置"})
    try:
        text = await asr.transcribe_base64(b64, "wav")
    except Exception as e:
        logger.error("voice_wake: {}", e)
        # 不吞异常：前端要靠 ok=False 计连续失败次数并熔断，静默成功会让它一直重试。
        # Do not swallow: the frontend counts ok=False toward its circuit breaker; a silent success
        # would keep it retrying.
        return JSONResponse({"ok": False, "error": str(e)})

    result = detect(text, config.settings.voice.wake_word.keywords)
    # 每次上传记一笔，用**共用前缀**便于一条 grep 数全（spec「成本与隐私」）。
    # ⚠️ 不能写成「唯一依据」：/voice/transcribe（作答与指令那一路，往往更频繁）同样上传云端，
    # 它的审计在 Task 8 才补上。只看 via=wake 会**显著低估**调用量。
    # One audit line per upload, under a **shared prefix** so a single grep counts them all.
    # Do NOT call this "the only basis": /voice/transcribe (the answer/command path, usually more
    # frequent) uploads to the cloud too, and only gained its audit line in Task 8. Counting only
    # via=wake undercounts significantly.
    audit(
        f"audio-upload via=wake matched={result.matched} chars={len(text)} "
        f"command={result.command[:40]!r} text={text[:80]!r}"
    )
    return {"ok": True, "matched": result.matched, "command": result.command, "text": result.text}
```

`core/api/voice.py` 顶部 import 段加入 `from core.logger import audit`（若尚无）。

- [ ] **Step 4: 运行确认通过 + 重新生成类型**

Run: `python -m pytest tests/ -q && python -m mypy core/ server.py`
Expected: 全部通过

Run:
```bash
cd web && PYTHONIOENCODING=utf-8 python ../scripts/gen_openapi.py && npx --yes openapi-typescript@7.13.0 src/api/openapi.json -o src/api/generated.ts
cd .. && git diff --stat web/src/api/generated.ts
```
Expected: diff 非空（新增 `WakeResponse`，且 `VadConfig` 多了两个字段）

- [ ] **Step 5: 提交**

```bash
git add core/api/schemas.py core/api/voice.py tests/test_server.py web/src/api/generated.ts
git commit -m "feat(API): POST /api/voice/wake（转写 + 唤醒判定 + 指令切分）

与 /voice/transcribe 分开而不是复用：这步的产物是**判定**而非文本，放后端可
pytest 单测、前端保持薄。

ASR 异常不吞：前端要靠 ok=False 计连续失败并熔断，静默成功会让它一直重试。

新增 response_model 会改 openapi，故 generated.ts 必须同 commit 重新生成
（CI 的 gen:api 门禁会校验）。新增模型前先 grep 确认无同名类。"
```

---

## Task 4: 前端 API 客户端 `wakeDetect`

**Files:**
- Modify: `web/src/api.ts`（`transcribe` 附近）
- Test: `web/src/composables/assistant/__tests__/apiWake.spec.ts`

**Interfaces:**
- Consumes: Task 3 的端点与生成的 `WakeResponse` 类型
- Produces: `api.wakeDetect(blob: Blob): Promise<WakeResponse>`

- [ ] **Step 1: 写失败测试**

新建 `web/src/composables/assistant/__tests__/apiWake.spec.ts`：

```ts
import { describe, it, expect, vi, beforeEach } from 'vitest'

/** 唤醒检测客户端：必须复用 transcribe 的「Blob → WAV base64」转换，且带超时。
 *  The wake-detect client must reuse transcribe's Blob → WAV base64 conversion and carry a timeout. */
describe('api.wakeDetect', () => {
  beforeEach(() => { vi.resetModules(); vi.restoreAllMocks() })

  /** 走 /voice/wake 端点，body 里是 wav base64。
   *  It posts to /voice/wake with a wav base64 body. */
  it('POST /voice/wake 带 audio_base64', async () => {
    const calls: any[] = []
    vi.stubGlobal('fetch', vi.fn(async (url: string, init: any) => {
      calls.push({ url, body: init?.body })
      return { ok: true, status: 200, json: async () => ({ ok: true, matched: true, command: '查天气', text: '衍衡，查天气。' }) }
    }))
    const { api } = await import('../../../api')
    const r = await api.wakeDetect(new Blob(['x']))
    expect(String(calls[0].url)).toContain('/voice/wake')
    expect(JSON.parse(String(calls[0].body)).audio_base64).toBeTruthy()
    expect(r.matched).toBe(true)
    expect(r.command).toBe('查天气')
  })
})
```

- [ ] **Step 2: 运行确认失败**

Run: `cd web && npx vitest run src/composables/assistant/__tests__/apiWake.spec.ts`
Expected: FAIL — `api.wakeDetect is not a function`

- [ ] **Step 3: 实现**

`web/src/api.ts` 里 `transcribe` 之后新增（复用同一个 `blobToWavBase64`）：

```ts
  // 唤醒检测：转写 + 唤醒词判定 + 指令切分（后端完成判定，前端只需照结果行事）。
  // Wake detection: transcribe, judge the wake word, split out the command. The backend owns the
  // judgement; the frontend only acts on the result.
  /** 唤醒检测。Wake detection. */
  wakeDetect: async (blob: Blob): Promise<WakeResponse> => {
    const base64Wav = await blobToWavBase64(blob)
    return post<WakeResponse>('/voice/wake', { audio_base64: base64Wav })
  },
```

并在 `web/src/types.ts` 加类型别名（与既有的 `TextResponse` 同风格）：

```ts
export type WakeResponse = components['schemas']['WakeResponse']
```

- [ ] **Step 4: 运行确认通过 + 全量前端回归**

Run: `cd web && npm test && npm run build`
Expected: 全部通过

- [ ] **Step 5: 提交**

```bash
git add web/src/api.ts web/src/types.ts web/src/composables/assistant/__tests__/apiWake.spec.ts
git commit -m "feat(web): api.wakeDetect —— 唤醒检测客户端

复用 transcribe 的 Blob → WAV base64 转换，不重写一份（否则两边迟早漂移）。"
```

---

## Task 5: 常驻 VAD + 分段录音（`useSegmentRecorder.ts`）

**Files:**
- Create: `web/src/composables/assistant/useSegmentRecorder.ts`
- Test: `web/src/composables/assistant/__tests__/segmentRecorder.spec.ts`

**Interfaces:**
- Consumes: 无（只依赖浏览器 API）
- Produces: `createSegmentRecorder(stream: MediaStream, opts: SegmentOptions): SegmentRecorder`；
  `SegmentOptions = { speechThreshold: number; silenceMs: number; minSpeechMs: number; maxMs: number; onSegment: (blob: Blob) => void }`；
  `SegmentRecorder = { start(): void; stop(): void; isRecording(): boolean }`

- [ ] **Step 1: 写失败测试**

新建 `web/src/composables/assistant/__tests__/segmentRecorder.spec.ts`：

```ts
// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { createSegmentRecorder } from '../useSegmentRecorder'

/** 分段录音：常驻 VAD 决定何时开始/结束一段，短于 minSpeechMs 的段直接丢弃（不上传）。
 *  Segment recording: an always-on VAD decides when a segment starts and ends; anything shorter
 *  than minSpeechMs is dropped outright and never uploaded. */

class FakeAnalyser {
  fftSize = 2048
  smoothingTimeConstant = 0.3
  /** 由测试驱动的 RMS 时间线（0..1）。Test-driven RMS timeline. */
  static timeline: number[] = []
  static cursor = 0
  getByteTimeDomainData(arr: Uint8Array) {
    // **必须推进 cursor**：不推进的话每次读到的都是 timeline[0]，「先说后静音」这类
    // 用例永远走不到静音，段永远不结束，测试会以错误的原因失败。
    // The cursor **must** advance: otherwise every read returns timeline[0], a "speech then
    // silence" case never reaches silence, the segment never ends, and the test fails for the
    // wrong reason.
    const i = Math.min(FakeAnalyser.cursor, FakeAnalyser.timeline.length - 1)
    FakeAnalyser.cursor++
    const rms = FakeAnalyser.timeline[i] ?? 0
    for (let k = 0; k < arr.length; k++) arr[k] = 128 + Math.round(rms * 127)
  }
}

class FakeRecorder {
  static instances: FakeRecorder[] = []
  state = 'inactive'
  ondataavailable: ((e: any) => void) | null = null
  onstop: (() => void) | null = null
  constructor(public stream: any, public opts: any) { FakeRecorder.instances.push(this) }
  static isTypeSupported() { return true }
  start() { this.state = 'recording' }
  stop() {
    this.state = 'inactive'
    // 产生一小段数据，让 onstop 能构造 Blob
    this.ondataavailable?.({ data: new Blob(['audio']) })
    this.onstop?.()
  }
}

beforeEach(() => {
  vi.useFakeTimers()
  FakeAnalyser.timeline = []; FakeAnalyser.cursor = 0
  FakeRecorder.instances = []
  ;(globalThis as any).AudioContext = function () {
    return {
      createMediaStreamSource: () => ({ connect: () => {} }),
      createAnalyser: () => new FakeAnalyser(),
      close: async () => {},
    }
  }
  ;(globalThis as any).MediaRecorder = FakeRecorder as any
})

afterEach(() => { vi.useRealTimers() })

const stream = { getTracks: () => [] } as any
const OPTS = { speechThreshold: 0.02, silenceMs: 1000, minSpeechMs: 300, maxMs: 10000 }

/** 语音→静音 会产生一段，并带上录音 Blob。Speech then silence emits a segment with a blob. */
it('检测到语音后静音 → 产出一段', async () => {
  const got: Blob[] = []
  FakeAnalyser.timeline = [0.5, 0.5, 0.5, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]
  const rec = createSegmentRecorder(stream, { ...OPTS, onSegment: (b) => got.push(b) })
  rec.start()
  await vi.advanceTimersByTimeAsync(2000)
  expect(got.length).toBe(1)
  rec.stop()
})

/** 只有静音时永远不产生段（VAD 是第一道成本闸：静音根本不上传）。 */
it('纯静音不产段', async () => {
  const got: Blob[] = []
  FakeAnalyser.timeline = [0]
  const rec = createSegmentRecorder(stream, { ...OPTS, onSegment: (b) => got.push(b) })
  rec.start()
  await vi.advanceTimersByTimeAsync(5000)
  expect(got.length).toBe(0)
  rec.stop()
})

/** 短于 minSpeechMs 的爆音被丢弃 —— 这是省调用量的关键，必须单独钉住。 */
it('短于 minSpeechMs 的爆音不产段', async () => {
  const got: Blob[] = []
  // 100ms 有声音，随后长期静音：短于 minSpeechMs=300ms
  FakeAnalyser.timeline = [0.5]
  const rec = createSegmentRecorder(stream, { ...OPTS, onSegment: (b) => got.push(b) })
  rec.start()
  await vi.advanceTimersByTimeAsync(100)     // 仅 ~1 个检查周期有声
  FakeAnalyser.timeline = [0]
  await vi.advanceTimersByTimeAsync(3000)
  expect(got.length).toBe(0)
  rec.stop()
})

/** stop() 后不再产段。No segments after stop(). */
it('stop 后不再产段', async () => {
  const got: Blob[] = []
  FakeAnalyser.timeline = [0.5, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]
  const rec = createSegmentRecorder(stream, { ...OPTS, onSegment: (b) => got.push(b) })
  rec.start()
  rec.stop()
  await vi.advanceTimersByTimeAsync(3000)
  expect(got.length).toBe(0)
})
```

- [ ] **Step 2: 运行确认失败**

Run: `cd web && npx vitest run src/composables/assistant/__tests__/segmentRecorder.spec.ts`
Expected: FAIL — `Failed to resolve import "../useSegmentRecorder"`

- [ ] **Step 3: 实现**

新建 `web/src/composables/assistant/useSegmentRecorder.ts`：

```ts
/**
 * 常驻 VAD + 分段录音。
 *
 * 为什么要单独一个模块：唤醒链路改成「VAD 驱动录音」后，VAD 不再是录音的附属（旧代码里
 * 它跟着 MediaRecorder 起停），而是**驱动方** —— 它决定一段从哪里开始、到哪里结束，以及
 * 这一段值不值得上传。把这个决策单独成模块，才能脱离浏览器音频栈单测。
 *
 * Always-on VAD driving segment recording. Extracted because the wake pipeline now has the VAD
 * **drive** recording rather than tag along with it (in the old code it started and stopped with
 * the MediaRecorder): the VAD decides where a segment begins and ends, and whether it is worth
 * uploading at all. Isolating that decision is what makes it testable without a real audio stack.
 */

/** 分段录音的参数。Segment-recording options. */
export interface SegmentOptions {
  /** 判定为「有人在说」的 RMS 阈值（0..1）。RMS threshold above which someone is speaking. */
  speechThreshold: number
  /** 静音多久算一段说完（毫秒）。Silence duration that ends a segment, in ms. */
  silenceMs: number
  /** 短于此长度的段直接丢弃、不上传（毫秒）。Segments shorter than this are dropped, never uploaded. */
  minSpeechMs: number
  /** 单段硬上限（毫秒）。Hard cap on one segment, in ms. */
  maxMs: number
  /** 一段就绪时回调（已过滤掉过短的段）。Called with a finished segment, short ones already filtered. */
  onSegment: (blob: Blob) => void
}

/** 分段录音句柄。The segment recorder handle. */
export interface SegmentRecorder {
  /** 开始常驻监听。Start listening. */
  start(): void
  /** 停止并释放。Stop and release. */
  stop(): void
  /** 当前是否正在录一段。Whether a segment is being recorded right now. */
  isRecording(): boolean
}

/** VAD 检查周期（毫秒）。VAD check interval in ms. */
const CHECK_MS = 100

/**
 * 创建一个分段录音器。
 * Create a segment recorder.
 *
 * @param stream 麦克风流（与录音共用同一条流）。The mic stream (shared with recording).
 * @param opts 参数。Options.
 * @returns 句柄。The handle.
 */
export function createSegmentRecorder(stream: MediaStream, opts: SegmentOptions): SegmentRecorder {
  let ctx: AudioContext | null = null
  let analyser: AnalyserNode | null = null
  let timer: ReturnType<typeof setInterval> | null = null
  let recorder: MediaRecorder | null = null
  let chunks: Blob[] = []
  let recording = false
  /** 本段内是否已检测到语音（用于 minSpeechMs 判定）。Whether speech was seen in this segment. */
  let speechSeen = false
  /** 已检测到语音的累计时长（毫秒）。Accumulated speech duration in ms. */
  let speechMs = 0
  let silenceCount = 0
  let elapsed = 0

  function beginSegment() {
    chunks = []
    let mime = 'audio/webm'
    if (!MediaRecorder.isTypeSupported(mime)) {
      mime = MediaRecorder.isTypeSupported('audio/webm;codecs=opus') ? 'audio/webm;codecs=opus' : ''
    }
    try {
      recorder = new MediaRecorder(stream, mime ? { mimeType: mime } : undefined)
    } catch {
      return
    }
    recorder.ondataavailable = (e) => { if (e.data.size > 0) chunks.push(e.data) }
    recorder.onstop = () => {
      const blob = new Blob(chunks, { type: 'audio/webm' })
      chunks = []
      // 过短的段不上传：这是省调用量的第一道闸，VAD 已判过静音，这里再滤爆音。
      // Too-short segments are never uploaded: this is the first cost gate, on top of the VAD's
      // silence filtering, and it removes coughs and door slams.
      if (speechMs >= opts.minSpeechMs && blob.size > 0) opts.onSegment(blob)
      speechSeen = false
      speechMs = 0
    }
    recorder.start()
    recording = true
    // 注意：**不要**在这里重置 speechSeen / speechMs —— 调用方紧接着就会置 speechSeen=true
    // 并累加 speechMs，在此清零会让首帧统计丢失（顺序敏感的陷阱）。这两个变量由 onstop 收尾时复位。
    // Do **not** reset speechSeen / speechMs here: the caller sets speechSeen and accumulates
    // speechMs immediately after this returns, so clearing them here would drop the first frame's
    // tally (an order-sensitive trap). onstop resets them when the segment finishes.
    silenceCount = 0
    elapsed = 0
  }

  function endSegment() {
    recording = false
    if (recorder && recorder.state === 'recording') recorder.stop()
  }

  function tick() {
    if (!analyser) return
    elapsed += CHECK_MS
    const buf = new Uint8Array(analyser.fftSize)
    analyser.getByteTimeDomainData(buf)
    let sum = 0
    for (let i = 0; i < buf.length; i++) { const v = (buf[i] - 128) / 128; sum += v * v }
    const rms = Math.sqrt(sum / buf.length)

    if (rms >= opts.speechThreshold) {
      silenceCount = 0
      if (!speechSeen) { speechSeen = true; if (!recording) beginSegment() }
      speechMs += CHECK_MS
    } else {
      if (!speechSeen) return                 // 还没开口，什么都不做
      silenceCount += CHECK_MS
      if (silenceCount >= opts.silenceMs) endSegment()
    }

    if (recording && elapsed >= opts.maxMs) endSegment()
  }

  return {
    start() {
      if (timer) return
      try {
        ctx = new (window.AudioContext || (window as any).webkitAudioContext)()
        const source = ctx.createMediaStreamSource(stream)
        analyser = ctx.createAnalyser()
        analyser.fftSize = 2048
        analyser.smoothingTimeConstant = 0.3
        source.connect(analyser)
      } catch { return }
      timer = setInterval(tick, CHECK_MS)
    },
    stop() {
      if (timer) { clearInterval(timer); timer = null }
      if (recording) endSegment()
      analyser = null
      if (ctx) { try { ctx.close() } catch { /* ignore */ } ctx = null }
    },
    isRecording: () => recording,
  }
}
```

- [ ] **Step 4: 运行确认通过 + 全量前端回归**

Run: `cd web && npm test && npm run build`
Expected: 全部通过

- [ ] **Step 5: 提交**

```bash
git add web/src/composables/assistant/useSegmentRecorder.ts web/src/composables/assistant/__tests__/segmentRecorder.spec.ts
git commit -m "feat(web): 常驻 VAD + 分段录音模块

单独成模块的理由：唤醒链路改成「VAD 驱动录音」后，VAD 从录音的附属变成驱动方 ——
它决定一段的起止，以及这段值不值得上传。把这个决策单独出来才能脱离浏览器音频栈
单测。

minSpeechMs 是第一道成本闸（滤掉咳嗽/关门等爆音），单独钉了用例。"
```

---

## Task 6: 唤醒判定接入状态机（重写 `useWakeWord.ts`）

**Files:**
- Modify: `web/src/composables/assistant/useWakeWord.ts`（重写内部）
- Modify: `web/src/composables/assistant/store.ts`（移除 Vosk 专属状态）
- Test: `web/src/composables/assistant/__tests__/useWakeWord.spec.ts`（重写）

**Interfaces:**
- Consumes: Task 4 的 `api.wakeDetect`；Task 5 的 `createSegmentRecorder`
- Produces: `toggleWake()`（签名不变，供 `useAssistant` 复用）；`handleSegment(blob)`（导出供测试）

- [ ] **Step 1: 写失败测试**

重写 `web/src/composables/assistant/__tests__/useWakeWord.spec.ts`：

```ts
import { describe, it, expect, vi, beforeEach } from 'vitest'

/** 唤醒判定接入状态机：命中唤醒词且带指令 → 直接起一轮；只命中唤醒词 → 提示音后等下一段。
 *  Wiring the wake judgement into the state machine: a wake word plus command starts a turn
 *  immediately; a bare wake word chimes and treats the next segment as the command. */
describe('handleSegment 分流', () => {
  beforeEach(() => { vi.resetModules(); localStorage.clear() })

  async function setup(wakeResp: any) {
    const sent: string[] = []
    vi.doMock('../../../api', () => ({
      api: { wakeDetect: vi.fn(async () => wakeResp), transcribe: vi.fn() },
    }))
    vi.doMock('../useChat', () => ({
      sendText: (t: string) => { sent.push(t) },
      sendAnswer: vi.fn(),
      runTurn: vi.fn(),
    }))
    vi.doMock('../useTts', () => ({ speaking: { value: false }, speakAuto: vi.fn() }))
    const mod = await import('../useWakeWord')
    return { mod, sent }
  }

  /** 唤醒词 + 指令 → 直接用后半段起一轮，不再多录一次。 */
  it('唤醒词带指令 → 直接发起一轮', async () => {
    const { mod, sent } = await setup({ ok: true, matched: true, command: '帮我查天气', text: '衍衡，帮我查天气。' })
    await mod.handleSegment(new Blob(['x']))
    expect(sent).toEqual(['帮我查天气'])
  })

  /** 只有唤醒词 → 不起轮，记为「等指令」，下一段直接当指令。 */
  it('只有唤醒词 → 下一段当指令', async () => {
    const { mod, sent } = await setup({ ok: true, matched: true, command: '', text: '衍衡。' })
    await mod.handleSegment(new Blob(['x']))
    expect(sent).toEqual([])
    // 下一段不再判定唤醒词，直接当指令
    await mod.handleSegment(new Blob(['x']))
    expect(sent.length).toBe(1)
  })

  /** 不命中 → 什么都不做（噪音/无关对话被丢弃）。 */
  it('不命中 → 丢弃', async () => {
    const { mod, sent } = await setup({ ok: true, matched: false, command: '', text: '今天天气怎么样。' })
    await mod.handleSegment(new Blob(['x']))
    expect(sent).toEqual([])
  })

  /** ASR 失败 → 不起轮，且计入失败次数。 */
  it('唤醒检测失败 → 丢弃并计数', async () => {
    const { mod, sent } = await setup({ ok: false, error: '上游 502' })
    await mod.handleSegment(new Blob(['x']))
    expect(sent).toEqual([])
  })

  /**
   * **待答提问优先**：这一段是「回答」，绝不能送去判唤醒词 —— 否则用户答「允许本次」会被
   * 当成不含唤醒词的噪音丢掉，P6 的语音作答功能就此失效。这是本任务最容易写错的地方。
   *
   * A pending question takes precedence: the segment is an *answer* and must never be sent to wake
   * detection, or answering "允许本次" would be discarded as wake-word-less noise and the whole
   * voice-answering feature would silently stop working. This is the easiest thing to get wrong here.
   */
  it('待答提问时走答案通道，不判唤醒词', async () => {
    vi.doMock('../../../api', () => ({
      api: {
        wakeDetect: vi.fn(async () => ({ ok: true, matched: true, command: 'X', text: 'X' })),
        transcribe: vi.fn(async () => ({ ok: true, text: '允许本次' })),
      },
    }))
    vi.doMock('../useChat', () => ({ sendText: vi.fn(), sendAnswer: vi.fn(), runTurn: vi.fn() }))
    vi.doMock('../useTts', () => ({ speaking: { value: false }, speakAuto: vi.fn() }))
    const { api } = await import('../../../api')
    const { sendAnswer } = await import('../useChat')
    const store = await import('../store')
    store.state.value = 'awaiting_answer'
    store.pendingQuestion.value = {
      text: '确认执行吗？', kind: 'choice',
      options: [{ value: 'yes', label: '允许本次' }, { value: 'no', label: '拒绝' }],
    }
    const { handleSegment } = await import('../useWakeWord')
    await handleSegment(new Blob(['x']))

    expect(vi.mocked(api.wakeDetect)).not.toHaveBeenCalled()
    expect(vi.mocked(sendAnswer)).toHaveBeenCalledWith('', 'yes')   // label 精确命中 → 回传 value
  })
})
```

- [ ] **Step 2: 运行确认失败**

Run: `cd web && npx vitest run src/composables/assistant/__tests__/useWakeWord.spec.ts`
Expected: FAIL — `handleSegment is not exported`

- [ ] **Step 3: 实现**

`store.ts`：删除 `wakeConfig.model_path` 的 Vosk 默认值与 `modelLoading` / `modelProgress`（若无其他引用）。

`useWakeWord.ts` 重写要点（保留 `toggleWake` / `stopWake` 导出签名）：

```ts
import { state, wakeEnabled, wakeConfig, vadConfig, pendingQuestion, currentSessionId, statusLine } from './store'
import { api } from '../../api'
import { createSegmentRecorder, type SegmentRecorder } from './useSegmentRecorder'
import { sendText, sendAnswer } from './useChat'
import { speakAuto, speaking } from './useTts'
import { nextState } from './wakeFsm'

let segmenter: SegmentRecorder | null = null
let micStream: MediaStream | null = null
/** 仅听到唤醒词后置位：下一段直接当指令，不再判唤醒词。 */
let awaitingCommand = false
/** 连续上传失败次数，达阈值熔断。 */
let failures = 0
const FAILURE_LIMIT = 3
let lastUploadAt = 0

/** 处理一段音频：先看是不是在回答问题，否则做唤醒检测。导出供测试。 */
export async function handleSegment(blob: Blob) {
  // 熔断：连续失败后停止上传，避免疯狂重试烧钱。
  if (failures >= FAILURE_LIMIT) return
  const now = Date.now()
  if (now - lastUploadAt < vadConfig.upload_throttle_ms) return   // 节流
  lastUploadAt = now

  // ⚠️ 待答提问优先：这一段是**回答**，绝不能送去判唤醒词 ——
  // 否则用户答「允许本次」，会被当成不含唤醒词的噪音丢掉，P6 的语音作答就此失效。
  const pq = pendingQuestion.value
  if (pq && (state.value === 'awaiting_answer' || state.value === 'standby')) {
    let t: any
    try { t = await api.transcribe(blob) } catch { onUploadFailed(); return }
    const text = (t?.text || '').trim()
    if (!text) return
    failures = 0
    // 精确匹配到选项则回传该选项的 value，否则整段作为文本作答（与旧 handleTranscript 同规则）。
    const hit = matchOption(text, pq.options)
    await sendAnswer(hit ? '' : text, hit?.value)
    return
  }

  // 刚听到唤醒词、正在等指令：这一段直接当指令，不再判唤醒词。
  if (awaitingCommand) {
    awaitingCommand = false
    let t: any
    try { t = await api.transcribe(blob) } catch { onUploadFailed(); return }
    const text = (t?.text || '').trim()
    if (text) { failures = 0; sendText(text) }
    return
  }

  let r: any
  try { r = await api.wakeDetect(blob) } catch { onUploadFailed(); return }
  if (!r?.ok) { onUploadFailed(); return }
  failures = 0
  statusLine.value = ''

  if (!r.matched) return                       // 噪音/无关对话 → 丢弃
  if (r.command) { sendText(r.command); return }   // 唤醒词 + 指令 → 直接起一轮
  awaitingCommand = true                        // 仅唤醒词 → 提示音后等下一段
  playBeep()
}

/** 上传失败累计与熔断提示。Count upload failures and surface the circuit break. */
function onUploadFailed() {
  failures++
  if (failures >= FAILURE_LIMIT) {
    // spec「错误与降级」：云端不可用必须**明确提示**，不静默失败 ——
    // 否则用户只看到「唤醒突然不灵了」，无从判断原因。
    statusLine.value = '⚠️ 云端唤醒不可用（已连续失败 3 次）· 可双击悬浮球手动触发'
    console.warn('[wake] 连续失败达阈值，已暂停上传')
  }
}
```

> **`matchOption` 来自 `./answerMatch`**（既有模块，勿改：它只做 trim 后精确相等，是确认闸门的一部分）。

**`toggleWake` / `stopWake` 的改动范围**（其余逻辑保持原样）：

| 部分 | 处理 |
|---|---|
| 麦克风预检、`describeMicError` 兜底 | **保留不动** |
| 启动：`WakeWordEngine.init/start` | **替换**为 `getUserMedia` + `createSegmentRecorder`（见下） |
| 关闭分支 | **替换**引擎 stop 为 `segmenter.stop()` + 释放 `micStream` 轨道 |
| `playBeep` / `clearTimers` | **保留** |
| `startRecording` / `startVAD` / `startMaxTimer` / `stopRecording` / `onWakeDetected` | **删除**（录音与 VAD 已由 `useSegmentRecorder` 承担；状态流转由 `handleSegment` 驱动） |
| `watch(speaking)` 播报期间暂停监听 | **保留语义，改实现**：`segmenter.stop()` / 重新 `getUserMedia` 后 `segmenter.start()`；恢复时若 `pendingQuestion` 非空仍进入待答（原逻辑不得丢） |
| `initWakeModel` | **删除** |

启动分支：

```ts
      micStream = await navigator.mediaDevices.getUserMedia({
        audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true },
      })
      segmenter = createSegmentRecorder(micStream, {
        speechThreshold: vadConfig.silence_threshold,
        silenceMs: vadConfig.silence_duration_ms,
        minSpeechMs: vadConfig.min_speech_ms,
        maxMs: vadConfig.max_duration_ms,
        onSegment: (b) => { void handleSegment(b) },
      })
      segmenter.start()
      wakeEnabled.value = true
      state.value = 'listening'
```

`stopWake` 里停掉 `segmenter` 并释放 `micStream` 的轨道。

- [ ] **Step 4: 运行确认通过 + 全量前端回归**

Run: `cd web && npm test && npm run build`
Expected: 全部通过

- [ ] **Step 5: 提交**

```bash
git add web/src/composables/assistant/useWakeWord.ts web/src/composables/assistant/store.ts web/src/composables/assistant/__tests__/useWakeWord.spec.ts
git commit -m "feat(web): 唤醒判定接入状态机（VAD 驱动，去掉 Vosk 依赖）

分流：命中唤醒词且带指令 → 直接起一轮（省一次录音与 ASR）；只命中唤醒词 →
提示音后把下一段当指令；不命中 → 丢弃。

成本控制：upload_throttle_ms 节流 + 连续失败 3 次熔断，避免误触发时刷接口。
播报期间暂停监听的既有行为保留（改为停/起分段录音器）。"
```

---

## Task 7: 移除 Vosk（引擎 / 模型 / 类型 / 测试）

**Files:**
- Delete: `web/public/lib/wake-word.js`、`web/public/lib/vosk.js`、`web/public/models/vosk-model-small-cn-0.22.tar.gz`、`web/public/vosk-test.html`、`web/src/types/vosk.d.ts`、`web/src/types/raw.d.ts`
- Modify: `web/index.html`（删 7-8 行）
- Delete: `web/src/composables/assistant/__tests__/wakeEngineRestart.spec.ts`、`wakeKeywords.spec.ts`

**Interfaces:**
- Consumes: Task 6 已不再引用 Vosk
- Produces: 无（纯删除）

- [ ] **Step 1: 确认无人再引用**

Run（**排除本任务要删的文件本身**）：
```bash
grep -rn "vosk\|wake-word\|WakeWordEngine\|initWakeModel" web/src web/index.html \
  --include="*.ts" --include="*.vue" --include="*.html" --include="*.js" \
  | grep -v node_modules \
  | grep -vE "wakeEngineRestart\.spec\.ts|wakeKeywords\.spec\.ts|types/vosk\.d\.ts|types/raw\.d\.ts"
```
Expected: **无输出**（剩下 4 个命中都在本任务要删的文件里）。若仍有输出，说明上层没断开干净，先补完 Task 6 再继续。

> ⚠️ 注意门禁的写法：**不能把 `web/public` 也搜进去**。`public/lib/wake-word.js`、`public/vosk-test.html` 就在那里，
> 它们是本任务要删的对象；把它们算进「有人引用」会让这条门禁**永远不可能通过**。
> Note the gate deliberately excludes `web/public`: the files to be deleted live there, and counting them as
> "still referenced" would make this gate impossible to pass.

- [ ] **Step 2: 删除文件**

```bash
git rm -r web/public/lib/wake-word.js web/public/lib/vosk.js web/public/models web/public/vosk-test.html web/src/types/vosk.d.ts web/src/types/raw.d.ts web/src/composables/assistant/__tests__/wakeEngineRestart.spec.ts web/src/composables/assistant/__tests__/wakeKeywords.spec.ts
```

- [ ] **Step 3: 清掉 index.html 的脚本引用**

`web/index.html` 删除**三行**（`<head>` 里 7–9 行连着三个 script）：

```html
  <script src="/lib/vosk.js"></script>
  <script>window.vosk = window.Vosk</script>
  <script src="/lib/wake-word.js"></script>
```

> ⚠️ 第 3 行 `<script src="/lib/wake-word.js">` 容易漏 —— 它是**引擎本身**的加载标签，
> 删了文件却留着标签会让浏览器 404。删完确认 `<head>` 里不再有 `/lib/` 的 script。
> The third line loads the engine itself and is easy to miss; deleting the file while leaving the tag
> yields a 404. After deleting, confirm no `/lib/` script remains in `<head>`.

- [ ] **Step 4: 全量回归（前后端）**

Run:
```bash
cd web && npm test && npm run build
cd .. && python -m pytest tests/ -q && python -m mypy core/ server.py
```
Expected: 全部通过（前端测试数会下降，因为删掉了两个 Vosk 用例文件）

- [ ] **Step 5: 提交**

```bash
git add -A web/
git commit -m "chore(唤醒): 移除 Vosk 引擎与 43MB 模型

唤醒词改用「衍衡」「洛吉斯」后，Vosk 一个能用的唤醒词都不剩（实测全灭），
且它已不再被任何代码引用（Step 1 先 grep 确认过）。

顺带瘦身：引擎 + 运行时 + 模型共约 48MB，其中 43MB 模型是提交进 git 的。"
```

---

## Task 8: 收尾清理 + 端到端验证与文档

**Files:**
- Modify: `README.md`、`wiki/Security.md`、`wiki/Configuration.md`、`docs/architecture/roadmap.md`、`docs/architecture/01-voice-control-agent.md`
- Modify: `web/scripts/verify-voice.mjs`、`web/scripts/screenshot.mjs`
- Modify: `core/config/schema.py`、`core/api/schemas.py`、`config.yaml.example`（+ 本机 `config.yaml`）
- Modify: `vite.config.ts`、`server.py`
- Delete: `scripts/libs/vosk-0.3.45-py3-none-win_amd64.whl`

> **本任务的两半性质不同**：前半（Step 1–2）是 Task 7 审查挂起的清理项，**可自动化、由实现者完成**；
> 后半（Step 5–6）的**人工验收必须由真人对着麦克风做，不可由实现者代劳**。实现者做完前半、
> 把后半的清单交回控制器即可，**不得**在未实际验证的情况下把人工项写成通过。

- [ ] **Step 1: 清掉 Task 7 审查挂起的残留**

逐项处理（每条都来自 Task 7 的审查，理由见各条）：

1. **`web/scripts/verify-voice.mjs` 的检查 4 现在只能报空洞的 PASS** —— 它探的是已删除的
   `window.WakeWordEngine.isRunning()`，恒为假，导致 FAIL 分支不可达、`runningBefore/After` 恒为 0。
   这是**假保障**，而它正是交付给用户做人工验收的工具，必须先修。
   新架构下「播报含唤醒词不自触发」的等价判据是：**播报期间不得产生/上传任何音频分段**
   （助手自己的声音若被 VAD 切段并上传，就是自触发）。请把该检查重指到分段录音器/状态机上，
   并让它在**无法取得判据时报 INCONCLUSIVE 而不是 PASS**。
2. **`model_path` 默认值仍指向已删除的模型**：`core/config/schema.py` 与 `core/api/schemas.py`
   的默认值改为 `""`（两处手工副本必须同步 —— 老陷阱）。
   ⚠️ 这**会改 openapi**，故必须同 commit 重跑 `npm run gen:api` 并提交 `generated.ts`。
3. **删除 `scripts/libs/vosk-0.3.45-py3-none-win_amd64.whl`（14MB）** —— 不在 `requirements.txt`、
   无人 import，与刚删的 43MB 模型同属死重。
4. `vite.config.ts` 的 `publicDir: 'public'` 现指向不存在的目录（Vite 有 `existsSync` 守卫，无功能影响）——
   删除该行或改指向存在的目录。
5. 陈旧注释：`web/scripts/screenshot.mjs` 里「等 Vosk 模型就绪」的措辞、`server.py` 的 `_EXTRA_TYPES`
   （多数后缀只服务于已删的模型树）—— 一并清理；`_EXTRA_TYPES` 若仍被其它用途需要则只删模型专属项并说明。

- [ ] **Step 2: 全量自动化**

Run:
```bash
python -m pytest tests/ -q && python -m mypy core/ server.py
cd web && npm test && npm run build
```
Expected: 全部通过

- [ ] **Step 3: 类型同步门禁**

Run:
```bash
cd web && npm run gen:api && git diff --exit-code src/api/generated.ts && echo "OK: 已同步"
```
Expected: 无 diff 输出

- [ ] **Step 4: 起服务（严格确认端口）**

```bash
taskkill //F //FI "IMAGENAME eq python.exe" ; sleep 2
netstat -ano | grep ":8520.*LISTENING" || echo "端口空闲"
python main.py serve > /tmp/srv.log 2>&1 &
sleep 8 && (grep -qa "10048" /tmp/srv.log && echo "❌ 跑的是旧进程" || echo "✓ 绑定成功")
```

- [ ] **Step 5: 人工验收 —— ⛔ 由用户执行，实现者不得代劳**

> **这一步不能由自动化替代**：spec 里所有实测用的都是 **SAPI 合成音**，云端对合成音识别好
> **不代表对真人好**。必须真人有声环境下逐条验证。

| # | 验收项 | 结果 |
|---|---|---|
| 1 | 说「衍衡，帮我查天气」→ 一句话走通（**一次** ASR，无提示音等待） | |
| 2 | 说「衍衡」→ 提示音 → 说指令 → 走通 | |
| 3 | 说「洛吉斯，现在几点」→ 走通 | |
| 4 | 说「衍衡」后不说话 → 不产生任务，不报错 | |
| 5 | 屋里正常聊天（不含唤醒词）→ **不误触发** | |
| 6 | 双击悬浮球手动触发仍可用（回归） | |

**若某项未通过，如实标注「未通过」并停下**，不得据此宣称功能可用。

- [ ] **Step 6: 记录实测调用频率（成本）**

人工验收期间留意 console 的 `[wake]` 日志，记录：**每 10 分钟正常对话约触发几次上传**。
把数字写进下面的文档更新里 —— 这是成本控制的依据。

- [ ] **Step 7: 同步文档**

`README.md`：
- 「语音唤醒」一行改为：VAD → 唤醒判定 → ASR，唤醒词「衍衡」「洛吉斯」
- **「安全」节新增隐私边界说明**：*每次检测到人声都会把该片段送到云端 ASR（`api.xiaomimimo.com`），无论是否唤醒*；VAD 为本地闸门，但未唤醒时音频仍会出本机
- 「语音助手使用」补：一句话说完 / 只喊唤醒词两种用法

`wiki/Security.md`：同步隐私边界变化。

`docs/architecture/roadmap.md`：新增 P8（唤醒链路重构）一行，标注**子项目 1 完成、2/3/4 待做**。

- [ ] **Step 8: 提交并推送**

```bash
git add README.md wiki/Security.md docs/architecture/roadmap.md
git commit -m "docs: 唤醒链路重构（子项目 1）说明与隐私边界变化"
git push origin main
```

---

## 完成标准

- [ ] `python -m pytest tests/ -q` 全绿；`python -m mypy core/ server.py` 无问题
- [ ] `cd web && npm test` 全绿；`npm run build` 通过
- [ ] `generated.ts` 与后端 schema 同步（`git diff --exit-code` 无输出）
- [ ] **反例用例全绿**：`也行`、`若`、`我昨天说衍衡那个事` 均不命中
- [ ] **`VadConfig` 两份模型字段集合一致**（用例钉住）
- [ ] Vosk 相关文件**全部删除**，`grep -rn "vosk\|WakeWordEngine" web/src web/index.html` 无输出
- [ ] 人工验收 6 项**逐条记录**；未通过的如实标注，不得含糊
- [ ] README / wiki 的隐私边界变化已写明
