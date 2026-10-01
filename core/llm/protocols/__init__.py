# -*- coding: utf-8 -*-
"""LLM 协议适配器(按 core.vendors.resolve_protocol 分派)。

LLM protocol adapters (dispatched by core.vendors.resolve_protocol):
- openai   : OpenAI chat/completions SSE
- anthropic: Anthropic Messages API SSE
- gemini   : Gemini streamGenerateContent?alt=sse

入口仍为 core.llm.stream.stream_chat;本包只放各协议的 payload 构建与 SSE 解析。
The entry point remains core.llm.stream.stream_chat; this package holds only
per-protocol payload building and SSE parsing.
"""
