# -*- coding: utf-8 -*-
import pytest

from core.execution.fs import read_doc, write_doc


@pytest.mark.asyncio
async def test_read_write_json_roundtrip(tmp_path):
    p = tmp_path / "a.json"
    await write_doc(p, {"k": 1, "s": "v"})
    assert await read_doc(p) == {"k": 1, "s": "v"}


@pytest.mark.asyncio
async def test_read_write_csv_roundtrip(tmp_path):
    p = tmp_path / "a.csv"
    await write_doc(p, [["h", "i"], ["1", "2"]])
    assert await read_doc(p) == [["h", "i"], ["1", "2"]]


@pytest.mark.asyncio
async def test_read_write_yaml_roundtrip(tmp_path):
    p = tmp_path / "a.yaml"
    await write_doc(p, {"x": [1, 2]})
    assert await read_doc(p) == {"x": [1, 2]}


@pytest.mark.asyncio
async def test_read_write_toml_roundtrip(tmp_path):
    p = tmp_path / "a.toml"
    await write_doc(p, {"name": "x", "tags": ["a", "b"]})
    assert await read_doc(p) == {"name": "x", "tags": ["a", "b"]}


@pytest.mark.asyncio
async def test_read_write_xlsx_roundtrip(tmp_path):
    p = tmp_path / "a.xlsx"
    await write_doc(p, [["name", "age"], ["tom", 3]])
    assert await read_doc(p) == [["name", "age"], ["tom", 3]]


@pytest.mark.asyncio
async def test_read_write_sqlite_roundtrip(tmp_path):
    p = tmp_path / "a.db"
    await write_doc(p, {"users": [{"id": 1, "name": "a"}]})
    assert await read_doc(p) == {"users": [{"id": 1, "name": "a"}]}


@pytest.mark.asyncio
async def test_read_write_text(tmp_path):
    p = tmp_path / "a.txt"
    await write_doc(p, "hello 世界")
    assert await read_doc(p) == "hello 世界"


@pytest.mark.asyncio
async def test_list_dir_and_stat(tmp_path):
    from core.execution.fs import list_dir, stat_path
    (tmp_path / "f.txt").write_text("x", encoding="utf-8")
    (tmp_path / "sub").mkdir()
    entries = await list_dir(tmp_path)
    names = {e["name"] for e in entries}
    assert {"f.txt", "sub"} <= names
    st = await stat_path(tmp_path / "f.txt")
    assert st["is_file"] is True
