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
