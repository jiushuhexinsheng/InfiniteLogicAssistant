# -*- coding: utf-8 -*-
"""无声调拼音转换 — 唤醒词「发音级」匹配的地基

只看发音、不看字形：ASR 把「衍衡」写成「燕恒/言恒/严衡」都应命中。
用 pypinyin（带多音字上下文消歧），未知字符原样保留、各占一个音节位。

前端镜像：web/src/composables/assistant/wakeMatch/pinyin.ts（`toPinyinTokens`）。
两处语义必须一致 —— 用共享测试向量（tests/data/wake_vectors.json）钉住。

Toneless pinyin conversion — the foundation of pronunciation-level wake-word
matching. Only the pronunciation matters, not the characters: whatever ASR writes
for 衍衡 (燕恒/言恒/严衡) must match. Uses pypinyin (with polyphone disambiguation);
unknown characters are kept as-is, each occupying one syllable slot.

Frontend mirror: web/src/composables/assistant/wakeMatch/pinyin.ts (`toPinyinTokens`).
The two must agree semantically — pinned by shared test vectors
(tests/data/wake_vectors.json).
"""
from typing import Any, cast

from pypinyin import Style, pinyin


def _keep_chars(ch: str) -> list[str]:
    """未知字符兜底：**逐字符**展开，保证每个字符占一个音节位。

    pypinyin 默认把连续非中文字符合并成一个元素（`"abc" → ["abc"]`），若直接取
    `s[0]`，音节列表会比原文字符短，`wake.py` 的「音节下标即字符下标」假设失效
    （实测 `"hello衍衡"` 会被误判为前导 1 字并切出错误指令）。返回 list 让 pypinyin
    为每个未知字符各产出一个元素。

    Unknown-character fallback: expand **per character** so every character keeps one
    syllable slot. pypinyin merges consecutive non-Chinese characters into one element
    (`"abc" → ["abc"]`); taking `s[0]` would shorten the syllable list and break
    wake.py's "syllable index == character index" assumption (measured: `"hello衍衡"`
    was treated as one leading char and split a wrong command). Returning a list makes
    pypinyin emit one element per unknown character.
    """
    return list(ch)


def to_syllables(text: str) -> list[str]:
    """把文本转成无声调拼音音节列表（与原文字符 1:1 对齐）。

    未知字符（ASCII/数字等）原样保留、各占一个音节位 —— 保证
    `len(音节) == len(原文) == len(list(text))`，音节下标即字符下标（指令切分需要）。

    Convert text to toneless pinyin syllables (1:1 aligned with input characters).
    Unknown characters (ASCII/digits etc.) are kept as-is, one slot each — so
    `len(syllables) == len(text) == len(list(text))` and a syllable index is a
    character index (the command split needs that).
    """
    if not text:
        return []
    # pypinyin 的类型标注只声明 errors 返回 str，但运行期支持返回 list（逐字符展开）；
    # cast 仅用于通过静态检查，不改变运行行为。
    # pypinyin's stubs only declare a str return, but the runtime accepts a list
    # (per-character expansion); the cast only satisfies the type checker.
    raw = pinyin(text, style=Style.NORMAL, errors=cast(Any, _keep_chars))
    return [s[0] for s in raw]


def to_pinyin(text: str) -> str:
    """把文本转成无声调拼音串（调试/展示用）。Convert text to a toneless pinyin string."""
    return "".join(to_syllables(text))
