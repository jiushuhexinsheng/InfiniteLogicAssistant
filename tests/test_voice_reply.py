# -*- coding: utf-8 -*-
"""语音回复协议：只在【语音】段播报，正文只进聊天。

Voice-reply protocol: speak only the 【语音】 segment; 【正文】 stays in chat.
"""
from core.orchestrator.voice_reply import VoiceReplySplitter, split_voice_reply


def test_split_voice_and_body():
    """标准两段：语音段与正文分离。Standard two-part output."""
    speech, content = split_voice_reply("【语音】\n今天北京晴，20 度。\n【正文】\n## 天气\n北京今天晴…")
    assert speech == "今天北京晴，20 度。"
    assert content == "## 天气\n北京今天晴…"


def test_split_fallback_without_markers():
    """模型不守协议：整段作正文，取首句作语音。Fallback without markers."""
    speech, content = split_voice_reply("北京今天晴，最高 20 度。出门记得带外套。")
    assert content == "北京今天晴，最高 20 度。出门记得带外套。"
    assert speech == "北京今天晴，最高 20 度。"


def test_stream_holds_until_body_marker():
    """流式：正文在标记出现后才释放，语音段期间不泄露标记。Streaming."""
    sp = VoiceReplySplitter()
    out = []
    for chunk in ["【语", "音】你好。", "\n【正", "文】\n正文内容"]:
        out.append(sp.feed(chunk))
    speech, content = sp.finish()
    assert "".join(out) == "正文内容"
    assert speech == "你好。"
    assert content.strip() == "正文内容"


def test_stream_plain_text_passes_through():
    """无标记文本直接当正文流式输出。Plain text streams straight through."""
    sp = VoiceReplySplitter()
    assert sp.feed("普通回复") == "普通回复"
    speech, content = sp.finish()
    assert content == "普通回复"
    assert speech                         # fallback speech is non-empty


def test_empty_content_has_no_speech():
    """纯思考/空回复不播报。Empty content produces no speech."""
    sp = VoiceReplySplitter()
    sp.feed("")
    speech, content = sp.finish()
    assert (speech, content) == ("", "")


def test_snapshot_is_non_destructive():
    """暂停续写：snapshot 取当前进度但不破坏后续 feed。Pause: the snapshot is non-destructive."""
    sp = VoiceReplySplitter()
    sp.feed("【语音】你好。\n【正文】\n第一段")
    speech, content = sp.snapshot()
    assert speech == "你好。"
    assert content == "第一段"
    # 快照之后再喂增量，内容应当接续（不被快照清空）
    # Feeding after the snapshot continues the same content (the snapshot cleared nothing).
    sp.feed("第二段")
    s2, c2 = sp.finish()
    assert c2 == "第一段第二段"
    assert s2 == "你好。"


def test_snapshot_in_speech_state_keeps_buffer():
    """语音段未闭合时快照也不清缓冲（否则暂停会吞掉已生成文本）。
    Snapshotting with an unclosed speech segment keeps the buffer (a pause must not
    swallow generated text)."""
    sp = VoiceReplySplitter()
    sp.feed("【语音】半句")
    _, content = sp.snapshot()
    assert content == "半句"
    sp.feed("续写")
    _, final = sp.finish()
    assert "半句" in final and "续写" in final


def test_body_before_markers_keeps_speech_out_of_body():
    """模型先写正文再补标记（实测偶发）：标记不得泄漏，语音段不得混进正文。
    The model sometimes writes the body first and appends the markers later (observed):
    markers must never leak and the speech segment must stay out of the body."""
    sp = VoiceReplySplitter()
    out = []
    for chunk in ["## 标题\n正文开头。", "【语音】一句话总结。", "\n【正文】\n正文续写。"]:
        out.append(sp.feed(chunk))
    shown = "".join(out)
    speech, content = sp.finish()
    assert "【语音】" not in shown and "【正文】" not in shown
    assert "【语音】" not in content and "【正文】" not in content
    assert "一句话总结" not in content, "语音段不得混进正文"
    assert "正文开头。" in content and "正文续写。" in content
    assert speech == "一句话总结。"


def test_plain_mode_holds_split_marker_prefix():
    """正文模式里被拆开的标记前缀也不能提前吐出去。A marker split across chunks is
    held back in plain mode instead of leaking its prefix."""
    sp = VoiceReplySplitter()
    a = sp.feed("正文前半。")
    b = sp.feed("【语")
    c = sp.feed("音】总结。\n【正文】\n续写。")
    speech, content = sp.finish()
    assert "【" not in a + b + c
    assert content == "正文前半。续写。"
    assert speech == "总结。"


def test_trailing_speech_summary_after_body_is_not_leaked():
    """模型把语音总结补在正文末尾（实测）：标记不得泄漏，正文不被总结顶掉。
    The model appends the speech summary at the END of the body (observed): markers must
    not leak and the summary must not replace the body."""
    sp = VoiceReplySplitter()
    out = []
    for chunk in ["## 正文\n第一段内容。", "【语音】\n一句话总结。"]:
        out.append(sp.feed(chunk))
    speech, content = sp.finish()
    assert "【语音】" not in "".join(out)
    assert content == "## 正文\n第一段内容。"
    assert speech == "一句话总结。"


def test_body_marker_first_then_trailing_speech():
    """以【正文】开头、结尾再补【语音】：正文态也必须拦截迟到的语音标记。
    Starting with 【正文】 and appending 【语音】 at the end: content mode must intercept
    the late speech marker too."""
    sp = VoiceReplySplitter()
    out = []
    for chunk in ["【正文】\n正文内容。", "【语", "音】总结句。"]:
        out.append(sp.feed(chunk))
    speech, content = sp.finish()
    assert "【" not in "".join(out)
    assert content == "正文内容。"
    assert speech == "总结句。"
