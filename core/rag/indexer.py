# -*- coding: utf-8 -*-
"""RAG 索引 — 把文本文件按标题/段落切块，写入 sqlite

每个 chunk 同时把分词结果（terms）预计算进 chunk_terms 表，
检索时只加载 terms 而不必全量重分词/加载全文（见 retriever.py）。
"""
import re
import sqlite3
from pathlib import Path

from core import rag as rag_mod
from core.rag.tokenize import tokenize

MAX_CHUNK = 800

_HEADING_RE = re.compile(r"^#{1,3} .*$")


def _flush(buf: str, title: str, chunks: list[dict], path: str) -> None:
    for para in re.split(r"\n\s*\n", buf):
        para = para.strip()
        while len(para) > MAX_CHUNK:
            chunks.append({"path": path, "section": title, "text": para[:MAX_CHUNK]})
            para = para[MAX_CHUNK:]
        if para:
            chunks.append({"path": path, "section": title, "text": para})


def _chunk_text(text: str, path: str) -> list[dict]:
    parts = re.split(r"(?m)^(#{1,3} .*)$", text)
    chunks: list[dict] = []
    buf = ""
    title = ""
    for seg in parts:
        if _HEADING_RE.match(seg):
            _flush(buf, title, chunks, path)
            buf = ""
            title = seg.lstrip("#").strip()
        else:
            buf += seg
    _flush(buf, title, chunks, path)
    if not chunks:
        chunks.append({"path": path, "section": "", "text": text[:MAX_CHUNK]})
    return chunks


def _iter_files(src: Path):
    if src.is_file():
        yield src
    elif src.is_dir():
        for p in src.rglob("*"):
            if p.is_file() and p.suffix.lower() in (".md", ".txt", ".py", ".yaml", ".yml", ".json", ".toml"):
                yield p


async def index_sources(sources: list[Path], index_db: Path | None = None) -> int:
    """重建索引：把 sources（文件或目录）全部切块写入 sqlite，并预计算每块 terms。

    index_db 缺省用 rag_mod.INDEX_DB（动态读取，测试可 monkeypatch core.rag.INDEX_DB）。
    返回写入的 chunk 数。
    """
    db = Path(index_db) if index_db is not None else Path(rag_mod.INDEX_DB)
    db.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(str(db)) as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS chunks (id INTEGER PRIMARY KEY AUTOINCREMENT, path TEXT, section TEXT, text TEXT)")
        conn.execute("CREATE TABLE IF NOT EXISTS chunk_terms (chunk_id INTEGER PRIMARY KEY, terms TEXT)")
        conn.execute("DELETE FROM chunks")
        conn.execute("DELETE FROM chunk_terms")
        count = 0
        for src in sources:
            for p in _iter_files(Path(src)):
                try:
                    text = p.read_text(encoding="utf-8", errors="replace")
                except Exception:
                    continue
                for c in _chunk_text(text, str(p)):
                    cur = conn.execute("INSERT INTO chunks (path, section, text) VALUES (?,?,?)",
                                       (c["path"], c["section"], c["text"]))
                    terms = " ".join(tokenize(c["text"]))
                    conn.execute("INSERT INTO chunk_terms (chunk_id, terms) VALUES (?,?)",
                                 (cur.lastrowid, terms))
                    count += 1
    return count
