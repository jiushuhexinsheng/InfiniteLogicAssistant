# -*- coding: utf-8 -*-
"""RAG 分词 — 索引与检索共用的统一分词（保证两边 token 一致）

ASCII 词（≥2 字符）按整词；中文按字符二元组（无外部依赖的中文近似分词）。
"""
import re

TOKEN_RE = re.compile(r"[a-z0-9_]+|[一-鿿]+")


def tokenize(text: str) -> list[str]:
    """文本 → token 列表。空文本/无有效 token 返回 []。"""
    tokens: list[str] = []
    for m in TOKEN_RE.findall(text.lower()):
        if not m:
            continue
        if m[0].isascii():
            if len(m) >= 2:
                tokens.append(m)
        else:
            # 中文：按字符二元组切分，允许子串匹配
            if len(m) >= 2:
                tokens.extend(m[i:i + 2] for i in range(len(m) - 1))
    return tokens
