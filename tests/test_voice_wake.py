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
