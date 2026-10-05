# -*- coding: utf-8 -*-
"""模型获取脚本：残缺 tarball 自愈重下、部分解包不幂等短路、失败清理。

不打网络——urlretrieve 全部桩掉。No network: urlretrieve is stubbed throughout.
"""
import importlib.util
import io
import tarfile
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "fetch_local_asr_model.py"
_TOPDIR = "sherpa-onnx-streaming-zipformer-bilingual-zh-en-2023-02-20"


def _load():
    spec = importlib.util.spec_from_file_location("fetch_local_asr_model", _SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _fake_tarball(topdir: str = _TOPDIR) -> bytes:
    """构造与真实包同构的迷你 tar.bz2（顶层目录 + tokens.txt + 三前缀 onnx）。"""
    files = {
        f"{topdir}/tokens.txt": b"<blk> 0\n<sos/eos> 1\n",
        f"{topdir}/encoder-epoch-99-avg-1.onnx": b"ENC-FP32",
        f"{topdir}/encoder-epoch-99-avg-1.int8.onnx": b"ENC-I8",
        f"{topdir}/decoder-epoch-99-avg-1.onnx": b"DEC-FP32",
        f"{topdir}/decoder-epoch-99-avg-1.int8.onnx": b"DEC-I8",
        f"{topdir}/joiner-epoch-99-avg-1.onnx": b"JN-FP32",
        f"{topdir}/joiner-epoch-99-avg-1.int8.onnx": b"JN-I8",
    }
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:bz2") as tf:
        for name, data in files.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tf.addfile(info, io.BytesIO(data))
    return buf.getvalue()


def _setup(mod, tmp_path: Path, monkeypatch, tarball: bytes):
    monkeypatch.setattr(mod, "ROOT", tmp_path)
    monkeypatch.setattr(mod, "DEST", tmp_path / "models" / _TOPDIR)
    monkeypatch.setattr(mod, "TMP", tmp_path / "models" / "_asr_download.tar.bz2")
    monkeypatch.setattr(mod, "EXPECTED_TARBALL_SIZE", len(tarball))


def _stub_download(mod, monkeypatch, payload: bytes, calls: list):
    def retrieve(url, filename, *args, **kwargs):
        calls.append(url)
        Path(filename).write_bytes(payload)

    monkeypatch.setattr(mod.urllib.request, "urlretrieve", retrieve)


def test_corrupt_tarball_heals_with_redownload(tmp_path, monkeypatch, capsys):
    """Review Important：中断下载残留的残缺包 → 不裸抛，清理并走重下路径自愈。"""
    mod = _load()
    fake = _fake_tarball()
    _setup(mod, tmp_path, monkeypatch, fake)
    mod.TMP.parent.mkdir(parents=True)
    mod.TMP.write_bytes(b"truncated interrupt leftover")  # 大小≠预期的半截包
    calls: list = []
    _stub_download(mod, monkeypatch, fake, calls)

    assert mod.main() == 0
    assert calls, "残缺包必须触发重新下载（而非在 tarfile.open 裸抛）"
    assert not mod.TMP.exists(), "成功后 tarball 应删除"
    assert mod.is_complete(mod.DEST)
    out = capsys.readouterr().out
    assert "already present" not in out
    assert "downloading" in out and "done:" in out


def test_partial_extract_not_short_circuited(tmp_path, monkeypatch, capsys):
    """R10：tokens.txt 已在但 encoder 缺失（解压中途崩）→ 幂等检查不短路，重解补全。"""
    mod = _load()
    fake = _fake_tarball()
    _setup(mod, tmp_path, monkeypatch, fake)
    d = mod.DEST
    d.mkdir(parents=True)
    (d / "tokens.txt").write_bytes(b"<blk> 0\n")
    (d / "decoder-epoch-99-avg-1.onnx").write_bytes(b"DEC")
    (d / "joiner-epoch-99-avg-1.onnx").write_bytes(b"JN")
    assert mod.is_complete(d) is False, "缺 encoder 的半套不得判完整"

    calls: list = []
    _stub_download(mod, monkeypatch, fake, calls)

    assert mod.main() == 0
    assert calls, "不完整保留集必须重走下载/解包，而非 already present"
    out = capsys.readouterr().out
    assert "already present" not in out
    assert mod.is_complete(d)
    assert (d / "encoder-epoch-99-avg-1.int8.onnx").is_file()
    assert (d / mod.MANIFEST).is_file(), "解包成功后应记清单"


def test_complete_dest_short_circuits_and_repairs_manifest(tmp_path, monkeypatch, capsys):
    """完整保留集（无清单，历史解包）→ already present 不重下，并补写清单。"""
    mod = _load()
    fake = _fake_tarball()
    _setup(mod, tmp_path, monkeypatch, fake)
    d = mod.DEST
    d.mkdir(parents=True)
    (d / "tokens.txt").write_bytes(b"<blk> 0\n")
    (d / "encoder-x.int8.onnx").write_bytes(b"E")
    (d / "decoder-x.onnx").write_bytes(b"D")
    (d / "joiner-x.onnx").write_bytes(b"J")

    def forbid_download(*args, **kwargs):
        raise AssertionError("完整集不得触发网络下载")

    monkeypatch.setattr(mod.urllib.request, "urlretrieve", forbid_download)

    assert mod.main() == 0
    out = capsys.readouterr().out
    assert "already present" in out
    names = (d / mod.MANIFEST).read_text(encoding="utf-8").split()
    assert "tokens.txt" in names and any(n.startswith("encoder-") for n in names)


def test_broken_tarball_of_right_size_cleans_up(tmp_path, monkeypatch):
    """大小合规但内容损坏的 tarball → 解包失败时必须清理（下次重跑可重下），不静默。"""
    mod = _load()
    garbage = b"this is not a tar.bz2" * 10
    _setup(mod, tmp_path, monkeypatch, garbage)  # EXPECTED = len(garbage)
    mod.TMP.parent.mkdir(parents=True)
    mod.TMP.write_bytes(garbage)

    with pytest.raises(tarfile.TarError):
        mod.main()
    assert not mod.TMP.exists(), "解包失败后残包应被清理（重试路径可达）"
