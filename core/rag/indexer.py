# -*- coding: utf-8 -*-
"""RAG 索引 — 把文本文件按标题/段落切块，写入 sqlite"""
import re
import sqlite3
from pathlib import Path

from core.rag import INDEX_DB

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


async def index_sources(sources: list[Path]) -> None:
    """重建索引：把 sources（文件或目录）全部切块写入 sqlite。"""
    INDEX_DB.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(str(INDEX_DB)) as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS chunks (id INTEGER PRIMARY KEY AUTOINCREMENT, path TEXT, section TEXT, text TEXT)")
        conn.execute("DELETE FROM chunks")
        count = 0
        for src in sources:
            for p in _iter_files(Path(src)):
                try:
                    text = p.read_text(encoding="utf-8", errors="replace")
                except Exception:
                    continue
                for c in _chunk_text(text, str(p)):
                    conn.execute("INSERT INTO chunks (path, section, text) VALUES (?,?,?)",
                                 (c["path"], c["section"], c["text"]))
                    count += 1
    return count
