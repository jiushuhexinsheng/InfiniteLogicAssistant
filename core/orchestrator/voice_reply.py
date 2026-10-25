# -*- coding: utf-8 -*-
"""语音回复协议 — 把最终回答拆成「语音总结 + 正文」。

模型按约定输出：

    【语音】
    ≤60 字口语总结（无 Markdown/列表/代码/链接）
    【正文】
    完整回答

本模块负责流式解析：`【语音】` 段只用于 TTS，`【正文】` 段才进聊天；模型不守协议时
回退为「整段正文 + 首句作语音」。思考流由 LLM 层的 reasoning 通道单独处理，本模块
永远不把思考当作语音。

Voice-reply protocol: split the final answer into a spoken summary and the body.
The splitter holds content until the markers resolve, so markers never leak into the
chat stream; output without markers falls back to "whole text as content, first
sentence as speech". Reasoning never enters this module and is never spoken.
"""
from __future__ import annotations

import re

VOICE_MARK = "【语音】"
BODY_MARK = "【正文】"

# 没有标记时语音总结的最大长度（字符）。Max fallback speech length.
_SPEECH_MAX = 60
# 语音段一直等不到【正文】时的保险上限（防止模型漏标记导致正文被长期扣住）。
_MAX_HOLD = 400

_SENTENCE_SPLIT = re.compile(r"(?<=[。！？!?；;\n])")


def _fallback_speech(text: str) -> str:
    """从正文取首句作为语音总结。Take the first sentence as a speech fallback."""
    clean = text.strip()
    if not clean:
        return ""
    first = _SENTENCE_SPLIT.split(clean, maxsplit=1)[0].strip()
    if not first:
        first = clean
    return first[:_SPEECH_MAX]


class VoiceReplySplitter:
    """流式拆分器：feed(delta) 返回可立即展示的正文增量，finish() 给出最终两段。

    Streaming splitter: feed(delta) returns the body increment safe to show now;
    finish() returns the final (speech, content) pair.
    """

    def __init__(self) -> None:
        self._buf = ""
        self._state = "detect"   # detect | speech | content | plain
        self._speech = ""
        self._content = ""

    def feed(self, delta: str) -> str:
        """喂入一段增量，返回应立即作为正文展示的增量。Feed one delta.

        Args:
            delta: 模型增量文本。Model text delta.

        Returns:
            可展示的正文增量（标记期间为空串）。Body increment safe to display (empty
            while markers are unresolved).
        """
        if not delta:
            return ""
        if self._state in ("content", "plain"):
            self._content += delta
            return delta

        self._buf += delta
        if self._state == "detect":
            stripped = self._buf.lstrip()
            if stripped.startswith(VOICE_MARK):
                self._state = "speech"
                self._buf = stripped[len(VOICE_MARK):]
            elif stripped.startswith(BODY_MARK):
                # 模型跳过语音段：正文照常，语音走兜底。
                self._state = "content"
                self._buf = stripped[len(BODY_MARK):].lstrip("\r\n")
                self._content += self._buf
                out, self._buf = self._buf, ""
                return out
            elif VOICE_MARK.startswith(stripped) or stripped == "":
                return ""  # 还可能是标记前缀，继续等。Still a marker prefix.
            else:
                self._state = "plain"
                out, self._buf = self._buf, ""
                self._content += out
                return out

        if self._state == "speech":
            idx = self._buf.find(BODY_MARK)
            if idx >= 0:
                self._speech = self._buf[:idx].strip()
                rest = self._buf[idx + len(BODY_MARK):].lstrip("\r\n")
                self._buf = ""
                self._state = "content"
                self._content += rest
                return rest
            if len(self._buf) > _MAX_HOLD:
                # 漏了正文标记：整段按正文处理，语音走兜底。
                self._state = "plain"
                out, self._buf = self._buf, ""
                self._content += out
                return out
            return ""
        return ""

    def finish(self) -> tuple[str, str]:
        """结束：返回 (语音总结, 正文)。Finish and return (speech, content)."""
        if self._state == "content":
            return self._speech or _fallback_speech(self._content), self._content
        if self._state == "speech":
            text = self._buf.strip()
            self._buf = ""
            speech = self._speech or text or _fallback_speech(self._content)
            return speech[:_SPEECH_MAX], text or self._content
        if self._state == "plain":
            content = self._content or self._buf
            return _fallback_speech(content), content
        # detect：整段当正文
        content = (self._content + self._buf).strip()
        return (_fallback_speech(content), content) if content else ("", "")


def split_voice_reply(text: str) -> tuple[str, str]:
    """非流式拆分（测试/短路径用）。Non-streaming split for tests and short paths.

    Args:
        text: 完整回答。Full answer.

    Returns:
        (语音总结, 正文)。(speech, body).
    """
    splitter = VoiceReplySplitter()
    splitter.feed(text)
    return splitter.finish()
