# -*- coding: utf-8 -*-
"""无声调拼音转换 — 唤醒词「发音级」匹配的地基

只看发音、不看字形：ASR 把「衍衡」写成「燕恒/言恒/严衡」都应命中。
用 pypinyin（带多音字上下文消歧），未知字符原样保留、各占一个音节位。

前端镜像：web/src/composables/assistant/wakeMatch.ts（Web Speech 路径用）。
两处语义必须一致 —— 用共享测试向量（tests/data/wake_vectors.json）钉住。

Toneless pinyin conversion — the foundation of pronunciation-level wake-word
matching. Only the pronunciation matters, not the characters: whatever ASR writes
for 衍衡 (燕恒/言恒/严衡) must match. Uses pypinyin (with polyphone disambiguation);
unknown characters are kept as-is, each occupying one syllable slot.

Frontend mirror: web/src/composables/assistant/wakeMatch.ts (for the Web Speech
path). The two must agree semantically — pinned by shared test vectors
(tests/data/wake_vectors.json).
"""
from pypinyin import Style, pinyin


def _keep_char(ch: str) -> str:
    """未知字符兜底：原样返回、占一个音节位。Unknown-character fallback: keep as-is, one slot."""
    return ch


def to_syllables(text: str) -> list[str]:
    """把文本转成无声调拼音音节列表（与原文字符 1:1 对齐）。

    未知字符（ASCII/数字等）原样保留、各占一个音节位 —— 保证
    `len(音节) == len(text)`，音节下标即字符下标（指令切分需要）。

    Convert text to toneless pinyin syllables (1:1 aligned with input characters).
    Unknown characters (ASCII/digits etc.) are kept as-is, one slot each — so
    `len(syllables) == len(text)` and a syllable index is a character index (the
    command split needs that).
    """
    if not text:
        return []
    raw = pinyin(text, style=Style.NORMAL, errors=_keep_char)
    return [s[0] for s in raw]


def to_pinyin(text: str) -> str:
    """把文本转成无声调拼音串（调试/展示用）。Convert text to a toneless pinyin string."""
    return "".join(to_syllables(text))
