# -*- coding: utf-8 -*-
"""RAG — 索引 environment.md/文档 → sqlite 分块，TF-IDF/关键词检索注入"""
from pathlib import Path

from core.config import ROOT_DIR

INDEX_DB = ROOT_DIR / "rag" / "index.db"
DEFAULT_SOURCES = [ROOT_DIR / "environment.md", ROOT_DIR / "docs"]


async def maybe_rebuild_index(sources: list[Path] | None = None, index_db: Path | None = None) -> None:
    """index.db 缺失或任一源文件比索引新时重建；best-effort（失败不抛出）。"""
    from core.rag.indexer import index_sources
    sources = sources if sources is not None else DEFAULT_SOURCES
    db = Path(index_db) if index_db is not None else Path(INDEX_DB)
    if not db.exists():
        await index_sources(sources, index_db=db)
        return
    try:
        index_mtime = db.stat().st_mtime
    except OSError:
        return
    stale = False
    for src in sources:
        p = Path(src)
        try:
            if p.is_file():
                if p.stat().st_mtime > index_mtime:
                    stale = True
                    break
            elif p.is_dir():
                newest = 0.0
                for f in p.rglob("*"):
                    if f.is_file() and f.suffix.lower() in (".md", ".txt", ".py", ".yaml", ".yml", ".json", ".toml"):
                        newest = max(newest, f.stat().st_mtime)
                if newest > index_mtime:
                    stale = True
                    break
        except OSError:
            continue
    if stale:
        await index_sources(sources, index_db=db)
