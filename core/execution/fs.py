# -*- coding: utf-8 -*-
"""文件系统 — 读写所有通用格式（text/json/yaml/toml/csv/xlsx/sqlite/ini/env/md）。File system — read/write all common formats (text/json/yaml/toml/csv/xlsx/sqlite/ini/env/md).

按扩展名分发 reader/writer；未知扩展名按纯文本处理。
Readers/writers are dispatched by file extension; unknown extensions are treated as plain text.
"""
import csv
import json
import sqlite3
from pathlib import Path
from typing import Any

import yaml


def _ext(path: Path) -> str:
    """返回小写扩展名（不含点）。Return the lowercase extension without the leading dot."""
    return path.suffix.lower().lstrip(".")


# ── 各格式读写器 ──

def _read_json(p):
    """读取 JSON 文件。Read a JSON file."""
    return json.loads(p.read_text(encoding="utf-8"))
def _write_json(p, data):
    """写入 JSON 文件（保留中文，缩进 2）。Write a JSON file (preserving Chinese, indent 2)."""
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

def _read_yaml(p):
    """读取 YAML 文件。Read a YAML file."""
    return yaml.safe_load(p.read_text(encoding="utf-8"))
def _write_yaml(p, data):
    """写入 YAML 文件（允许 Unicode）。Write a YAML file (allowing Unicode)."""
    p.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")

def _read_toml(p):
    """读取 TOML 文件。Read a TOML file."""
    import tomllib
    return tomllib.loads(p.read_text(encoding="utf-8"))
def _write_toml(p, data):
    """写入 TOML 文件。Write a TOML file."""
    import tomli_w
    p.write_text(tomli_w.dumps(data), encoding="utf-8")

def _read_csv(p):
    """读取 CSV 文件为行列表。Read a CSV file as a list of rows."""
    with p.open("r", encoding="utf-8", newline="") as f:
        return [row for row in csv.reader(f)]
def _write_csv(p, data):
    """按行写入 CSV 文件。Write rows to a CSV file."""
    with p.open("w", encoding="utf-8", newline="") as f:
        csv.writer(f).writerows(data)

def _read_ini(p):
    """读取 INI 文件为 {section: {key: value}}。Read an INI file as {section: {key: value}}."""
    import configparser
    cp = configparser.ConfigParser()
    cp.read(p, encoding="utf-8")
    return {s: dict(cp.items(s)) for s in cp.sections()}
def _write_ini(p, data):
    """写入 INI 文件（值统一转字符串）。Write an INI file (values coerced to strings)."""
    import configparser
    cp = configparser.ConfigParser()
    for section, items in data.items():
        cp[section] = {k: str(v) for k, v in items.items()}
    with p.open("w", encoding="utf-8") as f:
        cp.write(f)

def _read_env(p):
    """读取 .env 文件为键值字典（跳过注释/空行）。Read a .env file as a key-value dict (skipping comments/blank lines)."""
    out = {}
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        out[k.strip()] = v.strip()
    return out
def _write_env(p, data):
    """写入 .env 文件（每行 key=value）。Write a .env file (one key=value per line)."""
    p.write_text("\n".join(f"{k}={v}" for k, v in data.items()) + "\n", encoding="utf-8")

def _read_xlsx(p):
    """读取 xlsx：单表返回二维列表，多表返回 {表名: 行列表}。Read xlsx: single sheet → 2D list, multiple sheets → {name: rows}."""
    from openpyxl import load_workbook
    wb = load_workbook(p, read_only=True, data_only=True)
    sheets = {ws.title: [[c.value for c in row] for row in ws.iter_rows()] for ws in wb.worksheets}
    wb.close()
    return next(iter(sheets.values())) if len(sheets) == 1 else sheets
def _write_xlsx(p, data):
    """写入 xlsx：列表写单表，字典按表名写多表。Write xlsx: a list goes to one sheet, a dict writes multiple sheets by name."""
    from openpyxl import Workbook
    wb = Workbook()
    if isinstance(data, list):
        ws = wb.active
        for row in data:
            ws.append(row)
    else:
        for i, (name, rows) in enumerate(data.items()):
            ws = wb.active if i == 0 else wb.create_sheet(title=name)
            for row in rows:
                ws.append(row)
    wb.save(p)

def _read_sqlite(p):
    """读取 sqlite 全部表为 {表名: 行字典列表}。Read all sqlite tables as {name: [row dicts]}."""
    con = sqlite3.connect(p)
    con.row_factory = sqlite3.Row
    tables = {r["name"] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    out = {}
    for t in tables:
        out[t] = [dict(r) for r in con.execute(f'SELECT * FROM "{t}"')]
    con.close()
    return out
def _write_sqlite(p, data):
    """写入 sqlite：按表建表并插入行。Write to sqlite: create tables and insert rows."""
    con = sqlite3.connect(p)
    for table, rows in data.items():
        if not rows:
            continue
        cols = list(rows[0].keys())
        col_sql = ", ".join(f'"{c}"' for c in cols)
        ph = ", ".join("?" for _ in cols)
        con.execute(f'CREATE TABLE IF NOT EXISTS "{table}" ({col_sql})')
        for r in rows:
            con.execute(f'INSERT INTO "{table}" ({col_sql}) VALUES ({ph})',
                        tuple(r.get(c) for c in cols))
    con.commit()
    con.close()

def _read_text(p):
    """以纯文本读取。Read as plain text."""
    return p.read_text(encoding="utf-8")
def _write_text(p, data):
    """以纯文本写入。Write as plain text."""
    p.write_text(str(data), encoding="utf-8")


_READERS = {
    "json": _read_json, "yaml": _read_yaml, "yml": _read_yaml, "toml": _read_toml,
    "csv": _read_csv, "ini": _read_ini, "env": _read_env,
    "xlsx": _read_xlsx, "sqlite": _read_sqlite, "db": _read_sqlite,
}
_WRITERS = {
    "json": _write_json, "yaml": _write_yaml, "yml": _write_yaml, "toml": _write_toml,
    "csv": _write_csv, "ini": _write_ini, "env": _write_env,
    "xlsx": _write_xlsx, "sqlite": _write_sqlite, "db": _write_sqlite,
}


async def read_doc(path) -> Any:
    """按扩展名读取文件；未知格式按文本。Read a file by extension; unknown formats fall back to text."""
    p = Path(path)
    return _READERS.get(_ext(p), _read_text)(p)


async def write_doc(path, data) -> None:
    """按扩展名写回文件；未知格式按文本。Write a file by extension; unknown formats fall back to text."""
    p = Path(path)
    _WRITERS.get(_ext(p), _write_text)(p, data)


async def list_dir(path=".") -> list[dict]:
    """列出目录内容（目录优先，按名称排序）。List directory contents (dirs first, sorted by name)."""
    p = Path(path)
    out = []
    for child in p.iterdir():
        out.append({
            "name": child.name,
            "path": str(child),
            "is_file": child.is_file(),
            "is_dir": child.is_dir(),
            "size": child.stat().st_size if child.is_file() else 0,
        })
    return sorted(out, key=lambda e: (not e["is_dir"], e["name"]))


async def stat_path(path) -> dict:
    """获取路径的元信息（大小/修改时间）。Get path metadata (size/mtime)."""
    p = Path(path)
    st = p.stat()
    return {
        "path": str(p),
        "is_file": p.is_file(),
        "is_dir": p.is_dir(),
        "size": st.st_size,
        "mtime": st.st_mtime,
    }
