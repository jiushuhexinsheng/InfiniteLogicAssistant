# -*- coding: utf-8 -*-
"""唤醒词检测 — 从 ASR 转写里判定唤醒词并切出指令（拼音级）

**为什么是拼音级**：ASR 是「听音写字」，同一发音会被写成不同汉字（实测「衍衡」→
「燕恒」，还可能「言恒/严衡」……）。字面量/同音字表是打地鼠 —— 表永远补不全。
拼音级匹配只看发音：只要声母韵母对，写成什么字都命中。

**为什么不是模糊/近音匹配**：唤醒是执行闸门的前置，错触发的代价远大于漏触发。
实测 Vosk 把「衍衡」听成「也行」、把「洛吉斯」听成「若」—— 这两个都是中文里的
高频词，且与唤醒词**不同音**（yexing≠yanheng、ruo≠luojisi）。拼音严格相等恰好
把它们挡在外面：比同音字表宽（同音全收），比拼音模糊匹配严（近音不收）。

**句首容差**：唤醒词前允许至多 2 个字的语气词噪音（「呃衍衡」命中），再远就是
句中提及（「我昨天说衍衡那个事」），不命中 —— 防误触发与 TTS 回声循环。

前端镜像：web/src/composables/assistant/wakeMatch.ts（Web Speech 路径），
语义由共享测试向量 tests/data/wake_vectors.json 钉住（pytest 与 vitest 共跑）。

Wake-word detection: decide whether an ASR transcript starts with a wake word and split out the
command (pinyin level). **Why pinyin**: ASR maps sound to characters and writes the same sound
differently (measured 衍衡 → 燕恒, also 言恒/严衡/…). Literal or homophone-table matching is
whack-a-mole — the table can never be complete. Pinyin-level matching looks only at the
pronunciation. **Why not fuzzy**: a false wake is far costlier than a miss. Measurement showed
Vosk hearing 衍衡 as 也行 and 洛吉斯 as 若 — both common Chinese words, yet *different sounds*
(yexing≠yanheng, ruo≠luojisi). Strict pinyin equality keeps them out: broader than a homophone
table (all homophones in), stricter than fuzzy pinyin (near-sounds out). **Leading tolerance**: up
to 2 filler characters before the keyword (呃衍衡 hits); further back it is a mid-sentence
mention (我昨天说衍衡那个事) and must not fire — prevents false wakes and TTS echo loops.

Frontend mirror: web/src/composables/assistant/wakeMatch.ts (Web Speech path). Semantics pinned by
the shared test vectors tests/data/wake_vectors.json (run by both pytest and vitest).
"""
from dataclasses import dataclass

from core.voice.pinyin import to_syllables

# 归一化时剥掉的字符：ASCII 标点 + 中文标点 + 全部空白。
# Characters stripped during normalisation: ASCII punctuation, CJK punctuation, all whitespace.
_STRIP = set(
    " \t\n\r\v\f"
    "!\"#$%&'()*+,-./:;<=>?@[\\]^_`{|}~"
    "，。！？、；：“”‘’（）《》【】〈〉「」『』…—～·"
)

# 句首容差：唤醒词前允许的噪音字数（语气词/口头禅）。
# Leading tolerance: how many noise characters (fillers) may precede the keyword.
MAX_LEAD_CHARS = 2


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
    """判定转写是否**靠近句首**包含唤醒词（拼音级），并切出其后内容作为指令。

    匹配在「归一化文本的音节序列」上做（音节与字符 1:1 对齐，下标即字符下标）：
    - 发音对就行：「衍衡/燕恒/言恒/严衡」同为 yanheng，全命中
    - 句首容差 MAX_LEAD_CHARS：「呃衍衡」命中；「我昨天说衍衡那个事」不命中
    - 多个候选命中时取最长者，避免短词抢占（「衍」vs「衍衡」）

    Decide whether the transcript contains a wake word NEAR THE START (pinyin level) and split out
    what follows as the command. Matching runs on the normalised text's syllable sequence
    (syllables align 1:1 with characters, so a syllable index is a character index):
    pronunciation decides (衍衡/燕恒/言恒/严衡 are all yanheng and all hit); leading tolerance is
    MAX_LEAD_CHARS (呃衍衡 hits, 我昨天说衍衡那个事 does not); the longest candidate wins.

    Args:
        text: ASR 原始转写。The raw ASR transcript.
        keywords: 已配置的唤醒词列表。The configured wake words.

    Returns:
        判定结果。The judgement.
    """
    norm = normalize(text)
    norm_sylls = to_syllables(norm)
    best_len = 0
    best_end = -1
    for keyword in keywords:
        kw_sylls = to_syllables(normalize(keyword))
        if not kw_sylls:
            continue
        # 只看第一次出现：后面的出现必然更偏离句首（前导只会更长）
        # Only the first occurrence matters: later ones are further from the start.
        idx = _index_of(norm_sylls, kw_sylls)
        if idx < 0 or idx > MAX_LEAD_CHARS:
            continue
        if len(kw_sylls) > best_len:
            best_len = len(kw_sylls)
            best_end = idx + len(kw_sylls)
    if best_end < 0:
        return WakeResult(matched=False, command="", text=text)
    return WakeResult(matched=True, command=norm[best_end:], text=text)


def _index_of(haystack: list[str], needle: list[str]) -> int:
    """音节序列里找第一次出现的下标（无则 -1）。First occurrence of needle in haystack, or -1."""
    n = len(needle)
    for i in range(0, len(haystack) - n + 1):
        if haystack[i:i + n] == needle:
            return i
    return -1
