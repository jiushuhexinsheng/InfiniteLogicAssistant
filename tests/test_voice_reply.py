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
