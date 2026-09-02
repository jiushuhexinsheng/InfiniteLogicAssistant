# -*- coding: utf-8 -*-
"""该模块测试 core.execution.fs 对 JSON/CSV/YAML/TOML/XLSX/SQLite/文本等格式的读写往返，以及目录列举与文件状态查询。
Tests core.execution.fs read/write roundtrips for JSON, CSV, YAML, TOML, XLSX, SQLite, and text formats, plus directory listing and file stat queries.
"""
import pytest

from core.execution.fs import read_doc, write_doc


@pytest.mark.asyncio
async def test_read_write_json_roundtrip(tmp_path):
    """验证 JSON 数据写入后读取往返一致。Verifies JSON data survives a write-then-read roundtrip."""
    p = tmp_path / "a.json"
    await write_doc(p, {"k": 1, "s": "v"})
    assert await read_doc(p) == {"k": 1, "s": "v"}


@pytest.mark.asyncio
async def test_read_write_csv_roundtrip(tmp_path):
    """验证 CSV 数据写入后读取往返一致。Verifies CSV data survives a write-then-read roundtrip."""
    p = tmp_path / "a.csv"
    await write_doc(p, [["h", "i"], ["1", "2"]])
    assert await read_doc(p) == [["h", "i"], ["1", "2"]]


@pytest.mark.asyncio
async def test_read_write_yaml_roundtrip(tmp_path):
    """验证 YAML 数据写入后读取往返一致。Verifies YAML data survives a write-then-read roundtrip."""
    p = tmp_path / "a.yaml"
    await write_doc(p, {"x": [1, 2]})
    assert await read_doc(p) == {"x": [1, 2]}


@pytest.mark.asyncio
async def test_read_write_toml_roundtrip(tmp_path):
    """验证 TOML 数据写入后读取往返一致。Verifies TOML data survives a write-then-read roundtrip."""
    p = tmp_path / "a.toml"
    await write_doc(p, {"name": "x", "tags": ["a", "b"]})
    assert await read_doc(p) == {"name": "x", "tags": ["a", "b"]}


@pytest.mark.asyncio
async def test_read_write_xlsx_roundtrip(tmp_path):
    """验证 XLSX 表格写入后读取往返一致。Verifies XLSX sheet data survives a write-then-read roundtrip."""
    p = tmp_path / "a.xlsx"
    await write_doc(p, [["name", "age"], ["tom", 3]])
    assert await read_doc(p) == [["name", "age"], ["tom", 3]]


@pytest.mark.asyncio
async def test_read_write_sqlite_roundtrip(tmp_path):
    """验证 SQLite 表数据写入后读取往返一致。Verifies SQLite table data survives a write-then-read roundtrip."""
    p = tmp_path / "a.db"
    await write_doc(p, {"users": [{"id": 1, "name": "a"}]})
    assert await read_doc(p) == {"users": [{"id": 1, "name": "a"}]}


@pytest.mark.asyncio
async def test_read_write_text(tmp_path):
    """验证纯文本写入后读取往返一致。Verifies plain text survives a write-then-read roundtrip."""
    p = tmp_path / "a.txt"
    await write_doc(p, "hello 世界")
    assert await read_doc(p) == "hello 世界"


@pytest.mark.asyncio
async def test_list_dir_and_stat(tmp_path):
    """验证 list_dir 列举目录条目且 stat_path 报告文件状态。Verifies list_dir lists directory entries and stat_path reports file status."""
    from core.execution.fs import list_dir, stat_path
    (tmp_path / "f.txt").write_text("x", encoding="utf-8")
    (tmp_path / "sub").mkdir()
    entries = await list_dir(tmp_path)
    names = {e["name"] for e in entries}
    assert {"f.txt", "sub"} <= names
    st = await stat_path(tmp_path / "f.txt")
    assert st["is_file"] is True
