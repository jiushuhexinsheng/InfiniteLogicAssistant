# -*- coding: utf-8 -*-
"""RAG — 索引 environment.md/文档 → sqlite 分块，TF-IDF/关键词检索注入"""
from pathlib import Path

from core.config import ROOT_DIR

INDEX_DB = ROOT_DIR / "rag" / "index.db"
DEFAULT_SOURCES = [ROOT_DIR / "environment.md", ROOT_DIR / "docs"]
